"use strict";
// ---------------------------------------------------------------------------
// The moduli map: a walk through the moduli space of one type, across walls.
//
// Step 1: draw a subdivision (the main app's editor), put markings on the
// curve, choose the five legs of M_0,5 and the evaluated markings (on the
// picture). Step 2: the curve over the current point, its two skeleton paths
// in two colours, and beside it the cell of M_0,5 it maps to -- a quadrant,
// a line or a point -- with the region where the type has a curve through the
// fixed points and all the region's walls. Drag the point; at a wall it stops,
// the curve becomes the type with that edge contracted, and its regenerations
// (the ways of resolving the new vertex) appear as small pictures: pick one
// to go on (or back) a little way into it.
//
// The math is in tropcurves/moduli.py (exact). web/app.js is loaded first, in
// library mode, for Python, drawing, the subdivision editor, zoom and help.
// ---------------------------------------------------------------------------
const MW_KEY = "tropcurves.walk.v1";
const PATH_COLORS = ["#d62728", "#1f77b4"];      // the two skeleton paths / axes

const MW = {
  base: null,          // the drawn type's id
  legs: [],            // five ends or markings, by name
  evaluated: [],       // markings fixed at points of the plane
  mode: "markings",    // the setup picture's mode
  step: "setup",       // "setup" | "walk"
  cur: null,           // the type the curve is of now (a wall type on a wall)
  points: null,        // { marking: [x, y] } (exact strings)
  m: null,             // the point of M_0,5 { splits, lengths }
  coords: null,        // its coordinates in the current type's cone
  R: 4,                // the cell picture shows [0, R]^2
  wall: null,          // on a wall: { from, edge, edgeName, wallId, vertex, regenerations }
  view: null,          // the last moduli_view
};

// --- boot ----------------------------------------------------------------------
async function mwBoot() {
  document.getElementById("app-version").textContent = "v" + APP_VERSION;
  applyBackgroundTheme(loadSettings().bgColor);
  await bootCore(document.getElementById("boot-msg"));
  document.getElementById("boot").hidden = true;
  document.getElementById("mw").hidden = false;
  wireMenu();
  trackTopbarHeight();
  mwWire();
  let restored = false;
  try {
    const saved = localStorage.getItem(MW_KEY);
    if (saved) restored = mwRestore(JSON.parse(saved));
  } catch (e) { reportError(e); }
  if (!restored) mwShow();
}

function mwWire() {
  const on = (id, ev, f) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, f); };
  on("modal-cancel", "click", closeModal);
  on("mw-draw", "click", () => openSubdivisionEditor(cells => mwNewType(cells)));
  on("mw-paste-go", "click", () => {
    let cells;
    try { cells = parseSubdivision(document.getElementById("mw-paste-text").value); }
    catch (e) { alert("Could not read it: " + e.message); return; }
    try { mwNewType(cells); } catch (e) { alert(e.message); }
  });
  on("mw-restart", "click", () => {
    if (MW.base && !confirm("Forget this type and start with a new one?")) return;
    api("load", JSON.stringify({ schema: 1, kind: "workspace", nodes: [] }));
    Object.assign(MW, { base: null, legs: [], evaluated: [], step: "setup", cur: null, points: null,
                        m: null, coords: null, wall: null, view: null });
    mwShow(); mwSave();
  });
  on("mw-start", "click", () => mwGuard(mwStart));
  on("mw-back", "click", () => { MW.step = "setup"; mwShow(); mwSave(); });
  document.querySelectorAll(".mw-tabs button").forEach(b => {
    b.onclick = () => { MW.mode = b.dataset.mode; mwDrawType(); mwSave(); };
  });
  const bg = () => resolvedVar("--panel", "#ffffff");
  on("mw-copy-curve", "click", ev => copyPanelPng("mw-curve", null, ev.target, "curve.png"));
  on("mw-copy-cell", "click", ev => copyPanelPng("mw-cell", bg(), ev.target, "cell.png"));
  // the cell's own pointer handling first, so a drag of the point is not a pan
  mwWireCell();
  ["mw-type-svg", "mw-curve", "mw-cell"].forEach(id => makeZoomable(document.getElementById(id)));
  const panelHelp = (sel, key) => {
    const h = document.querySelector(sel);
    if (!h || h.querySelector(".help-btn")) return;
    h.classList.add("with-help");
    h.appendChild(helpButton(key));
  };
  panelHelp("#mw-setup .section-head h2", "moduliType");
  panelHelp("#mw-curve-sec .view-head h2", "moduliCurve");
  panelHelp("#mw-cell-sec .view-head h2", "moduliCell");
  const top = document.getElementById("btn-help");
  if (top) top.addEventListener("click", ev => { ev.helpClick = true; toggleHelp(top, "moduliTop"); });
}

