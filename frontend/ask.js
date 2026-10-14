// The ask box and its citations (ADR-0047). Pure functions and one small scheduler, no DOM: loaded by index.html and
// tested with `deno test` (ask_test.js).

/** Seconds -> "m:ss" below an hour ("11:28"), "h:mm:ss" from one hour on ("1:02:05"). Invalid -> null. */
export function clock(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** "mm:ss–mm:ss" for a citation's window (an en dash between the two clocks). */
export function formatRange(start, end) {
  const a = clock(start);
  const b = clock(end);
  return a === null || b === null ? null : `${a}–${b}`;
}

/** The text on a citation button: its rank and the window's time range. Never the transcript, a score or a summary. */
export function citationLabel(c) {
  const range = formatRange(c.start, c.end);
  return range === null ? `Moment ${c.rank}` : `Moment ${c.rank}: ${range}`;
}

/** Check a typed question against the limit. Returns {ok, question (trimmed), message}. Counts characters, not UTF-16 units. */
export function checkQuestion(text, max) {
  const question = typeof text === "string" ? text.trim() : "";
  if (question === "") return { ok: false, question, message: "Type a question first." };
  const length = [...question].length;
  if (length > max) {
    return { ok: false, question, message: `Your question is ${length} characters long. Please shorten it to ${max} or fewer.` };
  }
  return { ok: true, question, message: "" };
}

/** "123 / 300" for the live counter. */
export const counterText = (text, max) => `${[...(typeof text === "string" ? text.trim() : "")].length} / ${max}`;

/**
 * Decide which citations to show from an ask response; drops anything without a usable seek time.
 * Returns [{rank, label, seek_s}] in the server's order.
 */
export function citationsToShow(response) {
  const list = Array.isArray(response?.citations) ? response.citations : [];
  return list
    .filter((c) => typeof c?.seek_s === "number" && Number.isFinite(c.seek_s) && c.seek_s >= 0)
    .map((c) => ({ rank: c.rank, label: citationLabel(c), seek_s: c.seek_s }));
}

/**
 * Keeps the rewrite model loaded without ever blocking a question (ADR-0047).
 * `post()` sends POST .../warm-up and may return a promise; errors are swallowed. `warm()` is called when the player
 * opens; `afterAsk(response)` re-warms when an answer says the model was not loaded (an ingest job unloaded it). Any call
 * is skipped if the last one was less than `minGapMs` ago, and `gpu_busy` never triggers one.
 */
export function createWarmUp({ post, now = () => Date.now(), minGapMs = 30000 }) {
  let last = null;
  const call = () => {
    const t = now();
    if (last !== null && t - last < minGapMs) return false;
    last = t;
    try {
      Promise.resolve(post()).catch(() => {});
    } catch { /* the warm-up is best effort */ }
    return true;
  };
  return {
    warm: call,
    afterAsk(response) {
      return response?.rewrite?.fallback_reason === "llm_not_loaded" ? call() : false;
    },
  };
}
