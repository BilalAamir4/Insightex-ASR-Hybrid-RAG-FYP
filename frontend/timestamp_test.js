import assert from "node:assert/strict";
import { formatTimestamp, parseTimestamp } from "./timestamp.js";

Deno.test("plain seconds", () => {
  assert.equal(parseTimestamp("0"), 0);
  assert.equal(parseTimestamp("90"), 90);
  assert.equal(parseTimestamp(" 125 "), 125);
  assert.equal(parseTimestamp("12.5"), 12.5);
  assert.equal(parseTimestamp("7200"), 7200);
});

Deno.test("unit form 1h2m3s", () => {
  assert.equal(parseTimestamp("1h2m3s"), 3723);
  assert.equal(parseTimestamp("1H2M3S"), 3723);
  assert.equal(parseTimestamp("2m"), 120);
  assert.equal(parseTimestamp("45s"), 45);
  assert.equal(parseTimestamp("1h"), 3600);
  assert.equal(parseTimestamp("1h30s"), 3630);
  assert.equal(parseTimestamp("90m"), 5400);
  assert.equal(parseTimestamp("1m2.5s"), 62.5);
});

Deno.test("mm:ss", () => {
  assert.equal(parseTimestamp("1:05"), 65);
  assert.equal(parseTimestamp("00:00"), 0);
  assert.equal(parseTimestamp("75:30"), 4530);
  assert.equal(parseTimestamp("0:59.5"), 59.5);
});

Deno.test("h:mm:ss", () => {
  assert.equal(parseTimestamp("1:02:03"), 3723);
  assert.equal(parseTimestamp("0:00:01"), 1);
  assert.equal(parseTimestamp("10:59:59"), 39599);
});

Deno.test("invalid input is null", () => {
  for (const bad of [
    "", "   ", "abc", "-5", "-1:00", "1:60", "1:2:60", "1:60:00", "1:2:3:4", ":", "1:", ":30", "1::30",
    "1h2m3", "3s2m", "1h 2m", "h", "m", "s", "hms", "1.2.3", "1,5", "NaN", "Infinity", "0x10", "1e3",
    "1:xx", "1:05s", "--5",
  ]) {
    assert.equal(parseTimestamp(bad), null, `expected null for ${JSON.stringify(bad)}`);
  }
  for (const bad of [null, undefined, 5, {}, []]) {
    assert.equal(parseTimestamp(bad), null);
  }
});

Deno.test("formatTimestamp", () => {
  assert.equal(formatTimestamp(0), "0:00:00");
  assert.equal(formatTimestamp(65), "0:01:05");
  assert.equal(formatTimestamp(3723.9), "1:02:03");
  assert.equal(formatTimestamp(1139.984), "0:18:59");
  assert.equal(formatTimestamp(null), null);
  assert.equal(formatTimestamp(-1), null);
  assert.equal(formatTimestamp(NaN), null);
});

Deno.test("format and parse round trip", () => {
  for (const t of [0, 59, 60, 3599, 3600, 86399]) assert.equal(parseTimestamp(formatTimestamp(t)), t);
});
