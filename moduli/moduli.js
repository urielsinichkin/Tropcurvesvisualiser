"use strict";
// ---------------------------------------------------------------------------
// The moduli map explorer: ev x ft : M_{0,n}(R^2, Delta) -> (R^2)^k x M_{0,5}.
//
// The math is in tropcurves/moduli.py (exact); this page chooses the setup,
// shows M_{0,5} twice -- a flat chart of five cones around the apex (a 5-cycle
// of the Petersen graph) and the whole Petersen graph at one size -- and the
// curves over the current point, whose evaluation points can be dragged.
// web/app.js is loaded first (in library mode) for Python, drawing, export
// and help.
// ---------------------------------------------------------------------------
const MM_KEY = "tropcurves.moduli.v1";

// --- M_{0,5}: rays are 2-subsets of the five legs, cones disjoint pairs ------
const MM_RAYS = [];
for (let i = 0; i < 5; i++) for (let j = i + 1; j < 5; j++) MM_RAYS.push([i, j]);
const rk = r => "" + r[0] + r[1];
const rayOf = k => [+k[0], +k[1]];
const disjoint = (a, b) => !a.some(x => b.includes(x));
const coneKey = (a, b) => [rk(a), rk(b)].sort().join("|");
const MM_CONES = [];
MM_RAYS.forEach((a, i) => MM_RAYS.slice(i + 1).forEach(b => { if (disjoint(a, b)) MM_CONES.push([a, b]); }));
// the twelve 5-cycles of the Petersen graph, as lists of ray keys
const MM_CYCLES = (() => {
  const seen = new Set(), out = [];
  const keys = MM_RAYS.map(rk);
  const adj = k => keys.filter(o => disjoint(rayOf(k), rayOf(o)));
  const walk = path => {
    if (path.length === 5) {
      if (!adj(path[4]).includes(path[0])) return;
      const id = [...path].sort().join() + "/" + [0, 1, 2, 3, 4].map(i =>
        [path[i], path[(i + 1) % 5]].sort().join("-")).sort().join();
      if (!seen.has(id)) { seen.add(id); out.push(path); }
      return;
    }
    adj(path[path.length - 1]).forEach(n => { if (!path.includes(n)) walk([...path, n]); });
  };
  keys.forEach(k => walk([k]));
  return out;
})();
const cycleCones = c => c.map((r, i) => coneKey(rayOf(r), rayOf(c[(i + 1) % 5])));

// --- state -------------------------------------------------------------------
const MM = {
  library: null,        // workspace JSON text
  groups: [],
  config: null,         // { group, evaluated, legs, points }
  check: null,          // moduli_check result
  m: null,              // exact point of M_0,5: { splits, lengths }
  cycle: null,          // five ray keys in chart order
  lastCone: null,       // the 2-dim cone the point is (or last was) in
  R: 10,                // the chart shows a + b <= R
  regions: {},          // cone key -> regions
  overview: null, overviewSize: null,
  pre: null,            // last preimage result
  selected: null,       // type id of the big figure
  frame: null,          // a frozen transform while a point is dragged
  onWall: null,         // { name, edge } when snapped onto a wall
  onImage: null,        // { name } when snapped onto the image of a type
  images: [],           // images of the types that are not full-dimensional
  path: { from: null, to: null, cycle: null, t: 0, playing: false, log: [] },
};

// --- boot --------------------------------------------------------------------
async function mmBoot() {
  document.getElementById("app-version").textContent = "v" + APP_VERSION;
  applyBackgroundTheme(loadSettings().bgColor);
  await bootCore(document.getElementById("boot-msg"));
  document.getElementById("boot").hidden = true;
  document.getElementById("mm").hidden = false;
  wireMenu();
  trackTopbarHeight();
  mmWire();
  const from = new URLSearchParams(location.search).get("from");
  const fromApp = !!from;
  if (fromApp) history.replaceState(null, "", location.pathname);
  let restored = false;
  if (from === "types") {
    // the main app handed over chosen types (a type's "M" button)
    let text = null;
    try { text = localStorage.getItem(MODULI_HANDOFF_KEY); localStorage.removeItem(MODULI_HANDOFF_KEY); } catch (e) { /* none */ }
    if (text) { mmLoadLibrary(text); mmAutosave(); return; }
  }
  if (!fromApp) {
    try {
      const saved = localStorage.getItem(MM_KEY);
      if (saved) restored = mmRestore(JSON.parse(saved));
    } catch (e) { /* start afresh */ }
  }
  if (!restored) mmUseAppLibrary(true);
}

function mmWire() {
  const on = (id, ev, f) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, f); };
  on("mm-from-app", "click", () => mmUseAppLibrary(false));
  on("mm-import", "click", () => document.getElementById("mm-file").click());
  on("mm-file", "change", mmImportFile);
  on("mm-save", "click", () => downloadJSON(JSON.stringify(mmState(), null, 1), "moduli-session.json"));
  on("mm-send", "click", ev => mmSendToApp(ev.target));
  on("modal-cancel", "click", closeModal);
  on("mm-range-in", "click", () => mmSetRange(MM.R / 1.5));
  on("mm-range-out", "click", () => mmSetRange(MM.R * 1.5));
  on("mm-snap", "change", mmAutosave);
  on("mm-size", "input", mmSizeInput);
  const bg = () => resolvedVar("--panel", "#ffffff");
  on("mm-copy-chart", "click", ev => copyPanelPng("mm-chart", bg(), ev.target, "m05-chart.png"));
  on("mm-copy-overview", "click", ev => copyPanelPng("mm-overview", bg(), ev.target, "m05-overview.png"));
  on("mm-copy-figure", "click", ev => copyPanelPng("mm-figure", null, ev.target, "curve.png"));
  on("mm-svg-chart", "click", () => mmDownloadSvg("mm-chart", bg(), "m05-chart.svg"));
  on("mm-svg-overview", "click", () => mmDownloadSvg("mm-overview", bg(), "m05-overview.svg"));
  on("mm-svg-figure", "click", () => mmDownloadSvg("mm-figure", null, "curve.svg"));
  on("mm-reset-points", "click", () => mmGuard(mmResetPoints));
  on("mm-reset-m", "click", () => mmGuard(mmResetM));
  on("mm-path-from", "click", () => mmPathEnd("from"));
  on("mm-path-to", "click", () => mmPathEnd("to"));
  on("mm-path-play", "click", mmPathPlay);
  on("mm-path-clear", "click", mmPathClear);
  on("mm-path-t", "input", ev => { mmPathPause(); mmPathSeek(ev.target.value / 1000); });
  mmWireChart();
  mmWireFigure();
  mmWireHelp();
}

function panelHelp(sel, key) {
  const h = document.querySelector(sel);
  if (!h || h.querySelector(".help-btn")) return;
  h.classList.add("with-help");
  h.appendChild(helpButton(key));
}
function mmWireHelp() {
  panelHelp("#mm-setup .section-head h2", "moduliSetup");
  panelHelp("#mm-space > .view-head h2", "moduliChart");
  panelHelp("#mm-space .mm-sub h2", "moduliOverview");
  panelHelp("#mm-path summary h2", "moduliPath");
  panelHelp("#mm-curves > .view-head h2", "moduliFigure");
  panelHelp("#mm-curves .mm-sub h2", "moduliGallery");
  const top = document.getElementById("btn-help");
  if (top) top.addEventListener("click", ev => { ev.helpClick = true; toggleHelp(top, "moduliTop"); });
}

function mmDownloadSvg(id, background, filename) {
  try {
    const xml = new XMLSerializer().serializeToString(standaloneSvg(id, background));
    downloadBlob(new Blob([xml], { type: "image/svg+xml" }), filename);
  } catch (e) { reportError(e); }
}

// --- library and session -------------------------------------------------------
function mmUseAppLibrary(quiet) {
  let text = null;
  try { text = localStorage.getItem(STORAGE_KEY); } catch (e) { /* none */ }
  if (!text) {
    if (!quiet) alert("The main app has no library saved in this browser yet.");
    mmLoadLibrary(JSON.stringify({ schema: 1, kind: "workspace", nodes: [] }));
    return;
  }
  mmLoadLibrary(text);
}

function mmLoadLibrary(text, keep) {
  api("load", text);
  MM.library = text;
  MM.groups = api("moduli_groups");
  const cfg = keep && MM.groups.some(g => g.key === keep.config.group) ? keep : null;
  if (cfg) {
    MM.config = cfg.config;
    MM.m = cfg.m; MM.cycle = cfg.cycle; MM.lastCone = cfg.lastCone; MM.R = cfg.R || MM.R;
    MM.selected = cfg.selected || null;
    try { mmConfigChanged(false); } catch (e) { mmConfigChanged(true); }
  } else {
    MM.config = null;
    const g = [...MM.groups].sort((a, b) => b.types.length - a.types.length)
      .find(g => mmDefaults(g)) || MM.groups[0];
    if (g) { MM.config = mmDefaults(g) || { group: g.key, evaluated: [], legs: [], points: {}, base: g.types[0].id, extra: [] }; }
    mmConfigChanged(true);
  }
}

// a setup whose dimensions match, if the group has one
function mmDefaults(g) {
  const k = (g.dim - 2) / 2;
  if (!(k >= 0 && Number.isInteger(k) && k <= g.markings.length)) return null;
  const ev = g.markings.slice(0, k);
  const legs = [...g.ends.map(e => e.name), ...g.markings.filter(m => !ev.includes(m)), ...ev].slice(0, 5);
  if (legs.length < 5) return null;
  return { group: g.key, evaluated: ev, legs: mmLegOrder(g, legs), points: {}, base: g.types[0].id, extra: [] };
}

// The types the page works with: the opened type (shown in the setup picture,
// the one edits change) and the types added at walls it crossed. Other types
// of the library are left out. config.types is what the core is given.
function mmCandidates() {
  const cfg = MM.config, g = mmGroup();
  if (!cfg || !g) return;
  const ids = g.types.map(t => t.id);
  if (!ids.includes(cfg.base)) cfg.base = ids[0];
  cfg.extra = (cfg.extra || []).filter(id => ids.includes(id) && id !== cfg.base);
  cfg.types = [cfg.base, ...cfg.extra];
}
const mmGroup = () => MM.config && MM.groups.find(g => g.key === MM.config.group);
// legs in a fixed order (ends, then markings, by name), whatever order ticked
function mmLegOrder(g, legs) {
  return [...g.ends.map(e => e.name), ...g.markings].filter(n => legs.includes(n));
}

