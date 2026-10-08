"""Per-video workspaces and their manifest (ADR-0034).

Layout under the workspaces root::

    <workspace_id>/
      manifest.json                              completed stages: key, time, outputs
      stages/<stage_name>/<stage_key>/...        final outputs of a completed stage
      .staging/<stage_name>-<stage_key>-<pid>/   in-progress outputs; abandoned if the worker dies

The manifest plus the presence of the output files says whether a stage is done. The jobs table says
what a job is doing. Only the worker writes workspaces.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = 1
WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$")
STAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_workspace_id(workspace_id: str) -> str:
    """Return `workspace_id` if it is safe as one path component, else raise ValueError.

    Allowed: 1 to 128 characters of letters, digits, `_`, `-` and `.`, not starting with `.`.
    """
    if not isinstance(workspace_id, str) or not WORKSPACE_ID_RE.match(workspace_id):
        raise ValueError(
            f"invalid workspace id {workspace_id!r}: use 1 to 128 characters from A-Z a-z 0-9 _ - . "
            f"and do not start with a dot"
        )
    return workspace_id


def validate_stage_name(name: str) -> str:
    """Return `name` if it is safe as one path component (lowercase letters, digits, `_`), else raise."""
    if not isinstance(name, str) or not STAGE_NAME_RE.match(name):
        raise ValueError(f"invalid stage name {name!r}: use lowercase letters, digits and underscores")
    return name


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Workspaces:
    """All workspaces under one root directory. Every method validates ids before touching the disk."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, workspace_id: str) -> Path:
        return self.root / validate_workspace_id(workspace_id)

    def stage_dir(self, workspace_id: str, stage_name: str, stage_key: str) -> Path:
        """Final output directory of a stage at a given key."""
        return self.path(workspace_id) / "stages" / validate_stage_name(stage_name) / _check_key(stage_key)

    def staging_dir(self, workspace_id: str, stage_name: str, stage_key: str, pid: int) -> Path:
        """Where a running stage writes. Named by pid so a leftover from a dead worker never collides."""
        name = f"{validate_stage_name(stage_name)}-{_check_key(stage_key)}-{pid}"
        return self.path(workspace_id) / ".staging" / name

    # -- manifest ---------------------------------------------------------------------------------

    def read_manifest(self, workspace_id: str) -> dict[str, Any]:
        """The workspace manifest, or an empty one (no stages) if the workspace has none yet."""
        path = self.path(workspace_id) / MANIFEST_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                "schema_version": MANIFEST_SCHEMA,
                "workspace_id": workspace_id,
                "source": {},
                "created_at": _now(),
                "stages": {},
            }
        return data

    def write_manifest(self, workspace_id: str, manifest: dict[str, Any]) -> None:
        """Write the manifest atomically: temp file in the same directory, fsync, os.replace, fsync the directory."""
        directory = self.path(workspace_id)
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".manifest-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, sort_keys=True, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, directory / MANIFEST_NAME)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        _fsync_dir(directory)

    def set_source(self, workspace_id: str, source: dict[str, Any]) -> None:
        """Record free-form source info (URL, video id, hash) in the manifest."""
        manifest = self.read_manifest(workspace_id)
        manifest["source"] = source
        self.write_manifest(workspace_id, manifest)

    def record_stage(
        self, workspace_id: str, stage_name: str, stage_key: str, duration_s: float, outputs: list[str]
    ) -> str | None:
        """Mark a stage complete at `stage_key`; return the key it replaced, or None.

        `outputs` are file names inside the stage directory; the manifest stores them relative to the
        workspace so they can be opened without knowing the layout.
        """
        manifest = self.read_manifest(workspace_id)
        previous = manifest["stages"].get(stage_name, {}).get("key")
        base = f"stages/{stage_name}/{stage_key}"
        manifest["stages"][stage_name] = {
            "key": stage_key,
            "completed_at": _now(),
            "duration_s": round(duration_s, 3),
            "outputs": [f"{base}/{name}" for name in outputs],
        }
        self.write_manifest(workspace_id, manifest)
        return previous

    def stage_is_complete(self, workspace_id: str, stage_name: str, stage_key: str, outputs: list[str]) -> bool:
        """True if the manifest holds this stage at this key and every declared output file exists."""
        entry = self.read_manifest(workspace_id)["stages"].get(stage_name)
        if not entry or entry.get("key") != stage_key:
            return False
        directory = self.stage_dir(workspace_id, stage_name, stage_key)
        return all((directory / name).exists() for name in outputs)

    def stage_output_dir(self, workspace_id: str, stage_name: str) -> Path | None:
        """Directory of the stage's current completed outputs, or None if it has not completed.

        Lets the player and later stages find outputs without knowing keys. After a pipeline or config
        change the directory belongs to the last completed key, which can be stale until the stage reruns.
        """
        entry = self.read_manifest(workspace_id)["stages"].get(stage_name)
        if not entry:
            return None
        directory = self.stage_dir(workspace_id, stage_name, entry["key"])
        return directory if directory.is_dir() else None

    # -- cleanup ----------------------------------------------------------------------------------

    def clean_staging(self) -> int:
        """Delete every `.staging/` subdirectory in every workspace; return how many were removed.

        Call only at worker start. The worker is a singleton, so anything left there is abandoned.
        """
        removed = 0
        if not self.root.is_dir():
            return 0
        for staging in self.root.glob("*/.staging"):
            for child in staging.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
                removed += 1
        return removed

    def sweep_stale_keys(self, workspace_id: str) -> int:
        """Delete stage-key directories that the manifest does not name; return how many were removed.

        The runner removes the superseded key on the normal path. This catches what a crash left: a key
        directory moved into place before the manifest write, or a superseded one whose delete failed.
        Call it only while no job is running for the workspace.
        """
        stages_root = self.path(workspace_id) / "stages"
        if not stages_root.is_dir():
            return 0
        current = {name: entry.get("key") for name, entry in self.read_manifest(workspace_id)["stages"].items()}
        removed = 0
        for stage_dir in stages_root.iterdir():
            if not stage_dir.is_dir():
                continue
            for key_dir in stage_dir.iterdir():
                if key_dir.name != current.get(stage_dir.name):
                    try:
                        shutil.rmtree(key_dir)
                        removed += 1
                    except OSError as exc:
                        log.warning("could not remove stale stage dir %s: %s", key_dir, exc)
        return removed

    def remove_stage_key_dir(self, workspace_id: str, stage_name: str, stage_key: str) -> bool:
        """Delete a superseded stage directory. A failure is logged as a warning and returns False."""
        directory = self.stage_dir(workspace_id, stage_name, stage_key)
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            return True
        except OSError as exc:
            log.warning("could not remove superseded stage dir %s: %s", directory, exc)
            return False
        return True


def _check_key(stage_key: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{16}", stage_key):
        raise ValueError(f"invalid stage key {stage_key!r}")
    return stage_key
