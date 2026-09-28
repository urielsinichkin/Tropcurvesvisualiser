"use strict";

// ---------------------------------------------------------------------------
// Pyodide bootstrap
// ---------------------------------------------------------------------------
const PKG_FILES = [
  "geometry.py", "curve.py", "balancing.py", "newton.py", "layout.py",
  "subdivision.py", "subdivision_import.py", "operations.py", "workspace.py",
  "refined.py", "evaluation.py", "schema.py", "builders.py", "api.py", "__init__.py",
];
// Bump on each deploy. Shown in the top bar, so the loaded build is verifiable
// at a glance. (index.html fetches this file with a time-based token, so no
// ?v= bump is needed here -- only styles.css still uses a manual one.)
const APP_VERSION = "42";
const STORAGE_KEY = "tropcurves.workspace.v1";
const SETTINGS_KEY = "tropcurves.settings.v1";
const COLLAPSED_KEY = "tropcurves.collapsed.v1";   // type-tree view state, per browser
const LAYOUT_KEY = "tropcurves.layout.v1";         // side-panel widths, per browser

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
  applyBackgroundTheme(loadSettings().bgColor); // before anything is painted
  applyPanelWidths(loadLayout());
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
  applyPanelWidths(loadLayout());
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

// Labels are shown unless turned off, so an older saved settings blob (which
// has neither key) keeps the behaviour it had.
function showEdgeLabels(s) { return (s || loadSettings()).edgeLabels !== false; }
function showMarkingLabels(s) { return (s || loadSettings()).markingLabels !== false; }

// ---------------------------------------------------------------------------
// background theme: ONE chosen color, everything else derived
//
// The color the user picks is the background *behind the curve* (the panel) --
// that is the one they actually want to control, e.g. to match the paper of
// another app they paste into. The page background, borders, text and muted
// text are then derived from it: text goes near-black or near-white by the
// panel's relative luminance (keeping a hint of its hue so it reads as
// designed), and the page takes a small step away from the panel so panels
// still read as raised. That stays coherent for ANY chosen color.
// ---------------------------------------------------------------------------
const BG_PRESETS = [
  ["#ffffff", "White"],
  ["#f7f7f5", "Paper"],
  ["#fdf6e3", "Cream"],
  ["#eef2f7", "Cool grey"],
  ["#e9f0ea", "Sage"],
  ["#202225", "Charcoal"],
  ["#1b2430", "Slate"],
  ["#102620", "Forest"],
];

function hexToRgb(h) {
  const s = String(h).replace("#", "");
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}
function rgbToHex(c) {
  const f = v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
  return "#" + f(c[0]) + f(c[1]) + f(c[2]);
}
function relLum(rgb) {
  const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
}
function mixRgb(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function deriveTheme(panelHex) {
  const panel = hexToRgb(panelHex);
  const lum = relLum(panel);
  const dark = lum < 0.4;
  const toward = dark ? [255, 255, 255] : [0, 0, 0];
  const ink = mixRgb(panel, toward, dark ? 0.93 : 0.9);
  // The page sits a step away from the panel so panels read as raised. Darker
  // normally; but an (almost) black panel has no room below it, so there we
  // lift the page instead of leaving the two indistinguishable.
  const page = lum < 0.01
    ? mixRgb(panel, [255, 255, 255], 0.13)
    : mixRgb(panel, [0, 0, 0], dark ? 0.35 : 0.05);
  return {
    dark,
    bg: rgbToHex(page),
    panel: rgbToHex(panel),
    ink: rgbToHex(ink),
    muted: rgbToHex(mixRgb(panel, ink, 0.55)),
    line: rgbToHex(mixRgb(panel, ink, 0.18)),
    accent: dark ? "#4fae7f" : "#2f6f4f",
    accentInk: dark ? "#10130f" : "#ffffff",
    danger: dark ? "#e06a6a" : "#b23b3b",
    warn: dark ? "#d8a63a" : "#b8860b",
    shadow: dark ? "0 1px 3px rgba(0,0,0,.4)"
                 : "0 1px 3px rgba(0,0,0,.08), 0 4px 16px rgba(0,0,0,.05)",
  };
}

// Inline custom properties on :root win over the stylesheet's light/dark
// blocks, so setting them overrides the system theme; removing them restores it.
function applyBackgroundTheme(bgHex) {
  const st = document.documentElement.style;
  if (!isHex6(bgHex)) {
    ["--bg", "--panel", "--ink", "--muted", "--line", "--accent", "--accent-ink",
     "--danger", "--warn", "--shadow", "color-scheme"].forEach(p => st.removeProperty(p));
    return;
  }
  const t = deriveTheme(bgHex);
  st.setProperty("--bg", t.bg);
  st.setProperty("--panel", t.panel);
  st.setProperty("--ink", t.ink);
  st.setProperty("--muted", t.muted);
  st.setProperty("--line", t.line);
  st.setProperty("--accent", t.accent);
  st.setProperty("--accent-ink", t.accentInk);
  st.setProperty("--danger", t.danger);
  st.setProperty("--warn", t.warn);
  st.setProperty("--shadow", t.shadow);
  st.setProperty("color-scheme", t.dark ? "dark" : "light"); // native controls follow
}

// The chosen color IS the curve/panel background, so report that one.
function currentBgHex() {
  const s = loadSettings();
  if (isHex6(s.bgColor)) return s.bgColor;
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue("--panel").trim();
    if (isHex6(v)) return v;
  } catch (e) { /* ignore */ }
  return "#ffffff";
}

function resolvedVar(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    if (v) return v;
  } catch (e) { /* ignore */ }
  return fallback;
}

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

// The actions collapse behind ☰ on a narrow screen (see styles.css). Opening
// is a class on the panel; anything that acts, Escape, or a tap outside closes
// it again. On a wide screen the class does nothing, so this is harmless there.
function wireMenu() {
  const btn = document.getElementById("btn-menu");
  const menu = document.getElementById("menu");
  if (!btn || !menu) return;
  const setOpen = open => {
    menu.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  };
  btn.onclick = ev => {
    ev.stopPropagation();
    setOpen(!menu.classList.contains("open"));
  };
  menu.addEventListener("click", ev => { if (ev.target.closest("button")) setOpen(false); });
  document.addEventListener("click", ev => {
    if (ev.target !== btn && !menu.contains(ev.target)) setOpen(false);
  });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape") setOpen(false); });
}

// ---------------------------------------------------------------------------
// resizable side panels
//
// The splitters between the columns drag with any pointer -- mouse, pen, or a
// finger on a tablet -- and the widths are kept per browser. Each side panel
// has sensible bounds, and the curve in the middle is never squeezed below a
// usable width. Double-click (or double-tap) a splitter to restore the
// default; with focus on one, the arrow keys nudge it.
// ---------------------------------------------------------------------------
const PANEL_WIDTHS = {            // [min, max, default] in CSS px
  types: [160, 560, 240],
  controls: [220, 640, 300],
};
const MIN_VIEWS_WIDTH = 360;

// The live layout is held in memory -- a drag updates it on every move -- and
// written to storage when the drag ends, so a release never snaps back to the
// last saved width.
let liveLayout = null;
function loadLayout() {
  if (!liveLayout) {
    try { liveLayout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}"); }
    catch (e) { liveLayout = {}; }
  }
  return liveLayout;
}
function saveLayout(layout) {
  liveLayout = layout;
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch (e) { /* ignore */ }
}
function panelWidth(which) {
  const w = loadLayout()[which];
  return typeof w === "number" ? w : PANEL_WIDTHS[which][2];
}
// Show the saved widths -- shrunk, if the window is now too narrow for them,
// so the curve keeps its room. The saved preference is not touched, so
// widening the window again brings the chosen widths back.
function applyPanelWidths(layout) {
  const root = document.documentElement.style;
  const want = w => (typeof layout[w] === "number" ? layout[w] : PANEL_WIDTHS[w][2]);
  let t = want("types"), c = want("controls");
  const app = document.getElementById("app");
  if (app && app.clientWidth && window.innerWidth > 900) {
    const avail = app.clientWidth - 48 - MIN_VIEWS_WIDTH;
    const over = t + c - avail;
    if (over > 0) {
      const tt = Math.max(PANEL_WIDTHS.types[0], Math.round(t - over * t / (t + c)));
      c = Math.max(PANEL_WIDTHS.controls[0], avail - tt);
      t = tt;
    }
  }
  root.setProperty("--types-w", t + "px");
  root.setProperty("--controls-w", c + "px");
}
window.addEventListener("resize", () => applyPanelWidths(loadLayout()));
// the widest this panel may be, leaving the other panel and the curve their room
function clampPanel(which, w) {
  const [lo, hi] = PANEL_WIDTHS[which];
  const app = document.getElementById("app");
  const other = which === "types" ? "controls" : "types";
  const room = app ? app.clientWidth - 24 /* padding */ - 24 /* splitters */
                   - panelWidth(other) - MIN_VIEWS_WIDTH : hi;
  return Math.round(Math.max(lo, Math.min(hi, room, w)));
}
function setPanel(which, w, save) {
  const layout = loadLayout();
  layout[which] = clampPanel(which, w);
  applyPanelWidths(layout);
  if (save) saveLayout(layout);
}

function wireSplitter(id, which, sign) {
  const el = document.getElementById(id);
  if (!el) return;
  let startX = 0, startW = 0, dragging = false;
  el.addEventListener("pointerdown", ev => {
    if (ev.button !== undefined && ev.button !== 0) return;
    dragging = true; startX = ev.clientX; startW = panelWidth(which);
    el.setPointerCapture(ev.pointerId);
    el.classList.add("dragging"); document.body.classList.add("resizing");
    ev.preventDefault();
  });
  el.addEventListener("pointermove", ev => {
    if (!dragging) return;
    // dragging right widens the left panel and narrows the right one
    setPanel(which, startW + sign * (ev.clientX - startX), false);
  });
  const end = ev => {
    if (!dragging) return;
    dragging = false;
    try { el.releasePointerCapture(ev.pointerId); } catch (e) { /* already gone */ }
    el.classList.remove("dragging"); document.body.classList.remove("resizing");
    setPanel(which, panelWidth(which), true);
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
  el.addEventListener("dblclick", () => {
    const layout = { ...loadLayout() }; delete layout[which];
    saveLayout(layout); applyPanelWidths(layout);
  });
  el.addEventListener("keydown", ev => {
    const step = ev.shiftKey ? 64 : 16;
    if (ev.key === "ArrowLeft") setPanel(which, panelWidth(which) - sign * step, true);
    else if (ev.key === "ArrowRight") setPanel(which, panelWidth(which) + sign * step, true);
    else return;
    ev.preventDefault();
  });
}

function wireGlobalButtons() {
  wireMenu();
  wireSplitter("split-types", "types", +1);
  wireSplitter("split-controls", "controls", -1);
  wireZoom();
  bind("btn-new", "onclick", openNewDialog);
  bind("panel-layout", "onclick", openPanelLayoutDialog);
  bind("btn-settings", "onclick", openSettingsDialog);
  bind("btn-mult", "onclick", openMultiplicityDialog);
  bind("paint-curve", "onclick", openPaintDialog);
  bind("paint-change", "onclick", openPaintDialog);
  bind("paint-cancel", "onclick", stopPainting);
  bind("btn-save", "onclick", openExportDialog);
  bind("btn-load", "onclick", () => document.getElementById("file-input").click());
  bind("file-input", "onchange", importJSON);
  bind("modal-cancel", "onclick", closeModal);
  // the curve copies transparent (drop it on any background); the subdivision
  // copies with its panel background, since its cells are translucent fills
  // copy the plain figure: paint mode's rings and targets are not part of it
  bind("copy-curve", "onclick", async ev => {
    const held = painting;
    if (held) { painting = null; renderSelected(); }
    try { await copyPanelPng("curve-svg", null, ev.target, "curve.png"); }
    finally { if (held) { painting = held; renderSelected(); } }
  });
  bind("copy-sub", "onclick", ev =>
    copyPanelPng("sub-svg", resolvedVar("--panel", "#ffffff"), ev.target, "subdivision.png"));
}

// ---------------------------------------------------------------------------
// copying a panel as a PNG
// ---------------------------------------------------------------------------
// The live SVG paints with CSS custom properties (var(--ink), color-mix(...)),
// which mean nothing once the markup is detached from the document. So the
// clone gets every paint property resolved to a literal value first, otherwise
// the exported image comes out black or blank.
const COPY_SCALE = 2;
const PAINT_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray",
  "stroke-linejoin", "stroke-linecap", "opacity", "fill-opacity", "stroke-opacity",
  "font-size", "font-family", "font-weight", "text-anchor"];

async function svgToPngBlob(svgId, background) {
  const live = document.getElementById(svgId);
  if (!live) throw new Error("nothing to copy");
  const clone = live.cloneNode(true);
  clone.setAttribute("xmlns", SVGNS);

  const liveNodes = live.querySelectorAll("*");
  const cloneNodes = clone.querySelectorAll("*");
  for (let i = 0; i < liveNodes.length; i++) {
    const cs = getComputedStyle(liveNodes[i]);
    for (const p of PAINT_PROPS) {
      const v = cs.getPropertyValue(p);
      if (v) cloneNodes[i].setAttribute(p, v.trim());
    }
  }

  clone.setAttribute("viewBox", `0 0 ${VBW} ${VBH}`);   // the whole figure, not the zoomed part
  const vb = [0, 0, VBW, VBH];
  const [vx, vy, w, h] = vb;
  clone.setAttribute("width", w);
  clone.setAttribute("height", h);
  if (background) {
    const rect = document.createElementNS(SVGNS, "rect");
    rect.setAttribute("x", vx); rect.setAttribute("y", vy);
    rect.setAttribute("width", w); rect.setAttribute("height", h);
    rect.setAttribute("fill", background);
    clone.insertBefore(rect, clone.firstChild);
  }

  const xml = new XMLSerializer().serializeToString(clone);
  const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error("could not rasterize the drawing"));
    img.src = url;
  });
  const canvas = document.createElement("canvas");
  canvas.width = w * COPY_SCALE;
  canvas.height = h * COPY_SCALE;
  canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
  return await new Promise((resolve, reject) =>
    canvas.toBlob(b => b ? resolve(b) : reject(new Error("could not encode the image")), "image/png"));
}

function flashButton(btn, text) {
  if (!btn) return;
  if (!btn.dataset.label) btn.dataset.label = btn.textContent;
  btn.textContent = text;
  setTimeout(() => { btn.textContent = btn.dataset.label; }, 1500);
}

async function copyPanelPng(svgId, background, btn, filename) {
  let blob;
  try {
    blob = await svgToPngBlob(svgId, background);
  } catch (e) { flashButton(btn, "Failed"); return; }
  try {
    if (!navigator.clipboard || !window.ClipboardItem) throw new Error("no clipboard");
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
    flashButton(btn, "Copied ✓");
  } catch (e) {
    // Not every browser allows writing images to the clipboard; still hand the
    // image over rather than just failing.
    try {
      const a = document.getElementById("download-anchor");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      flashButton(btn, "Saved ↓");
    } catch (e2) { flashButton(btn, "Failed"); }
  }
}

function downloadJSON(text, filename) {
  downloadBlob(new Blob([text], { type: "application/json" }), filename);
}

