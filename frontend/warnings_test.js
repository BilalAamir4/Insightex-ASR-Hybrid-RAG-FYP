import assert from "node:assert/strict";
import { WARNING_MESSAGES, describeWarning } from "./warnings.js";

Deno.test("transcript warnings are plain sentences without the code", () => {
  const fallback = describeWarning({ code: "TEMPERATURE_FALLBACK", message: "3 segment(s) needed temperature fallback", segment_ids: [1, 2, 3] });
  const repeated = describeWarning({ code: "HIGH_COMPRESSION_RATIO", message: "technical", segment_ids: [4] });
  assert.equal(fallback, "Some parts of this transcript were hard to recognise; answers about them may be less reliable.");
  for (const text of [fallback, repeated]) {
    assert.ok(!/TEMPERATURE|COMPRESSION|FALLBACK|_/.test(text), text);
    assert.ok(text.endsWith("."));
  }
});

Deno.test("the technical message and segment ids from the API are never shown", () => {
  const text = describeWarning({ code: "TEMPERATURE_FALLBACK", message: "technical detail 123", segment_ids: [7] });
  assert.ok(!text.includes("technical") && !text.includes("7"));
});

Deno.test("every warning code the backend emits has a sentence", () => {
  for (const code of ["AUDIO_NEAR_SILENT", "ROTATED", "MULTIPLE_AUDIO_STREAMS", "VFR_SOURCE", "START_OFFSET_CORRECTED",
    "AV_DURATION_MISMATCH", "TEMPERATURE_FALLBACK", "HIGH_COMPRESSION_RATIO"]) {
    assert.ok(WARNING_MESSAGES[code], code);
  }
});

Deno.test("an unknown code still gives a notice", () => {
  assert.equal(describeWarning({ code: "NEW_ONE" }), "Notice: NEW_ONE");
});
