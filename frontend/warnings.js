// Plain-sentence texts for the warning codes the API sends (lecture and job `warnings`). Pure, tested in warnings_test.js.
// The codes stay in the API and the manifest; people read only these sentences.

export const WARNING_MESSAGES = {
  // normalise.json (media)
  AUDIO_NEAR_SILENT: "The audio is very quiet, so the transcript may be poor.",
  ROTATED: "This video was recorded rotated; it has been turned upright.",
  MULTIPLE_AUDIO_STREAMS: "The file has several audio tracks; the first suitable one was used.",
  VFR_SOURCE: "The video has a variable frame rate and was converted to a steady one.",
  START_OFFSET_CORRECTED: "The sound and picture started at slightly different times; this was corrected.",
  AV_DURATION_MISMATCH: "The sound and picture differ in length by more than a second.",
  // transcript.json (speech recognition)
  TEMPERATURE_FALLBACK: "Some parts of this transcript were hard to recognise; answers about them may be less reliable.",
  HIGH_COMPRESSION_RATIO: "Some parts of this transcript look repetitive and may be wrong; answers about them may be less reliable.",
};

/** The sentence for one warning `{code, ...}`. An unknown code falls back to a generic notice that names it. */
export const describeWarning = (w) =>
  WARNING_MESSAGES[w.code] ?? `Notice: ${w.code}${w.detail ? ` (${w.detail})` : ""}`;
