# Run-to-run variation: large-v3_ur

Same audio, parameters and scoring as the gate. Run 1 is the gate run; runs 2-3 are repeats.

| run | L2 WER | L1 WER | L2 CER | dropped speech | longest gap | deleted runs >= 8 words | segments | segments with temperature fallback | warm RTF |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 24.7% | 57.7% | 6.6% | 1.95% | 1.0s | 0 | 351 | not recorded (run 1 predates the field) | 0.119 |
| 2 | 24.7% | 57.7% | 6.6% | 1.95% | 1.0s | 0 | 351 | 0 | 0.118 |
| 3 | 24.7% | 57.7% | 6.6% | 1.95% | 1.0s | 0 | 351 | 0 | 0.118 |
- L2 WER: min 24.7%, mean 24.7%, max 24.7%
- L2 CER: min 6.6%, mean 6.6%, max 6.6%
- dropped speech: min 1.95%, mean 1.95%, max 1.95%
- longest gap: min 1.0s, mean 1.0s, max 1.0s

**Pass rule** (mean dropped speech <= 2% and no gap >= 10 s): mean 1.95%, max gap 1.0s -> **PASS**.