function mwGuard(f) { try { f(); } catch (e) { reportError(e); } }

// --- saving -------------------------------------------------------------------------
let mwSaveTimer = null;
function mwSave() {
  clearTimeout(mwSaveTimer);
  mwSaveTimer = setTimeout(() => {
    const el = document.getElementById("mw-saved");
    try {
      const wall = MW.wall && { from: MW.wall.from, edge: MW.wall.edge };
      localStorage.setItem(MW_KEY, JSON.stringify({
        library: api("save"), base: MW.base, legs: MW.legs, evaluated: MW.evaluated, mode: MW.mode,
        step: MW.step, cur: MW.cur, points: MW.points, m: MW.m, R: MW.R, wall }));
      el.textContent = "saved " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) { el.textContent = "not saved"; }
  }, 400);
}
function mwRestore(st) {
  if (!st || !st.library) return false;
  api("load", st.library);
  Object.assign(MW, { base: st.base, legs: st.legs || [], evaluated: st.evaluated || [], mode: st.mode || "markings",
                      step: st.step || "setup", cur: st.cur, points: st.points, m: st.m, R: st.R || 4, wall: null });
  if (!MW.base || !api("list_nodes").some(n => n.id === MW.base)) { MW.base = null; MW.step = "setup"; }
  if (MW.step === "walk" && st.wall) {
    try { mwEnterWall(st.wall.from, st.wall.edge); } catch (e) { MW.wall = null; }
  }
  mwShow();
  return true;
}

// --- step 1: the type -------------------------------------------------------------
function mwNewType(cells) {
  api("load", JSON.stringify({ schema: 1, kind: "workspace", nodes: [] }));
  const summ = api("add_from_subdivision", cells, "drawn");
  MW.base = summ.id;
  const ends = api("render", MW.base).curve.edges.filter(e => e.kind === "end").map(e => e.name);
  MW.legs = ends.slice(0, 5);                // a start; change on the picture
  MW.evaluated = [];
  MW.mode = "markings";
  MW.step = "setup";
  MW.wall = null;
  mwShow();
  mwSave();
}

function mwShow() {
  const walk = MW.step === "walk" && MW.base && MW.points;
  document.getElementById("mw-setup").hidden = !!walk;
  document.getElementById("mw-curve-sec").hidden = !walk;
  document.getElementById("mw-cell-sec").hidden = !walk;
  document.getElementById("mw-type").hidden = !MW.base;
  if (walk) mwGuard(mwRender);
  else if (MW.base) mwGuard(mwDrawType);
}

function mwNames(data) {
  const ends = data.curve.edges.filter(e => e.kind === "end").map(e => e.name);
  const marks = data.curve.markings.map(m => m.name);
  return { ends, marks, all: [...ends, ...marks] };
}

