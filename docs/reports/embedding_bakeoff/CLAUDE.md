# embedding_bakeoff/ — archived evidence, not tools

- Use only the `results_seq1024/` numbers.
- When re-running, pass `--max-seq-length 1024`. The 512 default truncates Qwen3 windows.
- Qwen3 gets an instruction prefix on the query side only.
- A hit means the retrieved window strictly overlaps the labelled range.
- Embeddings are L2-normalised and searched with `IndexFlatIP`.
- BGE-M3 vs Qwen3-Embedding-0.6B was a tie, broken on sparse weights for the router and lower VRAM.
- Old artefacts (512-token run, `selftest/` fixture, original commands) are recoverable with `git show import-baseline:_legacy_import/embedding/...`.
