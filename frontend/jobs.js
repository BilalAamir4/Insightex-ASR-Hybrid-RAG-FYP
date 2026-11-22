// Job stage rows and the home page's Recent jobs list (ADR-0054 Amendment 3). Pure functions and one small refresher,
// no DOM: loaded by index.html and tested with `deno test` (jobs_test.js).

/** How often the Recent jobs list is fetched again while any listed job is queued or running (ms). */
export const ACTIVE_REFRESH_MS = 2000;
/** How often it is fetched while every listed job is finished, and after a failed fetch (ms). */
export const IDLE_REFRESH_MS = 10000;
/** How many jobs the list shows (GET /api/jobs?limit=...). */
export const JOBS_LIMIT = 20;
/** Shown under the list when the last fetch failed; the previous list stays on screen. */
export const REFRESH_FAILED_NOTE = "Couldn't refresh jobs";

export const STAGE_LABELS = {
  fetch: "Download", normalise: "Convert video and audio", asr: "Transcribe", index: "Prepare for search",
  extract: "Find concepts",
};
export const STATUS_LABELS = {
  pending: "Waiting", running: "Working", succeeded: "Done", cached: "Done (reused)", failed: "Failed",
  cancelled: "Cancelled", skipped: "Skipped (extraction held)", queued: "Waiting",
};
export const KIND_LABELS = { ingest_link: "Add link", ingest_file: "Add file", extract_hold_release: "Release extraction hold" };

const STAGE_ERROR = /^(?:IngestRejected|IngestError|AsrError|ExtractStageError): ([A-Z_]+): (.*)$/;

/** The error code and message in a stage error's first line, or null when it carries none. */
export function parseStageError(firstLine) {
  const m = STAGE_ERROR.exec(firstLine ?? "");
  return m ? { code: m[1], message: m[2] } : null;
}

export const isTerminal = (status) => ["succeeded", "failed", "cancelled"].includes(status);
export const isActive = (job) => job?.status === "queued" || job?.status === "running";

/** The name a stage row shows. */
export const stageName = (job, stage) =>
  (job.kind === "ingest_file" && stage.name === "fetch") ? "Receive file" : (STAGE_LABELS[stage.name] ?? stage.name);

/**
 * One plain row per stage: {name, status, progress (0-100), message, error}. `message` is the running stage's progress
 * message (empty otherwise); `error` is the failed stage's text from `describeFailure(firstLine)` (first line only).
 */
export function stageRows(job, describeFailure = (line) => line) {
  return (job.stages ?? []).map((st) => ({
    name: stageName(job, st),
    status: STATUS_LABELS[st.status] ?? st.status,
    progress: Math.round((st.progress ?? 0) * 100),
    message: st.status === "running" ? (st.message ?? "") : "",
    error: st.status === "failed" && st.error ? describeFailure(st.error.split("\n")[0]) : "",
  }));
}

/** The delay before the next fetch: ACTIVE_REFRESH_MS while any job is queued or running, else IDLE_REFRESH_MS. */
export const nextDelay = (jobs, failed = false) =>
  !failed && (jobs ?? []).some(isActive) ? ACTIVE_REFRESH_MS : IDLE_REFRESH_MS;

/**
 * Keep the Recent jobs list fresh. `fetchJobs()` resolves to the job list; `render({jobs, failed})` draws it (on a
 * failed fetch, the last good list with `failed: true`). Fetching pauses while `isVisible()` is false; call
 * `visibilityChanged()` from a visibilitychange listener to fetch at once when the tab is shown again.
 */
export function createJobsRefresher({ fetchJobs, render, isVisible = () => true, setTimer = setTimeout,
  clearTimer = clearTimeout }) {
  let jobs = [];
  let timer = null;
  let inFlight = false;
  const schedule = (ms) => {
    if (timer !== null) clearTimer(timer);
    timer = isVisible() ? setTimer(tick, ms) : null;  // hidden: paused until visibilityChanged()
  };
  async function tick() {
    timer = null;
    if (!isVisible() || inFlight) return;
    inFlight = true;
    let failed = false;
    try {
      const got = await fetchJobs();
      jobs = Array.isArray(got) ? got : [];
    } catch {
      failed = true;  // keep the last list; no dialog
    } finally {
      inFlight = false;
    }
    render({ jobs, failed });
    schedule(nextDelay(jobs, failed));
  }
  return {
    start: tick,
    tick,
    visibilityChanged() {
      if (isVisible()) {
        if (timer !== null) { clearTimer(timer); timer = null; }
        return tick();
      }
      if (timer !== null) { clearTimer(timer); timer = null; }
      return undefined;
    },
    get jobs() { return jobs; },
    get scheduled() { return timer !== null; },
  };
}
