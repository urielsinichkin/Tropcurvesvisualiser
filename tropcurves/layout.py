"""Embedding a combinatorial type in the plane.

Slopes (primitive directions) are fixed by the combinatorial type; only the
positive **lengths** of bounded edges and the root position are free. This
module places the tree's vertices from a choice of lengths.

Two callers use this:

* the drawing/GUI layer wants a *readable* embedding (spread out, few near
  collisions) -- see :func:`readable_lengths` (a simple heuristic for now;
  aesthetic tuning is deferred, see ``docs/POSTPONED.md``);
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


def readable_lengths(curve: Curve, *, target: float = 0.06, tries: int = 96) -> Dict[str, Fraction]:
    """A deterministic length choice that keeps the picture legible.

    Slopes are fixed by the type, so the only freedom is the bounded-edge
    lengths -- and the obvious choice, all ones, is exactly the kind of special
    point where things line up: a vertex landing on an unrelated edge, two
    vertices coinciding, two parallel edges overlapping. Those coincidences are
    artifacts of the lengths, not features of the type (they form a measure-zero
    set), so they can always be jittered away.

    Search for it directly: score a candidate by :func:`min_clearance` -- how far
    the nearest vertex is from anything it is not part of, relative to the size
    of the picture -- and keep unit lengths if they already clear ``target``,
    otherwise take the first jittered candidate that does, or the roomiest one
    tried. The first round jitters within about +-35% of unit, so the result
    still looks even; only if that cannot clear the target does the search widen
    to lengths that differ by a real factor.

    Crossings *between edges* are left alone: those are real (they dualize to
    parallelograms), and no choice of lengths removes them.
    """
    base = {e.id: Fraction(1) for e in curve.bounded}
    if not base or not curve.is_connected():
        return base
    best, best_score = base, min_clearance(curve, embed(curve, base))
    for lo, hi, den in _JITTER_ROUNDS:
        for seed in range(1, tries + 1):
            if best_score >= target:
                return best
            cand = _jittered_lengths(curve, seed, lo, hi, den)
            score = min_clearance(curve, embed(curve, cand))
            if score > best_score:
                best, best_score = cand, score
    return best


# (lowest numerator, highest numerator, denominator): even-looking lengths
# first, a genuinely spread-out range only as a fallback.
_JITTER_ROUNDS = ((10, 21, 16), (2, 12, 4))


def _jittered_lengths(curve: Curve, seed: int, lo: int, hi: int, den: int) -> Dict[str, Fraction]:
    """Lengths in ``[lo/den, hi/den]``, deterministic in ``seed`` and exact."""
    out: Dict[str, Fraction] = {}
    for i, e in enumerate(curve.bounded):
        step = (seed * 2654435761 + i * 40503 + 12345) % (hi - lo + 1)
        out[e.id] = Fraction(lo + step, den)
    return out


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
    pts = {v: (float(x), float(y)) for v, (x, y) in pos.items()}
    if len(pts) < 2 and not curve.ends:
        return float("inf")
    vspan = vertex_span(pos)
    segments = []          # (endpoint vertices, a, b)
    for e in curve.bounded:
        segments.append(({e.tail, e.head}, pts[e.tail], pts[e.head]))
    for e in curve.ends:
        u, _ = primitive(e.vec)
        n = (float(u.x) ** 2 + float(u.y) ** 2) ** 0.5 or 1.0
        a = pts[e.tail]
        far = 2.0 * vspan
        segments.append(({e.tail}, a, (a[0] + far * u.x / n, a[1] + far * u.y / n)))

    # the picture is the vertices plus the ends *as drawn*
    drawn = end_ray_length(pos)
    tips = []
    for e in curve.ends:
        u, _ = primitive(e.vec)
        n = (float(u.x) ** 2 + float(u.y) ** 2) ** 0.5 or 1.0
        a = pts[e.tail]
        tips.append((a[0] + drawn * u.x / n, a[1] + drawn * u.y / n))
    xs = [p[0] for p in pts.values()] + [t[0] for t in tips]
    ys = [p[1] for p in pts.values()] + [t[1] for t in tips]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)

    best = float("inf")
    for v, p in pts.items():
        for ends, a, b in segments:
            if v in ends:
                continue
            best = min(best, _point_segment_distance(p, a, b))
        for w, q in pts.items():
            if w != v:
                best = min(best, _dist(p, q))
    return best / span


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
