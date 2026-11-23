"use strict";
// ---------------------------------------------------------------------------
// The polyhedron of curves: the curves of one combinatorial type satisfying
// constraints, and a walk through them across degenerations.
//
// Step 1: the type (from the main app, or drawn) in the plane; click markings
// to fix their images at points and ends to fix the lines they lie on, and
// drag the points and lines -- the curve follows, as long as a curve of the
// type satisfies them. Step 2: the curve, and beside it the polyhedron of such
// curves: up to dimension 2 drawn (its free coordinates as axes, the region
// where every edge is positive, its walls), with a point to drag; in higher
// dimension a direction of edge lengths (clicked on the curve) projected to
// the polyhedron, and a slider along it. When an edge reaches length 0 the
// walk stops there, on the type with that edge contracted, and offers its
// regenerations (the resolutions of the vertex it leaves).
//
// The math is in tropcurves/polyhedron.py (exact). web/app.js is loaded first,
// in library mode, for Python, drawing, the subdivision editor, zoom and help.
// ---------------------------------------------------------------------------
const PC_KEY = "tropcurves.poly.v1";
const PC_PLUS = "#2ca02c", PC_MINUS = "#d62728", PC_LINE = "#8e5bd8";

const PC = {
  base: null,         // the type the constraints were set on
  cur: null,          // the type the curve is of now
  z: null,            // its coordinates (exact strings)
  points: {},         // marking name -> [x, y]
  lines: {},          // end name -> line value det(v, P)
  mode: "points",
  step: "setup",      // "setup" | "walk"
  box: null,          // the chart's box (per type)
  delta: {},          // edge id -> +1 / -1: the direction asked for
  dir: null,          // its projection (poly_direction)
  reg: null,          // regenerations on offer: { vertex, from, list }
  view: null,         // the last poly_view
  status: null,       // the last poly_fit in step 1
};

// --- boot ----------------------------------------------------------------------
async function pcBoot() {
  document.getElementById("app-version").textContent = "v" + APP_VERSION;
  applyBackgroundTheme(loadSettings().bgColor);
  await bootCore(document.getElementById("boot-msg"));
  document.getElementById("boot").hidden = true;
  document.getElementById("pc").hidden = false;
  wireMenu();
  trackTopbarHeight();
  pcWire();
  let restored = false;
  try {
    const saved = localStorage.getItem(PC_KEY);
    if (saved) restored = pcRestore(JSON.parse(saved));
  } catch (e) { reportError(e); }
  if (!restored) pcShow();
  pcGuard(pcTakeHandoff);
}

function pcGuard(f) { try { f(); } catch (e) { reportError(e); } }

function pcWire() {
  const on = (id, ev, f) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, f); };
  on("modal-cancel", "click", closeModal);
  on("pc-draw", "click", () => openSubdivisionEditor(cells => pcGuard(() => {
    if (PC.base && !confirm("Replace the type here with the one drawn?")) return;
    api("load", JSON.stringify({ schema: 1, kind: "workspace", nodes: [] }));
    pcSetType(api("add_from_subdivision", cells, "drawn").id);
  })));
  on("pc-start", "click", () => pcGuard(pcStart));
  on("pc-back", "click", () => pcGuard(() => {
    PC.step = "setup"; PC.base = PC.cur; PC.reg = null; pcShow(); pcSave();
  }));
  document.querySelectorAll("#pc-type .mw-tabs button").forEach(b => {
    b.onclick = () => { PC.mode = b.dataset.mode; pcDrawPlane(); pcSave(); };
  });
  const bg = () => resolvedVar("--panel", "#ffffff");
  on("pc-copy-curve", "click", ev => copyPanelPng("pc-curve", null, ev.target, "curve.png"));
  on("pc-copy-chart", "click", ev => copyPanelPng("pc-chart", bg(), ev.target, "polyhedron.png"));
  // the handles' and the point's own dragging first, so it is not a pan
  pcWireHandles(document.getElementById("pc-plane"));
  pcWireChart();
  ["pc-plane", "pc-curve", "pc-chart"].forEach(id => makeZoomable(document.getElementById(id)));
  pcWireSlider();
  const panelHelp = (sel, key) => {
    const h = document.querySelector(sel);
    if (!h || h.querySelector(".help-btn")) return;
    h.classList.add("with-help");
    h.appendChild(helpButton(key));
  };
  panelHelp("#pc-setup .section-head h2", "polyConstraints");
  panelHelp("#pc-curve-sec .view-head h2", "polyCurve");
  panelHelp("#pc-cell-sec .view-head h2", "polyCell");
  const top = document.getElementById("btn-help");
  if (top) top.addEventListener("click", ev => { ev.helpClick = true; toggleHelp(top, "polyTop"); });
}