function mmState() {
  return {
    kind: "tropcurves-moduli-session", version: 1, library: MM.library,
    config: MM.config, m: MM.m, cycle: MM.cycle, lastCone: MM.lastCone, R: MM.R,
    selected: MM.selected, snap: document.getElementById("mm-snap").checked, pointsStart: MM.pointsStart, mStart: MM.mStart, edited: !!MM.edited,
    path: { from: MM.path.from, to: MM.path.to, cycle: MM.path.cycle },
  };
}

function mmRestore(st) {
  if (!st || st.kind !== "tropcurves-moduli-session" || !st.library) return false;
  document.getElementById("mm-snap").checked = st.snap !== false;
  MM.pointsStart = st.pointsStart || null;
  MM.mStart = st.mStart || null;
  MM.edited = !!st.edited;
  mmLoadLibrary(st.library, st);
  if (st.path && st.path.from && st.path.cycle) {
    MM.path.from = st.path.from; MM.path.to = st.path.to; MM.path.cycle = st.path.cycle;
    mmPathUpdate();
  }
  return true;
}

function mmImportFile(ev) {
  const f = ev.target.files && ev.target.files[0];
  ev.target.value = "";
  if (!f) return;
  f.text().then(text => {
    let obj;
    try { obj = JSON.parse(text); } catch (e) { alert("Not a JSON file."); return; }
    try {
      if (obj && obj.kind === "tropcurves-moduli-session") mmRestore(obj);
      else mmLoadLibrary(text, MM.config ? mmState() : null);
      mmAutosave();
    } catch (e) { alert("Could not load it: " + e.message); }
  });
}

let mmSaveTimer = null;
function mmAutosave() {
  clearTimeout(mmSaveTimer);
  mmSaveTimer = setTimeout(() => {
    const el = document.getElementById("mm-saved");
    try {
      localStorage.setItem(MM_KEY, JSON.stringify(mmState()));
      el.textContent = "saved " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) { el.textContent = "not saved (too large for this browser)"; }
  }, 600);
}

// --- setup panel -----------------------------------------------------------------
// After the setup changed: check the dimensions and recompute. With `fresh`
// (or when the setup has no points yet) take a starting point that has a
// curve over it; otherwise keep the points and the point of M_0,5.
function mmConfigChanged(fresh) {
  MM.check = null;
  MM.lastPre = null;          // a new setup is not a move: no walls crossed
  mmCandidates();
  const cfg = MM.config;
  let ok = false;
  if (cfg && cfg.legs.length === 5) {
    try {
      MM.check = api("moduli_check", { group: cfg.group, evaluated: cfg.evaluated, legs: cfg.legs, types: cfg.types });
      ok = MM.check.ok;
    } catch (e) { MM.check = { ok: false, message: e.message, types: [] }; }
  }
  if (ok) {
    const missing = cfg.evaluated.some(m => !(cfg.points || {})[m]);
    if (fresh || missing || !MM.m) {
      const ini = api("moduli_initial", cfg);
      if (ini.points) {
        cfg.points = ini.points; MM.m = ini.m;
        MM.pointsStart = JSON.parse(JSON.stringify(ini.points));
        MM.mStart = JSON.parse(JSON.stringify(ini.m));
        MM.edited = false;
        MM.R = mmNice(2.6 * mmSize(MM.m));
      } else { MM.m = null; }
      MM.cycle = null; MM.lastCone = null; MM.selected = null;
    }
    if (MM.m) {
      mmPreimage();         // throws on a point that does not fit the setup
      mmRecomputeAll();
    }
  }
  if (!ok || !MM.m) { MM.pre = null; MM.overview = null; }
  mmRenderSetup();
  if (!ok || !MM.m) mmClearViews();
  mmAutosave();
}

function mmRenderSetup() {
  const body = document.getElementById("mm-setup-body");
  body.innerHTML = "";
  if (!MM.groups.length) {
    body.innerHTML = `<p class="muted">This library has no types. Make some in the
      <a href="../web/index.html">main app</a>, or import a library file.</p>`;
    return;
  }
  const cfg = MM.config, g = mmGroup();
  const sel = document.createElement("select");
  sel.id = "mm-group";
  MM.groups.forEach(gr => {
    const o = document.createElement("option");
    o.value = gr.key;
    o.textContent = `${gr.ends.length} ends, ${gr.markings.length} markings · ${gr.types.length} types`;
    o.selected = g && gr.key === g.key;
    sel.appendChild(o);
  });
  sel.onchange = () => {
    const gr = MM.groups.find(x => x.key === sel.value);
    MM.config = mmDefaults(gr) || { group: gr.key, evaluated: [], legs: [], points: {}, base: gr.types[0].id, extra: [] };
    mmGuard(() => mmConfigChanged(true));
  };
  const lab = document.createElement("label");
  lab.className = "mm-field"; lab.append("Types ", sel);
  body.appendChild(lab);
  if (!g) return;
  // the opened type: the one shown and edited; the curves are of it and of
  // the types added where it crosses walls
  if (g.types.length > 1) {
    const tsel = document.createElement("select");
    tsel.id = "mm-base";
    const added = new Set(cfg.extra || []);
    g.types.forEach(t => {
      const o = document.createElement("option");
      o.value = t.id;
      o.textContent = t.name + (added.has(t.id) ? " (added at a wall)" : "");
      o.selected = t.id === cfg.base;
      tsel.appendChild(o);
    });
    tsel.onchange = () => {
      cfg.base = tsel.value; cfg.extra = [];
      mmGuard(() => mmConfigChanged(true));
    };
    const tl = document.createElement("label");
    tl.className = "mm-field"; tl.append("Opened type ", tsel);
    body.appendChild(tl);
  }
  const info = document.createElement("p");
  info.className = "muted mm-small";
  info.innerHTML = "Δ: " + g.ends.map(e => `${escapeHtml(e.name)} (${e.vec.join(", ")})`).join(", ") +
    `<br>markings: ${g.markings.map(escapeHtml).join(", ") || "none"} · dim M<sub>0,n</sub>(ℝ², Δ) = ${g.dim}`;
  body.appendChild(info);

  const setEvaluated = (n, on) => {
    cfg.evaluated = on ? g.markings.filter(m => m === n || cfg.evaluated.includes(m))
                       : cfg.evaluated.filter(m => m !== n);
    mmGuard(() => mmConfigChanged(true));
  };
  const setLeg = (n, on) => {
    cfg.legs = mmLegOrder(g, on ? [...cfg.legs, n] : cfg.legs.filter(x => x !== n));
    mmGuard(() => mmConfigChanged(true));
  };
  mmPickPicture(body, g, cfg, setEvaluated, setLeg);

  // the same choices as lists, for those who prefer them
  const lists = document.createElement("details");
  lists.className = "mm-lists";
  lists.open = !!MM.listsOpen;
  lists.ontoggle = () => { MM.listsOpen = lists.open; };
  lists.innerHTML = "<summary>Choose from lists instead</summary>";
  const ticks = (title, names, chosen, onSet, note) => {
    const box = document.createElement("fieldset");
    box.className = "mm-ticks";
    box.innerHTML = `<legend>${title}</legend>`;
    names.forEach(n => {
      const l = document.createElement("label");
      l.className = "check";
      const c = document.createElement("input");
      c.type = "checkbox"; c.checked = chosen.includes(n);
      c.onchange = () => onSet(n, c.checked);
      l.append(c, " " + n);
      box.appendChild(l);
    });
    if (note) { const s = document.createElement("div"); s.className = "muted mm-small"; s.textContent = note; box.appendChild(s); }
    lists.appendChild(box);
  };
  ticks("Evaluated markings (k = " + cfg.evaluated.length + ")", g.markings, cfg.evaluated, setEvaluated);
  const legNames = [...g.ends.map(e => e.name), ...g.markings];
  ticks("Legs of M0,5 (" + cfg.legs.length + " of 5)", legNames, cfg.legs, setLeg,
        "Rays of M0,5 are named by the two legs on one side.");
  body.appendChild(lists);

  const st = document.createElement("div");
  st.className = "status";
  if (cfg.legs.length !== 5) { st.classList.add("warn"); st.textContent = "Pick exactly five legs."; }
  else if (MM.check && !MM.check.ok) { st.classList.add("warn"); st.textContent = MM.check.message; }
  else if (MM.check) {
    st.textContent = `dim ${MM.check.dim} = 2·${cfg.evaluated.length} + 2 ✓`;
    const full = (MM.check.types || []).filter(t => t.full);
    if (!full.length) {
      st.classList.add("warn");
      const why = (MM.check.types || []).filter(t => t.why).slice(0, 3)
        .map(t => `${t.name}: ${t.why.reason}`);
      st.textContent += " — but with these choices no type here is full-dimensional, so over a general point " +
        "there is no curve. " + why.join(". ") + "." +
        (MM.m ? " Where such a type does have curves is drawn in orange in the chart; snap onto it." :
                " Try other legs or markings.");
    }
  }
  body.appendChild(st);

  if (MM.check && MM.check.ok && MM.m) {
    const pts = document.createElement("fieldset");
    pts.className = "mm-ticks";
    pts.innerHTML = "<legend>Points in ℝ² (drag them on the curve)</legend>";
    cfg.evaluated.forEach(m => {
      const row = document.createElement("div");
      row.className = "mm-point";
      row.append(m + " ");
      [0, 1].forEach(i => {
        const inp = document.createElement("input");
        inp.type = "text"; inp.size = 7; inp.value = mmShort(cfg.points[m][i]);
        inp.setAttribute("aria-label", (i ? "y" : "x") + " of " + m);
        inp.onchange = () => {
          const v = inp.value.trim();
          if (!/^-?\d+(\.\d+)?(\/\d+)?$/.test(v)) { inp.classList.add("bad"); return; }
          inp.classList.remove("bad");
          cfg.points[m][i] = v;
          mmGuard(() => { mmRecomputeAll(); mmAutosave(); });
        };
        row.append(i ? " y " : " x ", inp);
      });
      pts.appendChild(row);
    });
    const reset = document.createElement("button");
    reset.className = "small"; reset.textContent = "Reset points";
    reset.title = "Put the points back where they started; the point of M0,5 stays";
    reset.disabled = !mmPointsMoved();
    reset.onclick = () => mmGuard(mmResetPoints);
    const again = document.createElement("button");
    again.className = "small"; again.textContent = "New starting point";
    again.title = "Points and a point of M0,5 that have a curve over them";
    again.onclick = () => mmGuard(() => mmConfigChanged(true));
    const resetM = document.createElement("button");
    resetM.className = "small"; resetM.textContent = "Reset M₀,₅ point";
    resetM.title = "Put the point of M0,5 back where it started; the points in the plane stay";
    resetM.disabled = !mmMMoved();
    resetM.onclick = () => mmGuard(mmResetM);
    const btns = document.createElement("div");
    btns.className = "mm-bar";
    btns.append(reset, resetM, again);
    pts.appendChild(btns);
    body.appendChild(pts);
  }

  if (MM.check && MM.check.types && MM.check.types.length) {
    const d = document.createElement("details");
    d.className = "mm-types";
    const full = MM.check.types.filter(t => t.full);
    d.innerHTML = `<summary>${full.length} full-dimensional types, ${MM.check.types.length - full.length} others</summary>`;
    const ul = document.createElement("ul");
    MM.check.types.forEach(t => {
      const li = document.createElement("li");
      li.innerHTML = `${escapeHtml(t.name)} <span class="muted">— ${t.full ? "mult " + t.multiplicity + ", cone " + mmConeName(t.cone)
        : "not full-dimensional: " + escapeHtml(t.why ? t.why.reason : "")}</span>`;
      ul.appendChild(li);
    });
    d.appendChild(ul);
    body.appendChild(d);
  }
}

