#!/bin/bash
# Start the worker (background) and the API + UI (foreground). Ctrl-C stops both.
#   bash scripts/dev_run.sh
# The worker is a separate process that runs the jobs; the API only enqueues and reads them. If a worker is
# already running (it holds the flock on <run_dir>/worker.lock) it is used and left running on exit.
source "$(dirname "$(readlink -f "$0")")/../env/insightex_env.sh"
source "$HOME/envs/insightex/bin/activate"

read -r RUN_DIR LOGS_DIR < <(python -c '
from insightex.core.config import get_settings
s = get_settings()
print(s.jobs.run_dir, s.paths.logs_dir)') || exit 1
mkdir -p "$RUN_DIR" "$LOGS_DIR"

WORKER_PID=""
API_PID=""
cleanup() {
  trap '' INT TERM
  for pid in "$API_PID" "$WORKER_PID"; do   # a clean worker stop puts a running job back in the queue
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then kill -TERM "$pid"; wait "$pid" 2>/dev/null; fi
  done
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if flock -n "$RUN_DIR/worker.lock" true 2>/dev/null; then
  insightex worker 2>>"$LOGS_DIR/worker.stderr.log" &   # its log: $LOGS_DIR/worker.log
  WORKER_PID=$!
  echo "worker started (pid $WORKER_PID), log: $LOGS_DIR/worker.log"
else
  echo "a worker is already running; using it (insightex gpu status shows the GPU lease)"
fi

# Background + wait, so a signal sent to this script runs the trap at once instead of after the API exits.
python -m insightex.api &
API_PID=$!
wait "$API_PID"
