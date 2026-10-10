import assert from "node:assert/strict";
import { NOT_TRANSCRIBED, languageDisplay, sortedGroups } from "./languages.js";

const api = [
  { tier: "untested", label: "Not tested — transcription quality unknown", languages: [
    { id: "urdu", label: "Urdu", tier: "untested" }, { id: "afrikaans", label: "Afrikaans", tier: "untested" },
    { id: "english", label: "English", tier: "untested" }] },
  { tier: "tested", label: "Tested", languages: [{ id: "hindi", label: "Hindi (including Hindi-English mixed)", tier: "tested" }] },
];

Deno.test("tested group first, then untested, each sorted by label", () => {
  const groups = sortedGroups(api);
  assert.deepEqual(groups.map((g) => g.tier), ["tested", "untested"]);
  assert.deepEqual(groups[0].languages.map((l) => l.id), ["hindi"]);
  assert.deepEqual(groups[1].languages.map((l) => l.id), ["afrikaans", "english", "urdu"]);
});

Deno.test("sorting does not change the input", () => {
  sortedGroups(api);
  assert.equal(api[0].languages[0].id, "urdu");
});

Deno.test("untested language gets the badge, tested does not", () => {
  assert.deepEqual(languageDisplay({ id: "english", label: "English", tier: "untested" }),
    { text: "English", badge: true, missing: false });
  assert.deepEqual(languageDisplay({ id: "hindi", label: "Hindi", tier: "tested" }),
    { text: "Hindi", badge: false, missing: false });
});

Deno.test("an id no longer in the config (tier null) is treated as untested", () => {
  assert.equal(languageDisplay({ id: "old", label: "old", tier: null }).badge, true);
});

Deno.test("no language: not-transcribed text, no badge", () => {
  assert.deepEqual(languageDisplay(null), { text: NOT_TRANSCRIBED, badge: false, missing: true });
  assert.equal(NOT_TRANSCRIBED, "Not transcribed. Add it again and choose its language.");
});
