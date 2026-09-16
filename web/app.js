"use strict";

// ---------------------------------------------------------------------------
// Pyodide bootstrap
// ---------------------------------------------------------------------------
const PKG_FILES = [
  "geometry.py", "curve.py", "balancing.py", "newton.py", "layout.py",
  "subdivision.py", "subdivision_import.py", "operations.py", "workspace.py",
  "schema.py", "builders.py", "api.py", "__init__.py",
];
// Bump together with the ?v= query on the <script>/<link> tags in index.html.
// Shown in the top bar so a stale cached app.js is obvious at a glance.
const APP_VERSION = "5";
const STORAGE_KEY = "tropcurves.workspace.v1";
const SETTINGS_KEY = "tropcurves.settings.v1";

let pyodide = null;
let callFn = null;
let selectedId = null;

async function fetchPkgFile(name) {
  for (const base of ["../tropcurves/", "tropcurves/"]) {
    try {
      const r = await fetch(base + name, { cache: "no-store" });
      if (r.ok) return await r.text();
    } catch (e) { /* try next */ }
  }
  throw new Error("could not fetch " + name);
}

async function boot() {
  const ver = document.getElementById("app-version");
  if (ver) ver.textContent = "v" + APP_VERSION;
  const msg = document.getElementById("boot-msg");
  msg.textContent = "Loading Python runtime…";
  pyodide = await loadPyodide();
  msg.textContent = "Loading tropcurves…";
  pyodide.FS.mkdir("tropcurves");
  for (const f of PKG_FILES) {
    const text = await fetchPkgFile(f);
    pyodide.FS.writeFile("tropcurves/" + f, text);
  }
  pyodide.runPython(`
import sys, json, traceback
if '.' not in sys.path: sys.path.insert(0, '.')
from tropcurves.api import Session
session = Session()
def call(name, args_json):
    try:
        args = json.loads(args_json)
        return json.dumps(getattr(session, name)(*args))
    except Exception as e:
        return json.dumps({"__error": str(e)})
`);
  callFn = pyodide.globals.get("call");

  // restore autosave
  let restored = false;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) { api("load", saved); restored = true; }
  } catch (e) { /* ignore */ }

  document.getElementById("boot").hidden = true;
  document.getElementById("app").hidden = false;
  wireGlobalButtons();

  const nodes = api("list_nodes");
  if (!nodes.length && !restored) {
    api("add_preset", "caterpillar_square");
  }
  refreshAll();
  const all = api("list_nodes");
  if (all.length) selectNode(all[0].id);
}

function api(method, ...args) {
  const raw = callFn(method, JSON.stringify(args));
  const res = JSON.parse(raw);
  if (res && res.__error) throw new Error(res.__error);
  return res;
}

function autosave() {
  try { localStorage.setItem(STORAGE_KEY, api("save")); markSaved(); }
  catch (e) { /* storage may be unavailable */ }
}
function markSaved() {
  const el = document.getElementById("autosave");
  el.textContent = "saved " + new Date().toLocaleTimeString();
}

// ---------------------------------------------------------------------------
// display settings: the default color used for any edge/end/marking that has
// not been given its own color. Stored separately from the workspace (it's a
// display preference, not curve data). With no override it tracks the current
// theme (var(--ink)) so curves stay readable in light and dark automatically.
// ---------------------------------------------------------------------------
function loadSettings() {
  try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}"); }
  catch (e) { return {}; }
}
function saveSettings(s) {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); } catch (e) { /* ignore */ }
}
function isHex6(v) { return typeof v === "string" && /^#[0-9a-fA-F]{6}$/.test(v); }

function themeInkHex() {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim();
    if (isHex6(v)) return v;
  } catch (e) { /* ignore */ }
  return "#1c1c1e";
}

// For an SVG attribute value: a literal CSS var() stays correct even if the
// theme changes after this page loaded, so prefer it over a resolved hex.
function defaultColorForRender() {
  const s = loadSettings();
  return isHex6(s.defaultColor) ? s.defaultColor : "var(--ink)";
}
// For an <input type=color>, which requires a concrete "#rrggbb" (no var()).
function defaultColorHex() {
  const s = loadSettings();
  return isHex6(s.defaultColor) ? s.defaultColor : themeInkHex();
}
// The color to actually draw for an edge/end/marking ("" means "use default").
function renderColor(c) { return c || defaultColorForRender(); }

// ---------------------------------------------------------------------------
// top-level actions
// ---------------------------------------------------------------------------
// Bind defensively: if index.html is an older cached copy that lacks an
// element, skip it instead of throwing and taking the whole app down with it.
function bind(id, prop, handler) {
  const el = document.getElementById(id);
  if (el) el[prop] = handler;
  else console.warn("missing element (stale index.html?):", id);
}