// Export asks which types to save. A subset is not a truncation: whatever is
// left out is *deleted* from the copy being written, so a kept type re-attaches
// to its nearest kept ancestor (carrying the skipped steps) or becomes a root,
// and the file reads back as the same curves.
function openExportDialog() {
  const nodes = api("list_nodes");
  const body = dialogHead("Export",
    "Choose what to save. A type whose parent is left out is re-attached to " +
    "the nearest included one, carrying the steps in between, so it is still " +
    "the same derivation; with no included ancestor it becomes a root.");
  if (!nodes.length) {
    body.insertAdjacentHTML("beforeend", `<p class="muted">No types to export.</p>`);
    openModal(); return;
  }

  // nothing ticked to begin with; a row with derived types can tick (or
  // untick) itself together with all of them in one go
  const card = document.querySelector("#modal .modal-card");
  if (card) card.classList.add("wide");
  const byId = {}; nodes.forEach(n => byId[n.id] = n);
  const list = document.createElement("div");
  list.className = "export-list";
  list.style.margin = "10px 0";
  const boxes = [], subtreeBtns = [];
  const boxOf = id => boxes.find(b => b.value === id);
  const fold = foldableTypeTree(typeTreeOrder(nodes), (n, depth, lead) => {
    const line = document.createElement("div");
    line.className = "export-row";
    line.dataset.id = n.id;
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = n.id; cb.checked = false;
    cb.id = "export-cb-" + n.id;
    lead.appendChild(cb);
    const name = document.createElement("label");
    name.className = "tname"; name.htmlFor = cb.id;
    name.textContent = n.name;
    const meta = document.createElement("span");
    meta.className = "muted";
    meta.textContent = `${n.num_ends} ends · ${n.num_bounded} edges · ${n.num_markings} marks`;
    const below = api("descendants", n.id).filter(id => byId[id]);
    const cell = document.createElement("span");
    if (below.length) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "small subtree-btn";
      const ids = [n.id, ...below];
      b.onclick = () => {
        const on = !ids.every(id => boxOf(id).checked);
        ids.forEach(id => { boxOf(id).checked = on; });
        sync();
      };
      subtreeBtns.push({ b, ids, count: below.length });
      cell.appendChild(b);
    }
    line.append(lead, name, meta, cell);
    list.appendChild(line);
    boxes.push(cb);
    return { line: line, box: cb };
  });
  body.appendChild(row([fold.foldAll]));
  body.appendChild(list);

  const go = document.createElement("button");
  go.className = "primary";
  const all = document.createElement("button"); all.className = "small"; all.textContent = "Select all";
  const none = document.createElement("button"); none.className = "small"; none.textContent = "Select none";
  const picked = () => boxes.filter(b => b.checked).map(b => b.value);
  const sync = () => {
    const n = picked().length;
    go.textContent = n === 0 ? "Export" : n === nodes.length ? `Export all ${n}` : `Export ${n} of ${nodes.length}`;
    go.disabled = n === 0;
    subtreeBtns.forEach(({ b, ids, count }) => {
      const allOn = ids.every(id => boxOf(id).checked);
      b.textContent = (allOn ? "Unselect" : "Select") + ` with ${count} derived`;
      b.title = (allOn ? "Untick" : "Tick") + " this type and every type derived from it";
    });
    fold.refold();                 // folded rows count their ticked types
  };
  boxes.forEach(b => { b.onchange = sync; });
  all.onclick = () => { boxes.forEach(b => { b.checked = true; }); sync(); };
  none.onclick = () => { boxes.forEach(b => { b.checked = false; }); sync(); };
  go.onclick = () => {
    const ids = picked();
    let text;
    try { text = ids.length === nodes.length ? api("save") : api("export_subset", ids); }
    catch (e) { showModalError(e.message); return; }
    downloadJSON(text, exportFilename(ids, nodes, byId));
    closeModal();
  };
  sync();
  body.appendChild(row([go, all, none]));
  body.appendChild(errBox());
  openModal();
}

function exportFilename(ids, nodes, byId) {
  if (ids.length === nodes.length) return "tropical-workspace.json";
  if (ids.length === 1) {
    const safe = (byId[ids[0]].name || "curve").replace(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, "");
    return (safe || "curve") + ".json";
  }
  return `tropical-subset-${ids.length}.json`;
}

// Import a workspace file. Into an empty library it simply loads; otherwise
// the file's types can be added alongside the current ones or replace them.
function importJSON(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const text = reader.result;
    const have = api("list_nodes").length;
    if (!have) { finishImport(text, false); return; }
    let count = null;
    try { count = JSON.parse(text).nodes.length; } catch (e) { /* load reports it */ }
    const many = n => `${n} type${n === 1 ? "" : "s"}`;
    const body = dialogHead("Import " + file.name,
      `${count === null ? "This file" : `This file holds ${many(count)}`}; your library
       has ${many(have)}. Add the file's types to the library, or replace the
       library with them?`);
    const add = document.createElement("button");
    add.className = "primary"; add.id = "import-append";
    add.textContent = "Add to the library";
    add.onclick = () => finishImport(text, true);
    const replace = document.createElement("button");
    replace.className = "danger"; replace.id = "import-replace";
    replace.textContent = `Replace the library (discards the current ${many(have)})`;
    replace.onclick = () => finishImport(text, false);
    const note = document.createElement("p");
    note.className = "muted"; note.style.margin = "8px 0 0";
    note.textContent = "Added types keep their derivations. A name already in the library gets a number, e.g. “root (2)”.";
    const box = document.createElement("div");
    box.className = "reslist"; box.style.marginTop = "10px";
    box.append(add, replace);
    body.append(box, note, errBox());
    openModal();
  };
  reader.readAsText(file);
  ev.target.value = "";
}

