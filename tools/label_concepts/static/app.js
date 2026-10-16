// Labelling page for tools/label_concepts (M7, ADR-0048). Builds the DOM with textContent only (no innerHTML).
"use strict";

const $ = (id) => document.getElementById(id);
let session = null;        // from GET /api/session
let current = 0;           // position in session.windows
const labels = new Map();  // window_index -> {concepts, relations, important, cue}
const saved = new Set();   // window indices present in the labels file
let timer = null;
let windowEnd = null;      // stop playback here while "Play window" runs

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

function blank() {
  return { concepts: [], relations: [], important: false, cue: null };
}

function win() {
  return session.windows[current];
}

function state() {
  const w = win();
  if (!labels.has(w.window_index)) labels.set(w.window_index, blank());
  return labels.get(w.window_index);
}

function conceptLabels() {
  return state().concepts.map((c) => c.label.trim()).filter((l) => l);
}

// The body sent to the server: trimmed strings, aliases one per line, blank aliases dropped.
function payload() {
  const s = state();
  return {
    concepts: s.concepts.map((c) => ({
      label: c.label.trim(),
      aliases: c.aliasText.split("\n").map((a) => a.trim()).filter((a) => a),
    })),
    relations: s.relations.map((r) => ({ head: r.head, type: r.type, tail: r.tail })),
    important: s.important,
    cue: s.important ? (s.cue || "").trim() : null,
  };
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
  const res = await fetch(`/api/window/${w.window_index}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload()),
  });
  const body = await res.json();
  if (res.ok) {
    saved.add(w.window_index);
    setStatus(`Saved ${new Date().toLocaleTimeString()}`, "ok");
    renderList();
  } else {
    setStatus("Not saved:\n" + body.errors.join("\n"), "bad");
  }
}

function changed() {
  setStatus("Saving…");
  clearTimeout(timer);
  timer = setTimeout(save, 600);
}

function renderList() {
  const nav = $("list");
  nav.replaceChildren();
  session.windows.forEach((w, i) => {
    const b = el("button", { className: i === current ? "current" : "" }, [
      el("span", { textContent: `#${w.window_index}  ${fmt(w.start_s)}` }),
      el("span", { className: "tag" + (saved.has(w.window_index) ? " saved" : ""),
        textContent: (w.shared ? "shared " : "") + (saved.has(w.window_index) ? "✓" : "–") }),
    ]);
    b.onclick = () => go(i);
    nav.append(b);
  });
}

function renderConcepts() {
  const box = $("concepts");
  box.replaceChildren();
  state().concepts.forEach((c, i) => {
    const label = el("input", { type: "text", value: c.label, placeholder: "canonical English label" });
    label.oninput = () => { c.label = label.value; renderRelations(); changed(); };
    const aliases = el("textarea", { value: c.aliasText, placeholder: "aliases, one per line", dir: "auto" });
    aliases.oninput = () => { c.aliasText = aliases.value; changed(); };
    const del = el("button", { textContent: "Remove" });
    del.onclick = () => { state().concepts.splice(i, 1); renderConcepts(); renderRelations(); changed(); };
    box.append(el("div", { className: "concept" }, [label, aliases, del]));
  });
}

function select(options, value, onchange) {
  const s = el("select");
  const opts = [...options];
  if (value && !opts.includes(value)) opts.unshift(value); // keep a stale endpoint visible so the error shows
  s.append(el("option", { value: "", textContent: "—" }));
  for (const o of opts) {
    s.append(el("option", { value: o, textContent: options.includes(o) ? o : `${o} (no such concept)` }));
  }
  s.value = value || "";
  s.onchange = () => onchange(s.value);
  return s;
}

function renderRelations() {
  const box = $("relations");
  box.replaceChildren();
  const names = conceptLabels();
  state().relations.forEach((r, i) => {
    const head = select(names, r.head, (v) => { r.head = v; changed(); });
    const type = select(session.relation_types, r.type, (v) => { r.type = v; changed(); });
    const tail = select(names, r.tail, (v) => { r.tail = v; changed(); });
    const del = el("button", { textContent: "Remove" });
    del.onclick = () => { state().relations.splice(i, 1); renderRelations(); changed(); };
    box.append(el("div", { className: "relation" }, [head, type, tail, del]));
  });
}

function renderImportance() {
  const s = state();
  $("important").checked = s.important;
  $("cue").disabled = !s.important;
  $("cue").value = s.important ? (s.cue || "") : "";
}

function go(i) {
  if (timer) save();
  current = Math.max(0, Math.min(session.windows.length - 1, i));
  const w = win();
  $("span").textContent = `Window #${w.window_index}: ${fmt(w.start_s)} – ${fmt(w.end_s)}`;
  $("shared").textContent = w.shared ? "shared" : "";
  $("text").textContent = w.text;
  renderConcepts();
  renderRelations();
  renderImportance();
  renderList();
  setStatus(saved.has(w.window_index) ? "Saved" : "Not saved yet", saved.has(w.window_index) ? "ok" : "");
  const v = $("video");
  windowEnd = null;
  v.pause();
  if (v.readyState > 0) v.currentTime = w.start_s;
}

async function init() {
  session = await (await fetch("/api/session")).json();
  $("who").textContent = `${session.lecture_id} · labeller: ${session.labeller} · ${session.windows.length} windows`;
  for (const rec of session.labels) {
    labels.set(rec.window.window_index, {
      concepts: rec.concepts.map((c) => ({ label: c.label, aliasText: c.aliases.join("\n") })),
      relations: rec.relations.map((r) => ({ ...r })),
      important: rec.important,
      cue: rec.cue,
    });
    saved.add(rec.window.window_index);
  }
  $("addConcept").onclick = () => { state().concepts.push({ label: "", aliasText: "" }); renderConcepts(); };
  $("addRelation").onclick = () => { state().relations.push({ head: "", type: "", tail: "" }); renderRelations(); };
  $("important").onchange = () => { state().important = $("important").checked; renderImportance(); changed(); };
  $("cue").oninput = () => { state().cue = $("cue").value; changed(); };
  $("save").onclick = save;
  $("prev").onclick = () => go(current - 1);
  $("next").onclick = () => go(current + 1);
  const v = $("video");
  $("play").onclick = () => { v.currentTime = win().start_s; windowEnd = win().end_s; v.play(); };
  v.addEventListener("timeupdate", () => { if (windowEnd !== null && v.currentTime >= windowEnd) { v.pause(); windowEnd = null; } });
  v.addEventListener("loadedmetadata", () => { v.currentTime = win().start_s; });
  go(0);
}

init();
