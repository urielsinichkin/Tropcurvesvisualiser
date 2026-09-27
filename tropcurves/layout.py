"""Embedding a combinatorial type in the plane.

Slopes (primitive directions) are fixed by the combinatorial type; only the
positive **lengths** of bounded edges and the root position are free. This
module places the tree's vertices from a choice of lengths.

Two callers use this:

* the drawing/GUI layer wants a *readable* embedding, and for a derived type
  one that looks like its parent's -- see :func:`display_lengths`;
* the subdivision builder wants a *generic* embedding in a maximal-dimensional
  chamber, so that self-crossings are transverse and isolated -- see
  :func:`generic_lengths`.

Positions use :class:`fractions.Fraction` so intersections stay exact.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Dict, Optional, Tuple

from .curve import Curve, EdgeKind
from .geometry import Vec2, primitive

Point = Tuple[Fraction, Fraction]


def _root_of(curve: Curve, root: Optional[str]) -> str:
    if root is not None:
        if root not in curve.vertices:
            raise ValueError(f"unknown root vertex {root!r}")
        return root
    if not curve.vertices:
        raise ValueError("curve has no vertices")
    return curve.vertices[0]


def embed(
    curve: Curve,
    lengths: Optional[Dict[str, Fraction]] = None,
    root: Optional[str] = None,
) -> Dict[str, Point]:
    """Return vertex positions from bounded-edge lengths (exact rationals).

    ``lengths`` maps bounded-edge id -> positive length; missing edges default to
    length 1. ``root`` (default: first vertex) is placed at the origin. Requires
    a connected tree.
    """
    if not curve.is_connected():
        raise ValueError("cannot embed a disconnected curve")
    r = _root_of(curve, root)
    lengths = {k: Fraction(v) for k, v in (lengths or {}).items()}

    pos: Dict[str, Point] = {r: (Fraction(0), Fraction(0))}
    stack = [r]
    while stack:
        v = stack.pop()
        vx, vy = pos[v]
        for e in curve.incident(v):
            if e.kind is not EdgeKind.BOUNDED:
                continue
            w = e.other(v)
            if w in pos:
                continue
            L = lengths.get(e.id, Fraction(1))
            if L <= 0:
                raise ValueError(f"edge length must be positive (edge {e.name!r})")
            u, _ = primitive(e.outgoing(v))  # primitive ray direction v -> w
            pos[w] = (vx + L * u.x, vy + L * u.y)
            stack.append(w)
    return pos


# Ends are drawn as rays of a finite length, chosen from the picture's size so
# they read as unbounded without dwarfing it. Layout and rendering must agree on
# it, or the clearances computed here would not be the ones on screen.
def vertex_span(pos: Dict[str, Point]) -> float:
    """The larger side of the vertices' bounding box (1.0 if they coincide)."""
    xs = [float(x) for x, _ in pos.values()]
    ys = [float(y) for _, y in pos.values()]
    span = max((max(xs) - min(xs)) if xs else 0.0, (max(ys) - min(ys)) if ys else 0.0)
    return span or 1.0


def end_ray_length(pos: Dict[str, Point]) -> float:
    # Strictly proportional: scaling a layout up must not change how it reads.
    return 0.6 * vertex_span(pos)


# ---------------------------------------------------------------------------
# display layout
# ---------------------------------------------------------------------------
#
# What a readable picture of a type needs, in order:
#
# 1. Edges of comparable *drawn* length. Choosing lengths in lattice units
#    (L = 1 along the primitive direction) draws an edge in direction (3, 4) five
#    times as long as one in direction (1, 0) -- a spread that is pure artifact.
#    So target lengths are Euclidean: every bounded edge aims at length 1, and an
#    edge cut into pieces by interior markings shares that 1 between its pieces,
#    so marking a point on an edge does not stretch it.
# 2. Nothing touching that does not meet: see :func:`min_clearance`.
# 3. Few crossings, where lengths can avoid them (for a type drawn on its own).
# 4. For a derived type, the parent's picture: vertices the two share keep their
#    places as far as the lengths allow, so that, say, a type differing from its
#    parent only by a marking is drawn differing only by that marking.
#
# (4) is a least-squares fit, linear in the lengths: a vertex's position is the
# root's plus a signed sum of length * primitive direction along its path. It is
# solved by coordinate descent with lengths bounded below (pure Python, no numpy
# in the core); (1) enters as a weak prior pulling each edge toward its target,
# which also settles any length the fit leaves free. (2) and (3) are then a
# search over small perturbations of the result, nearest first.