function mwDrawType() {
  const data = api("render", MW.base);
  const names = mwNames(data);
  // forget choices of markings that are gone
  MW.legs = MW.legs.filter(n => names.all.includes(n));
  MW.evaluated = MW.evaluated.filter(n => names.marks.includes(n));
  const mode = MW.mode;
  document.querySelectorAll(".mw-tabs button").forEach(b => {
    const on = b.dataset.mode === mode;
    b.classList.toggle("primary", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    if (b.dataset.mode === "legs") b.textContent = `Legs of M₀,₅ (${MW.legs.length} of 5)`;
    if (b.dataset.mode === "points") b.textContent = `Evaluated (${MW.evaluated.length})`;
  });
  document.getElementById("mw-hint").textContent = {
    markings: "Click an edge or end to put a marking inside it, a ringed vertex to put one on it, a marking to take it off.",
    legs: "Click ends and markings: the five legs whose tree is the point of M₀,₅.",
    points: "Click markings to fix them at points of the plane.",
  }[mode];
  const drawn = drawCurve(data, {
    svgId: "mw-type-svg",
    pickEdge: e => (mode === "markings" && e.kind !== "marking") || (mode === "legs" && e.kind === "end"),
    pickVertex: mode === "markings" ? (() => true) : null,
    pickMarking: () => true,
  });
  const svg = drawn.svg, T = drawn.T;
  data.curve.edges.forEach(e => {
    if (e.kind === "end" && MW.legs.includes(e.name) && drawn.lines[e.id]) {
      drawn.lines[e.id].setAttribute("stroke", "var(--accent)");
      drawn.lines[e.id].setAttribute("stroke-width", 5);
    }
  });
  data.curve.markings.forEach(m => {
    const p = T(m.at), first = svg.querySelector(".pick-hit");
    if (MW.evaluated.includes(m.name)) {
      svg.insertBefore(svgEl("rect", { x: p[0] - 13, y: p[1] - 13, width: 26, height: 26, rx: 4, fill: "none",
        stroke: "var(--warn)", "stroke-width": 3, "pointer-events": "none" }), first);
    }
    if (MW.legs.includes(m.name)) {
      svg.insertBefore(svgEl("circle", { cx: p[0], cy: p[1], r: 9, fill: "none", stroke: "var(--accent)",
        "stroke-width": 3.5, "pointer-events": "none" }), first);
    }
  });
  const status = document.getElementById("mw-pick-status");
  const idle = mode === "legs" ? `Legs: ${MW.legs.join(", ") || "none"}`
    : mode === "points" ? `Evaluated: ${MW.evaluated.join(", ") || "none"}`
    : `${names.ends.length} ends, ${names.marks.length} markings`;
  status.textContent = idle;
  const describe = t => {
    if (mode === "markings") {
      if (t.kind === "mark") return `marking ${t.marking.name}: click to take it off`;
      if (t.kind === "edge") return `${t.edge.kind === "end" ? "end" : "edge"} ${t.edge.name}: click to put a marking inside it`;
      return "this vertex: click to put a marking on it";
    }
    const name = t.kind === "edge" ? t.edge.name : t.marking.name;
    if (mode === "legs") return `${name}: ` + (MW.legs.includes(name) ? "a leg — click to drop it" : "click to make it a leg");
    return `${name}: ` + (MW.evaluated.includes(name) ? "evaluated — click to free it" : "click to fix it at a point");
  };
  [...drawn.edgePicks, ...drawn.markPicks, ...drawn.vertexPicks].forEach(t => {
    t.hit.addEventListener("pick-enter", () => { status.textContent = describe(t); });
    t.hit.addEventListener("pick-leave", () => { status.textContent = idle; });
    t.hit.addEventListener("pick-click", () => mwGuard(() => {
      if (mode === "markings") {
        if (t.kind === "mark") api("moduli_remove_marking", MW.base, t.marking.id);
        else if (t.kind === "edge") api("add_marking_on_edge", MW.base, t.edge.id, "", "");
        else api("add_marking", MW.base, t.vertex.id, "", "");
      } else {
        if (t.kind === "edge" && mode !== "legs") return;
        const name = t.kind === "edge" ? t.edge.name : t.marking.name;
        const list = mode === "legs" ? MW.legs : MW.evaluated;
        const i = list.indexOf(name);
        if (i >= 0) list.splice(i, 1);
        else if (mode !== "legs" || list.length < 5) list.push(name);
        else { alert("Five legs already: click one of them to drop it first."); return; }
      }
      mwDrawType();
      mwSave();
    }));
  });
  mwCheck(names);
}

// the order the core sees the legs in: ends, then markings, by name
const mwLegOrder = names => names.all.filter(n => MW.legs.includes(n));

function mwCheck(names) {
  const el = document.getElementById("mw-check"), go = document.getElementById("mw-start");
  el.className = "status warn";
  go.disabled = true;
  const need = (names.ends.length + names.marks.length - 3) / 2;    // evaluated markings needed
  if (MW.legs.length !== 5) { el.textContent = `Choose ${5 - MW.legs.length} more leg${5 - MW.legs.length === 1 ? "" : "s"}.`; return; }
  if (!Number.isInteger(need)) {
    el.textContent = `With ${names.ends.length} ends and ${names.marks.length} markings the dimensions cannot match: add or take off one marking.`;
    return;
  }
  if (MW.evaluated.length !== need) {
    el.textContent = `Evaluate ${need} marking${need === 1 ? "" : "s"} (|Δ| + n − 1 = 2k + 2), now ${MW.evaluated.length}` +
      (names.marks.length < need ? `: add ${need - names.marks.length} more marking${need - names.marks.length === 1 ? "" : "s"} first.` : ".");
    return;
  }
  let out;
  try { out = api("moduli_check", MW.base, MW.evaluated, mwLegOrder(names)); }
  catch (e) { el.textContent = e.message; return; }
  if (!out.ok) { el.textContent = out.message; return; }
  if (!out.full) {
    el.textContent = `The dimensions match, but this type is not full-dimensional for the map: ${out.why ? out.why.reason : ""}. Choose other legs or markings.`;
    return;
  }
  el.className = "status";
  el.textContent = `dim ${out.dim} = 2·${MW.evaluated.length} + 2 ✓ — multiplicity ${out.multiplicity}`;
  go.disabled = false;
}

function mwStart() {
  const names = mwNames(api("render", MW.base));
  MW.legs = mwLegOrder(names);
  const st = api("moduli_start", MW.base, MW.evaluated, MW.legs);
  MW.points = st.points; MW.m = st.m; MW.cur = MW.base; MW.wall = null;
  const v = api("moduli_view", MW.cur, MW.evaluated, MW.legs, MW.points, MW.m, "1");
  MW.R = mwNice(2.2 * Math.max(...(v.coords || ["1"]).map(mwNum), 0.5));
  MW.step = "walk";
  mwShow();
  mwSave();
}
function mwNice(x) {
  if (!(x > 0)) return 4;
  const e = Math.pow(10, Math.floor(Math.log10(x))), f = x / e;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
}
const mwNum = s => { const [p, q] = String(s).split("/"); return q ? +p / +q : +p; };
const mwShort = s => { const x = mwNum(s); return Number.isInteger(x) ? String(x) : x.toFixed(3); };

// --- step 2: the walk ---------------------------------------------------------------
function mwRender() {
  const v = api("moduli_view", MW.cur, MW.evaluated, MW.legs, MW.points, MW.m, String(MW.R));
  MW.view = v;
  MW.coords = v.coords;
  if (v.full && v.region) MW.lastFull = { cone: JSON.stringify(v.cone), region: v.region };
  // keep the point in view: grow the picture when it nears the edge
  if (v.coords && Math.max(...v.coords.map(mwNum)) > 0.85 * MW.R) {
    MW.R = mwNice(1.6 * Math.max(...v.coords.map(mwNum)));
    return mwRender();
  }
  mwDrawCurve(v);
  mwDrawCell(v);
  mwDrawWall();
}

const rayName = sp => "{" + MW.legs[sp[0]] + "," + MW.legs[sp[1]] + "}";

function mwDrawCurve(v) {
  document.getElementById("mw-curve-name").textContent = v.name + (MW.wall ? " · on a wall" : "");
  if (!v.picture) { clearSvg("mw-curve"); return; }
  const drawn = drawCurve({ curve: v.picture }, { svgId: "mw-curve" });
  const svg = drawn.svg, T = drawn.T;
  // the skeleton: the edges whose lengths add up to each coordinate of M_0,5
  Object.entries(v.skeleton).forEach(([eid, i]) => {
    const ln = drawn.lines[eid];
    if (!ln) return;
    ln.setAttribute("stroke", PATH_COLORS[i]);
    ln.setAttribute("stroke-width", 5);
  });
  // the evaluated markings sit at their fixed points
  v.picture.markings.forEach(m => {
    if (!MW.evaluated.includes(m.name)) return;
    const p = T(m.at);
    svg.appendChild(svgEl("rect", { x: p[0] - 11, y: p[1] - 11, width: 22, height: 22, rx: 4, fill: "none",
      stroke: "var(--warn)", "stroke-width": 2.5, "pointer-events": "none" }));
  });
  const paths = document.getElementById("mw-paths");
  paths.innerHTML = "";
  v.cone.forEach((sp, i) => {
    const item = document.createElement("span");
    const sw = document.createElement("span");
    sw.className = "sub-swatch"; sw.style.background = PATH_COLORS[i];
    item.append(sw, document.createTextNode(`${rayName(sp)} = ${v.coords ? mwShort(v.coords[i]) : "?"}`));
    paths.appendChild(item);
  });
  if (!v.cone.length) paths.textContent = "The five legs meet at one point here (the apex of M₀,₅).";
}

// the cell picture: the type's cone as a quadrant (two rays), a line (one) or
// a point (the apex); the region where the type has curves and its walls
const CELL = { ox: 70, oy: 350, w: 500, h: 320 };
const cellS = () => Math.min(CELL.w, CELL.h) / MW.R;
const cellXY = ab => [CELL.ox + ab[0] * cellS(), CELL.oy - (ab[1] || 0) * cellS()];
const cellAB = q => [(q[0] - CELL.ox) / cellS(), (CELL.oy - q[1]) / cellS()];

function mwDrawCell(v) {
  const svg = clearSvg("mw-cell");
  const kind = v.cone.length === 2 ? "a quadrant" : v.cone.length === 1 ? "a line" : "a point";
  document.getElementById("mw-cell-kind").textContent = "— " + kind;
  const where = document.getElementById("mw-where");
  const c = v.coords ? v.coords.map(mwNum) : null;
  if (v.cone.length === 0) {
    svg.appendChild(svgEl("circle", { cx: 300, cy: 200, r: 8, fill: "var(--warn)" }));
    where.textContent = "The tree of the five legs has no inner edge: the apex of M₀,₅.";
    return;
  }
  // axes, coloured like the skeleton paths
  const end = MW.R * 1.02;
  v.cone.forEach((sp, i) => {
    const a = cellXY([0, 0]), b = cellXY(i === 0 ? [end, 0] : [0, end]);
    svg.appendChild(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: PATH_COLORS[i], "stroke-width": 3 }));
    const lbl = text(i === 0 ? b[0] : a[0] - 8, i === 0 ? a[1] + 24 : b[1] - 8, rayName(sp), PATH_COLORS[i]);
    lbl.setAttribute("text-anchor", i === 0 ? "end" : "start");
    svg.appendChild(lbl);
  });
  [0.5, 1].forEach(f => {
    const x = cellXY([MW.R * f, 0]);
    const tx = text(x[0], x[1] + 40, mwShort(String(MW.R * f)), "var(--muted)"); tx.setAttribute("font-size", "11");
    svg.appendChild(tx);
    if (v.cone.length === 2) {
      const y = cellXY([0, MW.R * f]);
      const ty = text(y[0] - 8, y[1] + 4, mwShort(String(MW.R * f)), "var(--muted)");
      ty.setAttribute("font-size", "11"); ty.setAttribute("text-anchor", "end");
      svg.appendChild(ty);
    }
  });
  // on a wall the wall type has no region of its own: show the one we came
  // from, faded, so the wall is seen as its border
  const ghost = !v.region && MW.wall && MW.lastFull && MW.lastFull.cone === JSON.stringify(v.cone);
  const region = v.region || (ghost ? MW.lastFull.region : null);
  if (v.cone.length === 2 && region) {
    const poly = region.polygon.map(q => cellXY(q).join(",")).join(" ");
    svg.insertBefore(svgEl("polygon", { points: poly, fill: "var(--accent)", "fill-opacity": ghost ? 0.06 : 0.13, stroke: "none" }), svg.firstChild);
    region.walls.forEach(w => {
      const a = cellXY(w.from), b = cellXY(w.to);
      svg.appendChild(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "var(--ink)", "stroke-width": 2.2,
        "stroke-linecap": "round" }));
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
      // the label on the region's side of its wall, clear of the axes
      const cen = cellXY([0, 1].map(k => region.polygon.reduce((t, q) => t + q[k], 0) / region.polygon.length));
      let nx = -dy / L, ny = dx / L;
      if ((cen[0] - mid[0]) * nx + (cen[1] - mid[1]) * ny < 0) { nx = -nx; ny = -ny; }
      const lbl = text(mid[0] + nx * 26, mid[1] + ny * 26 + 4, w.name + " → 0", "var(--ink)");
      lbl.setAttribute("font-size", "12");
      svg.appendChild(lbl);
    });
  }
  if (c) {
    const q = cellXY(v.cone.length === 2 ? c : [c[0], 0]);
    const onWall = !!MW.wall;
    svg.appendChild(svgEl("circle", { cx: q[0], cy: q[1], r: onWall ? 11 : 9, fill: onWall ? "var(--warn)" : "var(--accent)",
      stroke: "var(--panel)", "stroke-width": 2.5, class: "mw-dot" }));
    where.textContent = v.cone.map((sp, i) => `${rayName(sp)} = ${mwShort(v.coords[i])}`).join(", ") +
      (MW.wall ? ` — on the wall where ${MW.wall.edgeName} shrank to 0` : v.full ? " — drag the point; it stops at a wall" : "");
  } else where.textContent = "";
}

