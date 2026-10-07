# insightex.core

**Purpose:** Config loading, paths, logging, ids, errors, manifest.

**Model used:** none

**Feature numbers:** not assigned

**Status:** `config.py` (typed settings: default.yaml < local file < INSIGHTEX__ env < overrides), `ids.py` (canonical id -> lecture_id,
path-traversal-safe), `manifest.py` (per-lecture manifest.json, atomic writes, status transitions).
Logging and shared errors not yet.