function finishImport(text, append) {
  let added;
  try { added = api("load", text, append); }
  catch (e) {
    const msg = "Import failed: " + e.message;
    if (!document.getElementById("modal").hidden) showModalError(msg); else alert(msg);
    return;
  }
  if (!document.getElementById("modal").hidden) closeModal();
  refreshAll();
  const nodes = api("list_nodes");
  const first = added.find(id => nodes.some(n => n.id === id)) || (nodes[0] && nodes[0].id);
  if (first) selectNode(first);
  autosave();
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
      <label for="" id="set-default-label">Default edge / end / marking color</label>
      <div id="set-default-slot"></div>
      <p class="muted" id="set-default-note" style="margin:4px 0 0"></p>
      <div class="row" style="margin-top:8px">
        <button id="set-default-auto" class="small">Use automatic (theme-based)</button>
      </div>
    </div>
    <h3 style="margin-top:18px">Labels</h3>
    <p class="muted" style="margin:4px 0 8px">Names drawn next to each element.
      They are placed clear of the curve, so hiding them frees up room.</p>
    <label class="check"><input type="checkbox" id="set-edge-labels"> Edge and end names</label>
    <label class="check"><input type="checkbox" id="set-mark-labels"> Marking names</label>
    <h3 style="margin-top:18px">Background</h3>
    <p class="muted" style="margin:4px 0 8px">This is the background behind the
      curve — match it to wherever you paste. The page, borders and text are
      derived from it.</p>
    <label>Curve background</label>
    <div id="set-bg-slot"></div>
    <div class="swatches" id="bg-swatches"></div>
    <div class="row" style="margin-top:8px">
      <button id="set-bg-auto" class="small">Use automatic (system light/dark)</button>
    </div>`;

  const note = document.getElementById("set-default-note");
  const setNote = () => {
    note.textContent = isHex6(loadSettings().defaultColor)
      ? "Applies to any edge, end, or marking left at its default color."
      : "Automatic: follows your light/dark theme. Applies to any edge, end, or marking left at its default color.";
  };
  setNote();

  const defaultField = colorField(s.defaultColor, (hex) => {
    const s2 = loadSettings(); s2.defaultColor = hex; saveSettings(s2);
    setNote();
    if (selectedId) renderSelected();
  }, { live: true, fallback: defaultColorHex });
  document.getElementById("set-default-slot").appendChild(defaultField);

  const bindLabelToggle = (id, key) => {
    const box = document.getElementById(id);
    box.checked = loadSettings()[key] !== false;
    box.onchange = () => {
      const s2 = loadSettings();
      if (box.checked) delete s2[key]; else s2[key] = false;
      saveSettings(s2);
      if (selectedId) renderSelected();
    };
  };
  bindLabelToggle("set-edge-labels", "edgeLabels");
  bindLabelToggle("set-mark-labels", "markingLabels");

  // the background has its own swatches (BG_PRESETS) right below it
  const bgField = colorField(loadSettings().bgColor, (hex) => setBackground(hex),
    { live: true, fallback: currentBgHex, presets: false });
  document.getElementById("set-bg-slot").appendChild(bgField);

  function setBackground(hex) {
    const s2 = loadSettings();
    if (hex) s2.bgColor = hex; else delete s2.bgColor;
    saveSettings(s2);
    applyBackgroundTheme(hex);
    bgField.setValue(hex || null);
    // the default curve color follows the theme when not overridden
    if (!isHex6(loadSettings().defaultColor)) defaultField.setValue(null);
    if (selectedId) renderSelected();
  }
  const swatches = document.getElementById("bg-swatches");
  BG_PRESETS.forEach(([hex, label]) => {
    const b = document.createElement("button");
    b.className = "swatch";
    b.style.background = hex;
    b.title = label;
    b.setAttribute("aria-label", label);
    b.onclick = () => setBackground(hex);
    swatches.appendChild(b);
  });
  document.getElementById("set-bg-auto").onclick = () => setBackground(null);
  document.getElementById("set-default-auto").onclick = () => {
    const s2 = loadSettings(); delete s2.defaultColor; saveSettings(s2);
    defaultField.setValue(null);
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

// Which types have their derived types folded away. This is how the list is
// being looked at, not part of the workspace, so it lives in this browser only
// and is never exported.
function loadCollapsed() {
  try { return new Set(JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "[]")); }
  catch (e) { return new Set(); }
}
function saveCollapsed(set) {
  try { localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...set])); } catch (e) { /* ignore */ }
}

// Selecting a type unfolds whatever it sits under (a new child made from a
// folded parent, say) so the highlight is visible. Only selecting does this: a
// deliberate fold -- "Collapse all" included -- is left as the user made it.
function revealInTypeList(id) {
  const byId = {}; api("list_nodes").forEach(n => byId[n.id] = n);
  const set = loadCollapsed();
  let changed = false;
  for (let cur = byId[id]; cur && cur.parent_id; cur = byId[cur.parent_id]) {
    if (set.delete(cur.parent_id)) changed = true;
  }
  if (changed) saveCollapsed(set);
}

// The types in the order the types menu shows them -- each root followed by
// its derived types, depth first -- with their depth in the tree.
function typeTreeOrder(nodes) {
  const byId = {}; nodes.forEach(n => byId[n.id] = n);
  const out = [];
  const walk = (n, depth) => {
    out.push({ node: n, depth: depth });
    (n.children || []).forEach(cid => { if (byId[cid]) walk(byId[cid], depth + 1); });
  };
  nodes.filter(n => !n.parent_id || !byId[n.parent_id]).forEach(r => walk(r, 0));
  return out;
}

// A list of types (typeTreeOrder's output) whose subtrees fold, as in the
// types menu, for the dialogs that list types. `makeRow(node, depth, lead)`
// builds one row and returns { line, box }: `lead` holds the indent and the
// fold toggle (the row puts its checkbox there too), `line` is the row, and
// `box` its checkbox, if any. Folds start as the menu has them, but folding
// here is the dialog's own business and never changes the menu. A folded row
// says how many types it hides and how many of those are ticked -- they still
// count. Returns { refold, foldAll }: refold() after changing ticks from
// code, and foldAll is a Collapse all / Expand all button to place.
function foldableTypeTree(tree, makeRow) {
  const inTree = new Set(tree.map(t => t.node.id));
  const folded = new Set([...loadCollapsed()].filter(id => inTree.has(id)));
  const parentOf = {}, lines = {}, order = [];
  tree.forEach(({ node, depth }) => {
    parentOf[node.id] = node.parent_id;
    const kids = (node.children || []).filter(cid => inTree.has(cid));
    const lead = document.createElement("span");
    lead.className = "fold-lead";
    const indent = document.createElement("span");
    indent.className = "tree-indent"; indent.style.width = (depth * 14) + "px";
    lead.appendChild(indent);
    let tw = null;
    if (kids.length) {
      tw = document.createElement("button");
      tw.type = "button"; tw.className = "twisty";
      tw.onclick = () => {
        if (folded.has(node.id)) folded.delete(node.id); else folded.add(node.id);
        refold();
      };
      lead.appendChild(tw);
    } else {
      const slot = document.createElement("span"); slot.className = "twisty-slot";
      lead.appendChild(slot);
    }
    const made = makeRow(node, depth, lead);
    lines[node.id] = { kids: kids, tw: tw, line: made.line, box: made.box || null };
    order.push(node.id);
  });
  const subtree = id => lines[id].kids.flatMap(c => [c, ...subtree(c)]);
  const parents = order.filter(id => lines[id].kids.length);

  const foldAll = document.createElement("button");
  foldAll.type = "button"; foldAll.className = "small";
  foldAll.onclick = () => {
    const allFolded = parents.every(id => folded.has(id));
    folded.clear();
    if (!allFolded) parents.forEach(id => folded.add(id));
    refold();
  };
  const refold = () => {
    order.forEach(id => {
      const l = lines[id];
      let hidden = false;
      for (let a = parentOf[id]; a && inTree.has(a); a = parentOf[a]) if (folded.has(a)) { hidden = true; break; }
      l.line.hidden = hidden;
      if (!l.tw) return;
      const isFolded = folded.has(id);
      l.tw.textContent = isFolded ? "▸" : "▾";
      l.tw.title = isFolded ? "Show derived types" : "Hide derived types";
      l.tw.setAttribute("aria-expanded", isFolded ? "false" : "true");
      let badge = l.line.querySelector(".fold-badge");
      if (isFolded) {
        const below = subtree(id);
        const ticked = below.filter(c => lines[c].box && lines[c].box.checked).length;
        if (!badge) {
          badge = document.createElement("span"); badge.className = "badge fold-badge";
          badge.title = "derived types folded away";
          l.line.querySelector(".tname").appendChild(badge);
        }
        badge.textContent = `+${below.length}` + (ticked ? ` (${ticked} ticked)` : "");
      } else if (badge) badge.remove();
    });
    foldAll.hidden = !parents.length;
    foldAll.textContent = parents.length && parents.every(id => folded.has(id)) ? "Expand all" : "Collapse all";
  };
  refold();
  return { refold: refold, foldAll: foldAll };
}

function renderTypeList() {
  const nodes = api("list_nodes");
  const byId = {}; nodes.forEach(n => byId[n.id] = n);
  const roots = nodes.filter(n => !n.parent_id);
  const collapsed = loadCollapsed();

  // forget types that no longer exist, or no longer have anything to fold
  let changed = false;
  for (const id of [...collapsed]) {
    if (!byId[id] || !(byId[id].children || []).some(c => byId[c])) { collapsed.delete(id); changed = true; }
  }
  if (changed) saveCollapsed(collapsed);

  const countBelow = n => (n.children || []).reduce(
    (k, cid) => byId[cid] ? k + 1 + countBelow(byId[cid]) : k, 0);
  // a folded row that hides the selected type is marked, so it is not lost
  const hidesSelection = n => {
    for (let cur = byId[selectedId]; cur && cur.parent_id; cur = byId[cur.parent_id]) {
      if (cur.parent_id === n.id) return true;
    }
    return false;
  };

  const ul = document.getElementById("type-list");
  ul.innerHTML = "";
  const walk = (n, depth) => {
    const kids = (n.children || []).filter(cid => byId[cid]);
    const folded = kids.length > 0 && collapsed.has(n.id);
    const li = document.createElement("li");
    li.className = "type-item" + (n.id === selectedId ? " selected" : "")
      + (folded && hidesSelection(n) ? " holds-selection" : "");
    li.onclick = () => selectNode(n.id);
    const warn = n.status !== "ok" ? `<span class="badge warn">needs attention</span>` : "";
    const hidden = folded ? `<span class="badge" title="derived types folded away">+${countBelow(n)}</span>` : "";
    li.innerHTML = `<span class="tree-indent" style="width:${depth * 14}px"></span>
      <span class="twisty-slot"></span>
      <span style="flex:1;min-width:0">
        <span class="tname">${escapeHtml(n.name)}</span> ${warn} ${hidden}<br/>
        <span class="tmeta">${n.num_ends} ends · ${n.num_bounded} edges · ${n.num_markings} marks${n.parent_id ? (n.follow_parent ? " · follows" : " · detached") : ""}</span>
      </span>`;
    if (kids.length) {
      const tw = document.createElement("button");
      tw.className = "twisty";
      tw.textContent = folded ? "▸" : "▾";
      tw.title = folded ? "Show derived types" : "Hide derived types";
      tw.setAttribute("aria-expanded", folded ? "false" : "true");
      tw.onclick = ev => {
        ev.stopPropagation();           // folding is not selecting
        const set = loadCollapsed();
        if (folded) set.delete(n.id); else set.add(n.id);
        saveCollapsed(set);
        renderTypeList();
      };
      li.querySelector(".twisty-slot").replaceWith(tw);
    }
    const del = document.createElement("button");
    del.className = "row-del";
    del.textContent = "🗑";
    del.title = `Delete ${n.name}…`;
    del.setAttribute("aria-label", `Delete ${n.name}`);
    del.onclick = ev => { ev.stopPropagation(); openDeleteDialog(n.id); };
    li.appendChild(del);
    ul.appendChild(li);
    if (!folded) kids.forEach(cid => walk(byId[cid], depth + 1));
  };
  roots.forEach(r => walk(r, 0));

  // fold / unfold everything at once
  const parents = nodes.filter(n => (n.children || []).some(c => byId[c])).map(n => n.id);
  const tools = document.getElementById("types-tools");
  if (tools) {
    tools.hidden = parents.length === 0;
    const allFolded = parents.length > 0 && parents.every(id => collapsed.has(id));
    const btn = document.getElementById("types-fold-all");
    btn.textContent = allFolded ? "Expand all" : "Collapse all";
    btn.onclick = () => {
      saveCollapsed(allFolded ? new Set() : new Set(parents));
      renderTypeList();
    };
  }
}

function selectNode(id) {
  if (id !== selectedId && curveZoom) curveZoom.reset(false);
  selectedId = id;
  revealInTypeList(id);
  const details = document.getElementById("sub-details");
  if (details) details.open = false; // each curve's subdivision starts collapsed
  renderTypeList();
  renderSelected();
}

// ---------------------------------------------------------------------------
// zooming a picture
//
// The mouse wheel (or a trackpad pinch, which arrives as a ctrl+wheel) zooms
// about the pointer; two fingers pinch-zoom and move the picture together;
// once zoomed in, dragging moves around. Zoom works on the viewBox, so a
// redraw into the same element (an edit, painting, a dialog re-highlighting)
// keeps the view, and every click target still lines up. A drag that moved
// the picture is not a click, so it never picks or paints. The main curve and
// the pick dialogs' pictures each get their own; choosing another type starts
// the main one from the whole picture, and Copy always copies the whole figure.
// ---------------------------------------------------------------------------
const ZOOM_MIN = 1, ZOOM_MAX = 16;

// Make `svg` zoomable; `ui` holds the optional level/fit/out/in controls.
// The controller is kept on the element (svg._zoom), where clearSvg finds it.
function makeZoomable(svg, ui = {}) {
  let z = { k: 1, x: 0, y: 0 };                 // viewBox = x y VBW/k VBH/k
  const viewBox = () => `${z.x} ${z.y} ${VBW / z.k} ${VBH / z.k}`;
  const apply = () => {
    svg.setAttribute("viewBox", viewBox());
    const zoomed = z.k > 1.001;
    svg.classList.toggle("zoomable", zoomed);
    if (ui.level) ui.level.textContent = zoomed ? Math.round(z.k * 100) + "%" : "";
    if (ui.fit) ui.fit.hidden = !zoomed;
    if (ui.out) ui.out.disabled = !zoomed;
    if (ui.in) ui.in.disabled = z.k >= ZOOM_MAX - 1e-6;
  };
  // keep at least half of the picture's width/height in view
  const clamp = () => {
    z.k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z.k));
    if (z.k <= 1.001) { z = { k: 1, x: 0, y: 0 }; return; }
    const w = VBW / z.k, h = VBH / z.k;
    z.x = Math.min(VBW - w / 2, Math.max(-w / 2, z.x));
    z.y = Math.min(VBH - h / 2, Math.max(-h / 2, z.y));
  };
  // zoom by `factor`, keeping the picture point `at` ([x, y] in viewBox
  // units) where it is on screen
  const zoomBy = (factor, at) => {
    const k2 = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z.k * factor));
    const c = at || [z.x + VBW / z.k / 2, z.y + VBH / z.k / 2];
    z.x = c[0] - (c[0] - z.x) * z.k / k2;
    z.y = c[1] - (c[1] - z.y) * z.k / k2;
    z.k = k2;
    clamp(); apply();
  };
  const reset = (redraw = true) => { z = { k: 1, x: 0, y: 0 }; if (redraw) apply(); };
  // with "meet" the drawing fills the same box at any zoom
  const fitScale = () => {
    const r = svg.getBoundingClientRect();
    return { r, fit: Math.min(r.width / VBW, r.height / VBH) };
  };

  svg.addEventListener("wheel", ev => {
    // pixels, lines or pages; a trackpad pinch comes as small ctrl+wheel steps
    const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? 400 : 1;
    const dy = ev.deltaY * unit * (ev.ctrlKey ? 4 : 1);
    // nothing to zoom out of: let the page (or dialog) scroll on past it
    if (dy > 0 && z.k <= 1.001 && !ev.ctrlKey) return;
    ev.preventDefault();
    zoomBy(Math.exp(-dy * 0.0015), svgPoint(svg, ev.clientX, ev.clientY));
  }, { passive: false });

  const pointers = new Map();        // pointerId -> [clientX, clientY]
  let gesture = null, moved = false;
  const begin = () => {
    const pts = [...pointers.values()];
    if (pts.length >= 2) {
      const [a, b] = pts;
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      gesture = { kind: "pinch", d0: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, k0: z.k,
                  anchor: svgPoint(svg, mid[0], mid[1]) };
    } else if (pts.length === 1) {
      gesture = { kind: "pan", last: pts[0], start: pts[0] };
    } else gesture = null;
  };
  svg.addEventListener("pointerdown", ev => {
    if (ev.pointerType === "mouse" && ev.button !== 0) return;
    pointers.set(ev.pointerId, [ev.clientX, ev.clientY]);
    if (pointers.size === 1) moved = false;
    begin();
  });
  svg.addEventListener("pointermove", ev => {
    if (!pointers.has(ev.pointerId) || !gesture) return;
    pointers.set(ev.pointerId, [ev.clientX, ev.clientY]);
    if (gesture.kind === "pinch" && pointers.size >= 2) {
      const [a, b] = [...pointers.values()];
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      z.k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN,
        gesture.k0 * Math.hypot(a[0] - b[0], a[1] - b[1]) / gesture.d0));
      // put the anchor back under the fingers' midpoint (s: px per unit)
      const { r, fit } = fitScale(), sc = fit * z.k;
      z.x = gesture.anchor[0] - (mid[0] - r.left - (r.width - VBW * fit) / 2) / sc;
      z.y = gesture.anchor[1] - (mid[1] - r.top - (r.height - VBH * fit) / 2) / sc;
      moved = true;
      clamp(); apply();
    } else if (gesture.kind === "pan" && z.k > 1.001) {
      const pt = [ev.clientX, ev.clientY];
      if (!moved && Math.hypot(pt[0] - gesture.start[0], pt[1] - gesture.start[1]) < 5) return;
      if (!moved) {
        moved = true; svg.classList.add("panning");
        // only now: capturing at pointerdown would retarget the click itself
        try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
      }
      const sc = fitScale().fit * z.k;
      z.x -= (pt[0] - gesture.last[0]) / sc;
      z.y -= (pt[1] - gesture.last[1]) / sc;
      gesture.last = pt;
      clamp(); apply();
    }
  });
  const end = ev => {
    if (!pointers.delete(ev.pointerId)) return;
    svg.classList.remove("panning");
    begin();                         // a pinch left with one finger goes on as a pan
    if (gesture && gesture.kind === "pan") gesture.start = gesture.last;
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  // a drag that moved the picture is not a click on whatever it ended over
  svg.addEventListener("click", ev => {
    if (moved) { ev.stopImmediatePropagation(); ev.preventDefault(); moved = false; }
  }, true);

  if (ui.in) ui.in.onclick = () => zoomBy(1.5);
  if (ui.out) ui.out.onclick = () => zoomBy(1 / 1.5);
  if (ui.fit) ui.fit.onclick = () => reset();
  const ctl = { viewBox, apply, reset, zoomBy, get k() { return z.k; } };
  svg._zoom = ctl;
  apply();
  return ctl;
}

// The level / − / + / Fit controls, as in the curve panel's header.
function zoomControls() {
  const box = document.createElement("span");
  box.className = "zoom-tools";
  box.title = "Zoom: mouse wheel or pinch; drag to move around";
  const level = document.createElement("span");
  level.className = "zoom-level";
  const mk = (text, cls, label) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "small " + cls; b.textContent = text;
    if (label) b.setAttribute("aria-label", label);
    return b;
  };
  const out = mk("−", "zoom-step", "Zoom out"), inn = mk("+", "zoom-step", "Zoom in");
  const fit = mk("Fit", "", null);
  fit.title = "Show the whole curve";
  box.append(level, out, inn, fit);
  return { box, ui: { level, out, in: inn, fit } };
}

// client (screen) point -> viewBox point, under the current zoom
function svgPoint(svg, cx, cy) {
  const pt = svg.createSVGPoint();
  pt.x = cx; pt.y = cy;
  const q = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [q.x, q.y];
}

let curveZoom = null;
function wireZoom() {
  const $ = id => document.getElementById(id);
  curveZoom = makeZoomable($("curve-svg"),
    { level: $("zoom-level"), out: $("zoom-out"), in: $("zoom-in"), fit: $("zoom-fit") });
}

// ---------------------------------------------------------------------------
// painting colors straight onto the curve
//
// Pick a color, then click edges, ends or markings on the figure to give them
// that color -- once, or until Cancel. The bar above the figure (with Cancel)
// shows for either choice, so a change of mind is always one click away.
// While painting, markings are drawn larger and ringed to make them easy to
// hit, and hovering previews the new color. Each click is an ordinary color
// edit: saved, and propagated to derived types like any other.
// ---------------------------------------------------------------------------
let painting = null;              // { color, sticky } while active

function openPaintDialog() {
  const s0 = loadSettings();
  let color = isHex6(s0.paintColor) ? s0.paintColor : "#e53935";
  const body = dialogHead("Paint edges and markings",
    "Choose a color, then click edges, ends or markings on the curve to give " +
    "them that color.");
  const field = colorField(color, h => { color = h; }, { live: true });
  body.appendChild(labeled("Color", field));
  const keep = document.createElement("label");
  keep.className = "check";
  keep.innerHTML = `<input type="checkbox" id="paint-sticky"> Keep painting until I press Cancel`;
  body.appendChild(keep);
  const box = keep.querySelector("input");
  box.checked = !!(painting ? painting.sticky : s0.paintSticky);
  const note = document.createElement("p");
  note.className = "muted"; note.style.margin = "4px 0 10px";
  const sync = () => {
    note.textContent = box.checked
      ? "Every edge or marking you click takes the color, until you press Cancel."
      : "The next edge or marking you click takes the color; then painting stops. " +
        "Cancel is there too if you change your mind.";
  };
  box.onchange = sync; sync();
  body.appendChild(note);
  const go = document.createElement("button");
  go.className = "primary";
  go.textContent = painting ? "Use this color" : "Start painting";
  go.onclick = () => {
    const s2 = loadSettings(); s2.paintColor = color; s2.paintSticky = box.checked; saveSettings(s2);
    closeModal();
    startPainting(color, box.checked);
  };
  body.appendChild(row([go]));
  openModal();
}

function startPainting(color, sticky) {
  painting = { color: color, sticky: sticky };
  showPaintBar();
  if (selectedId) renderSelected();
}

function stopPainting() {
  painting = null;
  showPaintBar();
  if (selectedId) renderSelected();
}

function showPaintBar() {
  const bar = document.getElementById("paint-bar");
  const view = document.getElementById("curve-svg").closest(".view");
  if (!bar) return;
  bar.hidden = !painting;
  if (view) view.classList.toggle("painting", !!painting);
  if (!painting) return;
  document.getElementById("paint-chip").style.background = painting.color;
  document.getElementById("paint-hint").textContent = painting.sticky
    ? "Painting: click edges and markings to color them."
    : "Painting: click an edge or marking to color it.";
}

// hover previews the color; a click (or tap) applies it
function wirePainting(drawn) {
  const targets = [...drawn.edgePicks, ...drawn.markPicks];
  targets.forEach(t => {
    const el = t.kind === "edge" ? t.line : t.disc;
    const attr = t.kind === "edge" ? "stroke" : "fill";
    const orig = { col: el.getAttribute(attr), w: el.getAttribute("stroke-width") };
    t.hit.addEventListener("pick-enter", ev => {
      if (ev.detail.pointerType !== "mouse" || !painting) return;
      el.setAttribute(attr, painting.color);
      if (t.kind === "edge") el.setAttribute("stroke-width", +orig.w + 2);
    });
    t.hit.addEventListener("pick-leave", () => {
      el.setAttribute(attr, orig.col);
      if (t.kind === "edge") el.setAttribute("stroke-width", orig.w);
    });
    t.hit.addEventListener("pick-click", () => {
      if (!painting) return;
      try { api("set_color", selectedId, t.id, painting.color); }
      catch (e) { alert(e.message); return; }
      autosave();
      if (!painting.sticky) stopPainting();       // redraws, without targets
      else renderSelected();
    });
  });
}

document.addEventListener("keydown", ev => {
  if (ev.key === "Escape" && painting && document.getElementById("modal").hidden) stopPainting();
});

function renderSelected() {
  const data = api("render", selectedId);
  document.getElementById("curve-name").textContent = data.name;
  const st = document.getElementById("curve-status");
  st.textContent = ""; st.className = "status";
  if (data.status !== "ok") {
    st.className = "status warn";
    st.textContent = "⚠ needs attention — this type could not be rebuilt from its parent. ";
    const again = document.createElement("button");
    again.className = "small";
    again.textContent = "Try again";
    again.title = "Re-derive this type from its parent as it is now";
    again.onclick = () => {
      try { api("retry", selectedId); refreshAll(); autosave(); }
      catch (e) { st.append(" (" + e.message + ")"); }
    };
    st.appendChild(again);
  }
  if (painting) {
    const drawn = drawCurve(data, { pickEdge: () => true, pickMarking: () => true });
    wirePainting(drawn);
  } else {
    drawCurve(data);
  }
  drawSubdivision(data);
  renderControls();
}

// ---------------------------------------------------------------------------
// SVG helpers
// ---------------------------------------------------------------------------
const SVGNS = "http://www.w3.org/2000/svg";
const VBW = 600, VBH = 400, PAD = 30;
// radius of a marking in the interior of an edge; bigger vertices scale from it
const MARK_UNIT_R = 5;

function fitTransform(points) {
  if (!points.length) return p => [VBW / 2, VBH / 2];
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const minx = Math.min(...xs), maxx = Math.max(...xs);
  const miny = Math.min(...ys), maxy = Math.max(...ys);
  const spanx = Math.max(maxx - minx, 1e-9), spany = Math.max(maxy - miny, 1e-9);
  const s = Math.min((VBW - 2 * PAD) / spanx, (VBH - 2 * PAD) / spany);
  const ox = (VBW - s * spanx) / 2, oy = (VBH - s * spany) / 2;
  const T = ([x, y]) => [ox + (x - minx) * s, VBH - (oy + (y - miny) * s)]; // flip y
  // expose the mapping so callers can invert it (e.g. to find which lattice
  // coordinates are actually on screen)
  T.params = { s, minx, miny, ox, oy };
  return T;
}

// Draw the integer lattice as graph paper behind a subdivision: faint grid
// lines with a dot at each lattice point. Covers the whole viewBox (not just
// the polygon's bounding box) so the panel reads as a lattice, and makes edge
// lattice lengths and interior lattice points easy to judge.
function drawLattice(svg, T) {
  const p = T.params;
  if (!p || !isFinite(p.s) || p.s <= 0) return;
  // invert the transform at the viewBox corners
  const xLo = p.minx + (0 - p.ox) / p.s;
  const xHi = p.minx + (VBW - p.ox) / p.s;
  const yLo = p.miny + (0 - p.oy) / p.s;
  const yHi = p.miny + (VBH - p.oy) / p.s;
  const x0 = Math.ceil(xLo), x1 = Math.floor(xHi);
  const y0 = Math.ceil(yLo), y1 = Math.floor(yHi);
  // a very dense lattice is unreadable (and slow), so skip it instead
  const MAX_LINES = 80;
  if (x1 - x0 > MAX_LINES || y1 - y0 > MAX_LINES) return;

  const g = svgEl("g", { "class": "lattice" });
  for (let x = x0; x <= x1; x++) {
    const a = T([x, yLo]), b = T([x, yHi]);
    g.appendChild(svgEl("line", {
      x1: a[0], y1: a[1], x2: b[0], y2: b[1],
      stroke: "var(--line)", "stroke-width": 1,
    }));
  }
  for (let y = y0; y <= y1; y++) {
    const a = T([xLo, y]), b = T([xHi, y]);
    g.appendChild(svgEl("line", {
      x1: a[0], y1: a[1], x2: b[0], y2: b[1],
      stroke: "var(--line)", "stroke-width": 1,
    }));
  }
  for (let x = x0; x <= x1; x++) {
    for (let y = y0; y <= y1; y++) {
      const q = T([x, y]);
      g.appendChild(svgEl("circle", {
        cx: q[0], cy: q[1], r: 1.4, fill: "var(--muted)", opacity: 0.55,
      }));
    }
  }
  svg.appendChild(g);
}

function svgEl(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}
function clearSvg(id) {
  const svg = document.getElementById(id);
  svg.setAttribute("viewBox", svg._zoom ? svg._zoom.viewBox() : `0 0 ${VBW} ${VBH}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  return svg;
}