// The choices on a picture of a type of the group: in "legs" mode a click
// on an end or a marking makes it one of the five legs of M_0,5 (or not), in
// "points" mode a click on a marking fixes it at a point of the plane.
function mmPickPicture(body, g, cfg, setEvaluated, setLeg) {
  const mode = MM.pickMode || "legs";
  const box = document.createElement("div");
  box.className = "mm-pick";
  const tabs = document.createElement("div");
  tabs.className = "mm-tabs";
  tabs.setAttribute("role", "tablist");
  [["legs", `Legs of M₀,₅ (${cfg.legs.length} of 5)`], ["points", `Evaluated markings (k = ${cfg.evaluated.length})`],
   ["move", "Move markings"], ["slopes", "Edit slopes"]]
    .forEach(([m, label]) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "small" + (m === mode ? " primary" : "");
      b.textContent = label;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", m === mode ? "true" : "false");
      b.onclick = () => { MM.pickMode = m; MM.moveFrom = null; MM.slope = null; mmRenderSetup(); };
      tabs.appendChild(b);
    });
  const hint = document.createElement("p");
  hint.className = "muted mm-small";
  hint.textContent = mode === "legs"
    ? "Click ends and markings to make them legs of M₀,₅ (exactly five)."
    : mode === "points" ? "Click markings to fix them at points of the plane."
    : mode === "slopes" ? (MM.slope && MM.slope.edit
        ? "Type the new direction, and click another end to be the dependent one (it absorbs the change). Then Apply."
        : "Click the end whose direction to change. This changes the type (and its degree).")
    : MM.moveFrom ? "Now click an edge (the marking goes inside it) or a ringed vertex (onto it); the marking again to put it down."
    : "Click a marking to pick it up, then an edge or a vertex to put it there. This changes the type.";
  // one svg, kept across redraws so its zoom survives
  if (!MM.pickSvg) {
    MM.pickSvg = document.createElementNS(SVGNS, "svg");
    MM.pickSvg.id = "mm-pick-svg";
    MM.pickSvg.setAttribute("viewBox", `0 0 ${VBW} ${VBH}`);
    MM.pickSvg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  }
  const status = document.createElement("div");
  status.className = "pick-status";
  const legend = document.createElement("div");
  legend.className = "sub-legend";
  legend.innerHTML = `<span><span class="mm-key mm-key-leg"></span>leg of M₀,₅</span>
    <span><span class="mm-key mm-key-ev"></span>evaluated (a point in ℝ²)</span>`;
  box.append(tabs, hint, MM.pickSvg, status, legend);
  if (mode === "move" || mode === "slopes") box.appendChild(mmEditBar());
  body.appendChild(box);
  if (!MM.pickSvg._zoom) MM.pickSvg._zoom = makeZoomable(MM.pickSvg);

  // the type drawn: the one shown large if it is in the group, else the first
  const ids = g.types.map(t => t.id);
  const id = ids.includes(cfg.base) ? cfg.base : ids[0];
  let data;
  try { data = api("render", id); } catch (e) { status.textContent = e.message; return; }
  const moving = mode === "move" && MM.moveFrom &&
    data.curve.markings.some(m => m.id === MM.moveFrom) ? MM.moveFrom : null;
  const drawn = drawCurve(data, {
    svgId: "mm-pick-svg",
    pickEdge: e => ((mode === "legs" || mode === "slopes") && e.kind === "end") || (moving && e.kind !== "marking"),
    pickVertex: moving ? (() => true) : null,
    pickMarking: () => mode !== "slopes",
  });
  const svg = drawn.svg;
  // what is chosen: legs thick in the accent, evaluated markings ringed
  data.curve.edges.forEach(e => {
    if (e.kind === "end" && cfg.legs.includes(e.name) && drawn.lines[e.id]) {
      drawn.lines[e.id].setAttribute("stroke", "var(--accent)");
      drawn.lines[e.id].setAttribute("stroke-width", 5);
    }
  });
  const T = drawn.T;
  if (mode === "slopes") mmSlopeMarks(box, data, drawn, id);
  data.curve.markings.forEach(m => {
    const p = T(m.at);
    const marks = [];
    if (cfg.evaluated.includes(m.name)) {
      marks.push(svgEl("rect", { x: p[0] - 13, y: p[1] - 13, width: 26, height: 26, rx: 4, fill: "none",
        stroke: "var(--warn)", "stroke-width": 3, "pointer-events": "none" }));
    }
    if (cfg.legs.includes(m.name)) {
      marks.push(svgEl("circle", { cx: p[0], cy: p[1], r: 9, fill: "none", stroke: "var(--accent)",
        "stroke-width": 3.5, "pointer-events": "none" }));
    }
    if (m.id === moving) {         // picked up
      marks.push(svgEl("circle", { cx: p[0], cy: p[1], r: 17, fill: "var(--accent)", "fill-opacity": 0.25,
        stroke: "var(--accent)", "stroke-width": 2, "pointer-events": "none" }));
    }
    // under the pick targets, which drawCurve put last
    const first = svg.querySelector(".pick-hit");
    marks.forEach(el => svg.insertBefore(el, first));
  });
  const describe = t => {
    if (mode === "slopes") {
      const sl = MM.slope || {};
      const v = `(${t.edge.vec.join(", ")})`;
      if (t.edge.id === sl.edit) return `end ${t.edge.name} ${v}: the one being changed — click to choose another`;
      if (t.edge.id === sl.dep) return `end ${t.edge.name} ${v}: the dependent end`;
      return `end ${t.edge.name} ${v}: click to ` + (sl.edit ? "make it the dependent end" : "change its direction");
    }
    if (mode === "move") {
      const mname = id => (data.curve.markings.find(m => m.id === id) || {}).name;
      if (t.kind === "mark") return t.marking.id === moving ? `${t.marking.name}: click to put it down`
        : `marking ${t.marking.name}: click to pick it up`;
      if (t.kind === "edge") return `${t.edge.kind === "end" ? "end" : "edge"} ${t.edge.name}: move ${mname(moving)} inside it`;
      return `this vertex: move ${mname(moving)} onto it`;
    }
    const name = t.kind === "edge" ? t.edge.name : t.marking.name;
    const what = t.kind === "edge" ? "end" : "marking";
    const leg = cfg.legs.includes(name), ev = cfg.evaluated.includes(name);
    const now = [leg ? "a leg" : "", ev ? "evaluated" : ""].filter(Boolean).join(" and ") || "not chosen";
    const act = mode === "legs" ? (leg ? "click to drop it as a leg" : "click to make it a leg")
      : (ev ? "click to free it" : "click to fix it at a point");
    return `${what} ${name}: ${now} — ${act}`;
  };
  const idle = mode === "legs" ? `Legs: ${cfg.legs.join(", ") || "none"}`
    : mode === "points" ? `Evaluated: ${cfg.evaluated.join(", ") || "none"}`
    : mode === "slopes" ? `Editing the slopes of ${data.name}`
    : `Moving markings of ${data.name}` + (moving ? `: ${(data.curve.markings.find(m => m.id === moving) || {}).name} picked up` : "");
  status.textContent = idle;
  [...drawn.edgePicks, ...drawn.markPicks, ...drawn.vertexPicks].forEach(t => {
    t.hit.addEventListener("pick-enter", () => { status.textContent = describe(t); });
    t.hit.addEventListener("pick-leave", () => { status.textContent = idle; });
    t.hit.addEventListener("pick-click", () => {
      if (mode === "slopes") {
        const sl = MM.slope || (MM.slope = {});
        if (!sl.edit || t.edge.id === sl.edit) { sl.edit = t.edge.id; sl.vec = null; sl.dep = null; }
        else sl.dep = t.edge.id === sl.dep ? null : t.edge.id;
        mmRenderSetup();
        return;
      }
      if (mode === "move") {
        if (t.kind === "mark") { MM.moveFrom = t.marking.id === moving ? null : t.marking.id; mmRenderSetup(); return; }
        if (!moving) return;
        MM.moveFrom = null;
        mmEdit(() => api("move_marking", id, moving, t.kind === "edge" ? "edge" : "vertex",
                         t.kind === "edge" ? t.edge.id : t.vertex.id), id);
        mmRenderSetup();
        return;
      }
      const name = t.kind === "edge" ? t.edge.name : t.marking.name;
      if (mode === "legs") setLeg(name, !cfg.legs.includes(name));
      else setEvaluated(name, !cfg.evaluated.includes(name));
    });
  });
}

