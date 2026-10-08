"""Workspace cache index: registration, access times, sizes, eviction and delete (ADR-0034).

The `workspaces` table indexes the directories under `jobs.workspaces_dir`. Directories without a row
are never evicted; `list_workspaces` shows them with `indexed=False` and `delete` still removes them.
Finished job rows that reference a deleted workspace are kept; they hold no lecture content.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from insightex.jobs.db import utcnow
from insightex.jobs.workspace import Workspaces, validate_workspace_id

log = logging.getLogger(__name__)

SOURCE_KINDS = ("youtube", "url", "upload", "dummy")


class WorkspaceBusy(Exception):
    """A queued or running job references the workspace."""


class WorkspaceNotFound(KeyError):
    """No row and no directory for that workspace id."""


def register(conn: sqlite3.Connection, workspace_id: str, source_kind: str, source_ref: str) -> None:
    """Insert the workspace if absent. An existing row is left untouched (`created_at` is never overwritten)."""
    validate_workspace_id(workspace_id)
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"unknown source kind {source_kind!r}; use one of {', '.join(SOURCE_KINDS)}")
    now = utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO workspaces (id, source_kind, source_ref, created_at, last_accessed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (workspace_id, source_kind, source_ref, now, now),
    )


def touch(conn: sqlite3.Connection, workspace_id: str) -> None:
    conn.execute("UPDATE workspaces SET last_accessed_at = ? WHERE id = ?", (utcnow(), workspace_id))


def dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def refresh_size(conn: sqlite3.Connection, workspaces: Workspaces, workspace_id: str) -> int:
    """Walk the workspace directory, store and return its total bytes."""
    size = dir_size(workspaces.path(workspace_id))
    conn.execute("UPDATE workspaces SET size_bytes = ? WHERE id = ?", (size, workspace_id))
    return size


def gc_stale_keys(workspaces: Workspaces, workspace_id: str) -> int:
    """Remove stage-key directories the manifest does not name (crash leftovers); return how many."""
    return workspaces.sweep_stale_keys(workspace_id)


def is_busy(conn: sqlite3.Connection, workspace_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM jobs WHERE workspace_id = ? AND status IN ('queued','running') LIMIT 1", (workspace_id,)
    ).fetchone()
    return row is not None


def pin(conn: sqlite3.Connection, workspace_id: str) -> None:
    _set_pinned(conn, workspace_id, 1)


def unpin(conn: sqlite3.Connection, workspace_id: str) -> None:
    _set_pinned(conn, workspace_id, 0)


def _set_pinned(conn: sqlite3.Connection, workspace_id: str, value: int) -> None:
    validate_workspace_id(workspace_id)
    cur = conn.execute("UPDATE workspaces SET pinned = ? WHERE id = ?", (value, workspace_id))
    if cur.rowcount == 0:
        raise WorkspaceNotFound(f"workspace {workspace_id!r} is not in the cache index")


def delete(conn: sqlite3.Connection, workspaces: Workspaces, workspace_id: str) -> None:
    """Remove the directory and the row. Raises WorkspaceBusy if a queued or running job uses it."""
    path = workspaces.path(workspace_id)
    row = conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    if row is None and not path.exists():
        raise WorkspaceNotFound(f"no workspace {workspace_id!r}")
    if is_busy(conn, workspace_id):
        raise WorkspaceBusy(f"workspace {workspace_id!r} has a queued or running job")
    if path.exists():
        shutil.rmtree(path)
    conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))


def evict(
    conn: sqlite3.Connection, workspaces: Workspaces, max_bytes: int, exclude: str | None = None
) -> list[str]:
    """If indexed workspaces exceed `max_bytes`, delete the least recently accessed until under the cap.

    Skips pinned workspaces, workspaces with a queued or running job, and `exclude` (the one whose job
    just finished). Returns the ids removed.
    """
    rows = conn.execute("SELECT id, size_bytes, last_accessed_at, pinned FROM workspaces").fetchall()
    total = sum(r["size_bytes"] for r in rows)
    if total <= max_bytes:
        return []
    for r in rows:
        if r["id"] == exclude and r["size_bytes"] > max_bytes:
            log.warning("workspace %s alone (%d bytes) exceeds cache.max_bytes (%d); it is kept", r["id"], r["size_bytes"], max_bytes)
    removed: list[str] = []
    for r in sorted(rows, key=lambda r: (r["last_accessed_at"], r["id"])):
        if total <= max_bytes:
            break
        if r["pinned"] or r["id"] == exclude or is_busy(conn, r["id"]):
            continue
        try:
            delete(conn, workspaces, r["id"])
        except (OSError, WorkspaceBusy) as exc:
            log.warning("could not evict workspace %s: %s", r["id"], exc)
            continue
        log.info("evicted workspace %s (%d bytes, last accessed %s)", r["id"], r["size_bytes"], r["last_accessed_at"])
        total -= r["size_bytes"]
        removed.append(r["id"])
    if total > max_bytes:
        log.warning("cache is %d bytes, over cache.max_bytes (%d): nothing else can be evicted", total, max_bytes)
    return removed


def list_workspaces(conn: sqlite3.Connection, workspaces: Workspaces) -> list[dict[str, Any]]:
    """Every indexed workspace plus directories with no row (`indexed` False), most recently accessed first."""
    rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM workspaces")}
    out = [{**r, "pinned": bool(r["pinned"]), "indexed": True, "busy": is_busy(conn, r["id"])} for r in rows.values()]
    if workspaces.root.is_dir():
        for child in sorted(workspaces.root.iterdir()):
            if child.is_dir() and child.name not in rows:
                out.append({
                    "id": child.name, "source_kind": None, "source_ref": None, "created_at": None,
                    "last_accessed_at": None, "size_bytes": dir_size(child), "pinned": False,
                    "indexed": False, "busy": is_busy(conn, child.name),
                })
    return sorted(out, key=lambda r: r["last_accessed_at"] or "", reverse=True)


def gc_all(conn: sqlite3.Connection, workspaces: Workspaces, max_bytes: int) -> tuple[int, list[str]]:
    """Stale-key sweep for every workspace without a queued or running job, then evict."""
    swept = 0
    if workspaces.root.is_dir():
        for child in sorted(workspaces.root.iterdir()):
            if child.is_dir() and not is_busy(conn, child.name):
                swept += gc_stale_keys(workspaces, child.name)
                if conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (child.name,)).fetchone():
                    refresh_size(conn, workspaces, child.name)
    return swept, evict(conn, workspaces, max_bytes)