// opts.svgId draws somewhere other than the main panel. Pick mode, for the
// dialogs that ask "which one?": opts.pickEdge(edge) / opts.pickVertex(vertex)
// give those generous click targets (returned with what they belong to), and
// opts.dim fades the rest of the edges and markings. Vertices are not drawn
// normally, so a pickable one gets a small ring to show it is there.
function drawCurve(data, opts = {}) {
  const svg = clearSvg(opts.svgId || "curve-svg");
  const pickEdge = opts.pickEdge || null, pickVertex = opts.pickVertex || null;
  const pickMarking = opts.pickMarking || null;
  const markPicks = [];
  const dim = !!opts.dim;
  const withLabels = opts.labels !== false;   // off for thumbnails too small to read
  const edgePicks = [], vertexPicks = [], lines = {};
  const c = data.curve;
  const pts = [];
  c.edges.forEach(e => { pts.push(e.from); pts.push(e.to); });
  c.vertices.forEach(v => pts.push([v.x, v.y]));
  const T = fitTransform(pts);
  const settings = loadSettings();

  // The picture is drawn first and the labels last, against everything already
  // in it: a label sitting on an edge or on another label reads as part of the
  // drawing rather than as a name for it.
  const segments = [];   // drawn edges, as obstacles
  const discs = [];      // drawn markings, as obstacles
  const wanted = [];     // labels still to place
  const hits = [];       // invisible, generous targets for revealing hidden labels
  const showEdges = showEdgeLabels(settings), showMarks = showMarkingLabels(settings);

  c.edges.forEach(e => {
    const a = T(e.from), b = T(e.to);
    const col = renderColor(e.color);
    const width = e.kind === "bounded" ? 3 : 2;
    const line = svgEl("line", {
      x1: a[0], y1: a[1], x2: b[0], y2: b[1],
      stroke: col, "stroke-width": width,
    });
    svg.appendChild(line);
    lines[e.id] = line;
    if (pickEdge && pickEdge(e)) edgePicks.push({ kind: "edge", id: e.id, edge: e, line: line, a: a, b: b });
    else if (dim) line.setAttribute("opacity", "0.3");
    segments.push({ a: a, b: b, half: width / 2 });
    const lbl = e.name + (e.weight > 1 ? " (w" + e.weight + ")" : "");
    if (lbl && withLabels) {
      wanted.push({ text: lbl, color: col, kind: "edge", a: a, b: b,
                    key: "e:" + e.id, hidden: !showEdges });
      if (!showEdges) {
        hits.push(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1],
                                  ...HIT_ATTRS, "data-key": "e:" + e.id }));
      }
    }
  });
  // Vertices are not drawn: where edges meet already shows them, and a dot at
  // every one competes with the markings, which are the points that carry
  // meaning. A marking sits exactly on its image, and its radius counts the
  // valence of the vertex it hangs from, less the two directions any point on
  // an edge already has -- so a marking in the interior of an edge (internally
  // a trivalent vertex) is one unit, one at a trivalent vertex is two, and so on.
  c.markings.forEach(m => {
    const p = T(m.at);
    const col = renderColor(m.color);
    const r = MARK_UNIT_R * Math.max(1, (m.valence || 3) - 2);
    const picked = pickMarking && pickMarking(m);
    // a pickable marking is drawn larger and ringed, so it is easy to see and hit
    const rr = picked ? r + 3 : r;
    if (picked) {
      svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: rr + 5, fill: "none",
                                        stroke: "var(--accent)", "stroke-width": 1.5,
                                        "stroke-dasharray": "3 3" }));
    }
    const disc = svgEl("circle", {
      cx: p[0], cy: p[1], r: rr, fill: col,
      stroke: "var(--panel)", "stroke-width": 1.5,
      ...(dim && !picked ? { opacity: "0.3" } : {}),
    });
    svg.appendChild(disc);
    if (picked) markPicks.push({ kind: "mark", id: m.id, marking: m, disc: disc, p: p, r: rr });
    discs.push({ p: p, r: picked ? rr + 5 : r });
    if (m.name && withLabels) {
      wanted.push({ text: m.name, color: col, kind: "mark", p: p, r: r,
                    key: "m:" + m.id, hidden: !showMarks });
      if (!showMarks) {
        hits.push(svgEl("circle", { cx: p[0], cy: p[1], r: r + 8,
                                    ...HIT_ATTRS, "data-key": "m:" + m.id }));
      }
    }
  });

  // Hidden labels are still placed -- after the shown ones, so those keep the
  // best spots -- and against everything, so revealing one never lands it on
  // anything else, even with several revealed at once on a touch screen.
  wanted.sort((x, y) => (x.hidden ? 1 : 0) - (y.hidden ? 1 : 0));
  // Edge targets under marking targets: a marking sits on edges and should win.
  hits.sort((x, y) => (x.tagName === "circle") - (y.tagName === "circle"));
  hits.forEach(h => svg.appendChild(h));
  if (pickVertex) {
    c.vertices.filter(v => pickVertex(v)).forEach(v => {
      const p = T([v.x, v.y]);
      const ring = svgEl("circle", { cx: p[0], cy: p[1], r: 6, fill: "var(--panel)",
                                     stroke: "var(--muted)", "stroke-width": 2 });
      svg.appendChild(ring);
      vertexPicks.push({ kind: "vertex", id: v.id, vertex: v, ring: ring, p: p });
      discs.push({ p: p, r: 6 });      // labels keep clear of the ring too
    });
  }
  // pick targets go on top of everything; vertices over edges, since a vertex
  // sits where edges meet and should win there
  edgePicks.forEach(pk => {
    pk.hit = svgEl("line", { x1: pk.a[0], y1: pk.a[1], x2: pk.b[0], y2: pk.b[1],
                             ...HIT_ATTRS, "stroke-width": 20, class: "pick-hit",
                             "data-pick": pk.id });
    svg.appendChild(pk.hit);
  });
  vertexPicks.forEach(pk => {
    pk.hit = svgEl("circle", { cx: pk.p[0], cy: pk.p[1], r: 14, ...HIT_ATTRS,
                               class: "pick-hit", "data-pick-vertex": pk.id });
    svg.appendChild(pk.hit);
  });
  markPicks.forEach(pk => {       // over edges: a marking sits on them
    pk.hit = svgEl("circle", { cx: pk.p[0], cy: pk.p[1], r: pk.r + 9, ...HIT_ATTRS,
                               class: "pick-hit", "data-pick-mark": pk.id });
    svg.appendChild(pk.hit);
  });
  routePicks(svg, [...edgePicks, ...vertexPicks, ...markPicks]);
  placeLabels(svg, wanted, segments, discs);
  return { svg: svg, edgePicks: edgePicks, vertexPicks: vertexPicks, markPicks: markPicks,
           lines: lines };
}

// Pick targets overlap -- a short edge lies inside its neighbours' wide hit
// strips -- so whichever was drawn last would win wherever they do. Instead the
// pointer goes to the nearest target among those under it, and each target's
// hit element receives "pick-enter", "pick-leave" and "pick-click" events
// (detail.pointerType) in place of the native ones. A marking beats the edge
// it sits on, and a vertex the edges meeting there, until the pointer is
// clearly off it.
function routePicks(svg, picks) {
  if (!picks.length) return;
  const byHit = new Map(picks.map(pk => [pk.hit, pk]));
  const score = (pk, x, y) => {
    if (pk.kind === "edge") return segmentDistance([x, y], pk.a, pk.b);
    const d = Math.hypot(x - pk.p[0], y - pk.p[1]);
    return pk.kind === "mark" ? d - pk.r - 6 : d - 8;
  };
  const at = ev => {
    const under = document.elementsFromPoint(ev.clientX, ev.clientY)
      .map(el => byHit.get(el)).filter(Boolean);
    if (under.length < 2) return under[0] || null;
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const q = pt.matrixTransform(svg.getScreenCTM().inverse());
    return under.reduce((best, pk) => score(pk, q.x, q.y) < score(best, q.x, q.y) ? pk : best);
  };
  const fire = (pk, type, ev) => pk.hit.dispatchEvent(
    new CustomEvent(type, { detail: { pointerType: ev.pointerType || "mouse" } }));
  let current = null;
  const moveTo = (pk, ev) => {
    if (pk === current) return;
    if (current) fire(current, "pick-leave", ev);
    current = pk;
    if (pk) fire(pk, "pick-enter", ev);
  };
  svg.addEventListener("pointermove", ev => moveTo(at(ev), ev));
  svg.addEventListener("pointerleave", ev => moveTo(null, ev));
  svg.addEventListener("click", ev => {
    const pk = at(ev);
    if (!pk) return;
    ev.stopImmediatePropagation();          // not a tap on empty space
    fire(pk, "pick-click", ev);
  });
}

function segmentDistance(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}

// Draw a curve that does not exist yet -- what an operation would produce --
// with the edge it adds picked out in the accent colour.
function drawPreview(svgId, preview, opts = {}) {
  const drawn = drawCurve({ curve: preview.curve }, { svgId: svgId, labels: opts.labels });
  const ln = drawn.lines[preview.new_edge];
  if (ln) {
    ln.setAttribute("stroke", "var(--accent)");
    ln.setAttribute("stroke-width", +ln.getAttribute("stroke-width") + 2);
  }
  return drawn;
}

// A picture in a dialog whose edges and/or vertices can be pointed at. With a
// mouse, hover highlights and names the target and a click acts on it; touch
// has no hover, so a tap selects and a second tap on the same target acts (or
// the dialog's button does). With clickCommits false, picking is only a first
// step -- the dialog then shows what to do with the target -- so a click, of
// any kind, just selects.
function mountPicker(data, svgId, o) {
  const drawn = drawCurve(data, { svgId: svgId, pickEdge: o.pickEdge,
                                  pickVertex: o.pickVertex, dim: o.dim });
  const targets = [...drawn.edgePicks, ...drawn.vertexPicks];
  const clickCommits = o.clickCommits !== false;
  let hovered = null, selected = null, lastPointer = "mouse";
  const labelOf = t => t.kind === "edge"
    ? drawn.svg.querySelector(`text[data-label-key="e:${CSS.escape(t.id)}"]`) : null;
  targets.forEach(t => {
    if (t.line) t.orig = { stroke: t.line.getAttribute("stroke"), w: t.line.getAttribute("stroke-width") };
  });
  const paint = () => {
    targets.forEach(t => {
      const on = t === hovered || t === selected;
      if (t.kind === "edge") {
        t.line.setAttribute("stroke", on ? "var(--accent)" : t.orig.stroke);
        t.line.setAttribute("stroke-width", on ? +t.orig.w + 3 : t.orig.w);
        const lab = labelOf(t);
        if (lab && lab.hasAttribute("data-label-hidden")) lab.setAttribute("visibility", on ? "visible" : "hidden");
      } else {
        t.ring.setAttribute("r", on ? 8 : 6);
        t.ring.setAttribute("fill", on ? "var(--accent)" : "var(--panel)");
        t.ring.setAttribute("stroke", on ? "var(--accent)" : "var(--muted)");
      }
    });
    const shown = selected || hovered;
    if (o.status) o.status.textContent = shown ? o.describe(shown) : (o.idle || "");
    if (o.button) {
      o.button.disabled = !selected;
      o.button.textContent = selected ? o.buttonText(selected) : o.buttonIdle;
    }
  };
  const select = t => {
    selected = t; paint();
    if (o.onSelect) o.onSelect(t);
  };
  drawn.svg.addEventListener("pointerdown", ev => { lastPointer = ev.pointerType || "mouse"; });
  targets.forEach(t => {
    t.hit.addEventListener("pick-enter", ev => {
      if (ev.detail.pointerType === "mouse") { hovered = t; paint(); }
    });
    t.hit.addEventListener("pick-leave", ev => {
      if (ev.detail.pointerType === "mouse" && hovered === t) { hovered = null; paint(); }
    });
    t.hit.addEventListener("pick-click", () => {
      if (clickCommits && (lastPointer === "mouse" || selected === t)) { o.commit(t); return; }
      select(t);
    });
  });
  drawn.svg.addEventListener("click", () => {      // a tap on empty space
    if (clickCommits && lastPointer !== "mouse" && selected) select(null);
  });
  if (o.button) o.button.onclick = () => { if (selected) o.commit(selected); };
  paint();
  return {
    drawn: drawn,
    select: id => select(targets.find(t => t.id === id) || null),
    selected: () => selected,
  };
}