// --- saving -----------------------------------------------------------------------
let pcSaveTimer = null;
function pcSave() {
  clearTimeout(pcSaveTimer);
  pcSaveTimer = setTimeout(() => {
    const el = document.getElementById("pc-saved");
    try {
      localStorage.setItem(PC_KEY, JSON.stringify({
        library: api("save"), base: PC.base, cur: PC.cur, z: PC.z, points: PC.points, lines: PC.lines,
        mode: PC.mode, step: PC.step, box: PC.box, delta: PC.delta,
        reg: PC.reg && { vertex: PC.reg.vertex, from: PC.reg.from } }));
      el.textContent = "saved " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) { el.textContent = "not saved"; }
  }, 400);
}
function pcRestore(st) {
  if (!st || !st.library) return false;
  api("load", st.library);
  const ids = api("list_nodes").map(n => n.id);
  Object.assign(PC, { base: st.base, cur: st.cur, z: st.z, points: st.points || {}, lines: st.lines || {},
                      mode: st.mode || "points", step: st.step || "setup", box: st.box || null,
                      delta: st.delta || {}, dir: null, reg: null });
  if (!ids.includes(PC.base)) { PC.base = null; PC.step = "setup"; }
  if (!ids.includes(PC.cur)) { PC.cur = PC.base; PC.step = "setup"; }
  if (PC.step === "walk" && st.reg) PC.reg = { vertex: st.reg.vertex, from: st.reg.from };
  pcShow();
  return true;
}

// A type sent from the main app (its ⬠ button): the address carries a token,
// and localStorage the type under it. It replaces the page's type -- after
// asking, when there is one.
function pcTakeHandoff() {
  const m = /[#&]type=([\w-]+)/.exec(location.hash);
  if (!m) return;
  history.replaceState(null, "", location.pathname + location.search);
  let h = null;
  try { h = JSON.parse(localStorage.getItem(POLY_HANDOFF_KEY) || "null"); } catch (e) { h = null; }
  if (!h || h.token !== m[1]) {
    alert("The type sent from the main app is no longer here: send it again with its ⬠ button.");
    return;
  }
  try { localStorage.removeItem(POLY_HANDOFF_KEY); } catch (e) { /* private mode */ }
  const name = (JSON.parse(h.library).nodes[0] || {}).name || "the type";
  if (PC.base && !confirm(`Replace the type here with ${name} from the main app?`)) return;
  api("load", h.library);
  pcSetType(api("list_nodes")[0].id);
}

function pcSetType(id) {
  Object.assign(PC, { base: id, cur: id, z: api("poly_start", id).z, points: {}, lines: {},
                      mode: "points", step: "setup", box: null, delta: {}, dir: null, reg: null, status: null });
  pcShow();
  pcSave();
}

function pcShow() {
  const walk = PC.step === "walk" && PC.cur && PC.z;
  document.getElementById("pc-setup").hidden = !!walk;
  document.getElementById("pc-curve-sec").hidden = !walk;
  document.getElementById("pc-cell-sec").hidden = !walk;
  document.getElementById("pc-type").hidden = !PC.base;
  document.getElementById("pc-empty").hidden = !!PC.base;
  if (walk) pcGuard(pcRender);
  else if (PC.base) pcGuard(() => { pcFit(); pcDrawPlane(); });
}

const pcNum = s => { const [p, q] = String(s).split("/"); return q ? +p / +q : +p; };
const pcShort = s => { const x = pcNum(s); return Number.isInteger(x) ? String(x) : x.toFixed(3).replace(/\.?0+$/, ""); };
const pcStr = x => (Math.round(x * 1000) / 1000).toString();

// --- drawing a curve with its constraints in the plane ------------------------------
// The constraints' points and lines; a line is {P : v_x P_y - v_y P_x = c}.
function pcLineGeom(vec, c, near) {
  const L2 = vec[0] * vec[0] + vec[1] * vec[1], L = Math.sqrt(L2);
  const p0 = [-pcNum(c) * vec[1] / L2, pcNum(c) * vec[0] / L2];       // the line's point nearest 0
  const u = [vec[0] / L, vec[1] / L];
  const s = (near[0] - p0[0]) * u[0] + (near[1] - p0[1]) * u[1];
  return { p0, u, handle: [p0[0] + s * u[0], p0[1] + s * u[1]] };
}
const pcInverse = T => q => [(q[0] - T.params.ox) / T.params.s + T.params.minx,
                             (VBH - q[1] - T.params.oy) / T.params.s + T.params.miny];

// Draw `picture` into svgId with the constraints. `keepT`: the transform to
// reuse (a drag keeps the view still). opts: pick* for drawCurve, handles.
function pcDraw(svgId, picture, opts = {}) {
  const ends = picture.edges.filter(e => e.kind === "end");
  let T = opts.keepT || null;
  if (!T) {
    const pts = [];
    picture.edges.forEach(e => { pts.push(e.from); pts.push(e.to); });
    Object.values(PC.points).forEach(p => pts.push(p.map(pcNum)));
    T = fitTransform(pts);
  }
  const drawn = drawCurve({ curve: picture }, { svgId, transform: T, pickEdge: opts.pickEdge,
                                               pickMarking: opts.pickMarking });
  const svg = drawn.svg, first = svg.querySelector(".pick-hit");
  const put = el => (first && !opts.handles ? svg.insertBefore(el, first) : svg.appendChild(el));
  // the lines first (under the points)
  Object.entries(PC.lines).forEach(([name, c]) => {
    const e = ends.find(x => x.name === name);
    if (!e) return;
    const g = pcLineGeom(e.vec, c, e.from);
    const far = 2000 / T.params.s;
    const a = T([g.p0[0] - far * g.u[0], g.p0[1] - far * g.u[1]]), b = T([g.p0[0] + far * g.u[0], g.p0[1] + far * g.u[1]]);
    svg.insertBefore(keepSize(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: PC_LINE,
      "stroke-dasharray": "7 5", "pointer-events": "none" }), { sw: 1.8 }), svg.firstChild);
    if (opts.handles) {
      const h = T(g.handle);
      put(keepSize(svgEl("rect", { x: h[0] - 8, y: h[1] - 8, width: 16, height: 16, fill: PC_LINE,
        stroke: "var(--panel)", transform: `rotate(45 ${h[0]} ${h[1]})`, class: "pc-handle",
        "data-line": name }), {}));
    }
  });
  Object.entries(PC.points).forEach(([name, p]) => {
    const q = T(p.map(pcNum));
    const sq = svgEl("rect", { x: q[0] - 10, y: q[1] - 10, width: 20, height: 20, rx: 4,
      fill: opts.handles ? "color-mix(in srgb, var(--warn) 25%, transparent)" : "none",
      stroke: "var(--warn)", "stroke-width": 2.5, "pointer-events": opts.handles ? "all" : "none" });
    if (opts.handles) { sq.setAttribute("class", "pc-handle"); sq.setAttribute("data-point", name); }
    put(sq);
  });
  return { ...drawn, T };
}