// Slope editing: the end being changed in the accent, the dependent end in
// orange, and under the picture the new direction and Apply.
function mmSlopeMarks(box, data, drawn, typeId) {
  const sl = MM.slope || {};
  const ends = data.curve.edges.filter(e => e.kind === "end");
  [[sl.edit, "var(--accent)"], [sl.dep, "var(--warn)"]].forEach(([eid, col]) => {
    if (eid && drawn.lines[eid]) {
      drawn.lines[eid].setAttribute("stroke", col);
      drawn.lines[eid].setAttribute("stroke-width", 6);
    }
  });
  if (!sl.edit || !ends.some(e => e.id === sl.edit)) return;
  const edit = ends.find(e => e.id === sl.edit);
  if (!sl.dep || !ends.some(e => e.id === sl.dep)) {
    sl.dep = (ends.find(e => e.id !== sl.edit) || {}).id || null;
    if (sl.dep && drawn.lines[sl.dep]) {
      drawn.lines[sl.dep].setAttribute("stroke", "var(--warn)");
      drawn.lines[sl.dep].setAttribute("stroke-width", 6);
    }
  }
  const dep = ends.find(e => e.id === sl.dep);
  const form = document.createElement("div");
  form.className = "mm-slope";
  const vec = sl.vec || edit.vec;
  const num = (v, label) => {
    const i = document.createElement("input");
    i.type = "number"; i.step = "1"; i.value = v; i.setAttribute("aria-label", label);
    i.oninput = () => { sl.vec = [parseInt(xi.value || "0", 10), parseInt(yi.value || "0", 10)]; };
    return i;
  };
  const xi = num(vec[0], "new x"), yi = num(vec[1], "new y");
  const apply = document.createElement("button");
  apply.type = "button"; apply.className = "small primary"; apply.textContent = "Apply";
  apply.onclick = () => {
    const v = [parseInt(xi.value || "0", 10), parseInt(yi.value || "0", 10)];
    if (!dep) { alert("Click a second end to be the dependent one."); return; }
    const ok = mmEdit(() => api("edit_slopes", typeId, edit.id, v, dep.id), typeId);
    if (ok) { MM.slope = null; mmRenderSetup(); }
  };
  const lab = document.createElement("span");
  lab.innerHTML = `<b>${escapeHtml(edit.name)}</b> (${edit.vec.join(", ")}) → `;
  const depLab = document.createElement("span");
  depLab.className = "muted";
  depLab.innerHTML = dep ? `dependent: <b>${escapeHtml(dep.name)}</b> (${dep.vec.join(", ")})` : "click a dependent end";
  form.append(lab, "(", xi, ",", yi, ") ", apply, depLab);
  box.appendChild(form);
}

// Changing the library from here: each change can be undone, and the result
// sent to the main app (which offers to add it).
function mmEdit(change, typeId) {
  const before = { library: MM.library, extra: [...(MM.config.extra || [])], edited: !!MM.edited };
  try { change(); } catch (e) { alert(e.message); return false; }
  // the types added at the old type's walls belong to the old type
  (MM.config.extra || []).forEach(id => { try { api("delete", id); } catch (e) { /* gone */ } });
  MM.config.extra = [];
  MM.edited = true;           // "Reset points" then looks for points through the new type
  MM.undo = MM.undo || [];
  MM.undo.push(before);
  if (MM.undo.length > 50) MM.undo.shift();
  mmLibraryChanged(typeId);
  return true;
}
function mmLibraryChanged(typeId) {
  MM.library = api("save");
  MM.groups = api("moduli_groups");
  // a new slope changes the degree, so the type moves to another group: follow
  // it there, keeping the choices (the names are the same)
  const home = typeId && MM.groups.find(g => g.types.some(t => t.id === typeId));
  if (home && home.key !== MM.config.group) MM.config.group = home.key;
  // otherwise (an undo, say) a group where the chosen names still exist
  if (!MM.groups.some(g => g.key === MM.config.group)) {
    const fits = MM.groups.find(g => {
      const names = [...g.ends.map(e => e.name), ...g.markings];
      return MM.config.legs.every(n => names.includes(n)) && MM.config.evaluated.every(n => g.markings.includes(n));
    });
    if (fits) MM.config.group = fits.key;
  }
  // the names are kept, so the group usually is too; if not, start afresh
  if (!MM.groups.some(g => g.key === MM.config.group)) {
    const g = MM.groups[0];
    MM.config = mmDefaults(g) || { group: g.key, evaluated: [], legs: [], points: {}, base: g.types[0].id, extra: [] };
    mmGuard(() => mmConfigChanged(true));
  } else {
    try { mmConfigChanged(false); } catch (e) { mmGuard(() => mmConfigChanged(true)); }
  }
  mmAutosave();
}
function mmUndo() {
  if (!MM.undo || !MM.undo.length) return;
  const st = MM.undo.pop();
  api("load", typeof st === "string" ? st : st.library);
  if (typeof st !== "string") { MM.config.extra = st.extra; MM.edited = st.edited; }
  mmLibraryChanged(MM.config.base);
}
function mmEditBar() {
  const bar = document.createElement("div");
  bar.className = "mm-bar";
  const undo = document.createElement("button");
  undo.type = "button"; undo.className = "small"; undo.textContent = "↶ Undo";
  undo.disabled = !(MM.undo && MM.undo.length);
  undo.title = "Undo the last change to the type";
  undo.onclick = () => mmGuard(mmUndo);
  const send = document.createElement("button");
  send.type = "button"; send.className = "small"; send.textContent = "Send to main app";
  send.title = "The main app offers to add this library (now if it is open, else when it next opens)";
  send.onclick = () => mmSendToApp(send);
  bar.append(undo, send);
  return bar;
}
function mmSendToApp(btn) {
  try {
    localStorage.setItem(FROM_MODULI_KEY, JSON.stringify({ at: Date.now(), library: api("save") }));
    flashButton(btn, "Sent ✓");
  } catch (e) { alert("Could not send it: " + e.message); }
}

// The points' starting positions: those of the last starting point (or,
// for a session saved before they were kept, a fresh starting point's).
function mmStartPoints() {
  const cfg = MM.config;
  const ok = p => p && cfg.evaluated.every(m => p[m]);
  if (ok(MM.pointsStart)) return MM.pointsStart;
  const ini = api("moduli_initial", cfg);
  if (ok(ini.points)) MM.pointsStart = JSON.parse(JSON.stringify(ini.points));
  return ok(MM.pointsStart) ? MM.pointsStart : null;
}
function mmPointsMoved() {
  const st = MM.pointsStart, cfg = MM.config;
  if (!st || MM.edited) return true;      // unknown, or the type changed since
  return cfg.evaluated.some(m => !st[m] || st[m][0] !== cfg.points[m][0] || st[m][1] !== cfg.points[m][1]);
}
function mmResetPoints() {
  if (MM.edited) { mmPointsThroughType(); return; }
  const start = mmStartPoints();
  if (!start) return;
  MM.lastPre = null;          // a jump, not a move through walls
  MM.config.evaluated.forEach(m => { MM.config.points[m] = [...start[m]]; });
  MM.onWall = null; MM.onImage = null;      // the walls move with the points
  MM.frame = null;
  mmRenderSetup();
  mmSchedule({ regions: true });
}

// After the type was edited, the old starting points may have no curve of it
// through them: choose points that do -- over the current point of M_0,5 when
// the type has curves there, else a whole new starting point.
function mmPointsThroughType() {
  const cfg = MM.config;
  const r = MM.m ? api("moduli_points_through", cfg, cfg.base, MM.m) : { points: null };
  MM.lastPre = null;
  MM.onWall = null; MM.onImage = null; MM.frame = null;
  if (r.points) {
    cfg.points = r.points;
    MM.pointsStart = JSON.parse(JSON.stringify(r.points));
    MM.edited = false;
    mmRenderSetup();
    mmSchedule({ regions: true });
  } else {
    mmConfigChanged(true);     // new points and a new point of M_0,5
  }
  mmAutosave();
}

// The same for the point of M_0,5: where the last starting point put it.
const mmSameM = (a, b) => !!a && !!b && JSON.stringify([a.splits, a.lengths]) === JSON.stringify([b.splits, b.lengths]);
function mmStartM() {
  if (MM.mStart) return MM.mStart;
  const ini = api("moduli_initial", MM.config);
  if (ini.m) MM.mStart = JSON.parse(JSON.stringify(ini.m));
  return MM.mStart;
}
function mmMMoved() { return !MM.mStart || !mmSameM(MM.m, MM.mStart); }
function mmResetM() {
  const start = mmStartM();
  if (!start) return;
  mmPathPause();
  MM.m = JSON.parse(JSON.stringify(start));
  MM.lastPre = null;          // a jump, not a move through walls
  MM.onWall = null; MM.onImage = null;
  if (MM.m.splits.length === 2) MM.lastCone = coneKey(MM.m.splits[0], MM.m.splits[1]);
  const before = (MM.cycle || []).join();
  mmEnsureCycle();
  mmSchedule(MM.cycle.join() === before ? { pre: true, overview: true } : { regions: true });
}

function mmGuard(f) { try { f(); } catch (e) { reportError(e); } }

