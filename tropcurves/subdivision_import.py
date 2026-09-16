"""Import a combinatorial type from a subdivision (the inverse of the export).

Given a subdivision of a lattice polygon as a list of convex lattice cells, build
the dual genus-0 plane tropical curve:

* each 2-cell -> a vertex;
* each interior edge (shared by two cells) -> a bounded edge, direction the
  clockwise 90-degree turn of the subdivision edge, weight its lattice length;
* each boundary edge -> an end (outward);
* each **parallelogram** cell is a *crossing*, not a genuine vertex, so it is
  opened: its two pairs of opposite (antiparallel-dual) edges are reconnected as
  two straight edges passing through, and the cell's vertex is removed.

The resulting parametrizing curve is validated to be a connected genus-0 tree.
No markings are created (markings are invisible in the subdivision).

The direction convention (clockwise turn) is the exact inverse of
:mod:`tropcurves.subdivision` / :mod:`tropcurves.newton`, so importing the cells
produced by exporting a curve recovers the same ends (hence the same Newton
polygon).

Known v1 limitation: the subdivision must be edge-to-edge, and cells are read as
their convex hull, so a genuine subdivision vertex lying in the *interior* of a
cell's edge (e.g. splitting two parallel ends) is dropped. See
``docs/POSTPONED.md``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from .curve import Curve, Edge, EdgeKind
from .geometry import Vec2, rot_minus90, primitive, convex_hull, polygon_area2


def _as_vec(p) -> Vec2:
    if isinstance(p, Vec2):
        return p
    return Vec2(int(p[0]), int(p[1]))


def _ccw(hull: List[Vec2]) -> List[Vec2]:
    # signed area > 0 means CCW
    s = 0
    n = len(hull)
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        s += a.x * b.y - b.x * a.y
    return hull if s > 0 else list(reversed(hull))


def _is_parallelogram(hull: List[Vec2]) -> bool:
    return len(hull) == 4 and (hull[0] + hull[2]) == (hull[1] + hull[3])


def import_subdivision(cells_points: Sequence[Sequence]) -> Curve:
    """Build the dual curve of a subdivision given as a list of cells.

    Each cell is a sequence of lattice points (``Vec2`` or ``[x, y]``). Cells are
    taken as their convex hull and must tile a lattice polygon edge-to-edge.
    """
    if not cells_points:
        raise ValueError("no cells given")

    cells: List[List[Vec2]] = []
    for pts in cells_points:
        hull = convex_hull([_as_vec(p) for p in pts])
        if len(hull) < 3:
            raise ValueError("a cell is degenerate (fewer than 3 corners)")
        cells.append(_ccw(hull))

    # edge -> list of (cell index, edge index)
    edge_cells: Dict[frozenset, List[Tuple[int, int]]] = defaultdict(list)
    for i, h in enumerate(cells):
        n = len(h)
        for j in range(n):
            a, b = h[j], h[(j + 1) % n]
            edge_cells[frozenset([(a.x, a.y), (b.x, b.y)])].append((i, j))
    for key, lst in edge_cells.items():
        if len(lst) > 2:
            raise ValueError("an edge is shared by more than two cells (not a subdivision)")

    # full dual: every cell is a vertex
    c = Curve()
    for i in range(len(cells)):
        c.add_vertex(f"c{i}")
    eid = 0
    for key, lst in edge_cells.items():
        (i, ji) = lst[0]
        h = cells[i]
        a, b = h[ji], h[(ji + 1) % len(h)]
        vec = rot_minus90(b - a)  # outgoing from cell i's vertex
        if len(lst) == 2:
            k = lst[1][0]
            c.add_bounded(f"e{eid}", f"c{i}", f"c{k}", vec)
        else:
            c.add_end(f"e{eid}", f"c{i}", vec)
        eid += 1

    # open every parallelogram (crossing) vertex
    for i, h in enumerate(cells):
        if _is_parallelogram(h):
            _open_crossing(c, f"c{i}")

    if not c.vertices:
        raise ValueError("subdivision yields no vertices (a bare crossing / reducible curve)")
    c.validate()  # connected genus-0 tree, balanced, no degenerate edges
    return c


def _open_crossing(c: Curve, vid: str) -> None:
    inc = c.incident(vid)
    if len(inc) != 4:
        raise ValueError(f"parallelogram vertex {vid!r} is not 4-valent (non-edge-to-edge?)")
    info = []
    for e in inc:
        u, _ = primitive(e.outgoing(vid))
        info.append((e, u))
    used = set()
    pairs = []
    for a in range(4):
        if a in used:
            continue
        for b in range(a + 1, 4):
            if b in used:
                continue
            if info[a][1] == -info[b][1]:  # antiparallel outgoing -> opposite sides
                pairs.append((info[a][0], info[b][0]))
                used.add(a); used.add(b)
                break
    if len(pairs) != 2:
        raise ValueError(f"crossing at {vid!r} does not split into two straight edges")
    for ea, eb in pairs:
        _merge_through(c, vid, ea, eb)
    c.vertices = [v for v in c.vertices if v != vid]
    c._vset.discard(vid)


def _merge_through(c: Curve, P: str, ea: Edge, eb: Edge) -> None:
    """Reconnect edges ``ea``, ``eb`` (which pass straight through vertex P) into
    a single edge/end, keeping ``ea`` and removing ``eb``."""
    XA = ea.other(P) if ea.kind is EdgeKind.BOUNDED else None
    XB = eb.other(P) if eb.kind is EdgeKind.BOUNDED else None

    if XA is not None and XB is not None:
        out_a = ea.outgoing(XA)
        del c.edges[eb.id]
        ea.tail, ea.head, ea.kind, ea.vec = XA, XB, EdgeKind.BOUNDED, out_a
    elif XA is not None:  # eb is an end -> end now emanates from XA
        out_a = ea.outgoing(XA)
        del c.edges[eb.id]
        ea.tail, ea.head, ea.kind, ea.vec = XA, None, EdgeKind.END, out_a
    elif XB is not None:  # ea is an end -> end now emanates from XB
        out_b = eb.outgoing(XB)
        del c.edges[eb.id]
        ea.tail, ea.head, ea.kind, ea.vec = XB, None, EdgeKind.END, out_b
    else:
        raise ValueError("a crossing joins two ends (a full line with no vertex): reducible curve")
