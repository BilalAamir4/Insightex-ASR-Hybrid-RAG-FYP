import assert from "node:assert/strict";
import {
  ACTIVE_REFRESH_MS, IDLE_REFRESH_MS, STATUS_LABELS, createJobsRefresher, nextDelay, parseStageError, stageRows,
} from "./jobs.js";

const stage = (name, status, extra = {}) => ({ name, status, progress: 0, message: null, error: null, ...extra });
const job = (id, status, stages, kind = "ingest_link") => ({ id, kind, status, workspace_id: "yt-x", stages });

/** A fake timer queue: run() fires the pending timer and returns its delay. */
function fakeTimers() {
  const pending = [];
  return {
    pending,
    setTimer: (fn, ms) => { const t = { fn, ms }; pending.push(t); return t; },
    clearTimer: (t) => { const i = pending.indexOf(t); if (i >= 0) pending.splice(i, 1); },
    async run() { const t = pending.shift(); await t.fn(); return t.ms; },
  };
}

function harness(responses, visible = { value: true }) {
  const timers = fakeTimers();
  const renders = [];
  let n = 0;
  const refresher = createJobsRefresher({
    fetchJobs: async () => { const r = responses[Math.min(n++, responses.length - 1)]; if (r instanceof Error) throw r; return r; },
    render: (state) => renders.push(state),
    isVisible: () => visible.value,
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  return { refresher, timers, renders, visible };
}

Deno.test("the skipped extract stage reads 'Skipped (extraction held)'", () => {
  const rows = stageRows(job("h", "succeeded", [stage("index", "cached", { progress: 1 }),
    stage("extract", "skipped", { progress: 1, message: "extraction held" })]));
  assert.deepEqual(rows.map((r) => [r.name, r.status]), [["Prepare for search", "Done (reused)"],
    ["Find concepts", "Skipped (extraction held)"]]);
  assert.equal(STATUS_LABELS.skipped, "Skipped (extraction held)");
  assert.equal(rows[1].message, "");  // only a running stage shows its message
});

Deno.test("a running stage shows its message; a failed one its first error line", () => {
  const rows = stageRows(job("r", "running", [
    stage("extract", "running", { progress: 0.25, message: "Finding concepts: window 6 of 23" }),
    stage("asr", "failed", { error: "AsrError: EMPTY_TRANSCRIPT: No speech.\nTraceback ..." })]),
  (line) => `described: ${parseStageError(line).code}`);
  assert.equal(rows[0].message, "Finding concepts: window 6 of 23");
  assert.equal(rows[0].progress, 25);
  assert.equal(rows[1].error, "described: EMPTY_TRANSCRIPT");
  assert.deepEqual(parseStageError("ExtractStageError: EXTRACT_OLLAMA_ERROR: x"), { code: "EXTRACT_OLLAMA_ERROR", message: "x" });
  assert.equal(parseStageError("RuntimeError: boom"), null);
});

Deno.test("a job without stages (hold release) has no rows", () => {
  assert.deepEqual(stageRows(job("rel", "succeeded", [], "extract_hold_release")), []);
});

Deno.test("intervals: 2 s while a job is active, 10 s when idle or after a failure", () => {
  assert.equal(ACTIVE_REFRESH_MS, 2000);
  assert.equal(IDLE_REFRESH_MS, 10000);
  assert.equal(nextDelay([job("a", "running", [])]), ACTIVE_REFRESH_MS);
  assert.equal(nextDelay([job("a", "queued", [])]), ACTIVE_REFRESH_MS);
  assert.equal(nextDelay([job("a", "succeeded", [])]), IDLE_REFRESH_MS);
  assert.equal(nextDelay([job("a", "running", [])], true), IDLE_REFRESH_MS);
});

Deno.test("a job started from the CLI appears on the next fetch", async () => {
  const cli = job("cli", "queued", [stage("fetch", "pending")]);
  const { refresher, timers, renders } = harness([[], [cli]]);
  await refresher.start();
  assert.deepEqual(renders.at(-1).jobs, []);
  assert.equal(timers.pending[0].ms, IDLE_REFRESH_MS);
  await timers.run();
  assert.deepEqual(renders.at(-1).jobs.map((j) => j.id), ["cli"]);
  assert.equal(timers.pending[0].ms, ACTIVE_REFRESH_MS);  // now active: refetch every 2 s
});

Deno.test("a running job's stage message updates on each fetch", async () => {
  const at = (i) => [job("r", "running", [stage("extract", "running", { message: `Finding concepts: window ${i} of 23` })])];
  const { refresher, timers, renders } = harness([at(1), at(2), at(3)]);
  await refresher.start();
  await timers.run();
  await timers.run();
  assert.deepEqual(renders.map((s) => stageRows(s.jobs[0])[0].message),
    ["Finding concepts: window 1 of 23", "Finding concepts: window 2 of 23", "Finding concepts: window 3 of 23"]);
});

Deno.test("a failed fetch keeps the last list with the note flag and retries at 10 s", async () => {
  const ok = [job("a", "running", [stage("extract", "running")])];
  const { refresher, timers, renders } = harness([ok, new Error("offline"), ok]);
  await refresher.start();
  assert.equal(timers.pending[0].ms, ACTIVE_REFRESH_MS);
  await timers.run();
  assert.equal(renders.at(-1).failed, true);
  assert.deepEqual(renders.at(-1).jobs, ok);  // the last good list stays
  assert.equal(timers.pending[0].ms, IDLE_REFRESH_MS);
  await timers.run();
  assert.equal(renders.at(-1).failed, false);
});

Deno.test("fetching pauses while hidden and runs at once when visible again", async () => {
  const visible = { value: true };
  const { refresher, timers, renders } = harness([[job("a", "running", [])]], visible);
  await refresher.start();
  visible.value = false;
  refresher.visibilityChanged();
  assert.equal(timers.pending.length, 0);
  assert.equal(refresher.scheduled, false);
  visible.value = true;
  await refresher.visibilityChanged();
  assert.equal(renders.length, 2);
  assert.equal(timers.pending.length, 1);
});