MIN_DRAWN_LENGTH = 0.3          # no bounded edge is drawn shorter than this
# The pull toward target lengths in the fit is only a tie-breaker: it settles
# lengths the parent does not determine, but must never compete with an exact
# match -- an edge renamed by a derivation (a contract-then-resolve that
# recreates it) has a fresh id and so no remembered length, and a stronger pull
# would drag it off the parent's picture.
PRIOR_WEIGHT = 1e-4


def _unit_len(e) -> float:
    u, _ = primitive(e.vec)
    return (float(u.x) ** 2 + float(u.y) ** 2) ** 0.5 or 1.0


def target_drawn_lengths(curve: Curve) -> Dict[str, float]:
    """Euclidean target per bounded edge: 1 per edge of the underlying curve.

    A vertex with exactly two (non-marking) edges is a point in the interior of
    an edge -- a marking put on it, or what removing that marking leaves -- so
    the maximal chains of bounded edges through such points are found, and each
    chain shares a total of 1 equally among its pieces.
    """
    def real(v):
        return [f for f in curve.incident(v) if f.kind is not EdgeKind.MARKING]
    interior = {v for v in curve.vertices if len(real(v)) == 2}
    out: Dict[str, float] = {}
    seen = set()
    for e in curve.bounded:
        if e.id in seen:
            continue
        chain, stack = [], [e]
        seen.add(e.id)
        while stack:                       # grow through interior points
            cur = stack.pop()
            chain.append(cur)
            for v in (cur.tail, cur.head):
                if v in interior:
                    for f in real(v):
                        if f.kind is EdgeKind.BOUNDED and f.id not in seen:
                            seen.add(f.id)
                            stack.append(f)
        for piece in chain:
            out[piece.id] = 1.0 / len(chain)
    return out


def _paths(curve: Curve) -> Dict[str, list]:
    """For each vertex, the (edge id, sign) steps from the root, as embed walks."""
    root = _root_of(curve, None)
    paths: Dict[str, list] = {root: []}
    stack = [root]
    while stack:
        v = stack.pop()
        for e in curve.incident(v):
            if e.kind is not EdgeKind.BOUNDED:
                continue
            w = e.other(v)
            if w in paths:
                continue
            paths[w] = paths[v] + [(e.id, 1.0 if e.tail == v else -1.0)]
            stack.append(w)
    return paths


def layout_reference(curve: Curve, lengths: Dict[str, Fraction]) -> dict:
    """What a derived type is fitted to: this curve's vertex positions and
    drawn edge lengths under ``lengths``."""
    pos = embed(curve, lengths)
    fpos = _float_pos(pos)
    return {
        "pos": fpos,
        "clearance": _Scene(curve).clearance(fpos),
        "span": _Scene._vspan(fpos),
        "drawn": {e.id: (float(lengths.get(e.id, Fraction(1))) * _unit_len(e),
                         primitive(e.vec)[0].to_list()) for e in curve.bounded},
    }