function wireGlobalButtons() {
  bind("btn-new", "onclick", openNewDialog);
  bind("btn-settings", "onclick", openSettingsDialog);
  bind("btn-save", "onclick", exportJSON);
  bind("btn-load", "onclick", () => document.getElementById("file-input").click());
  bind("file-input", "onchange", importJSON);
  bind("modal-cancel", "onclick", closeModal);
}

function exportJSON() {
  const text = api("save");
  const blob = new Blob([text], { type: "application/json" });
  const a = document.getElementById("download-anchor");
  a.href = URL.createObjectURL(blob);
  a.download = "tropical-workspace.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function importJSON(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      api("load", reader.result);
      refreshAll();
      const nodes = api("list_nodes");
      if (nodes.length) selectNode(nodes[0].id);
      autosave();
    } catch (e) { alert("Import failed: " + e.message); }
  };
  reader.readAsText(file);
  ev.target.value = "";
}

function openNewDialog() {
  const body = document.getElementById("modal-body");
  body.innerHTML = `<h2>New type</h2>
    <p class="muted">Start from a preset:</p>
    <div class="reslist">
      <button data-preset="line">Tropical line (unit triangle)</button>
      <button data-preset="caterpillar_square">4-ended curve (unit square)</button>
    </div>
    <h3 style="margin-top:16px">From a subdivision</h3>
    <div class="reslist"><button id="open-editor" class="primary">Draw a subdivision…</button></div>
    <details class="dbg" style="margin-top:10px">
      <summary>or paste as text</summary>
      <p class="muted">One cell per line, each a list of lattice points, e.g.
        <code>[[0,0],[1,0],[0,1]]</code>. Parallelograms become crossings.</p>
      <textarea id="subdiv-input" rows="5" class="dbg-text"
        placeholder="[[0,0],[1,0],[0,1]]&#10;[[1,0],[1,1],[0,1]]"></textarea>
      <div id="subdiv-err" class="err"></div>
      <div style="margin-top:6px"><button id="subdiv-create">Create from text</button></div>
    </details>`;
  body.querySelectorAll("button[data-preset]").forEach(b => {
    b.onclick = () => {
      const summ = api("add_preset", b.dataset.preset);
      closeModal(); refreshAll(); selectNode(summ.id); autosave();
    };
  });
  document.getElementById("open-editor").onclick = openSubdivisionEditor;
  document.getElementById("subdiv-create").onclick = () => {
    const errEl = document.getElementById("subdiv-err");
    errEl.textContent = "";
    let cells;
    try {
      cells = parseSubdivision(document.getElementById("subdiv-input").value);
    } catch (e) { errEl.textContent = "Could not parse: " + e.message; return; }
    try {
      const summ = api("add_from_subdivision", cells, null);
      closeModal(); refreshAll(); selectNode(summ.id); autosave();
    } catch (e) { errEl.textContent = e.message; }
  };
  openModal();
}

function openSettingsDialog() {
  const s = loadSettings();
  const hasOverride = isHex6(s.defaultColor);
  const body = document.getElementById("modal-body");
  body.innerHTML = `<h2>Display settings</h2>
    <div class="ctrl-group">
      <label>Default edge / end / marking color
        <input id="set-default-color" type="color" value="${defaultColorHex()}">
      </label>
      <p class="muted" id="set-default-note" style="margin:4px 0 0"></p>
      <div class="row" style="margin-top:8px">
        <button id="set-default-auto" class="small">Use automatic (theme-based)</button>
      </div>
    </div>`;
  const note = document.getElementById("set-default-note");
  const setNote = () => {
    const s2 = loadSettings();
    note.textContent = isHex6(s2.defaultColor)
      ? "Applies to any edge, end, or marking left at its default color."
      : "Automatic: follows your light/dark theme. Applies to any edge, end, or marking left at its default color.";
  };
  setNote();
  document.getElementById("set-default-color").oninput = (ev) => {
    const s2 = loadSettings(); s2.defaultColor = ev.target.value; saveSettings(s2);
    setNote();
    if (selectedId) renderSelected();
  };
  document.getElementById("set-default-auto").onclick = () => {
    const s2 = loadSettings(); delete s2.defaultColor; saveSettings(s2);
    document.getElementById("set-default-color").value = defaultColorHex();
    setNote();
    if (selectedId) renderSelected();
  };
  openModal();
}

function parseSubdivision(text) {
  // Accept a JSON array of cells, or one cell per non-empty line.
  const trimmed = text.trim();
  if (!trimmed) throw new Error("empty");
  try {
    const asJson = JSON.parse(trimmed);
    if (Array.isArray(asJson) && asJson.length && Array.isArray(asJson[0]) &&
        asJson[0].length && Array.isArray(asJson[0][0])) {
      return asJson; // already a list of cells
    }
  } catch (e) { /* fall through to line mode */ }
  return trimmed.split("\n").map(l => l.trim()).filter(Boolean).map(l => JSON.parse(l));
}

