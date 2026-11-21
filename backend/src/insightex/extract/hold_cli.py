"""`insightex extract-hold release <lecture_id>` and `insightex extract-hold list` (ADR-0054 decision 8, Amendment 1).

`release` only reads the manifest: without an unreleased hold it refuses (exit 2, no job); otherwise it enqueues an
`extract_hold_release` job, and the worker writes `released_at`. Releasing does not extract: a later re-add does.
`list` prints every held workspace as JSON lines.
"""

from __future__ import annotations

import argparse
import json
import sys

from insightex.core.config import get_settings
from insightex.extract import hold
from insightex.jobs import db, store
from insightex.jobs.workspace import Workspaces, validate_workspace_id


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="insightex extract-hold")
    sub = parser.add_subparsers(dest="action", required=True)
    p_rel = sub.add_parser("release", help="enqueue a job that releases a lecture's extraction hold")
    p_rel.add_argument("lecture_id")
    sub.add_parser("list", help="list lectures with an active extraction hold (JSON lines)")
    args = parser.parse_args(argv)
    settings = get_settings()
    workspaces = Workspaces(settings.jobs.workspaces_dir)
    if args.action == "list":
        for row in hold.held_workspaces(workspaces):
            print(json.dumps(row, ensure_ascii=False))
        return 0
    try:
        workspace_id = validate_workspace_id(args.lecture_id)
        manifest = workspaces.read_manifest(workspace_id)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if hold.active_hold(manifest) is None:
        print(f"error: {hold.NO_HOLD_MESSAGE}", file=sys.stderr)
        return 2
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    job_id = store.enqueue(conn, hold.RELEASE_KIND, {}, workspace_id)
    print(json.dumps({"job_id": job_id, "lecture_id": workspace_id}))
    return 0