// --- step 1: the constraints -------------------------------------------------------
function pcFit(z) {
  const r = api("poly_fit", PC.base, PC.points, PC.lines, z || PC.z);
  PC.status = r;
  if (r.z) PC.z = r.z;
  return r;
}

let pcPlaneT = null;
function pcDrawPlane(keepT) {
  const data = api("render", PC.base);
  document.getElementById("pc-type-name").textContent = data.curve ? api("list_nodes").find(n => n.id === PC.base).name : "";
  const mode = PC.mode;
  document.querySelectorAll("#pc-type .mw-tabs button").forEach(b => {
    const on = b.dataset.mode === mode;
    b.classList.toggle("primary", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    if (b.dataset.mode === "points") b.textContent = `Points (${Object.keys(PC.points).length})`;
    if (b.dataset.mode === "lines") b.textContent = `Lines (${Object.keys(PC.lines).length})`;
  });
  document.getElementById("pc-hint").textContent = mode === "points"
    ? "Click a marking to fix its image at a point (orange square), again to free it. Drag a square to move the point."
    : "Click an end to fix the line it lies on (dashed violet), again to free it. Drag the diamond to move the line.";
  const pic = (PC.status && PC.status.picture) || api("poly_view", PC.base, {}, {}, PC.z).picture;
  const d = pcDraw("pc-plane", pic, {
    keepT, handles: true,
    pickEdge: e => mode === "lines" && e.kind === "end",
    pickMarking: () => mode === "points",
  });
  pcPlaneT = d.T;
  if (PC.status && !PC.status.precise) {           // faded: not a curve through the constraints
    d.svg.querySelectorAll("line").forEach(l => { if (!l.getAttribute("stroke-dasharray")) l.setAttribute("opacity", "0.35"); });
  }
  const status = document.getElementById("pc-pick-status");
  const idle = mode === "points" ? `Points: ${Object.keys(PC.points).join(", ") || "none"}`
    : `Lines: ${Object.keys(PC.lines).join(", ") || "none"}`;
  status.textContent = idle;
  [...d.edgePicks, ...d.markPicks].forEach(t => {
    const name = t.kind === "edge" ? t.edge.name : t.marking.name;
    const has = t.kind === "edge" ? name in PC.lines : name in PC.points;
    t.hit.addEventListener("pick-enter", () => {
      status.textContent = `${name}: click to ` + (has ? "free it" : t.kind === "edge" ? "fix the line it lies on" : "fix its image");
    });
    t.hit.addEventListener("pick-leave", () => { status.textContent = idle; });
    t.hit.addEventListener("pick-click", () => pcGuard(() => {
      const vals = api("poly_values", PC.base, PC.z);
      if (t.kind === "edge") {
        if (has) delete PC.lines[name]; else PC.lines[name] = vals.lines[name];
      } else if (has) delete PC.points[name]; else PC.points[name] = vals.points[name];
      pcFit();
      pcDrawPlane(pcPlaneT);
      pcSave();
    }));
  });
  pcCheck();
}

function pcCheck() {
  const el = document.getElementById("pc-check"), go = document.getElementById("pc-start");
  const r = PC.status || pcFit();
  go.disabled = !r.precise;
  el.className = "status" + (r.precise ? "" : " warn");
  const k = Object.keys(PC.points).length, l = Object.keys(PC.lines).length;
  const what = `${k} point${k === 1 ? "" : "s"} (2 conditions each), ${l} line${l === 1 ? "" : "s"} (1 each)`;
  if (!r.feasible) el.textContent = `${what}: no curve of this type satisfies them. Move them, or free some.`;
  else if (!r.precise) el.textContent = `${what}: only degenerate curves (some edge of length 0) satisfy them. Move them, or free some.`;
  else el.textContent = `${what}: the curves of this type through them form a polyhedron of dimension ${r.dim}.`;
}

// dragging a point or a line (the plane picture's handles)
let pcRaf = 0;
function pcWireHandles(svg) {
  let drag = null, pending = null, swallow = false;
  const toSvg = ev => {
    const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    const q = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [q.x, q.y];
  };
  svg.addEventListener("click", ev => {
    if (swallow) { swallow = false; ev.stopImmediatePropagation(); }
  }, true);
  svg.addEventListener("pointerdown", ev => {
    const h = ev.target.closest && ev.target.closest(".pc-handle");
    if (!h || (ev.pointerType === "mouse" && ev.button !== 0)) return;
    ev.stopImmediatePropagation();
    ev.preventDefault();
    drag = { point: h.getAttribute("data-point"), line: h.getAttribute("data-line"), T: pcPlaneT,
             at: [ev.clientX, ev.clientY], moved: false };
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic */ }
  });
  svg.addEventListener("pointermove", ev => {
    if (!drag) return;
    ev.stopImmediatePropagation();
    if (!drag.moved && Math.hypot(ev.clientX - drag.at[0], ev.clientY - drag.at[1]) < 4) return;
    drag.moved = true;
    pending = pcInverse(drag.T)(toSvg(ev));
    if (pcRaf) return;
    pcRaf = requestAnimationFrame(() => {
      pcRaf = 0;
      const q = pending; pending = null;
      if (!q || !drag) return;
      pcGuard(() => {
        if (drag.point) PC.points[drag.point] = [pcStr(q[0]), pcStr(q[1])];
        else {
          const e = api("render", PC.base).curve.edges.find(x => x.name === drag.line);
          PC.lines[drag.line] = pcStr(e.vec[0] * q[1] - e.vec[1] * q[0]);
        }
        pcFit();
        pcDrawPlane(drag.T);
      });
    });
  });
  const end = ev => {
    if (!drag) return;
    ev.stopImmediatePropagation();
    const d = drag;
    drag = null;
    swallow = true;                       // the click that follows is not one on what is under it
    setTimeout(() => { swallow = false; }, 500);
    if (!d.moved && ev.type === "pointerup" && (d.point ? PC.mode === "points" : PC.mode === "lines")) {
      pcGuard(() => {                     // a tap: free it
        if (d.point) delete PC.points[d.point]; else delete PC.lines[d.line];
        pcFit();
        pcDrawPlane(pcPlaneT);
      });
    }
    pcSave();
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
}

function pcStart() {
  const r = pcFit();
  if (!r.precise) { pcCheck(); return; }
  Object.assign(PC, { cur: PC.base, step: "walk", box: null, delta: {}, dir: null, reg: null });
  pcShow();
  pcSave();
}

// --- step 2: the walk -------------------------------------------------------------------
function pcRender(keepCurveT) {
  const v = api("poly_view", PC.cur, PC.points, PC.lines, PC.z, PC.box);
  PC.view = v;
  if (v.chart) PC.box = v.chart.box;
  // regenerations: at a degeneration, or wherever the type has a vertex of valence >= 4
  if (v.high.length) {
    const vx = PC.reg && v.high.includes(PC.reg.vertex) ? PC.reg.vertex : v.high[0];
    const r = api("poly_regenerations", PC.cur, vx, PC.points, PC.lines, PC.z, pcScale(), PC.reg && PC.reg.from);
    PC.reg = { vertex: vx, from: PC.reg && PC.reg.from, edge: PC.reg && PC.reg.vertex === vx ? PC.reg.edge : null,
               list: r.regenerations };
  } else PC.reg = null;
  if (v.dim > 2) pcDirection();
  pcDrawCurve(v, keepCurveT);
  pcDrawChart(v);
  pcDrawDir(v);
  pcDrawWall();
}
const pcScale = () => {
  const ls = PC.view ? Object.values(PC.view.lengths).map(pcNum) : [];
  return pcStr(Math.max(1, ...ls));
};

let pcCurveT = null;
function pcDrawCurve(v, keepT) {
  document.getElementById("pc-curve-name").textContent = v.name + (PC.reg ? " · a vertex can regenerate" : "");
  const big = v.dim > 2;
  const d = pcDraw("pc-curve", v.picture, { keepT, pickEdge: big ? (e => e.kind === "bounded") : null });
  pcCurveT = d.T;
  // the direction asked for: lengthen in green, shorten in red
  Object.entries(PC.delta).forEach(([eid, s]) => {
    const ln = d.lines[eid];
    if (!ln) return;
    ln.setAttribute("stroke", s > 0 ? PC_PLUS : PC_MINUS);
    ln.setAttribute("stroke-width", 5);
  });
  const status = document.getElementById("pc-lengths");
  const idle = "lengths: " + Object.entries(v.lengths).map(([n, l]) => `${n} ${pcShort(l)}`).join(", ");
  status.textContent = idle;
  d.edgePicks.forEach(t => {
    t.hit.addEventListener("pick-enter", () => {
      const s = PC.delta[t.edge.id];
      status.textContent = `${t.edge.name} (${pcShort(v.lengths[t.edge.name])}): click to ` +
        (!s ? "lengthen it" : s > 0 ? "shorten it instead" : "leave it alone");
    });
    t.hit.addEventListener("pick-leave", () => { status.textContent = idle; });
    t.hit.addEventListener("pick-click", () => pcGuard(() => {
      const s = PC.delta[t.edge.id];
      if (!s) PC.delta[t.edge.id] = 1;
      else if (s > 0) PC.delta[t.edge.id] = -1;
      else delete PC.delta[t.edge.id];
      pcRender(pcCurveT);
      pcSave();
    }));
  });
}

// the chart: the polyhedron in its free coordinates (dimension 1 or 2)
const CH = { ox: 80, oy: 340, w: 480, h: 290 };
const chXY = (ab, box) => {
  const fx = (ab[0] - pcNum(box[0][0])) / (pcNum(box[0][1]) - pcNum(box[0][0]));
  if (box.length < 2) return [CH.ox + fx * CH.w, 200];
  const fy = (ab[1] - pcNum(box[1][0])) / (pcNum(box[1][1]) - pcNum(box[1][0]));
  return [CH.ox + fx * CH.w, CH.oy - fy * CH.h];
};
const chAB = (q, box) => {
  const a = pcNum(box[0][0]) + (q[0] - CH.ox) / CH.w * (pcNum(box[0][1]) - pcNum(box[0][0]));
  if (box.length < 2) return [a];
  return [a, pcNum(box[1][0]) + (CH.oy - q[1]) / CH.h * (pcNum(box[1][1]) - pcNum(box[1][0]))];
};
const pcZoom = () => { const z = document.getElementById("pc-chart")._zoom; return z ? z.k : 1; };

function pcDrawChart(v) {
  const svg = clearSvg("pc-chart");
  const dimEl = document.getElementById("pc-dim"), where = document.getElementById("pc-where");
  dimEl.textContent = v.dim == null ? "" : `— dimension ${v.dim}`;
  svg.style.display = v.chart || v.dim === 0 ? "" : "none";
  if (v.dim === 0) {
    svg.appendChild(keepSize(svgEl("circle", { cx: 300, cy: 200, r: 7, fill: "var(--accent)" }), { r: 7 }));
    where.textContent = "The constraints fix the curve: the polyhedron is a point.";
    applyKeptSizes(svg, pcZoom());
    return;
  }
  if (!v.chart) {
    where.textContent = v.dim > 2 ? "Too many dimensions to draw: choose a direction on the curve." : "";
    return;
  }
  const ch = v.chart, box = ch.box, two = ch.axes.length === 2;
  const c = ch.coords.map(pcNum);
  const label = (t, at, d, color, fs, anchor) => {
    const el = text(0, 0, t, color || "var(--muted)");
    if (anchor) el.setAttribute("text-anchor", anchor);
    svg.appendChild(keepSize(el, { fs: fs || 11, at, d }));
  };
  // the axes, with the ends of the box
  const A = chXY(two ? [pcNum(box[0][0]), pcNum(box[1][0])] : [pcNum(box[0][0])], box);
  const B = chXY(two ? [pcNum(box[0][1]), pcNum(box[1][0])] : [pcNum(box[0][1])], box);
  svg.appendChild(keepSize(svgEl("line", { x1: A[0], y1: A[1], x2: B[0], y2: B[1], stroke: "var(--muted)" }), { sw: 1.5 }));
  label(ch.axes[0].name, B, [0, 22], "var(--ink)", 12, "end");
  label(pcShort(box[0][0]), A, [0, 36]); label(pcShort(box[0][1]), B, [0, 36]);
  if (two) {
    const C = chXY([pcNum(box[0][0]), pcNum(box[1][1])], box);
    svg.appendChild(keepSize(svgEl("line", { x1: A[0], y1: A[1], x2: C[0], y2: C[1], stroke: "var(--muted)" }), { sw: 1.5 }));
    label(ch.axes[1].name, C, [-8, -8], "var(--ink)", 12, "start");
    label(pcShort(box[1][1]), C, [-8, 4], null, 10, "end");
  }
  const reg = ch.region;
  if (reg && reg.polygon) {
    const poly = reg.polygon.map(q => chXY(q, box).join(",")).join(" ");
    svg.insertBefore(svgEl("polygon", { points: poly, fill: "var(--accent)", "fill-opacity": 0.13, stroke: "none" }), svg.firstChild);
    const cen = chXY([0, 1].map(k => reg.polygon.reduce((t, q) => t + q[k], 0) / reg.polygon.length), box);
    reg.walls.forEach(w => {
      const a = chXY(w.from, box), b = chXY(w.to, box);
      svg.appendChild(keepSize(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "var(--ink)",
        "stroke-linecap": "round" }), { sw: 2 }));
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
      let nx = -dy / L, ny = dx / L;
      if ((cen[0] - mid[0]) * nx + (cen[1] - mid[1]) * ny < 0) { nx = -nx; ny = -ny; }
      label(w.name + " → 0", mid, [nx * 22, ny * 22 + 4], "var(--ink)", 11);
    });
  } else if (reg && reg.interval) {
    const a = chXY([reg.interval[0]], box), b = chXY([reg.interval[1]], box);
    svg.appendChild(keepSize(svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "var(--accent)",
      "stroke-opacity": 0.5, "stroke-linecap": "round" }), { sw: 10 }));
    reg.walls.forEach(w => {
      const p = chXY([w.at[0]], box);
      svg.appendChild(keepSize(svgEl("line", { x1: p[0], y1: p[1] - 14, x2: p[0], y2: p[1] + 14, stroke: "var(--ink)" }), { sw: 2 }));
      label(w.name + " → 0", p, [0, -22], "var(--ink)", 11);
    });
  }
  const q = chXY(two ? c : [c[0]], box);
  svg.appendChild(keepSize(svgEl("circle", { cx: q[0], cy: q[1], fill: "var(--accent)", stroke: "var(--panel)",
    class: "mw-dot" }), { r: 7, sw: 2 }));
  where.textContent = ch.axes.map((a, i) => `${a.name} = ${pcShort(ch.coords[i])}`).join(", ") +
    " — drag the point; it stops where an edge reaches length 0";
  applyKeptSizes(svg, pcZoom());
}

