# Jobs CLI contract

Commands (all load settings once; user errors print `error: <message>` to stderr and exit 1):

```
insightex db migrate
insightex worker                                   exit 2 if another worker runs; otherwise runs until SIGINT/SIGTERM (exit 0)
insightex probe URL                                print link metadata as JSON
insightex ingest URL --confirm-rights              enqueue an ingest_link job; prints {job_id, workspace_id, deduplicated}
insightex jobs enqueue-dummy [--cpu-seconds N] [--gpu-seconds N] [--label S] [--workspace ID]   prints the job id
insightex jobs list [--status S] [--limit N] [--json]
insightex jobs show ID [--json]
insightex jobs cancel ID
insightex jobs retry ID
insightex gpu status [--json]                      lease free or busy, with the exclusive holder if recorded
insightex cache list [--json]                      workspaces, most recently accessed first
insightex cache delete ID                          exit 1 with `error:` if a queued or running job uses it
insightex cache pin ID | unpin ID                  pinned workspaces are never evicted (ID must be indexed)
insightex cache gc                                 stale-key sweep for every idle workspace, then evict
```

## JSON shapes (stable)

`jobs show ID --json` prints one job object. `jobs list --json` prints `{"jobs": [<job>, ...]}`, newest first. Timestamps are UTC ISO 8601 with milliseconds and a trailing `Z`. Absent values are `null`.

```json
{
  "id": "32 hex characters",
  "kind": "dummy",
  "status": "queued | running | succeeded | failed | cancelled",
  "cancel_requested": false,
  "payload": {"cpu_seconds": 5, "gpu_seconds": 20, "label": ""},
  "workspace_id": "dummy-1a2b3c4d",
  "attempts": 1,
  "worker_pid": 1234,
  "error": null,
  "created_at": "2026-10-09T08:15:02.123Z",
  "started_at": "...",
  "finished_at": null,
  "updated_at": "...",
  "stages": [
    {
      "idx": 0,
      "name": "dummy_cpu",
      "status": "pending | running | succeeded | cached | failed | cancelled",
      "stage_key": "16 hex characters or null",
      "progress": 0.0,
      "message": null,
      "error": null,
      "started_at": null,
      "finished_at": null
    }
  ]
}
```

- `progress` is 0 to 1. `error` on a stage holds `Type: message` followed by a trimmed traceback; `error` on the job is one line.
- `attempts` counts claims by a worker. A clean worker shutdown does not count; a crash does.
- Fields are only added, never renamed or removed, within this contract.

## `gpu status --json`

```json
{
  "lease_path": "/home/user/insightex-data/run/gpu.lock",
  "run_dir": "/home/user/insightex-data/run",
  "workspaces_dir": "/home/user/insightex-data/workspaces",
  "ollama_base_url": "http://localhost:11434",
  "ollama_model": "qwen3.5:latest",
  "state": "free | busy",
  "holder": {"pid": 1234, "mode": "exclusive", "purpose": "<job_id>:<stage_name>", "acquired_at": "...Z"}
}
```

`run_dir`, `workspaces_dir`, `ollama_base_url` and `ollama_model` are the effective settings, so tools need not parse the config. `holder` is `null` when the lease is free, or when it is busy with shared holds only. It is diagnostic: the lock is the truth. The command takes a non-blocking exclusive lock and releases it at once.

## `cache list --json`

`{"workspaces": [<workspace>, ...]}`, most recently accessed first.

```json
{
  "id": "yt-dQw4w9WgXcQ",
  "source_kind": "youtube | url | upload | dummy | null",
  "source_ref": "URL, original file name or label; null when not indexed",
  "created_at": "...Z or null",
  "last_accessed_at": "...Z or null",
  "size_bytes": 123456,
  "pinned": false,
  "indexed": true,
  "busy": false
}
```

`indexed` is false for a directory with no row in the cache table; eviction skips it and `cache delete` still removes it. `busy` is true while a queued or running job references the workspace.