function openModal() { document.getElementById("modal").hidden = false; }
function closeModal() {
  const m = document.getElementById("modal");
  m.hidden = true;
  const card = m.querySelector(".modal-card");
  if (card) card.classList.remove("wide");
  ED = null;
}

// ---------------------------------------------------------------------------
// visual subdivision editor
// ---------------------------------------------------------------------------
const ED_VBW = 680, ED_VBH = 440, ED_PAD = 28;
let ED = null;

function openSubdivisionEditor() {
  const card = document.querySelector("#modal .modal-card");
  if (card) card.classList.add("wide");
  ED = { xmin: 0, xmax: 5, ymin: 0, ymax: 5, cells: [], current: [] };
  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <h2>Draw a subdivision</h2>
    <p class="muted">Click lattice points to trace each cell; click the first point again (or “Finish cell”) to close it.
      Parallelograms are detected automatically and become crossings.</p>
    <div class="editor-toolbar">
      <label>x <input id="ed-xmin" type="number" value="0"> to <input id="ed-xmax" type="number" value="5"></label>
      <label>y <input id="ed-ymin" type="number" value="0"> to <input id="ed-ymax" type="number" value="5"></label>
      <button id="ed-resize" class="small">Resize grid</button>
      <span style="flex:1"></span>
      <button id="ed-finish" class="small">Finish cell</button>
      <button id="ed-undo" class="small">Undo point</button>
      <button id="ed-delcell" class="small">Delete last cell</button>
      <button id="ed-clear" class="small danger">Clear</button>
    </div>
    <svg id="editor-svg" viewBox="0 0 ${ED_VBW} ${ED_VBH}"></svg>
    <div class="editor-status" id="ed-status"></div>
    <div id="ed-err" class="err"></div>
    <div class="copy-row">
      <button id="ed-create" class="primary">Create curve</button>
      <button id="ed-text" class="small">Show text</button>
    </div>
    <details class="dbg" id="ed-textwrap">
      <summary style="display:none"></summary>
      <textarea id="ed-textarea" class="dbg-text" rows="4" readonly></textarea>
      <div class="copy-row"><button id="ed-copy" class="small">Copy</button></div>
    </details>`;
  const v = id => document.getElementById(id).value;
  document.getElementById("ed-resize").onclick = () => {
    ED.xmin = Math.round(+v("ed-xmin")); ED.xmax = Math.round(+v("ed-xmax"));
    ED.ymin = Math.round(+v("ed-ymin")); ED.ymax = Math.round(+v("ed-ymax"));
    if (ED.xmax <= ED.xmin) ED.xmax = ED.xmin + 1;
    if (ED.ymax <= ED.ymin) ED.ymax = ED.ymin + 1;
    renderEditor();
  };
  document.getElementById("ed-finish").onclick = edFinish;
  document.getElementById("ed-undo").onclick = () => { ED.current.pop(); renderEditor(); };
  document.getElementById("ed-delcell").onclick = () => { ED.cells.pop(); renderEditor(); };
  document.getElementById("ed-clear").onclick = () => { ED.cells = []; ED.current = []; document.getElementById("ed-err").textContent = ""; renderEditor(); };
  document.getElementById("ed-create").onclick = edCreate;
  document.getElementById("ed-text").onclick = () => {
    const w = document.getElementById("ed-textwrap");
    w.open = !w.open;
    document.getElementById("ed-textarea").value = edCellsText();
  };
  document.getElementById("ed-copy").onclick = () => {
    const ta = document.getElementById("ed-textarea");
    ta.select();
    if (navigator.clipboard) navigator.clipboard.writeText(ta.value);
  };
  renderEditor();
  openModal();
}

function edGridToScreen() {
  const { xmin, xmax, ymin, ymax } = ED;
  const spanx = Math.max(xmax - xmin, 1), spany = Math.max(ymax - ymin, 1);
  const s = Math.min((ED_VBW - 2 * ED_PAD) / spanx, (ED_VBH - 2 * ED_PAD) / spany);
  const ox = (ED_VBW - s * spanx) / 2, oy = (ED_VBH - s * spany) / 2;
  return (x, y) => [ox + (x - xmin) * s, ED_VBH - (oy + (y - ymin) * s)];
}

function renderEditor() {
  const svg = document.getElementById("editor-svg");
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const T = edGridToScreen();

  ED.cells.forEach(cell => {
    const isPar = jsIsParallelogram(cell);
    const d = cell.map(([x, y]) => T(x, y));
    svg.appendChild(svgEl("polygon", {
      points: d.map(p => p.join(",")).join(" "),
      fill: isPar ? "color-mix(in srgb, var(--warn) 30%, transparent)"
                  : "color-mix(in srgb, var(--accent) 18%, transparent)",
      stroke: "var(--ink)", "stroke-width": 1.5, "stroke-linejoin": "round",
    }));
    if (isPar) {
      const cx = d.reduce((a, p) => a + p[0], 0) / d.length;
      const cy = d.reduce((a, p) => a + p[1], 0) / d.length;
      svg.appendChild(text(cx, cy + 5, "×", "var(--warn)"));
    }
  });

  if (ED.current.length) {
    const d = ED.current.map(([x, y]) => T(x, y));
    if (d.length >= 2) svg.appendChild(svgEl("polyline", {
      points: d.map(p => p.join(",")).join(" "),
      fill: "none", stroke: "var(--accent)", "stroke-width": 2, "stroke-dasharray": "5 4",
    }));
    d.forEach(p => svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: 4, fill: "var(--accent)" })));
  }

  for (let x = ED.xmin; x <= ED.xmax; x++) {
    for (let y = ED.ymin; y <= ED.ymax; y++) {
      const p = T(x, y);
      svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: 2.5, fill: "var(--muted)" }));
      const hit = svgEl("circle", { cx: p[0], cy: p[1], r: 12, fill: "transparent", class: "dot-hit" });
      hit.addEventListener("click", () => edClick(x, y));
      svg.appendChild(hit);
    }
  }

  const k = ED.cells.filter(jsIsParallelogram).length;
  document.getElementById("ed-status").textContent =
    `${ED.cells.length} cell(s), ${k} parallelogram(s) → crossings; ${ED.current.length} point(s) in current cell`;
  const tw = document.getElementById("ed-textwrap");
  if (tw && tw.open) document.getElementById("ed-textarea").value = edCellsText();
}

function edClick(x, y) {
  const cur = ED.current;
  if (cur.length >= 3 && x === cur[0][0] && y === cur[0][1]) { edFinish(); return; }
  if (cur.length && x === cur[cur.length - 1][0] && y === cur[cur.length - 1][1]) return;
  document.getElementById("ed-err").textContent = "";
  cur.push([x, y]);
  renderEditor();
}

function edFinish() {
  if (ED.current.length >= 3) { ED.cells.push(ED.current); ED.current = []; }
  else if (ED.current.length) document.getElementById("ed-err").textContent = "a cell needs at least 3 points";
  renderEditor();
}

function edCellsText() { return ED.cells.map(c => JSON.stringify(c)).join("\n"); }

function edCreate() {
  const err = document.getElementById("ed-err");
  err.textContent = "";
  if (ED.current.length) { err.textContent = "finish or clear the current cell first"; return; }
  if (!ED.cells.length) { err.textContent = "draw at least one cell"; return; }
  try {
    const summ = api("add_from_subdivision", ED.cells, null);
    closeModal(); refreshAll(); selectNode(summ.id); autosave();
  } catch (e) { err.textContent = e.message; }
}

function jsHull(pts) {
  const uniq = [...new Map(pts.map(p => [p[0] + "," + p[1], p])).values()];
  uniq.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (uniq.length < 3) return uniq;
  const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [];
  for (const p of uniq) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
  const up = [];
  for (let i = uniq.length - 1; i >= 0; i--) { const p = uniq[i]; while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}

function jsIsParallelogram(cell) {
  const h = jsHull(cell);
  if (h.length !== 4) return false;
  return (h[0][0] + h[2][0] === h[1][0] + h[3][0]) &&
         (h[0][1] + h[2][1] === h[1][1] + h[3][1]);
}

// ---------------------------------------------------------------------------
// rendering: type list
// ---------------------------------------------------------------------------
function refreshAll() {
  renderTypeList();
  if (selectedId && api("list_nodes").some(n => n.id === selectedId)) {
    renderSelected();
  }
}

function renderTypeList() {
  const nodes = api("list_nodes");
  const byId = {}; nodes.forEach(n => byId[n.id] = n);
  const roots = nodes.filter(n => !n.parent_id);
  const ul = document.getElementById("type-list");
  ul.innerHTML = "";
  const walk = (n, depth) => {
    const li = document.createElement("li");
    li.className = "type-item" + (n.id === selectedId ? " selected" : "");
    li.onclick = () => selectNode(n.id);
    const warn = n.status !== "ok" ? `<span class="badge warn">needs attention</span>` : "";
    li.innerHTML = `<span class="tree-indent" style="width:${depth * 14}px"></span>
      <span style="flex:1;min-width:0">
        <span class="tname">${escapeHtml(n.name)}</span> ${warn}<br/>
        <span class="tmeta">${n.num_ends} ends · ${n.num_bounded} edges · ${n.num_markings} marks${n.parent_id ? (n.follow_parent ? " · follows" : " · detached") : ""}</span>
      </span>`;
    ul.appendChild(li);
    (n.children || []).forEach(cid => byId[cid] && walk(byId[cid], depth + 1));
  };
  roots.forEach(r => walk(r, 0));
}

function selectNode(id) {
  selectedId = id;
  const details = document.getElementById("sub-details");
  if (details) details.open = false; // each curve's subdivision starts collapsed
  renderTypeList();
  renderSelected();
}

function renderSelected() {
  const data = api("render", selectedId);
  document.getElementById("curve-name").textContent = data.name;
  const st = document.getElementById("curve-status");
  if (data.status !== "ok") { st.textContent = "⚠ needs attention (a parent edit no longer applies)"; st.className = "status warn"; }
  else { st.textContent = ""; st.className = "status"; }
  drawCurve(data);
  drawSubdivision(data);
  renderControls();
}

// ---------------------------------------------------------------------------
// SVG helpers
// ---------------------------------------------------------------------------
const SVGNS = "http://www.w3.org/2000/svg";
const VBW = 600, VBH = 400, PAD = 30;

function fitTransform(points) {
  if (!points.length) return p => [VBW / 2, VBH / 2];
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const minx = Math.min(...xs), maxx = Math.max(...xs);
  const miny = Math.min(...ys), maxy = Math.max(...ys);
  const spanx = Math.max(maxx - minx, 1e-9), spany = Math.max(maxy - miny, 1e-9);
  const s = Math.min((VBW - 2 * PAD) / spanx, (VBH - 2 * PAD) / spany);
  const ox = (VBW - s * spanx) / 2, oy = (VBH - s * spany) / 2;
  return ([x, y]) => [ox + (x - minx) * s, VBH - (oy + (y - miny) * s)]; // flip y
}

function svgEl(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}
function clearSvg(id) {
  const svg = document.getElementById(id);
  svg.setAttribute("viewBox", `0 0 ${VBW} ${VBH}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  return svg;
}

