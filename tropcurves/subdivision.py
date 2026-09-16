"""Dual (mixed) subdivision of a combinatorial type -- a display convenience.

The combinatorial type (tree + slopes) is the object of record. To *draw* its
dual subdivision we pick an arbitrary maximal-dimensional (generic) chamber:
choose generic edge lengths, embed the tree, read off the transverse
self-crossings of the image, and dualize.

Construction (the classical moment/gradient duality):

* Embed the tree; every edge becomes a segment (bounded edge) or a ray (end),
  carrying a weight ``w`` and primitive direction ``u``.
* Clip the rays to a large box and split all segments at their transverse
  crossings, giving a planar arrangement (a DCEL).
* Trace the faces of the arrangement (regions of the complement of the curve).
* Assign each face a lattice point ``phi`` (a vertex of the subdivision):
  crossing a curve edge with data ``(w, u)`` from its right side to its left
  changes ``phi`` by ``w * rot90(u)``; box edges (not part of the curve) do not
  change it.
* The dual cell at each real curve vertex (tree vertex or crossing) is the
  convex hull of ``phi`` over the faces around it: triangles at trivalent
  vertices, parallelograms at crossings, larger mixed cells otherwise.

Cells tile the Newton polygon (up to translation). Multiplicities are out of
scope. See ``docs/DESIGN.md`` section 2.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Tuple

from .curve import Curve
from .geometry import Vec2, rot90, primitive, convex_hull
from .layout import embed, generic_lengths, Point

FPoint = Tuple[Fraction, Fraction]


# ---------------------------------------------------------------------------
# exact rational point helpers
# ---------------------------------------------------------------------------
def _sub(a: FPoint, b: FPoint) -> FPoint:
    return (a[0] - b[0], a[1] - b[1])


def _cross(a: FPoint, b: FPoint) -> Fraction:
    return a[0] * b[1] - a[1] * b[0]


def _dot(a: FPoint, b: FPoint) -> Fraction:
    return a[0] * b[0] + a[1] * b[1]


def _on_segment_interior(p: FPoint, a: FPoint, b: FPoint) -> bool:
    """True if p lies strictly between a and b on segment [a, b]."""
    ab = _sub(b, a)
    ap = _sub(p, a)
    if _cross(ab, ap) != 0:
        return False
    d = _dot(ap, ab)
    if d <= 0:
        return False
    return d < _dot(ab, ab)


# ---------------------------------------------------------------------------
# public result types
# ---------------------------------------------------------------------------
@dataclass
class SubdivisionCell:
    """One 2-cell of the dual subdivision (a convex lattice polygon, CCW)."""

    vertices: List[Vec2]

    @property
    def num_sides(self) -> int:
        return len(self.vertices)

    def is_parallelogram(self) -> bool:
        vs = self.vertices
        if len(vs) != 4:
            return False
        return (vs[0] + vs[2]) == (vs[1] + vs[3])


@dataclass
class Subdivision:
    cells: List[SubdivisionCell] = field(default_factory=list)
    lattice_points: List[Vec2] = field(default_factory=list)

    @property
    def num_cells(self) -> int:
        return len(self.cells)

    def cell_side_counts(self) -> List[int]:
        return sorted(c.num_sides for c in self.cells)


class SubdivisionError(RuntimeError):
    """Raised when a generic chamber could not be built (after retries)."""


# ---------------------------------------------------------------------------
# arrangement pieces
# ---------------------------------------------------------------------------
@dataclass
class _Seg:
    a: FPoint
    b: FPoint
    w: int          # weight; 0 for the bounding box
    u: Vec2         # primitive direction a -> b (meaningless when w == 0)


def _curve_segments_and_rays(curve: Curve, pos: Dict[str, Point]):
    segs: List[_Seg] = []          # bounded curve edges
    rays: List[Tuple[FPoint, Vec2, int]] = []   # (start, primitive dir, weight)
    for e in curve.bounded:
        a = pos[e.tail]
        b = pos[e.head]  # type: ignore[index]
        u, w = primitive(e.outgoing(e.tail))
        segs.append(_Seg(a=a, b=b, w=w, u=u))
    for e in curve.ends:
        u, w = primitive(e.vec)
        rays.append((pos[e.tail], u, w))
    return segs, rays


def _seg_ray_and_ray_ray_crossings(segs, rays) -> List[FPoint]:
    """Transverse crossings among bounded segments and end rays."""
    objs = []  # (a, dir, tmax or None)  tmax in primitive units
    for s in segs:
        # param of b from a in units of u
        tmax = _param_along(s.a, s.b, s.u)
        objs.append((s.a, s.u, tmax))
    for (a, u, _w) in rays:
        objs.append((a, u, None))

    pts: List[FPoint] = []
    for i in range(len(objs)):
        for j in range(i + 1, len(objs)):
            p = _obj_intersection(objs[i], objs[j])
            if p is not None:
                pts.append(p)
    return pts


def _param_along(a: FPoint, b: FPoint, u: Vec2) -> Fraction:
    if u.x != 0:
        return (b[0] - a[0]) / u.x
    return (b[1] - a[1]) / u.y


def _obj_intersection(o1, o2) -> Optional[FPoint]:
    a1, u1, t1max = o1
    a2, u2, t2max = o2
    d1 = (Fraction(u1.x), Fraction(u1.y))
    d2 = (Fraction(u2.x), Fraction(u2.y))
    denom = _cross(d1, d2)
    if denom == 0:
        return None
    diff = _sub(a2, a1)
    t = _cross(diff, d2) / denom
    s = _cross(diff, d1) / denom

    def ok(param, tmax):
        if param <= 0:
            return False
        if tmax is None:
            return True
        return param < tmax

    if not ok(t, t1max) or not ok(s, t2max):
        return None
    return (a1[0] + t * Fraction(u1.x), a1[1] + t * Fraction(u1.y))


# ---------------------------------------------------------------------------
# main build
# ---------------------------------------------------------------------------
def build_subdivision(curve: Curve, max_attempts: int = 10) -> Subdivision:
    """Build the dual mixed subdivision in a generic chamber.

    Tries a few generic length seeds until one yields a non-degenerate
    arrangement. Raises :class:`SubdivisionError` if none succeeds.
    """
    if not curve.ends:
        raise ValueError("curve has no ends; subdivision is undefined")
    _reject_parallel_at_vertex(curve)
    last_err: Optional[Exception] = None
    for seed in range(1, max_attempts + 1):
        try:
            pos = embed(curve, generic_lengths(curve, seed=seed))
            return _build_once(curve, pos)
        except SubdivisionError as exc:  # degenerate -> re-seed
            last_err = exc
            continue
    raise SubdivisionError(f"could not find a generic chamber after "
                           f"{max_attempts} attempts: {last_err}")


def _reject_parallel_at_vertex(curve: Curve) -> None:
    """Reject types with two incident edges sharing a primitive direction.

    Two edges leaving one vertex in the same primitive direction overlap in the
    image for *any* choice of lengths, so no generic (maximal-dimensional)
    chamber exists and the dual subdivision is not defined. (Antiparallel edges
    -- a straight line through the vertex -- are fine.)
    """
    for v in curve.vertices:
        seen: Dict[Tuple[int, int], str] = {}
        for e in curve.incident(v):
            out = e.outgoing(v)
            if out.is_zero():
                continue  # markings
            u, _ = primitive(out)
            key = (u.x, u.y)
            if key in seen:
                raise SubdivisionError(
                    f"edges {seen[key]!r} and {e.name!r} leave vertex {v!r} in the "
                    f"same direction {key}; the image is degenerate (no generic chamber)"
                )
            seen[key] = e.name


def _build_once(curve: Curve, pos: Dict[str, Point]) -> Subdivision:
    segs, rays = _curve_segments_and_rays(curve, pos)
    crossings = _seg_ray_and_ray_ray_crossings(segs, rays)
    _assert_distinct(crossings, [pos[v] for v in curve.vertices])

    # bounding box containing all tree vertices and crossings
    xs = [p[0] for p in pos.values()] + [c[0] for c in crossings]
    ys = [p[1] for p in pos.values()] + [c[1] for c in crossings]
    span = max(max(xs) - min(xs), max(ys) - min(ys), Fraction(1))
    m = span * 2 + 3
    xmin, xmax = min(xs) - m, max(xs) + m
    ymin, ymax = min(ys) - m, max(ys) + m
    corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]

    all_segs: List[_Seg] = list(segs)
    # rays -> segments clipped to the box
    for (a, u, w) in rays:
        exit_pt = _ray_box_exit(a, u, xmin, xmax, ymin, ymax)
        all_segs.append(_Seg(a=a, b=exit_pt, w=w, u=u))
    # box edges (weight 0)
    for i in range(4):
        all_segs.append(_Seg(a=corners[i], b=corners[(i + 1) % 4], w=0, u=Vec2(0, 0)))

    real_vertex_pts = {pos[v] for v in curve.vertices} | set(crossings)
    return _arrangement_to_subdivision(all_segs, real_vertex_pts, extra_nodes=crossings)


def _assert_distinct(crossings: List[FPoint], vertex_pts: List[FPoint]) -> None:
    seen = set()
    for c in crossings:
        if c in seen:
            raise SubdivisionError("two crossings coincide (degenerate chamber)")
        seen.add(c)
    vs = set(vertex_pts)
    for c in crossings:
        if c in vs:
            raise SubdivisionError("a crossing hits a vertex (degenerate chamber)")


def _ray_box_exit(a: FPoint, u: Vec2, xmin, xmax, ymin, ymax) -> FPoint:
    """Exit point of ray a + t*u (t>0) through the axis-aligned box."""
    cands: List[Fraction] = []
    if u.x != 0:
        for X in (xmin, xmax):
            t = (X - a[0]) / u.x
            if t > 0:
                y = a[1] + t * u.y
                if ymin <= y <= ymax:
                    cands.append(t)
    if u.y != 0:
        for Y in (ymin, ymax):
            t = (Y - a[1]) / u.y
            if t > 0:
                x = a[0] + t * u.x
                if xmin <= x <= xmax:
                    cands.append(t)
    if not cands:
        raise SubdivisionError("ray does not exit the bounding box")
    t = min(cands)
    return (a[0] + t * u.x, a[1] + t * u.y)


# ---------------------------------------------------------------------------
# DCEL from segments
# ---------------------------------------------------------------------------
def _arrangement_to_subdivision(segs: List[_Seg], real_vertex_pts,
                                extra_nodes=()) -> Subdivision:
    # 1. node set: all segment endpoints plus crossing points (which are interior
    # to the segments they lie on and must become split vertices).
    nodes: Dict[FPoint, int] = {}

    def node_id(p: FPoint) -> int:
        if p not in nodes:
            nodes[p] = len(nodes)
        return nodes[p]

    for s in segs:
        node_id(s.a)
        node_id(s.b)
    for p in extra_nodes:
        node_id(p)
    node_pts: List[FPoint] = [None] * len(nodes)  # type: ignore[list-item]
    for p, i in nodes.items():
        node_pts[i] = p

    # 2. split each segment at any node lying in its interior
    # darts: dict origin -> list of (target, w, u_dir)
    darts: List[Tuple[int, int, int, Vec2]] = []  # (origin, target, w, u)
    for s in segs:
        pts_on = [p for p in nodes if _on_segment_interior(p, s.a, s.b)]
        ab = _sub(s.b, s.a)
        # sort split points by scalar projection along a->b (works for any
        # direction, curve edge or box edge)
        chain = [s.a] + sorted(pts_on, key=lambda p: _dot(_sub(p, s.a), ab)) + [s.b]
        for k in range(len(chain) - 1):
            A, B = chain[k], chain[k + 1]
            ia, ib = nodes[A], nodes[B]
            u = s.u if s.w else Vec2(0, 0)
            darts.append((ia, ib, s.w, u))
            darts.append((ib, ia, s.w, Vec2(-u.x, -u.y)))

    # 3. rotation system: outgoing darts per node, sorted CCW by angle
    out: Dict[int, List[int]] = {i: [] for i in range(len(nodes))}
    for di, (o, t, w, u) in enumerate(darts):
        out[o].append(di)
    dart_index: Dict[Tuple[int, int], int] = {}
    for di, (o, t, w, u) in enumerate(darts):
        dart_index[(o, t)] = di

    def dart_dir(di: int) -> FPoint:
        o, t, w, u = darts[di]
        return _sub(node_pts[t], node_pts[o])

    for o in out:
        out[o].sort(key=lambda di: _angle_key(dart_dir(di)))
    pos_in_out: Dict[int, int] = {}
    for o, lst in out.items():
        for idx, di in enumerate(lst):
            pos_in_out[di] = idx

    def twin(di: int) -> int:
        o, t, w, u = darts[di]
        return dart_index[(t, o)]

    def next_in_face(di: int) -> int:
        # arrive at target; take the dart clockwise-before twin among target's
        # CCW-sorted outgoing darts (interior on the left -> CCW bounded faces).
        tw = twin(di)
        o = darts[tw][0]
        lst = out[o]
        k = pos_in_out[tw]
        return lst[(k - 1) % len(lst)]

    # 4. trace faces
    face_of: Dict[int, int] = {}
    faces: List[List[int]] = []
    for di in range(len(darts)):
        if di in face_of:
            continue
        cycle = []
        cur = di
        while cur not in face_of:
            face_of[cur] = len(faces)
            cycle.append(cur)
            cur = next_in_face(cur)
        faces.append(cycle)

    # identify outer face by signed area (most negative)
    def face_area(cycle: List[int]) -> Fraction:
        s = Fraction(0)
        for di in cycle:
            o, t, w, u = darts[di]
            ax, ay = node_pts[o]
            bx, by = node_pts[t]
            s += ax * by - bx * ay
        return s / 2

    areas = [face_area(f) for f in faces]
    outer = min(range(len(faces)), key=lambda i: areas[i])

    # 5. phi propagation across CURVE darts only (w > 0). The box edges are
    # artificial walls that do not transmit phi, and the outer face (outside the
    # box) is never a real region. Every real region has a curve edge on its
    # boundary, so this BFS reaches them all for a connected curve.
    phi: Dict[int, Vec2] = {}
    start = next((face_of[di] for di in range(len(darts)) if darts[di][2] > 0), None)
    if start is None:
        raise SubdivisionError("no curve edges to build a subdivision from")
    phi[start] = Vec2(0, 0)
    stack = [start]
    while stack:
        f = stack.pop()
        for di in faces[f]:
            o, t, w, u = darts[di]
            if w == 0:
                continue
            f2 = face_of[twin(di)]
            if f2 in phi:
                continue
            # face_of(di) is on the left of di; its twin's face is on the right.
            # phi(right) = phi(left) - w * rot90(u)
            phi[f2] = phi[f] - rot90(u) * w
            stack.append(f2)

    # consistency check (curve darts only)
    for di in range(len(darts)):
        o, t, w, u = darts[di]
        if w == 0:
            continue
        f1 = face_of[di]
        f2 = face_of[twin(di)]
        if f1 in phi and f2 in phi and phi[f1] - phi[f2] != rot90(u) * w:
            raise SubdivisionError("phi is inconsistent (degenerate chamber)")

    # 6. cells at real curve vertices
    cells: List[SubdivisionCell] = []
    all_pts: set[Tuple[int, int]] = set()
    for i, p in enumerate(node_pts):
        if p not in real_vertex_pts:
            continue
        face_ids = []
        for di in out[i]:
            f = face_of[di]
            if f == outer:
                continue
            face_ids.append(f)
        seen = set()
        pts: List[Vec2] = []
        for f in face_ids:
            if f in seen or f not in phi:
                continue
            seen.add(f)
            pts.append(phi[f])
        if len(pts) < 3:
            continue
        hull = convex_hull(pts)
        cells.append(SubdivisionCell(vertices=hull))
        for v in hull:
            all_pts.add((v.x, v.y))

    sub = Subdivision(cells=cells, lattice_points=[Vec2(x, y) for x, y in sorted(all_pts)])
    _normalize_translation(sub)
    return sub


def _angle_key(v: FPoint):
    x, y = v
    half = 0 if (y > 0 or (y == 0 and x > 0)) else 1
    return (half, _AngleCmpProxy(x, y))


class _AngleCmpProxy:
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y

    def __lt__(self, other):
        # smaller angle first within the same half-plane
        return self.x * other.y - self.y * other.x > 0


def _normalize_translation(sub: Subdivision) -> None:
    if not sub.lattice_points:
        return
    minx = min(p.x for p in sub.lattice_points)
    miny = min(p.y for p in sub.lattice_points)
    shift = Vec2(-minx, -miny)
    if shift.is_zero():
        return
    for c in sub.cells:
        c.vertices = [v + shift for v in c.vertices]
    sub.lattice_points = [p + shift for p in sub.lattice_points]
