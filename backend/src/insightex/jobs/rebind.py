"""Move a job from a provisional workspace (`pending-<job id>`) to its real, content-addressed one (ADR-0034).

Called by the runner between stages, after the stage that learned the real id has been published in the
provisional workspace and recorded in its manifest. Crash safety, in order of the steps:

1. Final workspace has no completed stages: rewrite the provisional manifest's id, `os.rename` the
   directory (atomic on one filesystem), then one transaction updates `jobs.workspace_id` and renames the
   cache row. A crash before the rename leaves the provisional state (the stage is cached and the rebind
   is replayed from its output). A crash between the rename and the transaction leaves a job that points
   at a directory that no longer exists; it re-fetches once and then takes the merge path. Never a mix.
2. Final workspace already has completed stages (same bytes seen before): make sure it holds the
   stage output (move ours in if not), then one transaction switches the job and drops the provisional
   cache row, then the provisional directory is deleted. A crash before the transaction replays the
   merge; a crash after it leaves an orphan `pending-*` directory that the worker's startup sweep removes.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3

from insightex.jobs import store
from insightex.jobs.db import transaction
from insightex.jobs.workspace import Workspaces, validate_workspace_id

log = logging.getLogger(__name__)


def _fsync_dir(path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def rebind(
    conn: sqlite3.Connection, workspaces: Workspaces, job_id: str, old_id: str, new_id: str, stage_name: str
) -> None:
    """Make `new_id` the job's workspace. `stage_name` is the stage whose output must end up there."""
    validate_workspace_id(new_id)
    old_path, new_path = workspaces.path(old_id), workspaces.path(new_id)
    old_manifest = workspaces.read_manifest(old_id)
    entry = old_manifest["stages"].get(stage_name)
    if entry is None:
        raise RuntimeError(f"cannot rebind {old_id} to {new_id}: stage {stage_name} is not recorded")

    merged = bool(workspaces.read_manifest(new_id)["stages"]) if new_path.exists() else False
    if merged:
        _merge_stage(workspaces, old_id, new_id, stage_name, entry)
        with transaction(conn):
            store.set_workspace(conn, job_id, new_id)
            conn.execute(
                "INSERT OR IGNORE INTO workspaces (id, source_kind, source_ref, created_at, last_accessed_at, "
                "size_bytes, pinned) SELECT ?, source_kind, source_ref, created_at, last_accessed_at, size_bytes, 0 "
                "FROM workspaces WHERE id = ?",
                (new_id, old_id),
            )
            conn.execute("DELETE FROM workspaces WHERE id = ?", (old_id,))
        shutil.rmtree(old_path, ignore_errors=True)
        log.info("job %s merged into existing workspace %s", job_id, new_id)
        return

    if new_path.exists():  # an empty leftover without any completed stage
        shutil.rmtree(new_path)
    old_manifest["workspace_id"] = new_id
    workspaces.write_manifest(old_id, old_manifest)
    os.rename(old_path, new_path)
    _fsync_dir(new_path.parent)
    with transaction(conn):
        store.set_workspace(conn, job_id, new_id)
        conn.execute("DELETE FROM workspaces WHERE id = ?", (new_id,))  # a row without a directory
        conn.execute("UPDATE workspaces SET id = ? WHERE id = ?", (new_id, old_id))
    log.info("job %s moved from %s to workspace %s", job_id, old_id, new_id)


def _merge_stage(workspaces: Workspaces, old_id: str, new_id: str, stage_name: str, entry: dict) -> None:
    """Ensure `new_id` holds `stage_name` at the key `entry` records, moving our directory in if needed."""
    key = entry["key"]
    outputs = [o.rsplit("/", 1)[-1] for o in entry["outputs"]]
    if workspaces.stage_is_complete(new_id, stage_name, key, outputs):
        return
    dest = workspaces.stage_dir(new_id, stage_name, key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    os.replace(workspaces.stage_dir(old_id, stage_name, key), dest)
    manifest = workspaces.read_manifest(new_id)
    previous = manifest["stages"].get(stage_name, {}).get("key")
    manifest["stages"][stage_name] = entry
    workspaces.write_manifest(new_id, manifest)
    if previous and previous != key:
        workspaces.remove_stage_key_dir(new_id, stage_name, previous)