def _fit(curve: Curve, reference: Optional[dict]) -> Dict[str, float]:
    """Lattice lengths: fitted to the reference, leaning toward the targets."""
    targets = target_drawn_lengths(curve)
    unit = {e.id: _unit_len(e) for e in curve.bounded}
    dirs = {e.id: primitive(e.vec)[0] for e in curve.bounded}
    # prior: the parent's drawn length for an edge it shares (same line), else target
    prior = dict(targets)
    if reference:
        for e in curve.bounded:
            ref = reference["drawn"].get(e.id)
            if ref and (ref[1] == dirs[e.id].to_list() or ref[1] == (-dirs[e.id]).to_list()):
                prior[e.id] = ref[0]
    L = {k: prior[k] / unit[k] for k in unit}
    L0 = dict(L)
    Lmin = {k: MIN_DRAWN_LENGTH / unit[k] for k in unit}
    w = {k: unit[k] ** 2 for k in unit}

    shared = []
    if reference:
        paths = _paths(curve)
        shared = [v for v in curve.vertices if v in reference["pos"] and v in paths]
    if len(shared) < 2:                     # nothing to fit beyond a translation
        return {k: max(L[k], Lmin[k]) for k in L}

    steps = {v: paths[v] for v in shared}
    touches: Dict[str, list] = {k: [] for k in unit}      # edge -> [(vertex, sign)]
    for v, st in steps.items():
        for eid, sg in st:
            touches[eid].append((v, sg))
    P = {v: reference["pos"][v] for v in shared}

    def place(v):
        x = y = 0.0
        for eid, sg in steps[v]:
            x += sg * L[eid] * dirs[eid].x
            y += sg * L[eid] * dirs[eid].y
        return x, y
    # residuals with the best translation
    R = {}
    for v in shared:
        x, y = place(v)
        R[v] = [x - P[v][0], y - P[v][1]]
    def recentre():
        mx = sum(r[0] for r in R.values()) / len(R)
        my = sum(r[1] for r in R.values()) / len(R)
        for r in R.values():
            r[0] -= mx; r[1] -= my
    recentre()
    for _ in range(400):
        biggest = 0.0
        for eid in L:
            ux, uy = float(dirs[eid].x), float(dirs[eid].y)
            a = PRIOR_WEIGHT * w[eid]
            g = PRIOR_WEIGHT * w[eid] * (L[eid] - L0[eid])
            for v, sg in touches[eid]:
                a += w[eid]
                g += sg * (ux * R[v][0] + uy * R[v][1])
            new = max(Lmin[eid], L[eid] - g / a)
            d = new - L[eid]
            if d:
                L[eid] = new
                for v, sg in touches[eid]:
                    R[v][0] += sg * d * ux
                    R[v][1] += sg * d * uy
                biggest = max(biggest, abs(d))
        recentre()
        if biggest < 1e-10:
            break
    return L


def _as_fractions(L: Dict[str, float]) -> Dict[str, Fraction]:
    return {k: Fraction(v).limit_denominator(4096) for k, v in L.items()}


def count_crossings(curve: Curve, pos: Dict[str, Point]) -> int:
    """Transverse crossings between edges that share no vertex, as drawn."""
    return _Scene(curve).crossings(_float_pos(pos))


CLEARANCE_GOAL = 0.045      # of the picture's span: ~24px on a 540px-wide curve
CLEARANCE_WEIGHT = 6.0      # a shortfall of the whole goal costs this much
CROSSING_WEIGHT = 1.0       # per crossing, for a type drawn on its own
DISTORTION_WEIGHT = 1.0     # mean |log(drawn / target)|
LIKENESS_WEIGHT = 5.0       # rms displacement from the parent, per picture span
_STEPS = (0.5, 0.7, 0.85, 1.18, 1.43, 2.0)


def _hill_climb(start: Dict[str, float], floor: Dict[str, float], cost, steps: int = 12):
    """Greedy best-improvement: each step makes the one edge change that lowers
    the cost most, until none does.

    Deterministic, and aimed where it matters: a bottleneck is usually one or two
    edges, and changing only those keeps the rest of the picture even.
    """
    L = dict(start)
    J = cost(L)
    for _ in range(steps):
        best_j, best = J, None
        for eid in sorted(L):
            old = L[eid]
            for f in _STEPS:
                cand = max(floor[eid], old * f)
                if cand == old:
                    continue
                L[eid] = cand
                j = cost(L)
                if j < best_j - 1e-9:
                    best_j, best = j, (eid, cand)
            L[eid] = old
        if best is None:
            break
        L[best[0]] = best[1]
        J = best_j
    return L


