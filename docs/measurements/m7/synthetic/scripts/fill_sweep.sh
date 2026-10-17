#!/usr/bin/env bash
# fill_sweep.sh <model> <num_ctx>...: one measure run per num_ctx, prompt filled with synthetic text up to the
# estimator's budget (est prompt + 1024 <= num_ctx); reports to docs/measurements/m7/synthetic/
set -euo pipefail
S=${SYNTH_DIR:?set SYNTH_DIR to a scratch directory holding synth.py and placeholder_prompt.txt}; M=$1; shift
safe=$(echo "$M" | tr ':/' '__')
mkdir -p ~/insightex/docs/measurements/m7/synthetic
for N in "$@"; do
  # est tokens/char for 35% Urdu script = .35/1.5 + .65/3.5 = 0.419; leave room for prompt (1519), overhead, margin
  chars=$(python3 -c "print(int(($N - 1024 - 1519 - 120) / 0.419))")
  ar=$(python3 -c "print(int($chars*0.35))"); ot=$(python3 -c "print($chars - int($chars*0.35))")
  python3 -I $S/synth.py fill $S/fill_$N.json $ar $ot
  bash ~/insightex/scripts/run_in_env.sh insightex extract-eval measure --lecture synthetic-fill --model "$M" \
    --prompt-file $S/placeholder_prompt.txt --k 1 --num-ctx $N --windows $S/fill_$N.json \
    --out ~/insightex/docs/measurements/m7/synthetic/fill_${safe}_ctx$N.json 2>&1 | tail -2
done