// --- naming --------------------------------------------------------------------
const mmLegName = i => MM.config.legs[i];
const mmRayName = r => "{" + mmLegName(r[0]) + "," + mmLegName(r[1]) + "}";
const mmConeName = c => c.map(mmRayName).join(" ");
const mmShort = s => { const x = Number(eval_frac(s)); return Number.isInteger(x) ? String(x) : (String(s).length <= 8 ? String(s) : x.toFixed(3)); };
function eval_frac(s) { const [p, q] = String(s).split("/"); return q ? Number(p) / Number(q) : Number(p); }
function mmSize(m) { return (m && m.lengths || []).reduce((a, x) => a + eval_frac(x), 0); }
function mmNice(x) {
  if (!(x > 0)) return 10;
  const e = Math.pow(10, Math.floor(Math.log10(x)));
  const f = x / e;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
}
// a float as a short exact decimal string, to `step`
function mmDec(x, step) {
  const d = Math.max(0, Math.ceil(-Math.log10(step)));
  const s = x.toFixed(Math.min(d, 12));
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

// --- computing ---------------------------------------------------------------------
function mmPreimage() {
  MM.pre = api("moduli_preimage", MM.config, MM.m);
  MM.m = MM.pre.m;
  if (mmCrossWalls()) MM.pre = api("moduli_preimage", MM.config, MM.m);
  MM.lastPre = { points: JSON.parse(JSON.stringify(MM.config.points)), m: MM.m,
                 ids: MM.pre.preimages.filter(p => p.full).map(p => p.type) };
  const ids = MM.pre.preimages.map(p => p.type);
  if (!ids.includes(MM.selected)) MM.selected = ids[0] || null;
  if (MM.m.splits.length === 2) MM.lastCone = coneKey(MM.m.splits[0], MM.m.splits[1]);
}

// A curve that was over the last point and is not over this one left through
// a wall: add the types on the wall and beyond it (the core builds them by
// contracting the edge that shrank and resolving the vertex it leaves), and
// work with them from now on. Returns whether any were added to the set.
function mmCrossWalls() {
  const last = MM.lastPre;
  if (!last || !last.ids.length) return false;
  const now = new Set(MM.pre.preimages.map(p => p.type));
  const gone = last.ids.filter(id => !now.has(id));
  if (!gone.length) return false;
  const cfg = MM.config, before = cfg.types.length, notes = [];
  gone.forEach(id => {
    const r = api("moduli_cross", cfg, id, last.points, last.m, MM.m);
    if (!r.edge) return;
    r.types.forEach(t => { if (t !== cfg.base && !cfg.extra.includes(t)) cfg.extra.push(t); });
    if (r.added.length) {
      const nm = (MM.check.types.find(t => t.id === id) || {}).name || id;
      notes.push(`crossed the wall where ${r.edge} of ${nm} shrinks to 0: added ${r.added.length} type${r.added.length === 1 ? "" : "s"}`);
    }
  });
  if (notes.length) MM.crossNote = { text: notes.join("; "), at: Date.now() };
  if (cfg.extra.length + 1 === before && !notes.length) return false;
  // the library and the set grew: the rest follows
  MM.library = api("save");
  MM.groups = api("moduli_groups");
  mmCandidates();
  MM.check = api("moduli_check", { group: cfg.group, evaluated: cfg.evaluated, legs: cfg.legs, types: cfg.types });
  mmRegions();
  mmOverview(true);
  // not while a finger is dragging: on a narrow screen the setup sits above
  // the chart, and a taller setup would slide the chart under it
  if (MM.dragging) MM.setupStale = true; else mmRenderSetup();
  return true;
}

function mmRecomputeAll() {
  if (!MM.m) return;
  mmEnsureCycle();
  mmRegions();
  mmOverview(true);
  mmPreimage();
  mmDrawAll();
  mmPathUpdate();
}
function mmRegions(withImages = true) {
  const cones = cycleCones(MM.cycle).map(k => k.split("|").map(rayOf));
  MM.regions = {};
  api("moduli_regions", MM.config, cones, String(MM.R)).forEach(c => {
    MM.regions[coneKey(c.cone[0], c.cone[1])] = c.regions;
  });
  // the images of the types that are not full-dimensional: slower, so not
  // redone on every frame of a drag of the points (they follow on release)
  if (withImages) MM.images = api("moduli_images", MM.config, String(MM.R));
}
function mmOverview(force) {
  const s = mmSize(MM.m) || MM.R / 2;
  if (!force && MM.overview && Math.abs(s - MM.overviewSize) < MM.R / 400) return;
  MM.overview = api("moduli_overview", MM.config, mmDec(s, MM.R / 4000));
  MM.overviewSize = s;
}

// Coalesce work into one per frame: a drag fires far more often than that.
const mmPending = { regions: false, overview: false, pre: false, quick: false };
let mmRaf = 0;
function mmSchedule(what) {
  Object.assign(mmPending, what);
  if (mmRaf) return;
  mmRaf = requestAnimationFrame(() => {
    mmRaf = 0;
    const p = { ...mmPending };
    mmPending.regions = mmPending.overview = mmPending.pre = mmPending.quick = false;
    mmGuard(() => {
      if (p.regions) mmRegions(!p.quick);
      if (p.overview || p.regions) mmOverview(p.regions);
      if (p.pre || p.regions) mmPreimage();
      mmDrawAll();
      if (p.regions) mmPathUpdate();
      mmAutosave();
    });
  });
}

// --- the chart: five cones around the apex --------------------------------------
const CH = { cx: 300, cy: 204, rho: 168 };
const chU = i => { const a = (90 + 72 * i) * Math.PI / 180; return [Math.cos(a), -Math.sin(a)]; };
const chK = () => CH.rho / MM.R;
const chScreen = v => [CH.cx + v[0] * chK(), CH.cy + v[1] * chK()];
const chPlane = q => [(q[0] - CH.cx) / chK(), (q[1] - CH.cy) / chK()];

function mmEnsureCycle() {
  if (!MM.m) return;
  const sp = MM.m.splits.map(rk);
  const has = c => sp.length === 2 ? cycleCones(c).includes(sp.slice().sort().join("|"))
                                   : sp.every(r => c.includes(r));
  if (MM.cycle && has(MM.cycle)) return;
  // prefer a cycle sharing the cone the point came from
  const cands = MM_CYCLES.filter(has);
  const pick = (MM.lastCone && cands.find(c => cycleCones(c).includes(MM.lastCone))) || cands[0];
  MM.cycle = pick ? [...pick] : [...MM_CYCLES[0]];
}

// the plane position of a point of M_0,5 in the current chart
function mmPlaneOf(m, cycle) {
  let v = [0, 0];
  m.splits.forEach((s, i) => {
    const idx = cycle.indexOf(rk(s));
    if (idx < 0) return;
    const u = chU(idx), L = eval_frac(m.lengths[i]);
    v = [v[0] + L * u[0], v[1] + L * u[1]];
  });
  return v;
}

// the point of M_0,5 at a plane position of the chart
function mmPointAt(v, cycle) {
  const ang = ((Math.atan2(-v[1], v[0]) * 180 / Math.PI) % 360 + 360) % 360;
  const i = Math.floor((((ang - 90) % 360) + 360) % 360 / 72) % 5, j = (i + 1) % 5;
  const ui = chU(i), uj = chU(j);
  const det = ui[0] * uj[1] - ui[1] * uj[0];
  let a = (v[0] * uj[1] - v[1] * uj[0]) / det, b = (ui[0] * v[1] - ui[1] * v[0]) / det;
  a = Math.max(0, a); b = Math.max(0, b);
  const step = MM.R / 2000;
  const splits = [], lengths = [];
  [[cycle[i], a], [cycle[j], b]].forEach(([r, L]) => {
    if (L >= step / 2) { splits.push(rayOf(r)); lengths.push(mmDec(L, step)); }
  });
  return { splits, lengths, cone: coneKey(rayOf(cycle[i]), rayOf(cycle[j])), a, b, i };
}

let mmChartHits = { walls: [], rays: [], images: [] };

function mmDrawChart() {
  const svg = clearSvg("mm-chart");
  const moved = MM.m ? mmMMoved() : false;
  const rb = document.getElementById("mm-reset-m");
  if (rb) rb.disabled = !moved;
  const sb = [...document.querySelectorAll("#mm-setup button")].find(b => b.textContent === "Reset M₀,₅ point");
  if (sb) sb.disabled = !moved;
  mmChartHits = { walls: [], rays: [], images: [] };
  const legendEl = document.getElementById("mm-chart-legend");
  if (legendEl) legendEl.hidden = true;
  if (!MM.m || !MM.cycle) return;
  const C = [CH.cx, CH.cy];
  const P = [0, 1, 2, 3, 4].map(i => chScreen([chU(i)[0] * MM.R, chU(i)[1] * MM.R]));
  svg.appendChild(svgEl("polygon", { points: P.map(p => p.join(",")).join(" "),
    fill: "color-mix(in srgb, var(--ink) 3%, transparent)", stroke: "var(--line)", "stroke-width": 1 }));
  // regions, shaded: overlaps are darker
  const cones = cycleCones(MM.cycle);
  const toScreen = (key, ab) => {
    const [r1, r2] = key.split("|");
    const v = [0, 0];
    [[r1, ab[0]], [r2, ab[1]]].forEach(([r, L]) => { const u = chU(MM.cycle.indexOf(r)); v[0] += L * u[0]; v[1] += L * u[1]; });
    return chScreen(v);
  };
  cones.forEach(key => (MM.regions[key] || []).forEach(reg => {
    const poly = svgEl("polygon", { points: reg.polygon.map(q => toScreen(key, q).join(",")).join(" "),
      fill: "var(--accent)", "fill-opacity": 0.11, stroke: "none" });
    const t = svgEl("title", {}); t.textContent = `${reg.name} (mult ${reg.multiplicity})`;
    poly.appendChild(t);
    svg.appendChild(poly);
  }));
  // walls
  cones.forEach(key => (MM.regions[key] || []).forEach(reg => reg.walls.forEach(w => {
    const a = toScreen(key, w.from), b = toScreen(key, w.to);
    const line = svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "var(--ink)",
      "stroke-width": 1.4, "stroke-opacity": 0.75, "stroke-linecap": "round" });
    const t = svgEl("title", {}); t.textContent = `wall: ${w.edge_name} → 0 in ${reg.name}`;
    line.appendChild(t);
    svg.appendChild(line);
    mmChartHits.walls.push({ a, b, cone: key, type: reg.type, edge: w.edge, name: reg.name, edgeName: w.edge_name });
  })));
  mmDrawImages(svg, toScreen);
  // rays, with their names, and the page-turners on the current cone's rays
  const cur = MM.lastCone ? MM.lastCone.split("|") : [];
  MM.cycle.forEach((r, i) => {
    const p = P[i], u = chU(i);
    svg.appendChild(svgEl("line", { x1: C[0], y1: C[1], x2: p[0], y2: p[1], stroke: "var(--muted)", "stroke-width": 2 }));
    mmChartHits.rays.push({ a: C, b: p, ray: r, i });
    const lbl = text(p[0] + u[0] * 16, p[1] + u[1] * 16 + 4, mmRayName(rayOf(r)), "var(--ink)");
    lbl.setAttribute("text-anchor", Math.abs(u[0]) < 0.3 ? "middle" : u[0] > 0 ? "start" : "end");
    lbl.setAttribute("font-size", "13");
    svg.appendChild(lbl);
    if (cur.includes(r) && cycleCones(MM.cycle).includes(MM.lastCone)) {
      const inCur = cycleCones(MM.cycle).indexOf(MM.lastCone);
      const side = inCur === i ? -1 : 1;   // the page to turn is on the other side of the ray
      const perp = [-u[1] * side, u[0] * side];
      const q = [C[0] + (p[0] - C[0]) * 0.62 + perp[0] * 26, C[1] + (p[1] - C[1]) * 0.62 + perp[1] * 26];
      const g = svgEl("g", { class: "mm-flip", tabindex: 0, role: "button",
        "aria-label": "Show the other cone at " + mmRayName(rayOf(r)) });
      g.appendChild(svgEl("circle", { cx: q[0], cy: q[1], r: 13, fill: "var(--panel)", stroke: "var(--accent)", "stroke-width": 1.5 }));
      const tx = text(q[0], q[1] + 5, "⇄", "var(--accent)");
      tx.setAttribute("text-anchor", "middle"); tx.setAttribute("font-size", "15");
      g.appendChild(tx);
      const tt = svgEl("title", {}); tt.textContent = "Turn the page: the other cone at " + mmRayName(rayOf(r));
      g.appendChild(tt);
      // a tap turns the page (the chart's own handlers tell a tap from a drag:
      // a finger landing near the button would otherwise always hit it)
      g.__flip = () => mmGuard(() => mmFlip(r));
      g.addEventListener("keydown", ev => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); g.__flip(); }
      });
      svg.appendChild(g);
    }
  });
  // the path
  if (MM.path.from && MM.path.cycle && MM.path.cycle.join() === MM.cycle.join()) {
    const a = chScreen(MM.path.from);
    if (MM.path.to) {
      const b = chScreen(MM.path.to);
      svg.appendChild(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "var(--warn)",
        "stroke-width": 2, "stroke-dasharray": "6 4" }));
      svg.appendChild(svgEl("circle", { cx: b[0], cy: b[1], r: 4, fill: "var(--warn)" }));
    }
    svg.appendChild(svgEl("circle", { cx: a[0], cy: a[1], r: 4, fill: "none", stroke: "var(--warn)", "stroke-width": 2 }));
  }
  // the point
  const q = chScreen(mmPlaneOf(MM.m, MM.cycle));
  svg.appendChild(svgEl("circle", { cx: q[0], cy: q[1], r: 7, fill: "var(--accent)", stroke: "var(--panel)", "stroke-width": 2 }));
  const where = document.getElementById("mm-where");
  const sp = MM.m.splits;
  where.textContent = MM.onImage ? `on the image of ${MM.onImage.name} (orange)`
    : MM.onWall ? `on the wall where ${MM.onWall.edge} of ${MM.onWall.name} shrinks to 0`
    : sp.length === 2 ? `cone ${mmConeName(sp)}: ${sp.map((s, i) => mmRayName(s) + " = " + mmShort(MM.m.lengths[i])).join(", ")}`
    : sp.length === 1 ? `on the ray ${mmRayName(sp[0])} = ${mmShort(MM.m.lengths[0])}` : "at the apex";
  where.title = where.textContent;
  document.getElementById("mm-chart-note").textContent = `(a + b ≤ ${mmShort(String(MM.R))})`;
}

