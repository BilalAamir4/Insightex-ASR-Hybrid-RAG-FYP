# ADR-0004: Configuration system

Status: Accepted
Date decided: 2026-10-08
Date recorded: 2026-10-08
Module: M0b

## Context

Before this decision, `backend/src/insightex/core/config.py` returned an untyped dict (`config/default.yaml` merged with `config/local.yaml`, `${VAR}` expansion). A typo in a key was silently ignored, defaults were repeated in code (`IngestSettings`, `api/__main__.py`, `ollama_client.py`), and `INSIGHTEX_DATA` and `OLLAMA_BASE_URL` were read from `os.environ` in three places. `default.yaml` held five keys no code read.

## Decision

**Files** (repo-root `config/`):
- `default.yaml`: committed; every setting with its default value and a one-line comment with unit. Defaults are defined only here; the typed models have no defaults.
- `local.example.yaml`: committed example of overriding three keys.
- `local.yaml`: optional, gitignored, partial override.
- `config/models.yaml` is the model registry, not settings, and is not loaded by the settings code.

**Loader**: `backend/src/insightex/core/config.py`. Pydantic v2 models (`extra="forbid"`, `frozen=True`) for sections `paths`, `api`, `ingest`, `ollama`, `visual`. `default.yaml` is located from the package file location (`repo_root()`), never the working directory, and works for the editable install.

**Precedence**, lowest to highest:
1. `config/default.yaml`
2. the local file: `$INSIGHTEX_CONFIG` if set (a missing file is an error), otherwise `config/local.yaml` if it exists
3. env vars `INSIGHTEX__<SECTION>__<KEY>` (double underscore, case-insensitive), parsed to the field type by pydantic
4. the `overrides` dict passed to `load_settings(overrides)` (tests, CLI flags)

**Aliases**: `INSIGHTEX_DATA` is an alias for `paths.data_dir`; `OLLAMA_BASE_URL` is an alias for `ollama.base_url`. If an alias and its `INSIGHTEX__` form are both set to different values, loading fails with an error naming both.

**Validation**: an unknown key in YAML or in an `INSIGHTEX__` env var, or a wrong type, fails at startup. The message names the file or env var and the dotted key. Path fields expand `~` and environment variables and resolve to absolute paths; loading never creates directories.

**API**: `load_settings(overrides=None) -> Settings`, cached `get_settings()`, `clear_settings_cache()`. Entry points (`insightex` CLI, `python -m insightex.api`, `insightex.ingest.cli`) load once and pass settings down. `chat_json` keeps `num_ctx` as a required argument with no default; entry points pass `settings.ollama.num_ctx`.

**CLI**: `insightex config show` prints the merged settings as YAML and tags every value with its origin (`default`, `file <path>`, `env <VAR>`, `override`). `insightex config validate` exits 0 or prints the error and exits 1.

**Library and process variables** stay in `env/insightex_env.sh` and are not settings: `INSIGHTEX_HOME`, `INSIGHTEX_MODEL_CACHE_MASTER`, `HF_HOME`, `HF_HUB_OFFLINE`, `TORCH_HOME`, `PIP_CACHE_DIR`, `LD_LIBRARY_PATH`. `tools/` scripts do not import the loader.

| Variable | Disposition |
|---|---|
| `INSIGHTEX_DATA` | alias for `paths.data_dir` |
| `OLLAMA_BASE_URL` | alias for `ollama.base_url` |
| `INSIGHTEX_CONFIG` | selects the local override file |
| `INSIGHTEX__<SECTION>__<KEY>` | config key override |
| `INSIGHTEX_HOME` | stays in env script; `repo_root()` still honours it to locate `config/` |
| `INSIGHTEX_MODEL_CACHE_MASTER`, `HF_HOME`, `HF_HUB_OFFLINE`, `TORCH_HOME`, `PIP_CACHE_DIR`, `LD_LIBRARY_PATH` | stays in env script: library/process variable |
| `INSIGHTEX_TEST_<NAME>_URL`, `_EXPECT` | stays: test-only inputs for network tests |

**Removed keys** (nothing read them; grep over `tools/`, `scripts/`, `env/`, `workers/` and `backend/` confirmed): `window_seconds`, `paths.home`, `paths.model_cache_master`, `paths.hf_home`, `paths.lectures`, `endpoints.ollama_base_url`. `window_seconds` returns with the embedding module.

**Rule**: no hardcoded tunables in `backend/src/`. A new tunable goes into `config/default.yaml` with a comment and is read through the typed settings object.

## Alternatives considered

- Plain environment variables only: no types, no nesting, no per-key validation, and about 40 settings do not fit a shell script.
- pydantic-settings: not installed in `~/envs/insightex`; adding it needs a package install. The env-var layer needs one small function over pydantic, which is installed.
- TOML: `config/default.yaml`, `config/local.yaml` and `config/models.yaml` already use YAML and PyYAML is installed; switching format adds a migration and no capability.
- Hydra / OmegaConf: neither is installed; both add a dependency and a composition model (config groups, CLI overrides) that a flat, single-user, two-layer file setup does not use.

## Consequences

- A misspelled key fails at startup instead of being ignored.
- An unsourced shell (no `env/insightex_env.sh`) now uses the default Ollama URL `http://localhost:11434` instead of raising "OLLAMA_BASE_URL is not set". `insightex config show` marks that value as `default`, so a missing env script remains visible.
- Logs are always written under `paths.data_dir/logs` (default `~/insightex-data`). Before, the API and ingest CLI skipped file logging when `INSIGHTEX_DATA` was unset.
- `paths.lectures` is no longer a key; the lectures directory is `<data_dir>/lectures` (on-disk layout unchanged).
- `IngestSettings` stays a dataclass so tests can construct it directly; its defaults must equal `default.yaml`, and a test fails if they differ.
- Where a caller passes no settings, `media/ffmpeg.py`, `ingest/netguard.py`, `ingest/urls.py`, `ingest/engine.py` and `llm/ollama_client.py` fall back to `get_settings()`. Entry points pass settings explicitly.
- Constants that are contracts rather than tunables stay in code: the 16 kHz ASR sample rate, workspace file names, the single ingest worker, and the token-estimate ratios of ADR-0002.

## Evidence

- `backend/tests/unit/test_config.py`: defaults, local override, missing `INSIGHTEX_CONFIG` file, env override with type conversion, unknown YAML and env keys, wrong type with dotted key, alias and conflict, `~` expansion, override precedence, `visual.enabled` default, origin tagging.
- `ruff` is not installed, so lint configuration is declared in `pyproject.toml` and not run.

## Gate / revisit when

Revisit when a module needs a setting that the section layout cannot hold, when pydantic-settings is added to the environment for another reason, or when a second user needs per-machine config beyond `local.yaml`.