function drawCurve(data) {
  const svg = clearSvg("curve-svg");
  const c = data.curve;
  const pts = [];
  c.edges.forEach(e => { pts.push(e.from); pts.push(e.to); });
  c.vertices.forEach(v => pts.push([v.x, v.y]));
  const T = fitTransform(pts);

  c.edges.forEach(e => {
    const a = T(e.from), b = T(e.to);
    const col = renderColor(e.color);
    svg.appendChild(svgEl("line", {
      x1: a[0], y1: a[1], x2: b[0], y2: b[1],
      stroke: col, "stroke-width": e.kind === "bounded" ? 3 : 2,
      "stroke-dasharray": e.kind === "end" ? "" : "",
    }));
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const lbl = e.name + (e.weight > 1 ? " (w" + e.weight + ")" : "");
    svg.appendChild(text(mx, my - 4, lbl, col));
  });
  c.vertices.forEach(v => {
    const p = T([v.x, v.y]);
    svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: 4, fill: "var(--ink)" }));
  });
  c.markings.forEach(m => {
    const p = T(m.at);
    const col = renderColor(m.color);
    svg.appendChild(svgEl("circle", { cx: p[0] + 8, cy: p[1] - 8, r: 5, fill: col, stroke: "var(--panel)", "stroke-width": 1.5 }));
    svg.appendChild(text(p[0] + 14, p[1] - 8, m.name, col));
  });
}