// The picture-or-list frame the pick dialogs share: a toggle, the picture view
// (a hint, the drawing, a status line, an optional button) and the list view.
function pickFrame(body, hintText, withButton) {
  const card = document.querySelector("#modal .modal-card");
  if (card) card.classList.add("wide");
  const pickView = document.createElement("div");
  const hint = document.createElement("p");
  hint.className = "muted"; hint.style.margin = "4px 0 6px";
  hint.textContent = hintText;
  const holder = document.createElementNS(SVGNS, "svg");
  holder.id = "pick-svg";
  holder.setAttribute("preserveAspectRatio", "xMidYMid meet");
  const status = document.createElement("div");
  status.className = "pick-status";
  // the hint, with the zoom controls beside it
  const zc = zoomControls();
  const head = document.createElement("div");
  head.className = "pick-head";
  head.append(hint, zc.box);
  pickView.append(head, holder, status);
  makeZoomable(holder, zc.ui);
  let button = null;
  if (withButton) {
    button = document.createElement("button");
    button.className = "primary";
    pickView.appendChild(row([button]));
  }
  const listView = document.createElement("div");
  const toggle = document.createElement("button");
  toggle.className = "small ghost";
  let onSwitch = null;
  const setView = picture => {
    pickView.hidden = !picture; listView.hidden = picture;
    toggle.textContent = picture ? "Choose from a list instead" : "Pick on the curve instead";
    if (onSwitch) onSwitch(picture);
  };
  toggle.onclick = () => setView(pickView.hidden);
  body.append(toggle, pickView, listView);
  setView(true);
  return { pickView, listView, status, button, onSwitch: f => { onSwitch = f; } };
}

// Transparent as attributes, not via the stylesheet: a PNG copy serializes the
// SVG without the stylesheet, and an unstyled circle is filled black.
const HIT_ATTRS = { class: "label-hit", stroke: "transparent", fill: "transparent",
                    "stroke-width": 16, "pointer-events": "all" };

// A hidden label shows while the mouse is over its edge or marking, and a tap
// toggles it on a touch screen, where there is no hover; tapping empty space
// hides whatever was revealed. Visibility is an attribute rather than a CSS
// class so that copying the picture as PNG -- which serializes the SVG away
// from the stylesheet -- leaves hidden labels hidden.
function wireLabelReveal(svg) {
  if (svg.dataset.revealWired) return;
  svg.dataset.revealWired = "1";
  let lastPointer = "mouse";
  const labelFor = t => {
    const key = t && t.getAttribute && t.getAttribute("data-key");
    return key ? svg.querySelector(`text[data-label-key="${CSS.escape(key)}"]`) : null;
  };
  const show = (el, on) => { if (el) el.setAttribute("visibility", on ? "visible" : "hidden"); };
  svg.addEventListener("pointerdown", ev => { lastPointer = ev.pointerType || "mouse"; });
  svg.addEventListener("pointerover", ev => {
    if (ev.pointerType === "mouse") show(labelFor(ev.target), true);
  });
  svg.addEventListener("pointerout", ev => {
    if (ev.pointerType === "mouse") show(labelFor(ev.target), false);
  });
  svg.addEventListener("click", ev => {
    if (lastPointer === "mouse") return;
    const el = labelFor(ev.target);
    if (el) {
      show(el, el.getAttribute("visibility") !== "visible");
    } else {
      svg.querySelectorAll("text[data-label-hidden]").forEach(t => show(t, false));
    }
  });
}

// ---------------------------------------------------------------------------
// label placement
//
// Each label is tried at a series of spots near what it names, nearest first,
// and takes the first that hits nothing: no edge, no marking, no label already
// placed, and nothing over the panel's edge. A crowded picture can leave no
// such spot, and then the least-bad one is used -- a label pushed somewhere
// arbitrary would be worse than one slightly crowded.
// ---------------------------------------------------------------------------
const LBL_PAD = 2;      // breathing room around a label's box
const LBL_EDGE = 3;     // keep labels off the very edge of the panel

function placeLabels(svg, wanted, segments, discs) {
  const placed = [];
  wireLabelReveal(svg);
  wanted.forEach(req => {
    const el = text(0, 0, req.text, req.color);
    el.setAttribute("dominant-baseline", "middle");
    el.setAttribute("pointer-events", "none");
    if (req.key) el.setAttribute("data-label-key", req.key);
    svg.appendChild(el);
    const box = measureLabel(el, req.text);
    const candidates = req.kind === "edge"
      ? edgeLabelSpots(req, box)
      : markLabelSpots(req, box);

    let best = null, bestScore = Infinity;
    for (let i = 0; i < candidates.length; i++) {
      const rect = labelRect(candidates[i], box);
      const score = labelPenalty(rect, segments, discs, placed);
      if (score < bestScore) { bestScore = score; best = { at: candidates[i], rect: rect }; }
      if (score === 0) break;
    }
    el.setAttribute("x", best.at[0]);
    el.setAttribute("y", best.at[1]);
    if (req.hidden) {
      el.setAttribute("visibility", "hidden");
      el.setAttribute("data-label-hidden", "1");
    }
    placed.push(best.rect);
  });
}

function labelRect(at, box) {
  return {
    x: at[0] - box.w / 2 - LBL_PAD, y: at[1] - box.h / 2 - LBL_PAD,
    w: box.w + 2 * LBL_PAD, h: box.h + 2 * LBL_PAD,
  };
}

// getBBox needs the element in a rendered document; fall back to an estimate
// when it is not (a hidden panel, a detached clone).
function measureLabel(el, s) {
  try {
    const b = el.getBBox();
    if (b.width > 0 && b.height > 0) return { w: b.width, h: b.height };
  } catch (e) { /* not rendered */ }
  return { w: 0.58 * 13 * s.length, h: 13 };
}

function labelPenalty(rect, segments, discs, placed) {
  let n = 0;
  if (!insideCanvas(rect)) n++;
  for (const s of segments) if (rectHitsSegment(rect, s)) n++;
  for (const d of discs) if (rectHitsDisc(rect, d)) n++;
  for (const p of placed) if (rectsOverlap(rect, p)) n++;
  return n;
}

// Spots along an edge, close in and near the middle first, on both sides.
function edgeLabelSpots(req, box) {
  const ax = req.a[0], ay = req.a[1];
  const dx = req.b[0] - ax, dy = req.b[1] - ay;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;      // unit normal
  const out = [];
  for (const gap of [5, 13, 22, 32]) {
    const off = box.h / 2 + gap;
    for (const t of [0.5, 0.38, 0.62, 0.26, 0.74, 0.14, 0.86]) {
      for (const side of [1, -1]) {
        out.push([ax + dx * t + nx * off * side, ay + dy * t + ny * off * side]);
      }
    }
  }
  return out;
}

// Spots around a marking's disc, closest ring first.
function markLabelSpots(req, box) {
  const dirs = [[1, 0], [1, -1], [0, -1], [-1, -1], [-1, 0], [-1, 1], [0, 1], [1, 1]];
  const out = [];
  for (const gap of [6, 14, 24, 36]) {
    for (const d of dirs) {
      const n = Math.hypot(d[0], d[1]) || 1;
      const ux = d[0] / n, uy = d[1] / n;
      const reach = req.r + gap + (Math.abs(ux) * box.w + Math.abs(uy) * box.h) / 2;
      out.push([req.p[0] + ux * reach, req.p[1] + uy * reach]);
    }
  }
  return out;
}

function insideCanvas(r) {
  return r.x >= LBL_EDGE && r.y >= LBL_EDGE &&
         r.x + r.w <= VBW - LBL_EDGE && r.y + r.h <= VBH - LBL_EDGE;
}
function rectsOverlap(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}
function rectHitsDisc(r, d) {
  const nx = Math.max(r.x, Math.min(d.p[0], r.x + r.w));
  const ny = Math.max(r.y, Math.min(d.p[1], r.y + r.h));
  const dx = d.p[0] - nx, dy = d.p[1] - ny;
  return dx * dx + dy * dy < (d.r + 1) * (d.r + 1);
}
function rectHitsSegment(r, seg) {
  const pad = seg.half + 1;   // the stroke has width, so grow the box by it
  const R = { x: r.x - pad, y: r.y - pad, w: r.w + 2 * pad, h: r.h + 2 * pad };
  const x2 = R.x + R.w, y2 = R.y + R.h;
  if (pointInRect(seg.a, R) || pointInRect(seg.b, R)) return true;
  return segsCross(seg.a, seg.b, [R.x, R.y], [x2, R.y]) ||
         segsCross(seg.a, seg.b, [x2, R.y], [x2, y2]) ||
         segsCross(seg.a, seg.b, [x2, y2], [R.x, y2]) ||
         segsCross(seg.a, seg.b, [R.x, y2], [R.x, R.y]);
}
function pointInRect(p, r) {
  return p[0] >= r.x && p[0] <= r.x + r.w && p[1] >= r.y && p[1] <= r.y + r.h;
}
function segsCross(p1, p2, q1, q2) {
  const side = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const d1 = side(q1, q2, p1), d2 = side(q1, q2, p2);
  const d3 = side(p1, p2, q1), d4 = side(p1, p2, q2);
  return ((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0));
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
  drawLattice(svg, T); // behind the cells
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

  const parts = {};
  parts.type = () => {
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
    const del = document.createElement("button");
    del.className = "small danger";
    del.textContent = "Delete…";
    del.title = "Remove this type; anything derived from it moves up to its parent";
    del.onclick = () => openDeleteDialog();
    wrap.appendChild(row([dup, del]));
    return wrap;
  };

  parts.mult = () => {
    const wrap = document.createElement("div");
    wrap.className = "ctrl-group";
    const info = api("refined_multiplicity", selectedId);
    const line = document.createElement("div");
    if (info.defined) {
      line.className = "mult";
      line.textContent = info.text;
      wrap.appendChild(line);
      const how = document.createElement("p");
      how.className = "muted"; how.style.margin = "0"; how.style.fontSize = "12px";
      how.textContent = info.vertices.map(v => v.factor).join(" · ")
        + `  ·  at q = 1: ${info.at_q_1}`;
      wrap.appendChild(how);
    } else {
      line.className = "muted";
      line.textContent = "undefined — " + info.reason;
      wrap.appendChild(line);
    }
    return wrap;
  };

  // actions: each opens a dedicated dialog
  const ends = c.edges.filter(e => e.kind === "end");
  const bounded = c.edges.filter(e => e.kind === "bounded");
  const v4 = Object.entries(summ.valences).filter(([v, k]) => k >= 4).map(([v]) => v);
  parts.actions = () => {
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
         "this type has no vertex of valence 4 or more to resolve", openResolveDialog),
      mk("Evaluation matrix…", c.vertices.length >= 1,
         "this type has no vertices", openEvalDialog),
    ]));
    return g;
  };

  // markings
  parts.markings = () => {
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
  };

  // edges & ends: rename + color
  parts.edges = () => {
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
  };

  renderPanelParts(body, parts);
}

// ---------------------------------------------------------------------------
// the edit panel's layout
//
// Its parts fold open and shut from their headings, and the Layout dialog
// (from the panel's title line) sets their order and which are shown. All of
// it is how this browser looks at the panel, not part of the workspace, so it
// lives in the settings (panelLayout) and is never exported. A part that is
// hidden or folded is not built at all -- the refined multiplicity is not
// computed until it is opened.
// ---------------------------------------------------------------------------
const PANEL_PARTS = [
  { key: "type", title: "Type" },
  { key: "mult", title: "Refined multiplicity" },
  { key: "actions", title: "Actions" },
  { key: "markings", title: "Markings" },
  { key: "edges", title: "Edges & ends" },
];

function loadPanelLayout() {
  const saved = loadSettings().panelLayout || {};
  const known = PANEL_PARTS.map(p => p.key);
  // saved order first (dropping stale keys), then any part it does not know
  const order = (Array.isArray(saved.order) ? saved.order : []).filter(k => known.includes(k));
  known.forEach(k => { if (!order.includes(k)) order.push(k); });
  const list = v => (Array.isArray(v) ? v : []).filter(k => known.includes(k));
  return { order, hidden: list(saved.hidden), collapsed: list(saved.collapsed) };
}
function savePanelLayout(layout) {
  const s = loadSettings();
  s.panelLayout = layout;
  saveSettings(s);
}

function renderPanelParts(body, builders) {
  const layout = loadPanelLayout();
  const shown = layout.order.filter(k => !layout.hidden.includes(k));
  shown.forEach(key => {
    const part = PANEL_PARTS.find(p => p.key === key);
    const det = document.createElement("details");
    det.className = "panel-part";
    det.dataset.part = key;
    det.open = !layout.collapsed.includes(key);
    const sum = document.createElement("summary");
    const h = document.createElement("h3");
    h.textContent = part.title;
    sum.appendChild(h);
    det.appendChild(sum);
    const fill = () => { if (det.children.length === 1) det.appendChild(builders[key]()); };
    if (det.open) fill();
    det.addEventListener("toggle", () => {
      if (det.open) fill();
      const l = loadPanelLayout();
      l.collapsed = l.collapsed.filter(k => k !== key);
      if (!det.open) l.collapsed.push(key);
      savePanelLayout(l);
    });
    body.appendChild(det);
  });
  if (!shown.length) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "Every part of this panel is hidden; use Layout above to show some.";
    body.appendChild(p);
  }
}

function openPanelLayoutDialog() {
  const body = dialogHead("Edit panel layout",
    "Choose which parts the edit panel shows, and in what order. This is saved in this browser.");
  const list = document.createElement("div");
  list.className = "layout-list";
  const apply = layout => {
    savePanelLayout(layout);
    if (selectedId) renderControls();
    draw();
  };
  const draw = () => {
    const layout = loadPanelLayout();
    list.innerHTML = "";
    layout.order.forEach((key, i) => {
      const part = PANEL_PARTS.find(p => p.key === key);
      const r = document.createElement("div");
      r.className = "layout-row";
      r.dataset.part = key;
      const lab = document.createElement("label");
      lab.className = "check";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !layout.hidden.includes(key);
      cb.onchange = () => {
        const l = loadPanelLayout();
        l.hidden = l.hidden.filter(k => k !== key);
        if (!cb.checked) l.hidden.push(key);
        apply(l);
      };
      lab.append(cb, document.createTextNode(part.title));
      const move = (d, text, label) => {
        const b = document.createElement("button");
        b.type = "button"; b.className = "small"; b.textContent = text;
        b.setAttribute("aria-label", `Move ${part.title} ${label}`);
        b.title = `Move ${label}`;
        const j = i + d;
        if (j < 0 || j >= layout.order.length) b.disabled = true;
        b.onclick = () => {
          const l = loadPanelLayout();
          [l.order[i], l.order[j]] = [l.order[j], l.order[i]];
          apply(l);
          // keep the keyboard on the part that moved
          const again = list.querySelector(`.layout-row[data-part="${key}"] button[aria-label="${b.getAttribute("aria-label")}"]`);
          if (again && !again.disabled) again.focus();
        };
        return b;
      };
      const btns = document.createElement("span");
      btns.className = "row"; btns.style.gap = "4px";
      btns.append(move(-1, "↑", "up"), move(+1, "↓", "down"));
      r.append(lab, btns);
      list.appendChild(r);
    });
  };
  draw();
  const reset = document.createElement("button");
  reset.className = "small";
  reset.textContent = "Reset to default";
  reset.onclick = () => apply({ order: PANEL_PARTS.map(p => p.key), hidden: [], collapsed: [] });
  body.append(list, row([reset]));
  openModal();
}

