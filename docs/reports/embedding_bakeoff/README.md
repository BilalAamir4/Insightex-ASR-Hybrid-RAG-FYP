# Embedding bake-off (archived evidence)

The bake-off is complete. The decision is `BAAI/bge-m3` with 30-second windows (see `docs/adr/0001-bge-m3.md` and `docs/reports/Embedding_Report.md`).
These files are kept as evidence, not as tools; nothing here is maintained or imported.

- `results_seq1024/`: the authoritative run (max sequence length 1024). Use only these numbers.
- `queries.csv`: the 28 labelled queries (also copied to `$INSIGHTEX_DATA/eval/day04_batch_vs_online/eval/queries.csv`).
- `embed_bakeoff.py`: the only existing windowing + FAISS implementation (reference only).
- `doc_updates.md`: staged draft edits for proposal/feature documents.
- `window_comparison.md`: compares the 512-token and 1024-token runs side by side; table (a) mixes both runs, and table (b) and the decision rule use the 1024-token run.

Recorded paths inside these files (for example in `results_seq1024/run_config.json`) are the original `/mnt/e/FYP/...` paths and are left unchanged as evidence.
The removed test suite, synthetic `selftest/` fixture and the outdated 512-token `results/` run are recoverable from git tag `import-baseline` (under `_legacy_import/embedding/`).