// drag the chart's point (from the point itself); a tap elsewhere walks it there.
// A drag ends where the type changes (an edge reached length 0): the press
// still held is spent -- its moves and the click on letting go do nothing --
// and only a new press moves the point on, in the new type.
let pcChartRaf = 0;
function pcWireChart() {
  const svg = document.getElementById("pc-chart");
  let drag = null, pending = null;          // null | "active" | "spent"
  const toSvg = ev => {
    const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
    const q = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [q.x, q.y];
  };
  const can = () => PC.step === "walk" && PC.view && PC.view.chart;
  const walkTo = q => {
    pending = q;
    if (pcChartRaf) return;
    pcChartRaf = requestAnimationFrame(() => {
      pcChartRaf = 0;
      const target = pending; pending = null;
      if (!target || !can() || drag === "spent") return;
      const before = PC.cur;
      pcGuard(() => pcMove(chAB(target, PC.view.chart.box)));
      if (PC.cur !== before && drag === "active") drag = "spent";
    });
  };
  svg.addEventListener("pointerdown", ev => {
    if (!can() || (ev.pointerType === "mouse" && ev.button !== 0)) return;
    const ch = PC.view.chart, c = ch.coords.map(pcNum);
    const dot = chXY(ch.axes.length === 2 ? c : [c[0]], ch.box), q = toSvg(ev);
    if (Math.hypot(q[0] - dot[0], q[1] - dot[1]) > 24 / pcZoom()) return;   // not the point: pan / pinch
    ev.stopImmediatePropagation();
    ev.preventDefault();
    drag = "active";
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic */ }
  });
  svg.addEventListener("pointermove", ev => {
    if (!drag) return;
    ev.stopImmediatePropagation();               // a spent press does not pan either
    if (drag === "active") walkTo(toSvg(ev));
  });
  const end = ev => {
    if (!drag) return;
    drag = null;
    ev.stopImmediatePropagation();
    PC.chartDragEndAt = Date.now();
    pcSave();
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("click", ev => {
    if (!can() || Date.now() - (PC.chartDragEndAt || 0) < 400) return;
    walkTo(toSvg(ev));
    setTimeout(pcSave, 0);
  });
}

