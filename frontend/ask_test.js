import assert from "node:assert/strict";
import { checkQuestion, citationLabel, citationsToShow, clock, counterText, createWarmUp, formatRange } from "./ask.js";

Deno.test("clock: minutes below an hour, hours from one hour", () => {
  assert.equal(clock(0), "0:00");
  assert.equal(clock(59.9), "0:59");
  assert.equal(clock(688.03), "11:28");
  assert.equal(clock(3599), "59:59");
  assert.equal(clock(3600), "1:00:00");
  assert.equal(clock(3725), "1:02:05");
});

Deno.test("clock: invalid input is null", () => {
  for (const bad of [-1, NaN, Infinity, null, undefined, "5", {}]) assert.equal(clock(bad), null);
});

Deno.test("formatRange uses an en dash and null on bad input", () => {
  assert.equal(formatRange(552, 578), "9:12\u20139:38");
  assert.equal(formatRange(660, 688.03), "11:00–11:28");
  assert.equal(formatRange(3590, 3620), "59:50–1:00:20");
  assert.equal(formatRange(NaN, 5), null);
});

Deno.test("citationLabel shows rank and time range only", () => {
  assert.equal(citationLabel({ rank: 2, start: 540, end: 570, seek_s: 541.58 }), "Moment 2: 9:00–9:30");
  assert.equal(citationLabel({ rank: 3, start: "x", end: 1 }), "Moment 3");
});

Deno.test("checkQuestion: empty, whitespace, limit, trimming", () => {
  assert.equal(checkQuestion("", 300).ok, false);
  assert.equal(checkQuestion("   \n ", 300).message, "Type a question first.");
  assert.equal(checkQuestion(undefined, 300).ok, false);
  const ok = checkQuestion("  what is batch learning?  ", 300);
  assert.deepEqual([ok.ok, ok.question, ok.message], [true, "what is batch learning?", ""]);
  assert.equal(checkQuestion("a".repeat(300), 300).ok, true);
  const long = checkQuestion("a".repeat(301), 300);
  assert.equal(long.ok, false);
  assert.match(long.message, /301 characters/);
  assert.match(long.message, /300 or fewer/);
});

Deno.test("checkQuestion counts characters, not UTF-16 units", () => {
  assert.equal(checkQuestion("\u{1F600}".repeat(300), 300).ok, true); // 300 emoji = 600 units
  assert.equal(checkQuestion("ل".repeat(300), 300).ok, true);
  assert.equal(counterText("  \u{1F600}\u{1F600} ", 300), "2 / 300");
  assert.equal(counterText(undefined, 300), "0 / 300");
});

Deno.test("citationsToShow keeps the server order and drops entries without a seek time", () => {
  const response = { citations: [
    { rank: 1, start: 660, end: 688.03, seek_s: 660.76 },
    { rank: 2, start: 540, end: 570 },
    { rank: 3, start: 210, end: 240, seek_s: 211.14 },
  ] };
  assert.deepEqual(citationsToShow(response), [
    { rank: 1, label: "Moment 1: 11:00–11:28", seek_s: 660.76 },
    { rank: 3, label: "Moment 3: 3:30–4:00", seek_s: 211.14 },
  ]);
  assert.deepEqual(citationsToShow(null), []);
  assert.deepEqual(citationsToShow({ citations: "x" }), []);
});

function fakeWarm(minGapMs = 30000) {
  const clockState = { t: 1000 };
  const posts = [];
  const w = createWarmUp({ post: () => { posts.push(clockState.t); }, now: () => clockState.t, minGapMs });
  return { w, clockState, posts };
}

Deno.test("warm-up: once on open, then at most once per 30 s, only for llm_not_loaded", () => {
  const { w, clockState, posts } = fakeWarm();
  assert.equal(w.warm(), true);
  clockState.t += 5000;
  assert.equal(w.afterAsk({ rewrite: { used: false, fallback_reason: "llm_not_loaded" } }), false); // still inside 30 s
  clockState.t += 30000;
  assert.equal(w.afterAsk({ rewrite: { used: false, fallback_reason: "llm_not_loaded" } }), true);
  clockState.t += 1000;
  assert.equal(w.afterAsk({ rewrite: { used: false, fallback_reason: "llm_not_loaded" } }), false);
  assert.equal(posts.length, 2);
});

Deno.test("warm-up: gpu_busy, success and other reasons never trigger it", () => {
  const { w, clockState, posts } = fakeWarm();
  clockState.t += 100000;
  for (const reason of ["gpu_busy", "timeout", "unusable", "error", "llm_unreachable", "rewrite_disabled", null]) {
    assert.equal(w.afterAsk({ rewrite: { used: reason === null, fallback_reason: reason } }), false);
  }
  assert.equal(w.afterAsk(null), false);
  assert.equal(posts.length, 0);
});

Deno.test("warm-up never throws or blocks, even when the post fails", async () => {
  const t = { v: 0 };
  const w = createWarmUp({ post: () => Promise.reject(new Error("offline")), now: () => t.v });
  assert.equal(w.warm(), true);
  const w2 = createWarmUp({ post: () => { throw new Error("sync failure"); }, now: () => t.v });
  assert.equal(w2.warm(), true);
  await new Promise((r) => setTimeout(r, 5)); // an unhandled rejection would fail the test run
});
