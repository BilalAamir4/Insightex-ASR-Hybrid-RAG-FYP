// Lecture-language helpers for the page (ADR-0040). Pure functions, tested in languages_test.js.

export const PLACEHOLDER = "Select the lecture's language";
export const UNTESTED_BADGE = "Untested language";
export const UNTESTED_TOOLTIP = "Transcription for this language has not been measured; results may be less reliable.";
export const NOT_TRANSCRIBED = "Not transcribed. Add it again and choose its language.";

const GROUP_ORDER = ["tested", "untested"];

/**
 * The dropdown groups from GET /api/languages: "Tested" first, then "Not tested — ...", each sorted by label.
 * Sorted here as well as on the server, so the order never depends on the response.
 */
export function sortedGroups(groups) {
  const rank = (g) => { const i = GROUP_ORDER.indexOf(g.tier); return i === -1 ? GROUP_ORDER.length : i; };
  return [...(groups ?? [])]
    .sort((a, b) => rank(a) - rank(b))
    .map((g) => ({
      ...g,
      languages: [...(g.languages ?? [])].sort((a, b) => a.label.localeCompare(b.label, "en", { sensitivity: "base" })),
    }));
}

/**
 * How a job's or lecture's language is shown. `language` is {id, label, tier} with the tier from the current
 * config, or null. A lecture without one (added before languages existed) shows NOT_TRANSCRIBED and no badge.
 */
export function languageDisplay(language) {
  if (!language) return { text: NOT_TRANSCRIBED, badge: false, missing: true };
  return { text: language.label, badge: language.tier !== "tested", missing: false };
}