// drag the point (from the point itself); a tap elsewhere walks it there
let mwRaf = 0;
function mwWireCell() {
  const svg = document.getElementById("mw-cell");
  let drag = false, pending = null;
  const toSvg = ev => {
    const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    const q = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [q.x, q.y];
  };
  const canMove = () => MW.step === "walk" && MW.view && MW.view.full && !MW.wall && MW.coords;
  const walkTo = q => {
    pending = q;
    if (mwRaf) return;
    mwRaf = requestAnimationFrame(() => {
      mwRaf = 0;
      const target = pending; pending = null;
      if (!target || !canMove()) return;
      mwGuard(() => mwMove(cellAB(target)));
    });
  };
  svg.addEventListener("pointerdown", ev => {
    if (!canMove() || (ev.pointerType === "mouse" && ev.button !== 0)) return;
    const c = MW.coords.map(mwNum), dot = cellXY(MW.view.cone.length === 2 ? c : [c[0], 0]);
    const q = toSvg(ev);
    if (Math.hypot(q[0] - dot[0], q[1] - dot[1]) > 28) return;      // not on the point: pan / pinch
    ev.stopImmediatePropagation();
    ev.preventDefault();
    drag = true;
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic */ }
  });
  svg.addEventListener("pointermove", ev => {
    if (!drag) return;
    ev.stopImmediatePropagation();
    walkTo(toSvg(ev));
  });
  const end = ev => {
    if (!drag) return;
    drag = false;
    ev.stopImmediatePropagation();
    MW.dragEndAt = Date.now();
    mwSave();
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  // a tap away from the point walks it there (not the click that ends a drag)
  svg.addEventListener("click", ev => {
    if (!canMove() || Date.now() - (MW.dragEndAt || 0) < 400) return;
    walkTo(toSvg(ev));
    setTimeout(mwSave, 0);
  });
}