function pcMove(ab) {
  const r = api("poly_move", PC.cur, PC.points, PC.lines, PC.z, ab.map(pcStr));
  PC.z = r.z;
  if (r.wall) pcSnap(r.wall.edge);
  pcRender();
}

// an edge reached length 0: the curve is now of the type with it contracted
function pcSnap(edgeId) {
  const from = PC.cur;
  const w = api("poly_wall", PC.cur, edgeId, PC.points, PC.lines, PC.z, pcScale(), false);
  Object.assign(PC, { cur: w.wall_id, z: w.z, box: null, delta: {}, dir: null,
                      reg: { vertex: w.vertex, from, edge: w.edge } });
}

// --- higher dimension: a direction --------------------------------------------------
function pcDirection() {
  PC.dir = Object.keys(PC.delta).length
    ? api("poly_direction", PC.cur, PC.points, PC.lines, PC.z, PC.delta) : null;
}

function pcDrawDir(v) {
  const box = document.getElementById("pc-dir");
  box.hidden = !(v.dim > 2);
  if (box.hidden) return;
  const txt = document.getElementById("pc-dir-text");
  const endTxt = document.getElementById("pc-dir-end");
  pcSlider.set(0);
  const d = PC.dir;
  if (!d) { txt.textContent = "No direction yet."; endTxt.textContent = ""; pcSlider.enable(false); return; }
  if (!d.moves) {
    txt.textContent = "With the constraints kept this direction does not move the curve: choose others.";
    endTxt.textContent = ""; pcSlider.enable(false); return;
  }
  pcSlider.enable(true);
  txt.innerHTML = "Moving: " + Object.entries(d.change).map(([n, x]) =>
    `<b style="color:${pcNum(x) > 0 ? PC_PLUS : PC_MINUS}">${escapeHtml(n)}</b> ${pcNum(x) > 0 ? "+" : "−"}${pcShort(String(Math.abs(pcNum(x))))}`).join(", ");
  endTxt.textContent = d.wall ? `All the way: ${d.wall.name} reaches length 0 (after ${pcShort(d.t_max)}).`
    : "Nothing degenerates along it: the slider goes a fixed way.";
}