// ---------------------------------------------------------------------------
// action dialogs
// ---------------------------------------------------------------------------
function fmtVec(v) { return v ? `(${v[0]}, ${v[1]})` : ""; }

// Vertices carry ids, but nothing in the picture shows them, so a dialog that
// asks the user to pick one names it by what does show: the edges, ends and
// markings that meet there, listed counterclockwise as they are drawn.
function vertexFlags(c, vid) {
  const flags = [];
  c.edges.forEach(e => {
    if (e.tail === vid) flags.push({ id: e.id, name: e.name, dir: [e.to[0] - e.from[0], e.to[1] - e.from[1]] });
    if (e.head === vid) flags.push({ id: e.id, name: e.name, dir: [e.from[0] - e.to[0], e.from[1] - e.to[1]] });
  });
  flags.sort((a, b) => Math.atan2(a.dir[1], a.dir[0]) - Math.atan2(b.dir[1], b.dir[0]));
  // markings have no direction of their own, so they come last
  return flags.concat(c.markings.filter(m => m.tail === vid)
                       .map(m => ({ id: m.id, name: m.name, dir: [0, 0] })));
}
function vertexLabel(c, vid) {
  const names = vertexFlags(c, vid).map(f => f.name);
  return names.length ? names.join(", ") : vid;
}

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

function clearViews() {
  document.getElementById("curve-name").textContent = "";
  const st = document.getElementById("curve-status");
  st.textContent = ""; st.className = "status";
  clearSvg("curve-svg");
  clearSvg("sub-svg");
  document.getElementById("sub-note").textContent = "";
  setSubDebug(null);
  document.getElementById("controls-body").innerHTML =
    `<p class="muted">No types yet — use “New” to create one.</p>`;
}

// Deleting is one type only: nothing else goes with it. Its derived types move
// up to its parent, carrying its derivation steps in front of their own, so
// each stays the same derivation expressed from one type further up; the
// children of a root become roots. There is no undo, so it asks first, and
// says where the derived types will end up rather than just warning.
// The refined multiplicity of every type at once, and the question the whole
// thing is for: can these curves be split into two halves that carry the same
// total? Multiplicities are exact (Laurent polynomials in q^(1/2), or a ratio
// of them), so "the same" here means equal on the nose, not numerically.
function openMultiplicityDialog() {
  const rows = api("refined_multiplicities", null);
  const body = dialogHead("Refined multiplicities",
    "Goettsche-Schroeter: the product of [&mu;(V)]<sub>q</sub><sup>&minus;</sup> " +
    "over the unmarked vertices and [&mu;(V)]<sub>q</sub><sup>+</sup> over the " +
    "marked ones, where &mu;(V) is the lattice area of the vertex's dual triangle. " +
    "It needs every vertex to be trivalent, or trivalent with one marking; a " +
    "marking in the interior of an edge is not a vertex of the curve, so it " +
    "does not count.");
  if (!rows.length) {
    body.insertAdjacentHTML("beforeend", `<p class="muted">No types yet.</p>`);
    openModal(); return;
  }

  // the types menu's order and nesting, with the same folding
  const rowById = {}; rows.forEach(r => rowById[r.id] = r);
  const tree = typeTreeOrder(api("list_nodes")).filter(t => rowById[t.node.id]);
  const list = document.createElement("div");
  list.className = "mult-tree";
  list.style.margin = "6px 0 10px";
  const boxes = [];
  const fold = foldableTypeTree(tree, (node, depth, lead) => {
    const r = rowById[node.id];
    const line = document.createElement("div");
    line.className = "mult-row";
    line.dataset.id = r.id;
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = r.id; cb.checked = false; cb.disabled = !r.defined;
    cb.id = "mult-cb-" + r.id;
    lead.appendChild(cb);
    const name = document.createElement("label");
    name.className = "tname"; name.htmlFor = cb.id; name.textContent = r.name;
    const val = document.createElement("span");
    val.className = r.defined ? "mult" : "muted";
    val.textContent = r.defined ? r.text : "undefined — " + r.reason;
    line.append(lead, name, val);
    list.appendChild(line);
    if (r.defined) boxes.push(cb);
    return { line: line, box: cb };
  });
  const refold = fold.refold;
  boxes.forEach(b => b.addEventListener("change", refold));
  body.appendChild(row([fold.foldAll]));
  body.appendChild(list);

  const all = document.createElement("button");
  all.className = "small";
  all.textContent = "Select all";
  all.onclick = () => { boxes.forEach(b => { b.checked = true; }); result.textContent = ""; refold(); };
  const none = document.createElement("button");
  none.className = "small";
  none.textContent = "Select none";
  none.onclick = () => { boxes.forEach(b => { b.checked = false; }); result.textContent = ""; refold(); };
  const go = document.createElement("button");
  go.textContent = "Check for a balanced split";
  const result = document.createElement("div");
  result.style.marginTop = "10px";
  // balance only the values at q = 1 (the Mikhalkin multiplicities)?
  const q1Label = document.createElement("label");
  q1Label.className = "check";
  const q1 = document.createElement("input");
  q1.type = "checkbox"; q1.id = "split-q1";
  q1.checked = !!loadSettings().splitAtQ1;
  q1.onchange = () => {
    const s = loadSettings(); s.splitAtQ1 = q1.checked; saveSettings(s);
    result.textContent = "";
  };
  q1Label.append(q1, document.createTextNode("Only the values at q = 1 have to balance"));

  go.onclick = () => {
    const picked = boxes.filter(b => b.checked).map(b => b.value);
    result.textContent = "";
    if (picked.length < 2) {
      result.className = "muted";
      result.textContent = "Pick at least two types to split.";
      return;
    }
    let out;
    try { out = api("balanced_split", picked, q1.checked); }
    catch (e) { showModalError(e.message); return; }
    if (!out.ok) {
      result.className = "muted";
      result.textContent = out.reason ||
        ("some of these have no multiplicity: " +
         out.undefined.map(u => u.name).join(", "));
      return;
    }
    const nameOf = id => (rows.find(r => r.id === id) || {}).name || id;
    const atOne = out.at_q_1 ? " at q = 1" : "";
    result.className = "";
    if (!out.found) {
      result.innerHTML = `<p class="muted" style="margin:0">No subset balances${atOne}.
        The total${atOne} is <span class="mult">${escapeHtml(out.total)}</span>, and no
        way of splitting these ${picked.length} types gives two halves with the
        same total.</p>`;
      return;
    }
    result.innerHTML = `<p style="margin:0 0 4px">Balanced${atOne}, each half totalling
      <span class="mult">${escapeHtml(out.value)}</span>:</p>
      <p class="muted" style="margin:0">{${out.subset.map(nameOf).map(escapeHtml).join(", ")}}
      &nbsp;|&nbsp; {${out.complement.map(nameOf).map(escapeHtml).join(", ")}}</p>`;
  };
  body.appendChild(q1Label);
  body.appendChild(row([go, all, none]));
  body.appendChild(result);
  body.appendChild(errBox());
  openModal();
}

// ---------------------------------------------------------------------------
// evaluation matrix
//
// The matrix of n linear evaluation functions on the type's cell, whose
// coordinates are the root vertex's position (x0, y0) and the lengths of the
// bounded edges (tropcurves/evaluation.py has the conventions). n is fixed at
// #bounded + 2, and the matrix can only be made with exactly that many. The
// choices made for a type are kept for this session, so reopening the dialog
// picks up where it was left.
// ---------------------------------------------------------------------------
const evalState = new Map();      // node id -> { root, fns }

const EVAL_FORMATS = {
  python: { label: "Python", fmt: m => "[" + m.map(r => "[" + r.join(", ") + "]").join(",\n ") + "]" },
  mathematica: { label: "Mathematica", fmt: m => "{" + m.map(r => "{" + r.join(", ") + "}").join(",\n ") + "}" },
  sage: { label: "Sage", fmt: m => "matrix(ZZ, [" + m.map(r => "[" + r.join(", ") + "]").join(",\n           ") + "])" },
  matlab: { label: "MATLAB / Octave", fmt: m => "[" + m.map(r => r.join(" ")).join(";\n ") + "]" },
  latex: { label: "LaTeX", fmt: m => "\\begin{pmatrix}\n" + m.map(r => "  " + r.join(" & ")).join(" \\\\\n") + "\n\\end{pmatrix}" },
  plain: { label: "Plain (tab-separated)", fmt: m => m.map(r => r.join("\t")).join("\n") },
};

function openEvalDialog() {
  const nodeId = selectedId;
  const setup = api("evaluation_setup", nodeId);
  const card = document.querySelector("#modal .modal-card");
  if (card) card.classList.add("wide");
  const body = dialogHead("Evaluation matrix",
    `The matrix of ${setup.n} evaluation functions on this type's cell (the number
     of bounded edges plus 2). Its coordinates are the position (x0, y0) of the
     root vertex and the length of every bounded edge; an edge of length ℓ and
     direction vector u, weight included, moves its head by ℓ·u from its tail. A
     cross ratio cr(p1, p2, p3, p4) is the signed length of the intersection of
     the path from p1 to p3 with the path from p2 to p4: + where they run the
     same way, − where they run opposite ways (markings count as contracted ends).`);

  const markingName = {}; setup.markings.forEach(m => markingName[m.id] = m.name);
  const legIds = new Set(setup.legs.map(l => l.id));
  const valid = f => f.kind === "cross_ratio"
    ? (f.points || []).length === 4 && f.points.every(p => legIds.has(p))
    : markingName[f.marking] !== undefined;
  const saved = evalState.get(nodeId);
  let root = saved && setup.roots.some(r => r.vertex === saved.root) ? saved.root
           : (setup.roots[0] ? setup.roots[0].vertex : null);
  let fns = (saved ? saved.fns : setup.default_functions)
    .filter(valid).map(f => JSON.parse(JSON.stringify(f)));
  const remember = () => evalState.set(nodeId, { root, fns: JSON.parse(JSON.stringify(fns)) });

  // root: markings first, then the other vertices, each alphabetically
  const rootSel = document.createElement("select");
  rootSel.id = "eval-root";
  const group = (label, items) => {
    if (!items.length) return;
    const og = document.createElement("optgroup"); og.label = label;
    items.forEach(r => og.appendChild(new Option(r.label, r.vertex)));
    rootSel.appendChild(og);
  };
  group("Markings", setup.roots.filter(r => r.kind === "marking"));
  group("Other vertices", setup.roots.filter(r => r.kind === "vertex"));
  if (root) rootSel.value = root;
  rootSel.onchange = () => { root = rootSel.value; remember(); stale(); };
  body.appendChild(labeled("Root vertex", rootSel));

  const head = document.createElement("h3");
  head.className = "eval-head";
  head.textContent = "Evaluation functions";
  const list = document.createElement("div");
  list.className = "eval-fns";
  const status = document.createElement("div");
  status.className = "status";
  const add = document.createElement("button");
  add.className = "small"; add.textContent = "+ Add function";
  const reset = document.createElement("button");
  reset.className = "small"; reset.textContent = "Reset to x, y of every marking";
  const go = document.createElement("button");
  go.className = "primary"; go.id = "eval-go";
  go.textContent = "Make the matrix";
  const result = document.createElement("div");
  result.className = "eval-result";

  const legSelect = (value, onchange) => {
    const s = document.createElement("select");
    const mk = setup.legs.filter(l => l.kind === "marking"), en = setup.legs.filter(l => l.kind === "end");
    [["Markings", mk], ["Ends", en]].forEach(([label, items]) => {
      if (!items.length) return;
      const og = document.createElement("optgroup"); og.label = label;
      items.forEach(l => og.appendChild(new Option(l.name, l.id)));
      s.appendChild(og);
    });
    s.value = value;
    s.onchange = () => onchange(s.value);
    return s;
  };
  const newFunction = () => {
    if (setup.legs.length >= 4) return { kind: "cross_ratio", points: setup.legs.slice(0, 4).map(l => l.id) };
    return setup.markings.length ? { kind: "x", marking: setup.markings[0].id } : null;
  };
  const problem = f => f.kind === "cross_ratio" && new Set(f.points).size !== 4
    ? "a cross ratio needs four different markings or ends" : null;

  const draw = () => {
    list.innerHTML = "";
    fns.forEach((f, i) => {
      const r = document.createElement("div");
      r.className = "eval-fn";
      const num = document.createElement("span");
      num.className = "muted eval-num"; num.textContent = (i + 1) + ".";
      const kind = document.createElement("select");
      kind.className = "eval-kind";
      [["x", "x of marking"], ["y", "y of marking"], ["cross_ratio", "cross ratio"]].forEach(([v, t]) => {
        const o = new Option(t, v);
        if (v !== "cross_ratio" && !setup.markings.length) o.disabled = true;
        if (v === "cross_ratio" && setup.legs.length < 4) o.disabled = true;
        kind.appendChild(o);
      });
      kind.value = f.kind;
      kind.onchange = () => {
        const k = kind.value;
        if (k === "cross_ratio") fns[i] = newFunction();
        else fns[i] = { kind: k, marking: f.marking || setup.markings[0].id };
        changed();
      };
      const args = document.createElement("span");
      args.className = "eval-args";
      if (f.kind === "cross_ratio") {
        args.append("(");
        f.points.forEach((p, j) => {
          if (j) args.append(", ");
          args.appendChild(legSelect(p, v => { f.points[j] = v; changed(); }));
        });
        args.append(")");
      } else {
        const s = document.createElement("select");
        setup.markings.forEach(m => s.appendChild(new Option(m.name, m.id)));
        s.value = f.marking;
        s.onchange = () => { f.marking = s.value; changed(); };
        args.appendChild(s);
      }
      const btn = (t, label, fn, disabled) => {
        const b = document.createElement("button");
        b.type = "button"; b.className = "small"; b.textContent = t;
        b.setAttribute("aria-label", label); b.title = label;
        b.disabled = !!disabled; b.onclick = fn;
        return b;
      };
      const tools = document.createElement("span");
      tools.className = "eval-tools";
      tools.append(
        btn("↑", "Move up", () => { [fns[i - 1], fns[i]] = [fns[i], fns[i - 1]]; changed(); }, i === 0),
        btn("↓", "Move down", () => { [fns[i + 1], fns[i]] = [fns[i], fns[i + 1]]; changed(); }, i === fns.length - 1),
        btn("✕", "Remove", () => { fns.splice(i, 1); changed(); }));
      r.append(num, kind, args, tools);
      const bad = problem(f);
      if (bad) {
        const w = document.createElement("span");
        w.className = "eval-bad"; w.textContent = bad;
        r.appendChild(w);
      }
      list.appendChild(r);
    });
    const k = fns.length, n = setup.n;
    const bad = fns.some(problem);
    status.className = "status" + (k === n && !bad ? "" : " warn");
    status.textContent = k === n
      ? (bad ? "Fix the functions marked above." : `${k} of ${n} functions — ready.`)
      : k < n ? `${k} of ${n} functions — add ${n - k} more.` : `${k} of ${n} functions — remove ${k - n}.`;
    go.disabled = !(k === n && !bad && root);
    add.disabled = !newFunction();
  };
  const stale = () => { result.innerHTML = ""; };
  const changed = () => { remember(); stale(); draw(); };
  add.onclick = () => { const f = newFunction(); if (f) { fns.push(f); changed(); } };
  reset.onclick = () => { fns = JSON.parse(JSON.stringify(setup.default_functions)); changed(); };
  go.onclick = () => {
    let out;
    try { out = api("evaluation_matrix", nodeId, root, fns); }
    catch (e) { showModalError(e.message); return; }
    showModalError("");
    renderEvalResult(result, out);
  };

  body.append(head, list, status, row([add, reset]), row([go]), result, errBox());
  draw();
  openModal();
}

