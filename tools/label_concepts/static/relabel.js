// Gold relabelling page for tools/label_concepts (ADR-0048 Amendment 5). Builds the DOM with textContent only.
"use strict";

const $ = (id) => document.getElementById(id);
const REMOVE_REASON = "Named but not explained or used substantively in this window (guide: Concepts)";
const RENAME_REASON = "One canonical name for this concept across windows (guide: Canonical label)";
let session = null;       // from GET /api/relabel
let current = 0;          // position in session.windows
let timer = null;
let windowEnd = null;     // stop playback here while "Play window" runs
let lastName = null;      // the name box that last had focus, for "Labels in use" clicks

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  Object.assign(e, props);
  for (const c of children) e.append(c);
  return e;
}

function fmt(s) {
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

function win() {
  return session.windows[current];
}

function setStatus(text, cls) {
  const st = $("status");
  st.textContent = text;
  st.className = "status " + (cls || "");
}

async function save() {
  clearTimeout(timer);
  timer = null;
  const w = win();
  const body = {
    reviewed: w.reviewed,
    concepts: w.concepts.map((c) => ({ v1_label: c.v1_label, decision: c.decision, label: c.label, reason: c.reason })),
  };
  const res = await fetch(`/api/relabel/window/${w.window_index}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const out = await res.json();
  if (res.ok) {
    w.v2 = out.window.v2;  // the local decisions stay: they may already hold newer edits than this response
    session.summary = out.summary;
    setStatus(`Saved ${new Date().toLocaleTimeString()}`, "ok");
    renderResult();
    renderList();
    renderSide();
  } else {
    setStatus("Not saved (fix this; nothing was logged):\n" + out.errors.join("\n"), "bad");
  }
}

function changed(delay = 800) {
  setStatus("Saving…");
  clearTimeout(timer);
  timer = setTimeout(save, delay);
}

function renderList() {
  const nav = $("list");
  nav.replaceChildren();
  session.windows.forEach((w, i) => {
    const removed = w.concepts.filter((c) => c.decision === "remove").length;
    const renamed = w.concepts.filter((c) => c.decision === "keep" && c.label !== c.v1_label).length;
    const marks = (removed ? ` −${removed}` : "") + (renamed ? ` ✎${renamed}` : "");
    const b = el("button", { className: i === current ? "current" : "" }, [
      el("span", { textContent: `#${w.window_index}  ${fmt(w.start_s)}` }),
      el("span", { className: "tag" + (w.reviewed ? " done" : ""), textContent: (w.reviewed ? "✓" : "–") + marks }),
    ]);
    b.onclick = () => go(i);
    nav.append(b);
  });
}

function renderConcepts() {
  const box = $("concepts");
  box.replaceChildren();
  const w = win();
  if (!w.concepts.length) box.append(el("p", { className: "hint", textContent: "Gold v1 has no concepts in this window." }));
  w.concepts.forEach((c, n) => {
    const v1 = w.v1.concepts[n];
    const card = el("div", { className: "concept" });
    const paint = () => {
      card.className = "concept" + (c.decision === "remove" ? " remove" : "") +
        (c.decision === "keep" && c.label !== c.v1_label ? " rename" : "");
    };
    const group = `d${w.window_index}_${n}`;
    const keep = el("input", { type: "radio", name: group, checked: c.decision === "keep" });
    const remove = el("input", { type: "radio", name: group, checked: c.decision === "remove" });
    const name = el("input", { type: "text", value: c.label, disabled: c.decision === "remove" });
    name.setAttribute("list", "labelOptions");
    const reason = el("input", { type: "text", value: c.reason, placeholder: "reason (needed for a removal or a rename)" });
    keep.onchange = () => { c.decision = "keep"; name.disabled = false; paint(); changed(); };
    remove.onchange = () => {
      c.decision = "remove"; c.label = c.v1_label; name.value = c.v1_label; name.disabled = true;
      if (!c.reason) { c.reason = REMOVE_REASON; reason.value = c.reason; }
      paint(); changed();
    };
    name.onfocus = () => { lastName = { input: name, concept: c, paint }; };
    name.oninput = () => { c.label = name.value; paint(); changed(); };
    reason.oninput = () => { c.reason = reason.value; changed(); };
    const presets = el("div", { className: "row" }, [REMOVE_REASON, RENAME_REASON].map((text) => {
      const b = el("button", { className: "preset", textContent: text });
      b.onclick = () => { c.reason = text; reason.value = text; changed(0); };
      return b;
    }));
    card.append(
      el("div", { className: "v1", textContent: `Gold v1: ${c.v1_label}` }),
      el("div", { className: "aliases", dir: "auto",
        textContent: v1.aliases.length ? `aliases: ${v1.aliases.join(" · ")}` : "no aliases" }),
      el("div", { className: "choice" }, [
        el("label", {}, [keep, " Keep"]), el("label", {}, [remove, " Remove"]),
      ]),
      el("label", { className: "hint", textContent: "Name (rename here to the canonical name):" }), name,
      reason, presets,
    );
    paint();
    box.append(card);
  });
  $("reviewed").checked = w.reviewed;
}

