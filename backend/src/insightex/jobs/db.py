"""SQLite access for the job queue: connections, UTC timestamps and schema migration (ADR-0033).

Every connection runs in autocommit mode (`isolation_level=None`); code that needs a transaction issues
`BEGIN IMMEDIATE` itself (see `transaction`). WAL mode lets the API and CLI read while the worker writes.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

_local = threading.local()

# Ordered migrations: index + 1 is the schema version the script produces. Append only; never edit one.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE jobs (
        id               TEXT PRIMARY KEY,
        kind             TEXT NOT NULL,
        status           TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
        cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0,1)),
        payload          TEXT NOT NULL,
        workspace_id     TEXT NOT NULL,
        attempts         INTEGER NOT NULL DEFAULT 0,
        worker_pid       INTEGER,
        error            TEXT,
        created_at       TEXT NOT NULL,
        started_at       TEXT,
        finished_at      TEXT,
        updated_at       TEXT NOT NULL
    );
    CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);
    CREATE INDEX idx_jobs_workspace ON jobs(workspace_id);
    CREATE TABLE job_stages (
        job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        idx         INTEGER NOT NULL,
        name        TEXT NOT NULL,
        status      TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','cached','failed','cancelled')),
        stage_key   TEXT,
        progress    REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
        message     TEXT,
        error       TEXT,
        started_at  TEXT,
        finished_at TEXT,
        PRIMARY KEY (job_id, idx)
    );
    """,
]


def utcnow() -> str:
    """Current UTC time as ISO 8601 with milliseconds and a trailing Z, e.g. 2026-10-09T08:15:02.123Z."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def open_connection(db_path: Path, busy_timeout_ms: int) -> sqlite3.Connection:
    """Open a new connection: WAL, foreign keys on, busy timeout set, rows addressable by column name.

    The caller owns it and must use it from one thread only. Creates the parent directory.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect(db_path: Path, busy_timeout_ms: int) -> sqlite3.Connection:
    """The calling thread's connection to `db_path`, opened on first use (one connection per thread per file)."""
    conns: dict[Path, sqlite3.Connection] = _local.__dict__.setdefault("conns", {})
    conn = conns.get(db_path)
    if conn is None:
        conn = conns[db_path] = open_connection(db_path, busy_timeout_ms)
    return conn


def close_thread_connections() -> None:
    """Close every connection the calling thread opened through `connect` (tests, shutdown)."""
    for conn in _local.__dict__.pop("conns", {}).values():
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """`BEGIN IMMEDIATE` ... COMMIT, or ROLLBACK if the body raises.

    IMMEDIATE takes the write lock up front, so a read-then-write inside (such as claiming a job) cannot
    interleave with another writer.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def schema_version(conn: sqlite3.Connection) -> int:
    """The applied schema version, 0 for a database that has never been migrated."""
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return row["v"] or 0


def migrate(conn: sqlite3.Connection) -> int:
    """Bring the schema to the latest version; return how many migrations ran (0 when already current).

    Safe to call on every start and from several processes at once: the version check and the changes
    happen in one immediate transaction.
    """
    with transaction(conn):
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL)")
        current = schema_version(conn)
        pending = MIGRATIONS[current:]
        for offset, script in enumerate(pending, start=1):
            for statement in script.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)", (current + offset, utcnow()))
    return len(pending)