function drawSubdivision(data) {
  const svg = clearSvg("sub-svg");
  const note = document.getElementById("sub-note");
  if (!data.subdivision) {
    note.textContent = data.subdivision_error || "no subdivision";
    setSubDebug(null);
    return;
  }
  note.textContent = "";
  setSubDebug(data.subdivision.cells);
  const cells = data.subdivision.cells;
  const pts = [];
  cells.forEach(cell => cell.forEach(v => pts.push(v)));
  if (data.newton) data.newton.forEach(v => pts.push(v));
  const T = fitTransform(pts);
  cells.forEach(cell => {
    const isPar = cell.length === 4 && sameSum(cell);
    const d = cell.map(v => T(v));
    const poly = svgEl("polygon", {
      points: d.map(p => p.join(",")).join(" "),
      fill: isPar ? "color-mix(in srgb, var(--warn) 28%, transparent)" : "color-mix(in srgb, var(--accent) 16%, transparent)",
      stroke: "var(--ink)", "stroke-width": 1.5, "stroke-linejoin": "round",
    });
    svg.appendChild(poly);
  });
  // lattice points
  const seen = new Set();
  cells.forEach(cell => cell.forEach(v => {
    const k = v.join(",");
    if (seen.has(k)) return; seen.add(k);
    const p = T(v);
    svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: 3, fill: "var(--ink)" }));
  }));
}

function sameSum(cell) {
  return cell[0][0] + cell[2][0] === cell[1][0] + cell[3][0] &&
         cell[0][1] + cell[2][1] === cell[1][1] + cell[3][1];
}