def display_lengths(curve: Curve, reference: Optional[dict] = None, *,
                    target: float = CLEARANCE_GOAL) -> Dict[str, Fraction]:
    """Bounded-edge lengths for drawing ``curve`` (see the notes above).

    ``reference`` (from :func:`layout_reference`) is the parent's layout, for a
    derived type. The fit to it is kept as it is unless it leaves something
    touching -- and a child is only held to the clearance its parent achieved,
    so a type that differs from its parent by nothing but a marking comes out
    identical. Otherwise lengths are improved greedily against a cost of
    clearance shortfall plus, on its own, crossings and unevenness, or, for a
    derived type, displacement from the parent.
    """
    if not curve.bounded or not curve.is_connected():
        return {e.id: Fraction(1) for e in curve.bounded}
    scene = _Scene(curve)
    unit = {e.id: _unit_len(e) for e in curve.bounded}
    floor = {k: MIN_DRAWN_LENGTH / unit[k] for k in unit}
    base = _fit(curve, reference)

    if reference is None:
        goal = target
        targets = target_drawn_lengths(curve)
        import math
        def cost(L):
            pos = scene.positions(L)
            c = scene.clearance(pos)
            shortfall = max(0.0, goal - c) / goal
            distortion = sum(abs(math.log(L[k] * unit[k] / targets[k])) for k in L) / len(L)
            return (CLEARANCE_WEIGHT * shortfall + CROSSING_WEIGHT * scene.crossings(pos)
                    + DISTORTION_WEIGHT * distortion)
        pos = scene.positions(base)
        if scene.clearance(pos) >= goal and scene.crossings(pos) == 0:
            return _as_fractions(base)
        return _as_fractions(_hill_climb(base, floor, cost))

    goal = min(target, reference.get("clearance", target))
    pos = scene.positions(base)
    if scene.clearance(pos) >= goal * 0.999:
        return _as_fractions(base)
    shared = [v for v in curve.vertices if v in reference["pos"]]
    P = reference["pos"]
    span = reference.get("span", 1.0) or 1.0
    import math
    def cost(L):
        pos = scene.positions(L)
        c = scene.clearance(pos)
        shortfall = max(0.0, goal - c) / goal
        if shared:
            mx = sum(pos[v][0] - P[v][0] for v in shared) / len(shared)
            my = sum(pos[v][1] - P[v][1] for v in shared) / len(shared)
            rms = (sum((pos[v][0] - P[v][0] - mx) ** 2 + (pos[v][1] - P[v][1] - my) ** 2
                       for v in shared) / len(shared)) ** 0.5
        else:
            rms = 0.0
        drift = sum(abs(math.log(L[k] / base[k])) for k in L) / len(L)
        return CLEARANCE_WEIGHT * shortfall + LIKENESS_WEIGHT * rms / span + 0.2 * drift
    return _as_fractions(_hill_climb(base, floor, cost))


def readable_lengths(curve: Curve, *, target: float = CLEARANCE_GOAL, tries: int = 96) -> Dict[str, Fraction]:
    """The layout of a type drawn on its own (no parent to resemble)."""
    return display_lengths(curve, None, target=target)


