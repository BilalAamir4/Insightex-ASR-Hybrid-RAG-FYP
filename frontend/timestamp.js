// Timestamp parsing/formatting. Pure functions, no DOM: loaded by index.html and tested with `deno test`.

const NUM = String.raw`\d+(?:\.\d+)?`;
const UNITS_RE = new RegExp(String.raw`^(?:(\d+)h)?(?:(\d+)m)?(?:(${NUM})s)?$`);
const PLAIN_RE = new RegExp(`^${NUM}$`);

/**
 * Parse a timestamp into seconds. Returns null for anything invalid (never throws, never NaN).
 * Accepted: "90" or "90.5" (seconds), "1h2m3s" / "2m" / "45s" / "1h", "mm:ss" ("75:30"), "h:mm:ss".
 * With colons, seconds (and minutes when hours are present) must be below 60.
 */
export function parseTimestamp(input) {
  if (typeof input !== "string") return null;
  const s = input.trim().toLowerCase();
  if (s === "") return null;

  if (PLAIN_RE.test(s)) return Number(s);

  if (s.includes(":")) {
    const parts = s.split(":");
    if (parts.length < 2 || parts.length > 3) return null;
    if (!parts.every((p, i) => (i < parts.length - 1 ? /^\d+$/.test(p) : new RegExp(`^${NUM}$`).test(p)))) {
      return null;
    }
    const nums = parts.map(Number);
    const sec = nums[nums.length - 1];
    if (sec >= 60) return null;
    if (parts.length === 3) {
      if (nums[1] >= 60) return null;
      return nums[0] * 3600 + nums[1] * 60 + sec;
    }
    return nums[0] * 60 + sec;
  }

  const m = UNITS_RE.exec(s);
  if (!m || (m[1] === undefined && m[2] === undefined && m[3] === undefined)) return null;
  return Number(m[1] ?? 0) * 3600 + Number(m[2] ?? 0) * 60 + Number(m[3] ?? 0);
}

/** Seconds -> "h:mm:ss" (always with hours, e.g. "0:01:05"). Null/negative/non-finite -> null. */
export function formatTimestamp(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