// The slider (0 .. 1000, from here to the first degeneration), made of
// pointer events so mouse, touch and the Pencil drag it alike; arrow keys too.
// Moving it moves the curve along the direction; letting go keeps it there.
const pcSlider = (() => {
  const el = () => document.getElementById("pc-slider");
  let value = 0, enabled = false;
  const paint = () => {
    const f = value / 1000, s = el();
    s.querySelector(".pc-slider-thumb").style.left = `calc((100% - 20px) * ${f})`;
    s.querySelector(".pc-slider-fill").style.width = `calc((100% - 20px) * ${f})`;
    s.setAttribute("aria-valuenow", String(value));
  };
  return {
    get value() { return value; },
    set(v) { value = Math.max(0, Math.min(1000, Math.round(v))); paint(); },
    enable(on) { enabled = on; el().setAttribute("aria-disabled", on ? "false" : "true"); el().classList.toggle("off", !on); },
    get enabled() { return enabled; },
  };
})();

function pcWireSlider() {
  const s = document.getElementById("pc-slider");
  let base = null, raf = 0, active = false;
  const tOf = () => {
    const d = PC.dir, f = pcSlider.value / 1000;
    const tmax = d.t_max != null ? pcNum(d.t_max) : 4 * pcNum(pcScale());
    return f >= 1 && d.t_max != null ? d.t_max : pcStr(f * tmax);
  };
  const input = () => {
    if (!PC.dir || !PC.dir.moves) return;
    if (!base) base = { z: PC.z, T: pcCurveT };
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (!base) return;
      pcGuard(() => {
        const r = api("poly_at", PC.cur, PC.points, PC.lines, base.z, PC.dir.v, tOf());
        pcDraw("pc-curve", r.picture, { keepT: base.T });
      });
    });
  };
  const change = () => pcGuard(() => {
    if (!PC.dir || !PC.dir.moves || !base) return;
    const r = api("poly_at", PC.cur, PC.points, PC.lines, base.z, PC.dir.v, tOf());
    base = null;
    PC.z = r.z;
    if (r.wall) pcSnap(r.wall.edge);
    pcRender();
    pcSave();
  });
  const at = ev => {
    const r = s.getBoundingClientRect();
    return 1000 * Math.max(0, Math.min(1, (ev.clientX - r.left - 10) / Math.max(1, r.width - 20)));
  };
  s.addEventListener("pointerdown", ev => {
    if (!pcSlider.enabled || (ev.pointerType === "mouse" && ev.button !== 0)) return;
    ev.preventDefault();
    active = true;
    try { s.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic */ }
    pcSlider.set(at(ev)); input();
  });
  s.addEventListener("pointermove", ev => { if (active) { pcSlider.set(at(ev)); input(); } });
  const end = () => { if (active) { active = false; change(); } };
  s.addEventListener("pointerup", end);
  s.addEventListener("pointercancel", end);
  s.addEventListener("keydown", ev => {
    if (!pcSlider.enabled) return;
    const step = { ArrowRight: 20, ArrowUp: 20, ArrowLeft: -20, ArrowDown: -20, End: 1000, Home: -1000 }[ev.key];
    if (step == null) return;
    ev.preventDefault();
    pcSlider.set(pcSlider.value + step); input(); change();
  });
}