function renderEvalResult(box, out) {
  box.innerHTML = "";
  const table = document.createElement("table");
  table.className = "eval-table";
  const thead = document.createElement("tr");
  thead.appendChild(document.createElement("th"));
  out.columns.forEach(c => { const th = document.createElement("th"); th.textContent = c; thead.appendChild(th); });
  table.appendChild(thead);
  out.matrix.forEach((r, i) => {
    const tr = document.createElement("tr");
    const th = document.createElement("th"); th.className = "eval-rowlabel"; th.textContent = out.rows[i];
    tr.appendChild(th);
    r.forEach(v => { const td = document.createElement("td"); td.textContent = fmtEntry(v); tr.appendChild(td); });
    table.appendChild(tr);
  });
  const wrap = document.createElement("div");
  wrap.className = "eval-table-wrap";
  wrap.appendChild(table);
  const det = document.createElement("p");
  det.className = "eval-det";
  det.innerHTML = out.det === 0
    ? `det = 0 &nbsp;<span class="muted">(singular: rank ${out.rank} of ${out.matrix.length})</span>`
    : `det = ${fmtEntry(out.det)} &nbsp;<span class="muted">(|det| = ${Math.abs(out.det)})</span>`;

  // text for code
  const s0 = loadSettings();
  const fmtSel = document.createElement("select");
  fmtSel.id = "eval-format";
  Object.entries(EVAL_FORMATS).forEach(([k, f]) => fmtSel.appendChild(new Option(f.label, k)));
  fmtSel.value = EVAL_FORMATS[s0.evalFormat] ? s0.evalFormat : "python";
  const text = document.createElement("textarea");
  text.className = "eval-text"; text.readOnly = true; text.spellcheck = false;
  const fill = () => {
    text.value = EVAL_FORMATS[fmtSel.value].fmt(out.matrix);
    text.rows = Math.min(14, out.matrix.length + (fmtSel.value === "latex" ? 2 : 0) + 1);
  };
  fmtSel.onchange = () => { const s = loadSettings(); s.evalFormat = fmtSel.value; saveSettings(s); fill(); };
  fill();
  const copyText = document.createElement("button");
  copyText.className = "small"; copyText.textContent = "Copy text";
  copyText.onclick = async () => {
    try { await navigator.clipboard.writeText(text.value); flashButton(copyText, "Copied ✓"); }
    catch (e) { text.select(); flashButton(copyText, "Press Ctrl/⌘+C"); }
  };

  // image for pasting (Notability and the like)
  const labels = document.createElement("label");
  labels.className = "check";
  const withLabels = document.createElement("input");
  withLabels.type = "checkbox"; withLabels.checked = s0.evalImageLabels !== false;
  withLabels.onchange = () => { const s = loadSettings(); s.evalImageLabels = withLabels.checked; saveSettings(s); };
  labels.append(withLabels, document.createTextNode("Row and column labels"));
  const copyImg = document.createElement("button");
  copyImg.className = "small"; copyImg.textContent = "Copy image";
  copyImg.id = "eval-copy-image";
  copyImg.onclick = () => copyBlobPng(matrixPngBlob(out, withLabels.checked), copyImg, "evaluation-matrix.png");
  const saveImg = document.createElement("button");
  saveImg.className = "small"; saveImg.textContent = "Download image";
  saveImg.onclick = async () => {
    try { downloadBlob(await matrixPngBlob(out, withLabels.checked), "evaluation-matrix.png"); }
    catch (e) { flashButton(saveImg, "Failed"); }
  };

  const textHead = document.createElement("h3"); textHead.className = "eval-head"; textHead.textContent = "As text";
  const imgHead = document.createElement("h3"); imgHead.className = "eval-head"; imgHead.textContent = "As an image";
  box.append(wrap, det, textHead, row([fmtSel, copyText]), text, imgHead, labels, row([copyImg, saveImg]));
}

// a true minus sign reads better than a hyphen
function fmtEntry(v) { return v < 0 ? "−" + (-v) : String(v); }

// The matrix drawn on a canvas: white background, black entries in brackets,
// labels (optional) in grey above the columns and left of the rows.
function matrixPngBlob(out, withLabels) {
  const S = 2;                                       // pixel scale, for crispness
  const cv = document.createElement("canvas");
  const ctx = cv.getContext("2d");
  const numFont = `${18 * S}px "Latin Modern Math", "STIX Two Math", "Cambria Math", Georgia, serif`;
  const labFont = `${13 * S}px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`;
  const m = out.matrix, rows = m.length, cols = out.columns.length;
  const width = (font, t) => { ctx.font = font; return ctx.measureText(t).width; };
  const gap = 18 * S, rowH = 30 * S, margin = 16 * S, bracket = 10 * S, inset = 12 * S;
  const colW = out.columns.map((c, j) => Math.max(
    ...m.map(r => width(numFont, fmtEntry(r[j]))),
    withLabels ? width(labFont, c) : 0));
  const labelW = withLabels ? Math.max(...out.rows.map(t => width(labFont, t))) + 14 * S : 0;
  const headH = withLabels ? 24 * S : 0;
  const bodyW = colW.reduce((a, b) => a + b, 0) + gap * (cols - 1);
  cv.width = Math.ceil(margin * 2 + labelW + bracket * 2 + inset * 2 + bodyW);
  cv.height = Math.ceil(margin * 2 + headH + rowH * rows + 8 * S);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, cv.width, cv.height);
  const top = margin + headH, left = margin + labelW + bracket + inset;
  const xs = []; let x = left;
  colW.forEach(w => { xs.push(x + w); x += w + gap; });   // right edges
  ctx.textBaseline = "middle";
  if (withLabels) {
    ctx.fillStyle = "#6b6b70"; ctx.font = labFont; ctx.textAlign = "center";
    out.columns.forEach((c, j) => ctx.fillText(c, xs[j] - colW[j] / 2, margin + headH / 2));
    ctx.textAlign = "right";
    out.rows.forEach((t, i) => ctx.fillText(t, margin + labelW - 14 * S, top + 4 * S + rowH * (i + 0.5)));
  }
  ctx.fillStyle = "#111111"; ctx.font = numFont; ctx.textAlign = "right";
  m.forEach((r, i) => r.forEach((v, j) => ctx.fillText(fmtEntry(v), xs[j], top + 4 * S + rowH * (i + 0.5))));
  // square brackets
  ctx.strokeStyle = "#111111"; ctx.lineWidth = 1.6 * S;
  const bTop = top, bBot = top + rowH * rows + 8 * S;
  const bl = margin + labelW + bracket, br = left + bodyW + inset;
  ctx.beginPath();
  ctx.moveTo(bl, bTop); ctx.lineTo(bl - bracket * 0.6, bTop); ctx.lineTo(bl - bracket * 0.6, bBot); ctx.lineTo(bl, bBot);
  ctx.moveTo(br, bTop); ctx.lineTo(br + bracket * 0.6, bTop); ctx.lineTo(br + bracket * 0.6, bBot); ctx.lineTo(br, bBot);
  ctx.stroke();
  return new Promise((resolve, reject) =>
    cv.toBlob(b => b ? resolve(b) : reject(new Error("could not draw the matrix")), "image/png"));
}

// Copy a PNG (given as a promise, so the clipboard write starts while the
// click still counts as a user gesture -- Safari insists) or, failing that,
// save it.
async function copyBlobPng(blobPromise, btn, filename) {
  try {
    if (!navigator.clipboard || !window.ClipboardItem) throw new Error("no clipboard");
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blobPromise })]);
    flashButton(btn, "Copied ✓");
  } catch (e) {
    try { downloadBlob(await blobPromise, filename); flashButton(btn, "Saved ↓"); }
    catch (e2) { flashButton(btn, "Failed"); }
  }
}