// The images of types that are not full-dimensional, in orange: segments
// (or points, regions) where they have curves over the points, though not
// finitely many. Snapping lands on them exactly.
function mmDrawImages(svg, toScreen) {
  const shown = [];
  (MM.images || []).forEach(im => {
    let pts = null;
    if (im.cone.length === 2) {
      const key = coneKey(im.cone[0], im.cone[1]);
      if (!cycleCones(MM.cycle).includes(key)) return;
      // the image's coordinates follow the cone's sorted rays, as toScreen does
      pts = im.points.map(q => toScreen(key, q));
    } else if (im.cone.length === 1) {
      const idx = MM.cycle.indexOf(rk(im.cone[0]));
      if (idx < 0) return;
      const u = chU(idx);
      pts = im.points.map(q => chScreen([u[0] * q[0], u[1] * q[0]]));
    } else pts = [[CH.cx, CH.cy]];
    const tip = `${im.name}: ${im.reason}`;
    let el;
    if (im.kind === "region") {
      el = svgEl("polygon", { points: pts.map(q => q.join(",")).join(" "), fill: "var(--warn)", "fill-opacity": 0.22,
        stroke: "var(--warn)", "stroke-width": 2 });
    } else if (im.kind === "segment") {
      el = svgEl("line", { x1: pts[0][0], y1: pts[0][1], x2: pts[1][0], y2: pts[1][1], stroke: "var(--warn)",
        "stroke-width": 5, "stroke-linecap": "round", "stroke-opacity": 0.9 });
    } else {
      el = svgEl("circle", { cx: pts[0][0], cy: pts[0][1], r: 6, fill: "var(--warn)" });
    }
    const t = svgEl("title", {}); t.textContent = tip;
    el.appendChild(t);
    svg.appendChild(el);
    if (im.kind !== "region") {
      mmChartHits.images.push({ a: pts[0], b: pts[pts.length - 1], type: im.type, name: im.name, kind: im.kind });
    }
    shown.push(im);
  });
  const legend = document.getElementById("mm-chart-legend");
  if (legend && shown.length) {
    legend.hidden = false;
    legend.innerHTML = `<span><span class="sub-swatch" style="background:var(--warn)"></span>
      where ${shown.length === 1 ? escapeHtml(shown[0].name) + ", a type" : shown.length + " types"} that ${shown.length === 1 ? "is" : "are"}
      not full-dimensional ${shown.length === 1 ? "has" : "have"} curves over the points — reached only by snapping onto it</span>`;
  }
}

// The other cone at a ray of the current cone: the chart becomes the 5-cycle
// through it, the current cone and the current cone's other neighbour, turned
// so the current cone stays where it is.
function mmFlip(r) {
  const c = MM.cycle, i = c.indexOf(r);
  const cur = cycleCones(c).indexOf(MM.lastCone);
  if (i < 0 || cur < 0) return;
  // the current cone is {c[cur], c[cur+1]}; r is one of them
  const other = c[cur] === r ? c[(cur + 1) % 5] : c[cur];
  const behind = c[cur] === r ? c[(cur + 4) % 5] : c[(cur + 2) % 5];      // the page now shown past r
  const beyond = c[cur] === r ? c[(cur + 2) % 5] : c[(cur + 4) % 5];      // kept past `other`
  const third = MM_RAYS.map(rk).find(x => disjoint(rayOf(x), rayOf(r)) && x !== other && x !== behind);
  const want = [third, r, other, beyond];
  const cyc = MM_CYCLES.find(cy => want.every(x => cy.includes(x)) &&
    [[third, r], [r, other], [other, beyond]].every(([x, y]) => {
      const a = cy.indexOf(x), b = cy.indexOf(y);
      return (a + 1) % 5 === b || (b + 1) % 5 === a;
    }));
  if (!cyc) return;
  // turn the new cycle so r and other keep their places
  for (const seq of [cyc, [...cyc].reverse()]) {
    for (let s = 0; s < 5; s++) {
      const rot = seq.map((_, k) => seq[(k + s) % 5]);
      if (rot[i] === r && rot[c.indexOf(other)] === other) {
        MM.cycle = rot;
        mmSchedule({ regions: true });
        return;
      }
    }
  }
}

function mmWireChart() {
  const svg = document.getElementById("mm-chart");
  let dragging = false;
  const toSvg = ev => {
    const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    const q = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [q.x, q.y];
  };
  const moveTo = ev => {
    if (!MM.m || !MM.cycle) return;
    let q = toSvg(ev);
    const snap = document.getElementById("mm-snap").checked;
    if (snap) {
      const hit = mmNearest(q);
      if (hit && hit.kind === "wall") {
        const p = mmPointAt(chPlane(hit.q), MM.cycle);
        if (p.cone === hit.wall.cone) {
          const [r1] = hit.wall.cone.split("|");
          const v = chPlane(hit.q), i = MM.cycle.indexOf(r1), j = MM.cycle.indexOf(hit.wall.cone.split("|")[1]);
          const ui = chU(i), uj = chU(j), det = ui[0] * uj[1] - ui[1] * uj[0];
          const a = (v[0] * uj[1] - v[1] * uj[0]) / det, b = (ui[0] * v[1] - ui[1] * v[0]) / det;
          MM.m = api("moduli_on_wall", MM.config, hit.wall.cone.split("|").map(rayOf), hit.wall.type,
                     hit.wall.edge, String(a), String(b));
          MM.onWall = { name: hit.wall.name, edge: hit.wall.edgeName };
          mmSchedule({ pre: true, overview: true });
          return;
        }
      } else if (hit && hit.kind === "image") {
        MM.m = api("moduli_on_image", MM.config, hit.image.type, String(MM.R), hit.frac.toFixed(6));
        MM.onWall = null;
        MM.onImage = { name: hit.image.name };
        if (MM.m.splits.length === 2) MM.lastCone = coneKey(MM.m.splits[0], MM.m.splits[1]);
        mmSchedule({ pre: true, overview: true });
        return;
      } else if (hit && hit.kind === "ray") {
        q = hit.q;
      }
    }
    const p = mmPointAt(chPlane(q), MM.cycle);
    MM.m = { splits: p.splits, lengths: p.lengths };
    MM.onWall = null;
    MM.onImage = null;
    if (p.splits.length === 2) MM.lastCone = p.cone;
    mmSchedule({ pre: true, overview: true });
  };
  // Down on a page-turner (⇄) is a tap until the pointer travels: lifted in
  // place it turns the page, moved it drags the point like anywhere else.
  let onFlip = null;
  svg.addEventListener("pointerdown", ev => {
    if (ev.button > 0) return;
    mmPathPause();
    dragging = MM.dragging = true;
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic */ }
    ev.preventDefault();
    const flip = ev.target.closest && ev.target.closest(".mm-flip");
    if (flip) { onFlip = { el: flip, x: ev.clientX, y: ev.clientY }; return; }
    mmGuard(() => moveTo(ev));
  });
  svg.addEventListener("pointermove", ev => {
    if (!dragging) return;
    if (onFlip) {
      if (Math.hypot(ev.clientX - onFlip.x, ev.clientY - onFlip.y) < 8) return;
      onFlip = null;
    }
    mmGuard(() => moveTo(ev));
  });
  const end = ev => {
    if (onFlip && ev.type === "pointerup") onFlip.el.__flip();
    onFlip = null;
    dragging = MM.dragging = false;
    MM.dragEndAt = Date.now();
    // after the click a short touch drag still produces, so that click lands
    // where the finger was, not on whatever a taller setup moved there
    if (MM.setupStale) setTimeout(() => { MM.setupStale = false; mmGuard(mmRenderSetup); }, 350);
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
}

// the nearest wall or ray within reach of q (in picture units)
function mmNearest(q) {
  let best = null;
  const near = (a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2));
    const p = [a[0] + t * dx, a[1] + t * dy];
    return { p, d: Math.hypot(q[0] - p[0], q[1] - p[1]) };
  };
  mmChartHits.walls.forEach(w => {
    const n = near(w.a, w.b);
    if (n.d < 12 && (!best || n.d < best.d)) best = { kind: "wall", wall: w, q: n.p, d: n.d };
  });
  mmChartHits.rays.forEach(r => {
    const n = near(r.a, r.b);
    if (n.d < 9 && (!best || n.d < best.d - 2)) best = { kind: "ray", ray: r, q: n.p, d: n.d };
  });
  // the images of types that are not full-dimensional win: there is nothing
  // to see near them, only exactly on them
  mmChartHits.images.forEach(im => {
    const n = near(im.a, im.b);
    if (n.d < 14 && (!best || best.kind !== "image" || n.d < best.d)) {
      const L = Math.hypot(im.b[0] - im.a[0], im.b[1] - im.a[1]);
      best = { kind: "image", image: im, q: n.p, d: n.d,
               frac: L ? Math.hypot(n.p[0] - im.a[0], n.p[1] - im.a[1]) / L : 0 };
    }
  });
  return best;
}

function mmSetRange(R) {
  MM.R = mmNice(R * 0.999);
  mmSchedule({ regions: true });
}