class _Scene:
    """A curve prepared for evaluating many length choices quickly, in floats.

    Positions follow the same walk as :func:`embed`; clearance and crossings are
    measured exactly as :func:`min_clearance` and :func:`count_crossings`
    describe (those delegate here, so the optimizer and the checks agree).
    """

    def __init__(self, curve: Curve) -> None:
        self.curve = curve
        self.root = _root_of(curve, None)
        self.order = []                     # (child, parent, edge id, sign)
        seen = {self.root}
        stack = [self.root]
        while stack:
            v = stack.pop()
            for e in curve.incident(v):
                if e.kind is not EdgeKind.BOUNDED:
                    continue
                w = e.other(v)
                if w in seen:
                    continue
                seen.add(w)
                self.order.append((w, v, e.id, 1.0 if e.tail == v else -1.0))
                stack.append(w)
        self.dir = {}
        for e in curve.bounded:
            u, _ = primitive(e.vec)
            self.dir[e.id] = (float(u.x), float(u.y))
        self.bounded = [(e.id, e.tail, e.head) for e in curve.bounded]
        self.ends = []
        for e in curve.ends:
            u, _ = primitive(e.vec)
            n = (float(u.x) ** 2 + float(u.y) ** 2) ** 0.5 or 1.0
            self.ends.append((e.tail, u.x / n, u.y / n))

    def positions(self, L: Dict[str, float]) -> Dict[str, Tuple[float, float]]:
        pos = {self.root: (0.0, 0.0)}
        for w, v, eid, sg in self.order:
            ux, uy = self.dir[eid]
            l = float(L.get(eid, 1.0))
            pos[w] = (pos[v][0] + sg * l * ux, pos[v][1] + sg * l * uy)
        return pos

    @staticmethod
    def _vspan(pos) -> float:
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        return max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0

    def clearance(self, pos) -> float:
        if len(pos) < 2 and not self.ends:
            return float("inf")
        vspan = self._vspan(pos)
        far, drawn = 2.0 * vspan, 0.6 * vspan
        segs = [((t, h), pos[t], pos[h]) for _, t, h in self.bounded]
        segs += [((t, None), pos[t], (pos[t][0] + far * ux, pos[t][1] + far * uy))
                 for t, ux, uy in self.ends]
        xs = [p[0] for p in pos.values()] + [pos[t][0] + drawn * ux for t, ux, uy in self.ends]
        ys = [p[1] for p in pos.values()] + [pos[t][1] + drawn * uy for t, ux, uy in self.ends]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
        best = float("inf")
        items = list(pos.items())
        for i, (v, p) in enumerate(items):
            for ends, a, b in segs:
                if v == ends[0] or v == ends[1]:
                    continue
                d = _point_segment_distance(p, a, b)
                if d < best:
                    best = d
            for w, q in items[i + 1:]:
                d = _dist(p, q)
                if d < best:
                    best = d
        return best / span

    def crossings(self, pos) -> int:
        ray = 0.6 * self._vspan(pos)
        segs = [((t, h), pos[t], pos[h]) for _, t, h in self.bounded]
        segs += [((t, None), pos[t], (pos[t][0] + ray * ux, pos[t][1] + ray * uy))
                 for t, ux, uy in self.ends]
        def side(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        n = 0
        for i in range(len(segs)):
            vi, a1, a2 = segs[i]
            for j in range(i + 1, len(segs)):
                vj, b1, b2 = segs[j]
                if vi[0] in vj or (vi[1] is not None and vi[1] in vj):
                    continue
                d1, d2 = side(b1, b2, a1), side(b1, b2, a2)
                d3, d4 = side(a1, a2, b1), side(a1, a2, b2)
                if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
                    n += 1
        return n


def _float_pos(pos: Dict[str, Point]) -> Dict[str, Tuple[float, float]]:
    return {v: (float(x), float(y)) for v, (x, y) in pos.items()}


def min_clearance(curve: Curve, pos: Dict[str, Point]) -> float:
    """Distance from the nearest vertex to something it is not part of.

    Measured against every bounded edge and every end that the vertex is not an
    endpoint of, and against every other vertex; reported as a fraction of the
    picture's span, so it means the same thing at any zoom. Larger is cleaner; 0
    means something is touching.

    Ends are tested well past the length they are drawn at. A vertex sitting on
    the *continuation* of an end still reads as lying on it -- and a gap that
    exists only because the ray was cut off just short would vanish the moment
    the picture were drawn a little larger.
    """
    return _Scene(curve).clearance(_float_pos(pos))


def _dist(p, q) -> float:
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def _point_segment_distance(p, a, b) -> float:
    abx, aby = b[0] - a[0], b[1] - a[1]
    denom = abx * abx + aby * aby
    if denom == 0:
        return _dist(p, a)
    t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / denom
    t = max(0.0, min(1.0, t))
    return _dist(p, (a[0] + t * abx, a[1] + t * aby))


def generic_lengths(curve: Curve, seed: int = 1) -> Dict[str, Fraction]:
    """Distinct, deterministic lengths for a generic (maximal-chamber) embedding.

    Uses well-separated rationals so that, for typical inputs, self-crossings are
    transverse and isolated. The subdivision builder additionally verifies
    general position and re-seeds if a degeneracy is detected.
    """
    lengths: Dict[str, Fraction] = {}
    for i, e in enumerate(curve.bounded):
        # Values in [1, 2), all distinct, depending on seed.
        num = 1 + ((seed * 2654435761 + i * 40503) % 997)
        lengths[e.id] = Fraction(997 + num, 997)
    return lengths