function downloadBlob(blob, filename) {
  const a = document.getElementById("download-anchor");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// Delete a type -- by default alone, its derived types moving up to take its
// place; a checkbox (off unless ticked) removes every derived type with it.
function openDeleteDialog(id = selectedId) {
  const nodes = api("list_nodes");
  const summ = nodes.find(n => n.id === id);
  if (!summ) return;
  const kids = (summ.children || []).length;
  const below = api("descendants", id).length;
  const parent = summ.parent_id ? nodes.find(n => n.id === summ.parent_id) : null;
  const name = `<strong>${escapeHtml(summ.name)}</strong>`;

  let fate = "";
  if (kids) {
    const many = kids > 1 ? "s" : "";
    fate = parent
      ? ` Its ${kids} derived type${many} will move up to
         <strong>${escapeHtml(parent.name)}</strong>, keeping the same derivation.`
      : ` Its ${kids} derived type${many} will become
         ${kids > 1 ? "independent roots" : "an independent root"}, since nothing
         would be left to derive ${kids > 1 ? "them" : "it"} from.`;
  }
  const body = dialogHead("Delete this type", "");
  const blurb = body.querySelector("p");

  const go = document.createElement("button");
  go.className = "danger";
  let all = null;
  const describe = () => {
    const withAll = !!(all && all.checked);
    blurb.innerHTML = withAll
      ? `${name} will be removed from the workspace together with all
         ${below} type${below > 1 ? "s" : ""} derived from it. This cannot be undone.`
      : `${name} will be removed from the workspace, and nothing else.${fate}
         This cannot be undone.`;
    go.textContent = withAll
      ? `Delete ${summ.name} and ${below} derived type${below > 1 ? "s" : ""}`
      : "Delete " + summ.name;
  };
  if (below) {
    const lab = document.createElement("label");
    lab.className = "check"; lab.style.margin = "4px 0";
    all = document.createElement("input");
    all.type = "checkbox"; all.id = "delete-all";
    all.onchange = describe;
    lab.append(all, document.createTextNode(
      `Also delete all ${below} derived type${below > 1 ? "s" : ""} (and theirs, all the way down)`));
    body.appendChild(lab);
  }
  describe();
  go.onclick = () => {
    let removed;
    try {
      removed = api("delete", id, !!(all && all.checked)).removed;
    } catch (e) { showModalError(e.message); return; }
    closeModal();
    const remaining = api("list_nodes");
    let next = null;
    if (selectedId && !removed.includes(selectedId)) next = selectedId;
    else if (summ.parent_id && remaining.some(n => n.id === summ.parent_id)) next = summ.parent_id;
    else if (remaining.length) next = remaining[0].id;
    refreshAll();
    if (next) selectNode(next);
    else { selectedId = null; renderTypeList(); clearViews(); }
    autosave();
  };
  const box = document.createElement("div");
  box.className = "reslist"; box.style.marginTop = "10px";
  box.appendChild(go);
  body.appendChild(box);
  body.appendChild(errBox());
  openModal();
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

// A marking goes at a vertex or part-way along an edge; both are picked on the
// picture by default. Rings mark the vertices, which are otherwise not drawn.
function openMarkingDialog() {
  const data = api("render", selectedId);
  const summ = api("list_nodes").find(n => n.id === selectedId) || {};
  const val = summ.valences || {};
  const body = dialogHead("Add a marking",
    "A marking is a contracted end (direction 0). Attach it at an existing " +
    "vertex, or part-way along an edge or end, which subdivides the edge, " +
    "putting a new vertex between the two pieces and hanging the marking there.");
  body.insertAdjacentHTML("beforeend",
    `<label>Name (optional) <input id="mk-name" type="text" placeholder="auto"></label>`);

  const mkName = () => (document.getElementById("mk-name").value || "").trim();
  const run = (method, target) => {
    try {
      api(method, selectedId, target, mkName(), "");
      closeModal(); refreshAll(); autosave();
    } catch (e) { showModalError(e.message); }
  };
  const atVertexText = id => `at the vertex where ${vertexLabel(data.curve, id)} meet`
    + (val[id] ? ` (valence ${val[id]})` : "");
  const onEdgeText = e => `on ${e.name || e.id} (${e.kind === "end" ? "end" : "edge"}, ` +
    `direction ${fmtVec(e.vec)}), subdividing it`;

  const frame = pickFrame(body, wantPresetSwatches()
    ? "Click a vertex (ringed) or a point on an edge or end."
    : "Tap a vertex (ringed) or an edge or end, then tap it again or press Add.",
    true);

  const section = (title) => {
    const h = document.createElement("h3");
    h.textContent = title;
    h.style.margin = "14px 0 6px";
    h.style.fontSize = "14px";
    frame.listView.appendChild(h);
    const list = document.createElement("div");
    list.className = "reslist";
    frame.listView.appendChild(list);
    return list;
  };
  const atVertex = section("At a vertex");
  data.curve.vertices.forEach(v => {
    const b = document.createElement("button");
    b.textContent = `where ${vertexLabel(data.curve, v.id)} meet`
      + (val[v.id] ? `  (valence ${val[v.id]})` : "");
    b.onclick = () => run("add_marking", v.id);
    atVertex.appendChild(b);
  });
  const onEdge = section("On an edge or end (subdivides it)");
  data.curve.edges.forEach(e => {
    const b = document.createElement("button");
    b.textContent = `on ${e.name || e.id}  (${e.kind}, direction ${fmtVec(e.vec)})`;
    b.onclick = () => run("add_marking_on_edge", e.id);
    onEdge.appendChild(b);
  });

  body.appendChild(errBox());
  openModal();
  mountPicker(data, "pick-svg", {
    pickEdge: () => true, pickVertex: () => true,
    status: frame.status, button: frame.button,
    describe: t => t.kind === "vertex" ? atVertexText(t.id) : onEdgeText(t.edge),
    buttonText: t => t.kind === "vertex" ? "Add marking at this vertex" : `Add marking on ${t.edge.name}`,
    buttonIdle: "Add marking",
    commit: t => t.kind === "vertex" ? run("add_marking", t.id) : run("add_marking_on_edge", t.id),
  });
}

// Contracting picks an edge. The default is to pick it on a picture of the
// curve -- the natural way to say "that one" -- with the list one click away.
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
  const contract = e => {
    try {
      const child = api("contract", selectedId, e.id);
      closeModal(); refreshAll(); selectNode(child.id); autosave();
    } catch (err) { showModalError(err.message); }
  };
  const frame = pickFrame(body, wantPresetSwatches()
    ? "Click the edge to contract. Faded parts cannot be contracted."
    : "Tap the edge to contract, then tap it again or press Contract. Faded parts cannot be contracted.",
    true);
  const list = document.createElement("div"); list.className = "reslist";
  bounded.forEach(e => {
    const b = document.createElement("button");
    b.textContent = `${e.name}   direction ${fmtVec(e.vec)}` +
      (e.weight > 1 ? `, weight ${e.weight}` : "");
    b.onclick = () => contract(e);
    list.appendChild(b);
  });
  frame.listView.appendChild(list);
  body.appendChild(errBox());
  openModal();
  // drawn once the dialog shows, so labels can be measured
  mountPicker(data, "pick-svg", {
    pickEdge: e => e.kind === "bounded", dim: true,
    status: frame.status, button: frame.button,
    describe: t => `${t.edge.name}, direction ${fmtVec(t.edge.vec)}` +
      (t.edge.weight > 1 ? `, weight ${t.edge.weight}` : ""),
    buttonText: t => `Contract ${t.edge.name}`, buttonIdle: "Contract",
    commit: t => contract(t.edge),
  });
}

// The vertex to resolve is picked on the picture by default (ringed: vertices
// are not drawn otherwise), with a list one click away. Picking is only the
// first step -- the vertex's resolutions then appear below -- so a click just
// selects, and the ticked side of a big vertex is shown on the picture too.
function openResolveDialog() {
  const summ = api("list_nodes").find(n => n.id === selectedId) || {};
  const data = api("render", selectedId);
  const valences = summ.valences || {};
  const big = Object.entries(valences).filter(([, k]) => k >= 4).map(([v]) => v);
  const body = dialogHead("Resolve a vertex",
    "Resolving splits a vertex in two, joined by a new bounded edge whose " +
    "direction balancing forces. Each one is an adjacent maximal cell of the " +
    "tropical moduli space. A split whose forced edge comes out zero realizes " +
    "as a parallelogram, not an edge, and cannot be applied.");
  if (!big.length) {
    body.insertAdjacentHTML("beforeend", `<p class="muted">This type has no vertex of valence 4 or more.</p>`);
    openModal(); return;
  }
  const frame = pickFrame(body, big.length > 1
    ? (wantPresetSwatches() ? "Click a ringed vertex to resolve it." : "Tap a ringed vertex to resolve it.")
    : "The only vertex that can be resolved is ringed.", false);
  const sel = selectOf(big.map(v => [v, `where ${vertexLabel(data.curve, v)} meet`]));
  frame.listView.appendChild(labeled("vertex", sel));
  const listWrap = document.createElement("div");
  listWrap.style.marginTop = "10px";
  body.appendChild(listWrap);
  body.appendChild(errBox());
  let picker = null;
  let current = null;         // the vertex whose resolutions are shown
  let edgeHits = [];          // its edges' click targets on the picture
  const describeVertex = id => `where ${vertexLabel(data.curve, id)} meet (valence ${valences[id]})`;

  const commit = (fn) => {
    try {
      const child = fn();
      closeModal(); refreshAll(); selectNode(child.id); autosave();
    } catch (err) { showModalError(err.message); }
  };

  // Valence 4 has only three splits, so each is shown as the curve it makes:
  // click the one you want. Hovering one also shows, on the picture above,
  // which edges it pairs up.
  const fillList = (vertex) => {
    let list;
    try { list = api("list_resolutions", selectedId, vertex); }
    catch (e) { showModalError(e.message); return; }
    listWrap.insertAdjacentHTML("beforeend",
      `<p class="muted" style="margin:0 0 6px">Each resolution, as the curve it
       produces (the new edge highlighted). Pick one.</p>`);
    const box = document.createElement("div");
    box.className = "res-thumbs";
    const toDraw = [];
    list.forEach(r => {
      const b = document.createElement("button");
      b.className = "res-thumb";
      b.disabled = r.is_crossing;
      if (r.is_crossing) {
        b.title = "crossing pairing — realizes as a parallelogram";
        b.innerHTML = `<div class="res-thumb-x">crossing<br><span class="muted">realizes as a
          parallelogram, not an edge</span></div>`;
      } else {
        const svg = document.createElementNS(SVGNS, "svg");
        svg.id = "res-thumb-" + r.index;
        svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
        b.appendChild(svg);
        toDraw.push([svg.id, r]);
      }
      const cap = document.createElement("div");
      cap.className = "res-thumb-cap";
      cap.textContent = r.label.replace(/\s*\((edge|crossing)\)$/, "");
      b.appendChild(cap);
      b.onclick = () => commit(() => api("resolve", selectedId, vertex, r.index));
      b.addEventListener("pointerenter", () => showSplit(vertex, r.side_a));
      b.addEventListener("pointerleave", () => showSplit(vertex, []));
      box.appendChild(b);
    });
    listWrap.appendChild(box);
    toDraw.forEach(([id, r]) => {
      try { drawPreview(id, api("render_resolution", selectedId, vertex, r.side_a), { labels: false }); }
      catch (e) { /* leave that thumbnail blank rather than break the dialog */ }
    });
  };

  // Past that the list grows fast (25 splits at valence 6), so choose a side
  // instead: everything ticked goes to one new vertex, the rest to the other.
  const fillPicker = (vertex) => {
    const flags = vertexFlags(data.curve, vertex);
    const d = flags.length;
    listWrap.insertAdjacentHTML("beforeend",
      `<p class="muted" style="margin:0 0 6px">Tick the edges to gather on one side
       (at least 2, at most ${d - 2} of ${d}); the rest go on the other.</p>`);
    listWrap.insertAdjacentHTML("beforeend",
      `<p class="muted" style="margin:0 0 6px">You can also click the edges on the picture.</p>`);
    const boxes = [];
    flags.forEach(f => {
      const lab = document.createElement("label");
      lab.className = "check";
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.value = f.id;
      lab.append(cb, document.createTextNode(f.name));
      listWrap.appendChild(lab);
      boxes.push(cb);
    });
    // the vertex's edges on the picture toggle the same boxes
    if (picker) {
      const svg = picker.drawn.svg;
      flags.forEach(f => {
        const ln = picker.drawn.lines[f.id];
        const cb = boxes.find(b => b.value === f.id);
        if (!ln || !cb) return;
        const hit = svgEl("line", { x1: ln.getAttribute("x1"), y1: ln.getAttribute("y1"),
                                    x2: ln.getAttribute("x2"), y2: ln.getAttribute("y2"),
                                    ...HIT_ATTRS, "stroke-width": 20, class: "pick-hit" });
        hit.addEventListener("click", ev => {
          ev.stopPropagation();
          cb.checked = !cb.checked;
          update();
        });
        svg.appendChild(hit);
        edgeHits.push(hit);
      });
      // keep the vertex's own target on top, so it can still be clicked
      picker.drawn.vertexPicks.forEach(v => svg.appendChild(v.hit));
    }
    const note = document.createElement("p");
    note.className = "muted"; note.style.margin = "8px 0";
    const preview = document.createElementNS(SVGNS, "svg");
    preview.id = "res-preview";
    preview.classList.add("res-preview");
    preview.setAttribute("preserveAspectRatio", "xMidYMid meet");
    const go = document.createElement("button");
    go.className = "primary";
    go.textContent = "Resolve"; go.disabled = true;
    const chosen = () => boxes.filter(b => b.checked).map(b => b.value);
    const update = () => {
      const pick = chosen();
      let res;
      try { res = api("preview_resolution", selectedId, vertex, pick); }
      catch (e) { res = { ok: false, reason: e.message }; }
      if (res.ok) {
        const rest = flags.filter(f => !pick.includes(f.id)).map(f => f.name).join(", ");
        const side = flags.filter(f => pick.includes(f.id)).map(f => f.name).join(", ");
        note.textContent = `{${side}} | {${rest}}, joined by a new edge ${fmtVec(res.new_edge_vec)}`;
      } else {
        note.textContent = res.reason;
      }
      go.disabled = !res.ok;
      showSplit(vertex, pick);
      // what resolving would give, drawn as you choose (an SVG element has no
      // .hidden property, so the attribute is set directly)
      preview.toggleAttribute("hidden", !res.ok);
      if (res.ok) {
        try { drawPreview("res-preview", api("render_resolution", selectedId, vertex, pick)); }
        catch (e) { preview.setAttribute("hidden", ""); }
      }
    };
    boxes.forEach(b => { b.onchange = update; });
    go.onclick = () => commit(() => api("resolve_subset", selectedId, vertex, chosen(), null));
    listWrap.append(note, preview, row([go]));
    update();
  };

  // the ticked side in the accent colour, the rest as drawn
  const showSplit = (vertex, pick) => {
    if (!picker) return;
    const lines = picker.drawn.lines;
    vertexFlags(data.curve, vertex).forEach(f => {
      const ln = lines[f.id];
      if (!ln) return;                         // a marking: nothing to colour
      if (!ln.dataset.origStroke) {
        ln.dataset.origStroke = ln.getAttribute("stroke");
        ln.dataset.origWidth = ln.getAttribute("stroke-width");
      }
      const on = pick.includes(f.id);
      ln.setAttribute("stroke", on ? "var(--accent)" : ln.dataset.origStroke);
      ln.setAttribute("stroke-width", on ? +ln.dataset.origWidth + 2 : ln.dataset.origWidth);
    });
  };

  const fill = vertex => {
    if (current && current !== vertex) showSplit(current, []);
    edgeHits.forEach(h => h.remove());
    edgeHits = [];
    current = vertex;
    sel.value = vertex;
    listWrap.innerHTML = "";
    showModalError("");
    if (!vertex) return;
    if (valences[vertex] === 4) fillList(vertex); else fillPicker(vertex);
  };
  sel.onchange = () => { fill(sel.value); if (picker) picker.select(sel.value); };
  openModal();
  picker = mountPicker(data, "pick-svg", {
    pickVertex: v => (valences[v.id] || 0) >= 4,
    clickCommits: false,
    status: frame.status, idle: "",
    describe: t => describeVertex(t.id),
    onSelect: t => fill(t ? t.id : null),
  });
  // one choice, or coming back to the list, means a vertex is already chosen
  if (big.length === 1) picker.select(big[0]);
  frame.onSwitch(picture => {
    if (!picture && !current) fill(sel.value);
  });
}

// ---- small DOM helpers ----
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
// Accepts "#rrggbb", "rrggbb", "#rgb" or "rgb"; returns a normalized
// "#rrggbb", or null if it isn't a colour code.
function normalizeHex(v) {
  if (typeof v !== "string") return null;
  let s = v.trim().replace(/^#/, "");
  if (/^[0-9a-fA-F]{3}$/.test(s)) s = s.split("").map(c => c + c).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
  return "#" + s.toLowerCase();
}

// A colour swatch paired with a hex-code box, kept in sync, so a colour can be
// picked visually OR typed/pasted exactly (e.g. to match another app).
// `live`: commit on every valid keystroke (good for dialogs that preview
// instantly) vs only on Enter/blur (needed where committing rebuilds the
// surrounding DOM and would yank the field out from under the typist).
// Preset colors for curve elements. Phone colour pickers offer swatches of
// their own; desktop ones open a bare spectrum, so the app supplies these there.
const COLOR_PRESETS = [
  ["#000000", "Black"], ["#616161", "Grey"], ["#6d4c41", "Brown"], ["#ffffff", "White"],
  ["#e53935", "Red"], ["#fb8c00", "Orange"], ["#f9a825", "Amber"], ["#43a047", "Green"],
  ["#00897b", "Teal"], ["#00acc1", "Cyan"], ["#1e88e5", "Blue"], ["#3949ab", "Indigo"],
  ["#8e24aa", "Purple"], ["#ff00ff", "Magenta"], ["#d81b60", "Pink"], ["#7cb342", "Lime"],
];
// only where the platform's own picker has no swatches: a mouse or trackpad
const wantPresetSwatches = () => {
  try { return window.matchMedia("(pointer: fine)").matches; } catch (e) { return true; }
};

let openPresetPop = null;
function closePresetPop() {
  if (openPresetPop) { openPresetPop.remove(); openPresetPop = null; }
}
document.addEventListener("mousedown", ev => {
  if (openPresetPop && !openPresetPop.contains(ev.target) &&
      !ev.target.closest(".preset-btn")) closePresetPop();
});
document.addEventListener("keydown", ev => { if (ev.key === "Escape") closePresetPop(); });

// Fixed-position, so a scrolling dialog cannot clip it; placed under the
// button and kept on screen.
function showPresetPop(anchor, current, onPick) {
  closePresetPop();
  const pop = document.createElement("div");
  pop.className = "preset-pop";
  pop.setAttribute("role", "listbox");
  COLOR_PRESETS.forEach(([hex, name]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "swatch" + (current && current.toLowerCase() === hex ? " on" : "");
    b.style.background = hex;
    b.title = `${name} ${hex}`;
    b.setAttribute("aria-label", name);
    b.onclick = () => { closePresetPop(); onPick(hex); };
    pop.appendChild(b);
  });
  document.body.appendChild(pop);
  const r = anchor.getBoundingClientRect();
  const w = pop.offsetWidth, h = pop.offsetHeight;
  let left = Math.min(r.left, window.innerWidth - w - 8);
  let top = r.bottom + 6;
  if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 6);
  pop.style.left = Math.max(8, left) + "px";
  pop.style.top = top + "px";
  openPresetPop = pop;
}

function colorField(value, onSet, { live = true, fallback = defaultColorHex,
                                    presets = true } = {}) {
  const wrap = document.createElement("span");
  wrap.className = "color-field";
  const sw = document.createElement("input");
  sw.type = "color";
  sw.value = isHex6(value) ? value : fallback();
  if (!value) sw.title = "Using the default color";
  const hex = document.createElement("input");
  hex.type = "text";
  hex.className = "hexfield";
  hex.spellcheck = false;
  hex.autocapitalize = "off";
  hex.autocomplete = "off";
  hex.placeholder = isHex6(value) ? "#rrggbb" : fallback();
  hex.value = isHex6(value) ? value : "";
  hex.setAttribute("aria-label", "colour code");

  const apply = (h) => { sw.value = h; hex.classList.remove("bad"); onSet(h); };
  sw.oninput = () => { hex.value = sw.value; apply(sw.value); };
  hex.oninput = () => {
    const n = normalizeHex(hex.value);
    if (n) { sw.value = n; hex.classList.remove("bad"); if (live) onSet(n); }
    else hex.classList.add("bad");
  };
  const commit = () => {
    const n = normalizeHex(hex.value);
    if (n) { hex.value = n; apply(n); }
    else if (!hex.value.trim()) hex.classList.remove("bad"); // left blank: keep as is
    else hex.classList.add("bad");
  };
  hex.onchange = commit;
  hex.onblur = commit;
  hex.onkeydown = ev => { if (ev.key === "Enter") { ev.preventDefault(); commit(); hex.blur(); } };

  wrap.append(sw);
  if (presets && wantPresetSwatches()) {
    const pb = document.createElement("button");
    pb.type = "button";
    pb.className = "preset-btn small ghost";
    pb.textContent = "▾";
    pb.title = "Preset colors";
    pb.setAttribute("aria-label", "Preset colors");
    pb.onclick = () => {
      if (openPresetPop) { closePresetPop(); return; }
      showPresetPop(pb, sw.value, h => { hex.value = h; apply(h); });
    };
    wrap.append(pb);
  }
  wrap.append(hex);
  wrap.setValue = (h) => {
    sw.value = isHex6(h) ? h : fallback();
    hex.value = isHex6(h) ? h : "";
    hex.placeholder = isHex6(h) ? "#rrggbb" : fallback();
    hex.classList.remove("bad");
  };
  return wrap;
}
// A color picker plus a "reset to default" button, shown only once an edge/
// marking has an explicit color of its own (an empty color means "inherit").
function colorControl(val, onSet) {
  const wrap = document.createElement("span"); wrap.className = "edge-row";
  wrap.style.gap = "4px";
  // not live: each commit re-renders the controls panel, which would destroy
  // the field mid-typing
  wrap.appendChild(colorField(val, onSet, { live: false }));
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
