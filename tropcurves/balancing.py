"""Slope solving: derive edge directions from balancing.

The solver is written generally: given a set of edges whose ``vec`` is *known*
(fixed), it solves the per-vertex balancing equations for the remaining
*unknown* bounded edges. For a genus-0 tree with all ends known this is a
triangular system solved by repeatedly peeling off a vertex that has exactly one
unknown incident edge, so the solution is unique.

The v1 user-facing edit exposes only ``apply_two_ends_edit``: change one end and
let a designated dependent end absorb the change (keeping global balancing),
then re-derive every bounded edge.
"""

from __future__ import annotations

from typing import Iterable, Optional, Set

from .curve import Curve, Edge, EdgeKind
from .geometry import Vec2, ZERO


class SlopeSolveError(ValueError):
    """Raised when balancing cannot be solved consistently."""


def _known_ids_default(curve: Curve) -> Set[str]:
    """Ends and markings are known; bounded edges are the unknowns."""
    return {e.id for e in curve.edges.values() if e.kind is not EdgeKind.BOUNDED}


def solve_bounded(curve: Curve, known: Optional[Iterable[str]] = None) -> None:
    """Solve unknown bounded-edge directions from balancing, in place.

    ``known`` is the set of edge ids whose ``vec`` is fixed; defaults to all
    ends and markings (so every bounded edge is solved). Mutates ``curve``.

    Raises :class:`SlopeSolveError` if the system is under-determined (a cycle of
    unknowns — cannot happen on a tree) or inconsistent (balancing cannot hold,
    e.g. the ends do not globally sum to zero).
    """
    known_ids: Set[str] = set(known) if known is not None else _known_ids_default(curve)
    unknown: Set[str] = {e.id for e in curve.bounded if e.id not in known_ids}

    progressed = True
    while unknown and progressed:
        progressed = False
        for v in curve.vertices:
            inc = curve.incident(v)
            unk_here = [e for e in inc if e.id in unknown]
            if len(unk_here) != 1:
                continue
            target = unk_here[0]
            s = ZERO
            for e in inc:
                if e.id in unknown:
                    continue
                s = s + e.outgoing(v)
            # outgoing(target, v) must be -s
            out = -s
            target.vec = out if v == target.tail else -out
            unknown.discard(target.id)
            progressed = True

    if unknown:
        names = sorted(curve.edges[i].name for i in unknown)
        raise SlopeSolveError(
            "balancing is under-determined; could not solve edges: " + ", ".join(names)
        )

    # Consistency: every vertex must now balance. On a tree this can only fail
    # if the fixed data (the ends) do not globally sum to zero.
    for v in curve.vertices:
        r = curve.balancing_residual(v)
        if not r.is_zero():
            raise SlopeSolveError(
                f"balancing is inconsistent at vertex {v!r} (residual {r.to_list()}); "
                "the fixed directions cannot be balanced"
            )


def resolve_slopes(curve: Curve) -> None:
    """Re-derive every bounded edge from the (fixed) ends and markings."""
    solve_bounded(curve, known=_known_ids_default(curve))


def ends_sum(curve: Curve, exclude: Optional[str] = None) -> Vec2:
    """Sum of end direction vectors (markings are zero), optionally excluding one."""
    total = ZERO
    for e in curve.ends:
        if e.id == exclude:
            continue
        total = total + e.vec
    return total


def apply_two_ends_edit(
    curve: Curve,
    edit_end_id: str,
    new_vec: Vec2,
    dependent_end_id: str,
) -> None:
    """Edit one end's slope; a dependent end absorbs it to keep balancing.

    Sets ``edit_end`` to ``new_vec``, then sets ``dependent_end`` to
    ``-(sum of all other ends)`` so that ``sum of ends == 0`` (global balancing),
    and finally re-derives every bounded edge.

    Raises :class:`SlopeSolveError` if the edit is invalid: the two ends must be
    distinct ends, ``new_vec`` and the resulting dependent end must be non-zero,
    and no bounded edge may collapse to zero.
    """
    edit = curve.edges.get(edit_end_id)
    dep = curve.edges.get(dependent_end_id)
    if edit is None or edit.kind is not EdgeKind.END:
        raise SlopeSolveError(f"{edit_end_id!r} is not an end")
    if dep is None or dep.kind is not EdgeKind.END:
        raise SlopeSolveError(f"{dependent_end_id!r} is not an end")
    if edit_end_id == dependent_end_id:
        raise SlopeSolveError("the edited end and the dependent end must be different")
    if new_vec.is_zero():
        raise SlopeSolveError("an end direction must be non-zero")

    # Snapshot for rollback on failure.
    backup = curve.copy()

    edit.vec = new_vec
    # dependent = -(sum of all ends except the dependent one), which now includes
    # the freshly edited end.
    dep.vec = -ends_sum(curve, exclude=dependent_end_id)
    if dep.vec.is_zero():
        _restore(curve, backup)
        raise SlopeSolveError(
            "this edit forces the dependent end to zero; pick a different dependent end"
        )

    try:
        resolve_slopes(curve)
    except SlopeSolveError:
        _restore(curve, backup)
        raise

    degenerate = [e.name for e in curve.bounded if e.vec.is_zero()]
    if degenerate:
        _restore(curve, backup)
        raise SlopeSolveError(
            "this edit collapses bounded edge(s) to zero: " + ", ".join(sorted(degenerate))
        )


def _restore(curve: Curve, backup: Curve) -> None:
    curve.vertices = backup.vertices
    curve._vset = backup._vset
    curve.edges = backup.edges
