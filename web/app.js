"use strict";

// ---------------------------------------------------------------------------
// Pyodide bootstrap
// ---------------------------------------------------------------------------
const PKG_FILES = [
  "geometry.py", "curve.py", "balancing.py", "newton.py", "layout.py",
  "subdivision.py", "subdivision_import.py", "operations.py", "workspace.py",
  "schema.py", "builders.py", "api.py", "__init__.py",
];
const STORAGE_KEY = "tropcurves.workspace.v1";

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
// top-level actions
// ---------------------------------------------------------------------------
function wireGlobalButtons() {
  document.getElementById("btn-new").onclick = openNewDialog;
  document.getElementById("btn-save").onclick = exportJSON;
  document.getElementById("btn-load").onclick = () => document.getElementById("file-input").click();
  document.getElementById("file-input").onchange = importJSON;
  document.getElementById("modal-cancel").onclick = closeModal;
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
    svg.appendChild(svgEl("line", {
      x1: a[0], y1: a[1], x2: b[0], y2: b[1],
      stroke: e.color || "#333", "stroke-width": e.kind === "bounded" ? 3 : 2,
      "stroke-dasharray": e.kind === "end" ? "" : "",
    }));
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const lbl = e.name + (e.weight > 1 ? " (w" + e.weight + ")" : "");
    svg.appendChild(text(mx, my - 4, lbl, e.color || "#333"));
  });
  c.vertices.forEach(v => {
    const p = T([v.x, v.y]);
    svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: 4, fill: "var(--ink)" }));
  });
  c.markings.forEach(m => {
    const p = T(m.at);
    svg.appendChild(svgEl("circle", { cx: p[0] + 8, cy: p[1] - 8, r: 5, fill: m.color || "#c33", stroke: "var(--panel)", "stroke-width": 1.5 }));
    svg.appendChild(text(p[0] + 14, p[1] - 8, m.name, m.color || "#c33"));
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
    return wrap;
  }));

  // change slopes (ends)
  const ends = c.edges.filter(e => e.kind === "end");
  if (ends.length >= 2) {
    body.appendChild(group("Change end slope", () => {
      const g = document.createElement("div"); g.className = "ctrl-group";
      const editSel = selectOf(ends.map(e => [e.id, e.name]));
      const depSel = selectOf(ends.map(e => [e.id, e.name]));
      if (ends.length > 1) depSel.selectedIndex = 1;
      const xin = numInput(); const yin = numInput();
      const r1 = row([labeled("edit end", editSel), labeled("dependent", depSel)]);
      const r2 = row([labeled("new x", xin), labeled("new y", yin)]);
      const btn = document.createElement("button"); btn.textContent = "Apply"; btn.className = "primary small";
      btn.onclick = () => {
        try {
          api("edit_slopes", selectedId, editSel.value, [parseInt(xin.value || "0"), parseInt(yin.value || "0")], depSel.value);
          refreshAll(); autosave();
        } catch (e) { alert(e.message); }
      };
      g.append(r1, r2, btn);
      return g;
    }));
  }

  // contract
  const bounded = c.edges.filter(e => e.kind === "bounded");
  if (bounded.length) {
    body.appendChild(group("Contract edge", () => {
      const g = document.createElement("div"); g.className = "ctrl-group";
      const sel = selectOf(bounded.map(e => [e.id, e.name]));
      const btn = document.createElement("button"); btn.textContent = "Contract"; btn.className = "small";
      btn.onclick = () => {
        const child = api("contract", selectedId, sel.value);
        refreshAll(); selectNode(child.id); autosave();
      };
      g.append(row([labeled("edge", sel), btn]));
      return g;
    }));
  }

  // resolve (valence-4 vertices)
  const v4 = Object.entries(summ.valences).filter(([v, k]) => k === 4).map(([v]) => v);
  if (v4.length) {
    body.appendChild(group("Resolve 4-valent vertex", () => {
      const g = document.createElement("div"); g.className = "ctrl-group";
      const sel = selectOf(v4.map(v => [v, v]));
      const btn = document.createElement("button"); btn.textContent = "Show resolutions"; btn.className = "small";
      btn.onclick = () => openResolveDialog(sel.value);
      g.append(row([labeled("vertex", sel), btn]));
      return g;
    }));
  }

  // markings
  body.appendChild(group("Markings", () => {
    const g = document.createElement("div"); g.className = "ctrl-group";
    c.markings.forEach(m => {
      const rr = document.createElement("div"); rr.className = "edge-row";
      rr.appendChild(colorInput(m.color, col => { api("set_color", selectedId, m.id, col); refreshAll(); autosave(); }));
      rr.appendChild(nameSpanInput(m.name, val => { api("rename_edge", selectedId, m.id, val); refreshAll(); autosave(); }));
      const del = document.createElement("button"); del.textContent = "✕"; del.className = "small danger";
      del.onclick = () => { api("remove_marking", selectedId, m.id); refreshAll(); autosave(); };
      rr.appendChild(del);
      g.appendChild(rr);
    });
    const vsel = selectOf(c.vertices.map(v => [v.id, v.id]));
    const add = document.createElement("button"); add.textContent = "+ marking"; add.className = "small";
    add.onclick = () => { api("add_marking", selectedId, vsel.value, "", "#cc3333"); refreshAll(); autosave(); };
    g.append(row([labeled("at vertex", vsel), add]));
    return g;
  }));

  // edges & ends: rename + color
  body.appendChild(group("Edges & ends", () => {
    const g = document.createElement("div"); g.className = "ctrl-group";
    c.edges.forEach(e => {
      const rr = document.createElement("div"); rr.className = "edge-row";
      rr.appendChild(colorInput(e.color, col => { api("set_color", selectedId, e.id, col); refreshAll(); autosave(); }));
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

function openResolveDialog(vertex) {
  let list;
  try { list = api("list_resolutions", selectedId, vertex); }
  catch (e) { alert(e.message); return; }
  const body = document.getElementById("modal-body");
  body.innerHTML = `<h2>Resolutions of ${vertex}</h2>
    <p class="muted">Pick a trivalent resolution. Crossing pairings realize as a parallelogram and cannot become a bounded edge.</p>`;
  const wrap = document.createElement("div"); wrap.className = "reslist";
  list.forEach(r => {
    const b = document.createElement("button");
    b.textContent = r.label;
    b.disabled = r.is_crossing;
    b.onclick = () => {
      const child = api("resolve", selectedId, vertex, r.index);
      closeModal(); refreshAll(); selectNode(child.id); autosave();
    };
    wrap.appendChild(b);
  });
  body.appendChild(wrap);
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
  const i = document.createElement("input"); i.type = "color"; i.value = toHex(val);
  i.oninput = () => onchange(i.value); return i;
}
function toHex(c) { return (c && c[0] === "#" && c.length === 7) ? c : "#333333"; }
function escapeHtml(s) { return String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch])); }

boot().catch(err => {
  document.getElementById("boot-msg").innerHTML =
    '<span class="err">Failed to start: ' + escapeHtml(err.message) + "</span>";
  console.error(err);
});