function renderResult() {
  const w = win(), r = w.v2, box = $("result");
  box.replaceChildren(
    el("div", { textContent: "Concepts: " + (r.concepts.map((c) => c.label).join(", ") || "none") }),
    el("div", { textContent: "Relations: " + (r.relations.map((x) => `${x.head} ${x.type} ${x.tail}`).join("; ") || "none") }),
    el("div", { textContent: "Important: " + (r.important ? `yes (${r.cue})` : "no") }),
  );
}

function renderSide() {
  const s = session.summary;
  $("summary").replaceChildren(
    el("div", { textContent: `Reviewed ${s.reviewed} of ${s.windows} windows` }),
    el("div", { textContent: `Gold v1 concepts ${s.concepts_v1}: kept ${s.kept} (renamed ${s.renamed}), removed ${s.removed}, undecided ${s.undecided}` }),
    el("div", { textContent: `${s.log_entries} logged changes` }),
  );
  $("variants").replaceChildren(...s.possible_variants.map((g) =>
    el("p", { textContent: `One concept or several? ${g.join(" / ")}` })));
  const list = $("labels"), options = $("labelOptions");
  list.replaceChildren();
  options.replaceChildren();
  for (const [label, windows] of Object.entries(s.labels_in_use)) {
    const a = el("a", { href: "#", textContent: label });
    a.onclick = (ev) => {
      ev.preventDefault();
      if (!lastName || lastName.input.disabled) return;
      lastName.input.value = label; lastName.concept.label = label; lastName.paint(); changed(0);
    };
    list.append(el("li", {}, [a, ` (${windows.join(", ")})`]));
    options.append(el("option", { value: label }));
  }
}

function go(i) {
  if (timer) save();
  current = Math.max(0, Math.min(session.windows.length - 1, i));
  const w = win();
  lastName = null;
  $("span").textContent = `Window #${w.window_index}: ${fmt(w.start_s)} – ${fmt(w.end_s)}`;
  $("text").textContent = w.text;
  renderConcepts();
  renderResult();
  renderList();
  setStatus(w.reviewed ? "Reviewed" : "Not reviewed yet", w.reviewed ? "ok" : "");
  const v = $("video");
  windowEnd = null;
  v.pause();
  if (v.readyState > 0) v.currentTime = w.start_s;
}

async function init() {
  session = await (await fetch("/api/relabel")).json();
  $("who").textContent = `${session.lecture_id} · pass ${session.pass} · ${session.windows.length} windows`;
  $("reviewed").onchange = () => { win().reviewed = $("reviewed").checked; changed(0); };
  $("prev").onclick = () => go(current - 1);
  $("next").onclick = () => go(current + 1);
  const v = $("video");
  $("play").onclick = () => { v.currentTime = win().start_s; windowEnd = win().end_s; v.play(); };
  v.addEventListener("timeupdate", () => { if (windowEnd !== null && v.currentTime >= windowEnd) { v.pause(); windowEnd = null; } });
  v.addEventListener("loadedmetadata", () => { v.currentTime = win().start_s; });
  renderSide();
  go(0);
}

init();