function setSubDebug(cells) {
  const dbg = document.getElementById("sub-debug");
  if (!cells) { dbg.innerHTML = ""; dbg.hidden = true; return; }
  dbg.hidden = false;
  const body = cells.map(c => JSON.stringify(c)).join("\n");
  dbg.innerHTML = `<summary>subdivision text (debug)</summary>
    <textarea class="dbg-text" rows="4" readonly>${escapeHtml(body)}</textarea>
    <div class="copy-row"><button class="small" id="sub-copy">Copy</button></div>`;
  dbg.querySelector("#sub-copy").onclick = () => {
    const ta = dbg.querySelector("textarea");
    ta.select();
    if (navigator.clipboard) navigator.clipboard.writeText(ta.value);
  };
}

function text(x, y, s, color) {
  const t = svgEl("text", { x, y, "font-size": 13, fill: color || "var(--ink)", "text-anchor": "middle" });
  t.textContent = s;
  return t;
}

// ---------------------------------------------------------------------------
// controls
// ---------------------------------------------------------------------------
function renderControls() {
  const data = api("render", selectedId);
  const summ = api("list_nodes").find(n => n.id === selectedId);
  const c = data.curve;
  const body = document.getElementById("controls-body");
  body.innerHTML = "";

  body.appendChild(group("Type", () => {
    const wrap = document.createElement("div");
    wrap.className = "ctrl-group";
    const nm = labeled("Name", inputText(summ.name, val => { api("rename_node", selectedId, val); refreshAll(); autosave(); }));
    wrap.appendChild(nm);
    if (summ.parent_id) {
      const cb = document.createElement("label");
      cb.className = "edge-row";
      const box = document.createElement("input"); box.type = "checkbox"; box.checked = summ.follow_parent;
      box.onchange = () => { api("set_follow", selectedId, box.checked); refreshAll(); autosave(); };
      cb.appendChild(box); cb.appendChild(document.createTextNode(" follow parent (propagate edits)"));
      wrap.appendChild(cb);
    }
    const dup = document.createElement("button");
    dup.className = "small";
    dup.textContent = "Duplicate";
    dup.title = "Make an independent copy of this type as a new root";
    dup.onclick = () => {
      try {
        const copy = api("duplicate", selectedId, null);
        refreshAll(); selectNode(copy.id); autosave();
      } catch (e) { alert(e.message); }
    };
    wrap.appendChild(row([dup]));
    return wrap;
  }));

  // actions: each opens a dedicated dialog
  const ends = c.edges.filter(e => e.kind === "end");
  const bounded = c.edges.filter(e => e.kind === "bounded");
  const v4 = Object.entries(summ.valences).filter(([v, k]) => k === 4).map(([v]) => v);
  body.appendChild(group("Actions", () => {
    const g = document.createElement("div"); g.className = "ctrl-group";
    const mk = (label, enabled, why, onclick) => {
      const b = document.createElement("button");
      b.textContent = label;
      if (enabled) b.onclick = onclick;
      else { b.disabled = true; b.title = why; }
      return b;
    };
    g.appendChild(row([
      mk("Edit end slope…", ends.length >= 2,
         "needs at least two ends (one to edit, one to absorb the change)",
         openSlopeDialog),
      mk("Add marking…", c.vertices.length >= 1,
         "this type has no vertices", openMarkingDialog),
      mk("Contract edge…", bounded.length >= 1,
         "this type has no bounded edges to contract", openContractDialog),
      mk("Resolve vertex…", v4.length >= 1,
         "this type has no 4-valent vertex to resolve", openResolveDialog),
    ]));
    return g;
  }));

  // markings
  body.appendChild(group("Markings", () => {
    const g = document.createElement("div"); g.className = "ctrl-group";
    c.markings.forEach(m => {
      const rr = document.createElement("div"); rr.className = "edge-row";
      rr.appendChild(colorControl(m.color, col => { api("set_color", selectedId, m.id, col); refreshAll(); autosave(); }));
      rr.appendChild(nameSpanInput(m.name, val => { api("rename_edge", selectedId, m.id, val); refreshAll(); autosave(); }));
      const del = document.createElement("button"); del.textContent = "✕"; del.className = "small danger";
      del.onclick = () => { api("remove_marking", selectedId, m.id); refreshAll(); autosave(); };
      rr.appendChild(del);
      g.appendChild(rr);
    });
    if (!c.markings.length) {
      const p = document.createElement("p");
      p.className = "muted"; p.style.margin = "0";
      p.textContent = "None yet — use “Add marking…” above.";
      g.appendChild(p);
    }
    return g;
  }));

  // edges & ends: rename + color
  body.appendChild(group("Edges & ends", () => {
    const g = document.createElement("div"); g.className = "ctrl-group";
    c.edges.forEach(e => {
      const rr = document.createElement("div"); rr.className = "edge-row";
      rr.appendChild(colorControl(e.color, col => { api("set_color", selectedId, e.id, col); refreshAll(); autosave(); }));
      const inp = nameSpanInput(e.name, val => { api("rename_edge", selectedId, e.id, val); refreshAll(); autosave(); });
      rr.appendChild(inp);
      const tag = document.createElement("span"); tag.className = "muted"; tag.style.fontSize = "12px";
      tag.textContent = e.kind === "end" ? "end" : "edge";
      rr.appendChild(tag);
      g.appendChild(rr);
    });
    return g;
  }));
}

