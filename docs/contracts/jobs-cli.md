# Jobs CLI contract

Commands (all load settings once; user errors print `error: <message>` to stderr and exit 1):

```
insightex db migrate
insightex worker                                   exit 2 if another worker runs; otherwise runs until SIGINT/SIGTERM (exit 0)
insightex jobs enqueue-dummy [--cpu-seconds N] [--gpu-seconds N] [--label S] [--workspace ID]   prints the job id
insightex jobs list [--status S] [--limit N] [--json]
insightex jobs show ID [--json]
insightex jobs cancel ID
insightex jobs retry ID
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