function mwMove(ab) {
  const v = MW.view;
  const to = (v.cone.length === 2 ? ab : [ab[0]]).map(x => (Math.round(x * 1e4) / 1e4).toString());
  const r = api("moduli_move", MW.cur, MW.evaluated, MW.legs, MW.points, MW.coords, to);
  MW.m = r.m;
  if (r.wall) mwEnterWall(MW.cur, r.wall.edge);
  mwRender();
}

// --- at a wall ----------------------------------------------------------------------
function mwEnterWall(fromId, edgeId) {
  const w = api("moduli_wall", fromId, edgeId, MW.evaluated, MW.legs);
  MW.wall = { from: fromId, edge: edgeId, edgeName: w.edge, wallId: w.wall_id, vertex: w.vertex,
              regenerations: w.regenerations };
  MW.cur = w.wall_id;
}

function mwDrawWall() {
  const box = document.getElementById("mw-wall");
  if (!MW.wall) { box.hidden = true; return; }
  box.hidden = false;
  document.getElementById("mw-wall-text").textContent =
    `On a wall: ${MW.wall.edgeName} has length 0, and the curve has a vertex of valence 4. Choose how it regenerates:`;
  const list = document.getElementById("mw-regens");
  list.innerHTML = "";
  MW.wall.regenerations.forEach((r, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mw-regen" + (r.back ? " back" : "");
    const id = "mw-regen-" + i;
    const svg = document.createElementNS(SVGNS, "svg");
    svg.id = id; svg.setAttribute("viewBox", `0 0 ${VBW} ${VBH}`);
    b.appendChild(svg);
    const cap = document.createElement("span");
    cap.textContent = r.back ? "back" : r.full ? "go on" : "not full-dimensional";
    b.appendChild(cap);
    b.title = r.back ? "Go back the way you came" : r.full ? "Go on into this type" : r.why;
    b.disabled = !r.full;
    b.onclick = () => mwGuard(() => mwRegenerate(r.index));
    list.appendChild(b);
    drawCurve(r.picture.curve ? r.picture : { curve: r.picture }, { svgId: id, labels: false });
  });
}

function mwRegenerate(index) {
  const w = MW.wall;
  const r = api("moduli_regenerate", w.wallId, w.vertex, index, MW.evaluated, MW.legs, MW.points, MW.m,
                String(MW.R));
  if (!r.m) { alert("Cannot go on into it: " + r.why); return; }
  MW.cur = r.id; MW.m = r.m; MW.wall = null;
  mwRender();
  mwSave();
}

mwBoot().catch(err => {
  document.getElementById("boot-msg").innerHTML =
    '<span class="err">Failed to start: ' + escapeHtml(err.message) + "</span>";
  console.error(err);
});