// ---------------------------------------------------------------------------
// action dialogs
// ---------------------------------------------------------------------------
function fmtVec(v) { return v ? `(${v[0]}, ${v[1]})` : ""; }

function dialogHead(title, blurb) {
  const body = document.getElementById("modal-body");
  body.innerHTML = `<h2>${escapeHtml(title)}</h2>
    <p class="muted">${blurb}</p>`;
  return body;
}
function errBox() {
  const d = document.createElement("div");
  d.className = "err"; d.id = "modal-err";
  return d;
}
function showModalError(msg) {
  const el = document.getElementById("modal-err");
  if (el) el.textContent = msg; else alert(msg);
}

function openSlopeDialog() {
  const data = api("render", selectedId);
  const ends = data.curve.edges.filter(e => e.kind === "end");
  const body = dialogHead("Edit an end's slope",
    "Changing one end alone would break global balancing, so a second " +
    "<em>dependent</em> end absorbs the change; every bounded edge is then " +
    "re-derived. All other ends stay fixed.");
  if (ends.length < 2) {
    body.insertAdjacentHTML("beforeend", `<p class="muted">This type needs at least two ends.</p>`);
    openModal(); return;
  }
  const opts = ends.map(e => [e.id, `${e.name}  ${fmtVec(e.vec)}`]);
  const editSel = selectOf(opts);
  const depSel = selectOf(opts);
  depSel.selectedIndex = 1;
  const xin = numInput(), yin = numInput();
  const syncFromEdit = () => {
    const e = ends.find(x => x.id === editSel.value);
    if (e && e.vec) { xin.value = e.vec[0]; yin.value = e.vec[1]; }
    if (depSel.value === editSel.value) {
      depSel.selectedIndex = (editSel.selectedIndex + 1) % ends.length;
    }
  };
  editSel.onchange = syncFromEdit;
  depSel.onchange = () => {
    if (depSel.value === editSel.value) {
      depSel.selectedIndex = (editSel.selectedIndex + 1) % ends.length;
      showModalError("the edited end and the dependent end must be different");
    } else showModalError("");
  };
  syncFromEdit();
  const apply = document.createElement("button");
  apply.className = "primary"; apply.textContent = "Apply";
  apply.onclick = () => {
    showModalError("");
    try {
      api("edit_slopes", selectedId, editSel.value,
          [parseInt(xin.value || "0", 10), parseInt(yin.value || "0", 10)], depSel.value);
      closeModal(); refreshAll(); autosave();
    } catch (e) { showModalError(e.message); }
  };
  body.appendChild(row([labeled("end to edit", editSel), labeled("dependent end", depSel)]));
  body.appendChild(row([labeled("new x", xin), labeled("new y", yin)]));
  body.appendChild(errBox());
  body.appendChild(row([apply]));
  openModal();
}

function openMarkingDialog() {
  const data = api("render", selectedId);
  const summ = api("list_nodes").find(n => n.id === selectedId) || {};
  const val = summ.valences || {};
  const body = dialogHead("Add a marking",
    "A marking is a contracted end (direction 0) attached at a vertex. " +
    "Pick the vertex to attach it to.");
  body.insertAdjacentHTML("beforeend",
    `<label>Name (optional) <input id="mk-name" type="text" placeholder="auto"></label>`);
  const list = document.createElement("div");
  list.className = "reslist"; list.style.marginTop = "10px";
  data.curve.vertices.forEach(v => {
    const b = document.createElement("button");
    b.textContent = `at ${v.id}` + (val[v.id] ? `  (valence ${val[v.id]})` : "");
    b.onclick = () => {
      const nm = (document.getElementById("mk-name").value || "").trim();
      try {
        api("add_marking", selectedId, v.id, nm, "");
        closeModal(); refreshAll(); autosave();
      } catch (e) { showModalError(e.message); }
    };
    list.appendChild(b);
  });
  body.appendChild(list);
  body.appendChild(errBox());
  openModal();
}