// --- the overview: the Petersen graph at one size ----------------------------------
const OV = { cx: 300, cy: 196, outer: 160, inner: 72 };
const OV_OUTER = [[0, 1], [2, 3], [0, 4], [1, 2], [3, 4]];
const OV_INNER = OV_OUTER.map(o => MM_RAYS.find(r => disjoint(r, o) && !OV_OUTER.some(x => rk(x) === rk(r))));
function ovPos(r) {
  let i = OV_OUTER.findIndex(x => rk(x) === rk(r)), rad = OV.outer;
  if (i < 0) { i = OV_INNER.findIndex(x => rk(x) === rk(r)); rad = OV.inner; }
  const u = chU(i);
  return [OV.cx + rad * u[0], OV.cy + rad * u[1]];
}
const OV_COLORS = ["#b8860b", "#8e5bd8", "#d62728", "#1f77b4", "#ff7f0e", "#17becf"];

function mmDrawOverview() {
  const svg = clearSvg("mm-overview");
  const legend = document.getElementById("mm-legend");
  legend.innerHTML = ""; legend.hidden = true;
  if (!MM.m || !MM.overview) return;
  // the count that covers most of the graph gets the accent
  const total = {};
  MM.overview.forEach(c => c.counts.forEach((n, i) => { total[n] = (total[n] || 0) + c.breaks[i + 1] - c.breaks[i]; }));
  const values = Object.keys(total).map(Number).sort((a, b) => total[b] - total[a]);
  const colorOf = {};
  let k = 0;
  values.forEach(v => { colorOf[v] = v === 0 ? "var(--line)" : (v === values.filter(x => x).at(0) ? "var(--accent)" : OV_COLORS[k++ % OV_COLORS.length]); });
  MM.overview.forEach(c => {
    const a = ovPos(c.cone[0]), b = ovPos(c.cone[1]);
    const at = t => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    c.counts.forEach((n, i) => {
      const p = at(c.breaks[i]), q = at(c.breaks[i + 1]);
      svg.appendChild(svgEl("line", { x1: p[0], y1: p[1], x2: q[0], y2: q[1], stroke: colorOf[n],
        "stroke-width": n ? 5 : 3, "stroke-linecap": "butt" }));
    });
    c.breaks.slice(1, -1).forEach(t => {
      const p = at(t), dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
      svg.appendChild(svgEl("line", { x1: p[0] - dy / L * 7, y1: p[1] + dx / L * 7, x2: p[0] + dy / L * 7, y2: p[1] - dx / L * 7,
        stroke: "var(--ink)", "stroke-width": 1.5 }));
    });
    const hit = svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "transparent", "stroke-width": 18,
      class: "mm-ov-hit", "data-cone": coneKey(c.cone[0], c.cone[1]) });
    const tt = svgEl("title", {}); tt.textContent = "Go to the cone " + mmConeName(c.cone);
    hit.appendChild(tt);
    hit.addEventListener("click", ev => mmGuard(() => mmJumpToCone(c.cone, a, b, ev)));
    svg.appendChild(hit);
  });
  MM_RAYS.forEach(r => {
    const p = ovPos(r);
    svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: 4, fill: "var(--ink)" }));
    const outer = OV_OUTER.some(x => rk(x) === rk(r));
    const dx = p[0] - OV.cx, dy = p[1] - OV.cy, L = Math.hypot(dx, dy) || 1;
    const off = outer ? 16 : -2;
    const lbl = text(p[0] + dx / L * off + (outer ? 0 : 8), p[1] + dy / L * off + (outer ? 4 : -8), mmRayName(r), "var(--muted)");
    lbl.setAttribute("text-anchor", outer ? (Math.abs(dx) < 20 ? "middle" : dx > 0 ? "start" : "end") : "start");
    lbl.setAttribute("font-size", "11");
    lbl.setAttribute("pointer-events", "none");
    svg.appendChild(lbl);
  });
  // where the images of types that are not full-dimensional meet a + b = s
  const s0 = mmSize(MM.m) || MM.R / 2;
  (MM.images || []).forEach(im => {
    let at = null;
    if (im.cone.length === 2) {
      const sum = q => q[0] + q[1];
      const P = im.points[0], Q = im.points[im.points.length - 1];
      const d = sum(Q) - sum(P);
      const u = Math.abs(d) < 1e-12 ? (Math.abs(sum(P) - s0) < MM.R / 400 ? 0 : -1) : (s0 - sum(P)) / d;
      if (u < -1e-9 || u > 1 + 1e-9) return;
      const pa = P[0] + u * (Q[0] - P[0]), pb = P[1] + u * (Q[1] - P[1]);
      const A = ovPos(im.cone[0]), B = ovPos(im.cone[1]), t = pb / (pa + pb);
      at = [A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t];
    } else if (im.cone.length === 1) {
      const lo = im.points[0][0], hi = im.points[im.points.length - 1][0];
      if (s0 < Math.min(lo, hi) - 1e-9 || s0 > Math.max(lo, hi) + 1e-9) return;
      at = ovPos(im.cone[0]);
    }
    if (!at) return;
    const dot = svgEl("circle", { cx: at[0], cy: at[1], r: 6, fill: "none", stroke: "var(--warn)", "stroke-width": 3, "pointer-events": "none" });
    const tt = svgEl("title", {}); tt.textContent = `${im.name}: ${im.reason}`;
    dot.appendChild(tt);
    svg.appendChild(dot);
  });
  // the point
  const sp = MM.m.splits;
  let q = null;
  if (sp.length === 2) {
    const a = ovPos(sp[0]), b = ovPos(sp[1]);
    const la = eval_frac(MM.m.lengths[0]), lb = eval_frac(MM.m.lengths[1]), t = lb / (la + lb);
    q = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  } else if (sp.length === 1) q = ovPos(sp[0]);
  if (q) svg.appendChild(svgEl("circle", { cx: q[0], cy: q[1], r: 7, fill: "var(--accent)", stroke: "var(--panel)", "stroke-width": 2, "pointer-events": "none" }));
  // legend
  legend.hidden = false;
  values.sort((a, b) => a - b).forEach(v => {
    const item = document.createElement("span");
    const sw = document.createElement("span");
    sw.className = "sub-swatch"; sw.style.background = colorOf[v];
    item.append(sw, document.createTextNode("count " + v));
    legend.appendChild(item);
  });
  const size = document.getElementById("mm-size");
  size.value = Math.round(Math.min(1, mmSize(MM.m) / MM.R) * 1000);
  document.getElementById("mm-size-val").textContent = mmShort(mmDec(mmSize(MM.m), MM.R / 1000));
}

function mmJumpToCone(cone, a, b, ev) {
  if (Date.now() - (MM.dragEndAt || 0) < 500) return;    // the tail of a drag, not a click
  const svg = document.getElementById("mm-overview");
  const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
  const q = pt.matrixTransform(svg.getScreenCTM().inverse());
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const t = Math.max(0.02, Math.min(0.98, ((q.x - a[0]) * dx + (q.y - a[1]) * dy) / (dx * dx + dy * dy)));
  const s = mmSize(MM.m) || MM.R / 2;
  MM.onWall = null;
  MM.onImage = null;
  MM.m = { splits: cone, lengths: [mmDec(s * (1 - t), MM.R / 2000), mmDec(s * t, MM.R / 2000)] };
  MM.lastCone = coneKey(cone[0], cone[1]);
  MM.lastPre = null;          // a jump, not a move through walls
  if (!cycleCones(MM.cycle).includes(MM.lastCone)) {
    MM.cycle = null; mmEnsureCycle();
    mmSchedule({ regions: true });
  } else mmSchedule({ pre: true });
}

function mmSizeInput(ev) {
  if (!MM.m) return;
  const s = Math.max(MM.R / 1000, ev.target.value / 1000 * MM.R);
  const old = mmSize(MM.m);
  let m;
  if (old > 0) m = { splits: MM.m.splits, lengths: MM.m.lengths.map(L => mmDec(eval_frac(L) * s / old, MM.R / 2000)) };
  else {
    const [r1, r2] = (MM.lastCone || coneKey(...MM_CONES[0])).split("|");
    m = { splits: [rayOf(r1), rayOf(r2)], lengths: [mmDec(s / 2, MM.R / 2000), mmDec(s / 2, MM.R / 2000)] };
  }
  MM.onWall = null;
  MM.onImage = null;
  MM.m = m;
  mmSchedule({ pre: true, overview: true });
}

// --- the curves over the point -----------------------------------------------------
function mmWireFigure() {
  const svg = document.getElementById("mm-figure");
  let drag = null;
  const toSvg = ev => {
    const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    const q = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [q.x, q.y];
  };
  svg.addEventListener("pointerdown", ev => {
    const h = ev.target.closest && ev.target.closest("[data-handle]");
    if (!h || !MM.figT) return;
    mmPathPause();
    drag = { name: h.dataset.handle, T: MM.figT };
    MM.frame = MM.figT;      // the picture holds still while a point moves
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic */ }
    ev.preventDefault();
  });
  svg.addEventListener("pointermove", ev => {
    if (!drag) return;
    const q = toSvg(ev), p = drag.T.params;
    const x = p.minx + (q[0] - p.ox) / p.s, y = p.miny + (VBH - q[1] - p.oy) / p.s;
    const step = Math.pow(10, Math.floor(Math.log10((VBW - 2 * PAD) / p.s / 400)));
    MM.config.points[drag.name] = [mmDec(Math.round(x / step) * step, step), mmDec(Math.round(y / step) * step, step)];
    MM.onWall = null;       // the walls move with the points
    MM.onImage = null;
    mmSchedule({ regions: true, quick: true });
  });
  const end = () => {
    if (!drag) return;
    drag = null;
    MM.frame = null;
    mmRenderSetup();
    mmSchedule({ regions: true });
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
}

function mmDrawFigure() {
  const rb = document.getElementById("mm-reset-points");
  if (rb) rb.disabled = !mmPointsMoved();
  const note = document.getElementById("mm-figure-note");
  const name = document.getElementById("mm-curve-name");
  const pts = MM.config.evaluated.map(m => MM.config.points[m].map(eval_frac));
  const sel = MM.pre && MM.pre.preimages.find(p => p.type === MM.selected);
  let T = MM.frame;
  let svg;
  if (sel) {
    const pic = sel.picture;
    if (!T) {
      const all = [...pts];
      pic.edges.forEach(e => { all.push(e.from); all.push(e.to); });
      pic.vertices.forEach(v => all.push([v.x, v.y]));
      T = fitTransform(all);
    }
    svg = drawCurve({ curve: pic }, { svgId: "mm-figure", transform: T }).svg;
    name.textContent = sel.name + " · " + mmMultText(sel);
    note.textContent = "Drag a ringed point to move it.";
    note.classList.remove("warn");
  } else {
    if (!T) {
      const all = [...pts];
      if (all.length === 1) all.push([all[0][0] + 1, all[0][1] + 1], [all[0][0] - 1, all[0][1] - 1]);
      T = fitTransform(all.length ? all : [[0, 0], [1, 1]]);
    }
    svg = clearSvg("mm-figure");
    name.textContent = "";
    note.textContent = "No curve of the library lies over this point.";
    note.classList.add("warn");
  }
  MM.figT = T;
  MM.config.evaluated.forEach((m, i) => {
    const q = T(pts[i]);
    svg.appendChild(svgEl("circle", { cx: q[0], cy: q[1], r: 11, fill: "var(--accent)", "fill-opacity": 0.18,
      stroke: "var(--accent)", "stroke-width": 2, "pointer-events": "none" }));
    if (!sel) {
      const t = text(q[0] + 14, q[1] - 10, m, "var(--ink)");
      svg.appendChild(t);
    }
    const hit = svgEl("circle", { cx: q[0], cy: q[1], r: 20, fill: "transparent", "data-handle": m, class: "mm-handle" });
    const tt = svgEl("title", {}); tt.textContent = "Drag to move " + m;
    hit.appendChild(tt);
    svg.appendChild(hit);
  });
}

