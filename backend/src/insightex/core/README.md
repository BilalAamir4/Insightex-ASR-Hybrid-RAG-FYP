# insightex.core

**Purpose:** Config loading, paths, logging, ids, errors, manifest.

**Model used:** none

**Feature numbers:** not assigned

**Status:** `config.py` (typed settings: default.yaml < local file < INSIGHTEX__ env < overrides). The per-lecture `ids.py` and `manifest.py` were removed with the `lectures/` layout; workspaces and their manifest are in `insightex.jobs.workspace`.
Logging and shared errors not yet.