function openContractDialog() {
  const data = api("render", selectedId);
  const bounded = data.curve.edges.filter(e => e.kind === "bounded");
  const body = dialogHead("Contract an edge",
    "Contracting merges the edge's two endpoints into a single vertex, " +
    "creating a derived type that follows this one. Only bounded edges " +
    "can be contracted.");
  if (!bounded.length) {
    body.insertAdjacentHTML("beforeend", `<p class="muted">This type has no bounded edges.</p>`);
    openModal(); return;
  }
  const list = document.createElement("div"); list.className = "reslist";
  bounded.forEach(e => {
    const b = document.createElement("button");
    b.textContent = `${e.name}   direction ${fmtVec(e.vec)}` +
      (e.weight > 1 ? `, weight ${e.weight}` : "");
    b.onclick = () => {
      try {
        const child = api("contract", selectedId, e.id);
        closeModal(); refreshAll(); selectNode(child.id); autosave();
      } catch (err) { showModalError(err.message); }
    };
    list.appendChild(b);
  });
  body.appendChild(list);
  body.appendChild(errBox());
  openModal();
}

function openResolveDialog() {
  const summ = api("list_nodes").find(n => n.id === selectedId) || {};
  const v4 = Object.entries(summ.valences || {}).filter(([, k]) => k === 4).map(([v]) => v);
  const body = dialogHead("Resolve a 4-valent vertex",
    "Each resolution is an adjacent maximal cell of the tropical moduli space. " +
    "A crossing pairing realizes as a parallelogram, so it cannot become a " +
    "bounded edge and is offered only for reference.");
  if (!v4.length) {
    body.insertAdjacentHTML("beforeend", `<p class="muted">This type has no 4-valent vertex.</p>`);
    openModal(); return;
  }
  let sel = null;
  if (v4.length > 1) {
    sel = selectOf(v4.map(v => [v, v]));
    body.appendChild(labeled("vertex", sel));
  }
  const listWrap = document.createElement("div");
  listWrap.className = "reslist"; listWrap.style.marginTop = "10px";
  body.appendChild(listWrap);
  body.appendChild(errBox());
  const fill = () => {
    const vertex = sel ? sel.value : v4[0];
    listWrap.innerHTML = "";
    let list;
    try { list = api("list_resolutions", selectedId, vertex); }
    catch (e) { showModalError(e.message); return; }
    list.forEach(r => {
      const b = document.createElement("button");
      b.textContent = r.label;
      b.disabled = r.is_crossing;
      if (r.is_crossing) b.title = "crossing pairing — realizes as a parallelogram";
      b.onclick = () => {
        try {
          const child = api("resolve", selectedId, vertex, r.index);
          closeModal(); refreshAll(); selectNode(child.id); autosave();
        } catch (err) { showModalError(err.message); }
      };
      listWrap.appendChild(b);
    });
  };
  if (sel) sel.onchange = fill;
  fill();
  openModal();
}

// ---- small DOM helpers ----
function group(title, buildFn) {
  const wrap = document.createElement("div");
  const h = document.createElement("h3"); h.textContent = title;
  wrap.appendChild(h); wrap.appendChild(buildFn());
  return wrap;
}
function labeled(txt, el) {
  const l = document.createElement("label"); l.textContent = txt; l.appendChild(el); return l;
}
function row(children) {
  const d = document.createElement("div"); d.className = "row"; children.forEach(c => d.appendChild(c)); return d;
}
function selectOf(pairs) {
  const s = document.createElement("select");
  pairs.forEach(([val, label]) => { const o = document.createElement("option"); o.value = val; o.textContent = label; s.appendChild(o); });
  return s;
}
function numInput() { const i = document.createElement("input"); i.type = "number"; i.value = "0"; i.style.width = "72px"; return i; }
function inputText(val, onchange) {
  const i = document.createElement("input"); i.type = "text"; i.value = val;
  i.onchange = () => onchange(i.value); return i;
}
function nameSpanInput(val, onchange) {
  const i = document.createElement("input"); i.type = "text"; i.value = val; i.className = "en";
  i.onchange = () => { try { onchange(i.value); } catch (e) { alert(e.message); i.value = val; } };
  return i;
}
function colorInput(val, onchange) {
  const i = document.createElement("input"); i.type = "color";
  i.value = isHex6(val) ? val : defaultColorHex();
  i.title = val ? "" : "Using the default color";
  i.oninput = () => onchange(i.value); return i;
}
// A color picker plus a "reset to default" button, shown only once an edge/
// marking has an explicit color of its own (an empty color means "inherit").
function colorControl(val, onSet) {
  const wrap = document.createElement("span"); wrap.className = "edge-row";
  wrap.style.gap = "4px";
  wrap.appendChild(colorInput(val, onSet));
  if (val) {
    const reset = document.createElement("button");
    reset.type = "button"; reset.className = "small ghost"; reset.textContent = "⟲";
    reset.title = "Reset to default color";
    reset.onclick = () => onSet("");
    wrap.appendChild(reset);
  }
  return wrap;
}
function escapeHtml(s) { return String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch])); }

boot().catch(err => {
  document.getElementById("boot-msg").innerHTML =
    '<span class="err">Failed to start: ' + escapeHtml(err.message) + "</span>";
  console.error(err);
});