// --- regenerations -------------------------------------------------------------------
function pcDrawWall() {
  const box = document.getElementById("pc-wall");
  if (!PC.reg || !PC.reg.list) { box.hidden = true; document.getElementById("pc-regens").innerHTML = ""; return; }
  box.hidden = false;
  const v = PC.view.picture.vertices.find(x => x.id === PC.reg.vertex);
  document.getElementById("pc-wall-text").textContent = (PC.reg.edge
    ? `${PC.reg.edge} reached length 0: the curve has a vertex of higher valence. `
    : "The curve has a vertex of valence 4 or more. ") + "Choose how it regenerates (or move on in this type):";
  const list = document.getElementById("pc-regens");
  list.innerHTML = "";
  PC.reg.list.forEach((r, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mw-regen" + (r.back ? " back" : "");
    const id = "pc-regen-" + i;
    const svg = document.createElementNS(SVGNS, "svg");
    svg.id = id; svg.setAttribute("viewBox", `0 0 ${VBW} ${VBH}`);
    b.appendChild(svg);
    const cap = document.createElement("span");
    cap.textContent = r.back ? "back" : r.enter ? "go on" : "cannot";
    b.appendChild(cap);
    b.title = r.back ? "Go back the way you came" : r.enter ? "Go on into this type" : r.why;
    b.disabled = !r.enter;
    b.onclick = () => pcGuard(() => pcRegenerate(r.index));
    list.appendChild(b);
    drawCurve({ curve: r.picture }, { svgId: id, labels: false });
  });
}

function pcRegenerate(index) {
  const r = api("poly_regenerate", PC.cur, PC.reg.vertex, index, PC.points, PC.lines, PC.z, pcScale());
  if (!r.id) { alert("Cannot go on into it: " + r.why); return; }
  Object.assign(PC, { cur: r.id, z: r.z, box: null, delta: {}, dir: null, reg: null });
  pcRender();
  pcSave();
}

pcBoot().catch(err => {
  document.getElementById("boot-msg").innerHTML =
    '<span class="err">Failed to start: ' + escapeHtml(err.message) + "</span>";
  console.error(err);
});