// how a curve over the point counts
function mmMultText(p) {
  if (p.multiplicity) return "mult " + p.multiplicity;
  if (p.fibre) return `one of a ${p.fibre}-dimensional family (not counted)`;
  return "on a wall";
}

let mmGalleryTimer = null;
function mmDrawGallery(now) {
  clearTimeout(mmGalleryTimer);
  const run = () => mmGuard(() => {
    const box = document.getElementById("mm-gallery");
    box.innerHTML = "";
    const pre = MM.pre;
    const count = document.getElementById("mm-count");
    if (!pre) { count.textContent = ""; return; }
    const n = pre.preimages.length;
    count.textContent = `weighted count ${pre.count} · ${n} curve${n === 1 ? "" : "s"}` +
      (pre.on_wall ? " · on a wall" : "") + (MM.onImage ? " · on an orange image" : "");
    const notes = pre.notes.map(x => `${x.name}: ${x.note}`);
    if (MM.onWall && !pre.preimages.some(p => !p.full)) {
      notes.unshift(`On a wall: here ${MM.onWall.edge} of ${MM.onWall.name} has length 0. The curve of lower ` +
        `dimension on the wall (${MM.onWall.name} with ${MM.onWall.edge} contracted) is not in the library, ` +
        "so it is not listed; the count is lower here than on either side.");
    }
    if (MM.crossNote && Date.now() - MM.crossNote.at < 15000) notes.unshift("Just now: " + MM.crossNote.text + ".");
    if ((MM.config.extra || []).length) notes.push(`${MM.config.extra.length} type${MM.config.extra.length === 1 ? "" : "s"} added at walls so far.`);
    document.getElementById("mm-notes").textContent = notes.join(" ");
    pre.preimages.forEach((p, i) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "mm-card" + (p.type === MM.selected ? " selected" : "");
      const id = "mm-th-" + i;
      const svg = document.createElementNS(SVGNS, "svg");
      svg.id = id; svg.setAttribute("viewBox", `0 0 ${VBW} ${VBH}`);
      card.appendChild(svg);
      const cap = document.createElement("span");
      cap.innerHTML = `${escapeHtml(p.name)} <span class="muted">${mmMultText(p)}</span>`;
      card.appendChild(cap);
      card.onclick = () => { MM.selected = p.type; mmDrawFigure(); mmDrawGallery(true); mmAutosave(); };
      box.appendChild(card);
      drawCurve({ curve: p.picture }, { svgId: id, labels: false });
    });
  });
  if (now) run(); else mmGalleryTimer = setTimeout(run, 140);
}

function mmDrawAll() {
  mmDrawChart();
  mmDrawOverview();
  mmDrawFigure();
  mmDrawGallery(!mmRaf && !MM.path.playing);
}

function mmClearViews() {
  ["mm-chart", "mm-overview", "mm-figure"].forEach(id => clearSvg(id));
  document.getElementById("mm-gallery").innerHTML = "";
  document.getElementById("mm-count").textContent = "";
  document.getElementById("mm-notes").textContent = "";
  document.getElementById("mm-where").textContent = "";
  document.getElementById("mm-curve-name").textContent = "";
  document.getElementById("mm-figure-note").textContent = "";
  document.getElementById("mm-legend").hidden = true;
}

// --- animate a path ------------------------------------------------------------------
function mmPathEnd(which) {
  if (!MM.m) return;
  const v = mmPlaneOf(MM.m, MM.cycle);
  if (which === "from" || !MM.path.from) {
    MM.path.from = v; MM.path.cycle = [...MM.cycle];
    if (which === "from") MM.path.to = null;
  }
  if (which === "to") {
    if (MM.path.cycle.join() !== MM.cycle.join()) {
      alert("The start was set in another chart (a page was turned since). Set the start again in this one.");
      return;
    }
    MM.path.to = v;
  }
  MM.path.t = 0;
  mmPathUpdate();
  mmDrawChart();
  mmAutosave();
}

function mmPathClear() {
  mmPathPause();
  MM.path = { from: null, to: null, cycle: null, t: 0, playing: false, log: [] };
  mmPathUpdate();
  mmDrawChart();
  mmAutosave();
}

function mmPathUpdate() {
  const ready = !!(MM.path.from && MM.path.to);
  document.getElementById("mm-path-play").disabled = !ready;
  document.getElementById("mm-path-clear").disabled = !MM.path.from;
  const t = document.getElementById("mm-path-t");
  t.disabled = !ready;
  t.value = Math.round(MM.path.t * 1000);
  const log = document.getElementById("mm-path-log");
  log.innerHTML = "";
  if (!ready || !MM.config) return;
  mmGuard(() => {
    MM.path.log = mmPathCrossings();
    if (!MM.path.log.length) { log.innerHTML = '<li class="muted">The path crosses no wall in this chart.</li>'; return; }
    MM.path.log.forEach(c => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button"; b.className = "linklike";
      b.textContent = `t = ${c.t.toFixed(3)}`;
      b.onclick = () => { mmPathPause(); mmPathSeek(c.t); };
      li.append(b, " " + c.what + " — ");
      const ch = document.createElement("span");
      ch.innerHTML = (c.gone.length ? c.gone.map(n => `<span class="mm-gone">−${escapeHtml(n)}</span>`).join(" ") : "") + " " +
        (c.came.length ? c.came.map(n => `<span class="mm-came">+${escapeHtml(n)}</span>`).join(" ") : "") +
        ` <span class="muted">(count ${c.before} → ${c.after})</span>`;
      li.appendChild(ch);
      log.appendChild(li);
    });
  });
}

// where the straight path in the chart meets walls and rays, and what changes there
function mmPathCrossings() {
  const cyc = MM.path.cycle;
  if (cyc.join() !== (MM.cycle || []).join()) return [];
  const A = chScreen(MM.path.from), B = chScreen(MM.path.to);
  const cuts = [];
  const cross = (p, q, what) => {
    const r = [B[0] - A[0], B[1] - A[1]], s = [q[0] - p[0], q[1] - p[1]];
    const den = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(den) < 1e-12) return;
    const t = ((p[0] - A[0]) * s[1] - (p[1] - A[1]) * s[0]) / den;
    const u = ((p[0] - A[0]) * r[1] - (p[1] - A[1]) * r[0]) / den;
    if (t > 1e-6 && t < 1 - 1e-6 && u >= -1e-9 && u <= 1 + 1e-9) cuts.push({ t, what });
  };
  mmChartHits.walls.forEach(w => cross(w.a, w.b, `wall ${w.edgeName} → 0 of ${w.name}`));
  mmChartHits.rays.forEach(r => cross(r.a, r.b, `ray ${mmRayName(rayOf(r.ray))}`));
  cuts.sort((x, y) => x.t - y.t);
  const merged = [];
  cuts.forEach(c => {
    const last = merged[merged.length - 1];
    if (last && c.t - last.t < 1e-5) { if (!last.what.includes(c.what)) last.what += "; " + c.what; }
    else merged.push({ ...c });
  });
  const at = t => {
    const v = [MM.path.from[0] + (MM.path.to[0] - MM.path.from[0]) * t, MM.path.from[1] + (MM.path.to[1] - MM.path.from[1]) * t];
    const p = mmPointAt(v, cyc);
    const r = api("moduli_preimage", MM.config, { splits: p.splits, lengths: p.lengths });
    return { names: r.preimages.map(x => x.name), count: r.count };
  };
  return merged.map((c, i) => {
    const prev = i ? merged[i - 1].t : 0, next = i + 1 < merged.length ? merged[i + 1].t : 1;
    const before = at((prev + c.t) / 2), after = at((c.t + next) / 2);
    return { ...c, gone: before.names.filter(n => !after.names.includes(n)),
             came: after.names.filter(n => !before.names.includes(n)),
             before: before.count, after: after.count };
  });
}

function mmPathSeek(t) {
  if (!MM.path.from || !MM.path.to) return;
  MM.path.t = t;
  document.getElementById("mm-path-t").value = Math.round(t * 1000);
  if (MM.cycle.join() !== MM.path.cycle.join()) { MM.cycle = [...MM.path.cycle]; mmSchedule({ regions: true }); }
  const v = [MM.path.from[0] + (MM.path.to[0] - MM.path.from[0]) * t, MM.path.from[1] + (MM.path.to[1] - MM.path.from[1]) * t];
  const p = mmPointAt(v, MM.cycle);
  MM.onWall = null;
  MM.onImage = null;
  MM.m = { splits: p.splits, lengths: p.lengths };
  if (p.splits.length === 2) MM.lastCone = p.cone;
  mmSchedule({ pre: true, overview: true });
}

let mmPathLast = 0;
function mmPathPlay() {
  if (MM.path.playing) { mmPathPause(); return; }
  if (MM.path.t >= 1) MM.path.t = 0;
  MM.path.playing = true;
  document.getElementById("mm-path-play").textContent = "⏸ Pause";
  mmPathLast = performance.now();
  const step = now => {
    if (!MM.path.playing) return;
    const dt = Math.min(0.1, (now - mmPathLast) / 1000);
    mmPathLast = now;
    const t = Math.min(1, MM.path.t + dt / 6);       // six seconds end to end
    mmGuard(() => mmPathSeek(t));
    if (t >= 1) { mmPathPause(); mmDrawGallery(true); return; }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function mmPathPause() {
  if (!MM.path.playing) return;
  MM.path.playing = false;
  document.getElementById("mm-path-play").textContent = "▶ Play";
  mmDrawGallery(true);
}

mmBoot().catch(err => {
  document.getElementById("boot-msg").innerHTML =
    '<span class="err">Failed to start: ' + escapeHtml(err.message) + "</span>";
  console.error(err);
});
