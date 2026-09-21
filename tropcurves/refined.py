"""Refined (Goettsche-Schroeter) multiplicity of a combinatorial type.

For a trivalent curve the refined multiplicity is

    mult_q(C) = prod_{V unmarked} [mu(V)]_q^-  *  prod_{V marked} [mu(V)]_q^+

where ``mu(V)`` is the Mikhalkin multiplicity of the vertex -- the lattice
(normalized) area of its dual triangle, which is ``|v1 ^ v2|`` for two of the
three outgoing vectors -- and

    [a]_q^{+-} = (q^{a/2} +- q^{-a/2}) / (q^{1/2} +- q^{-1/2}).

A vertex is **marked** when it carries a marking: internally it is 4-valent
with one contracted end, and counts as a marked trivalent vertex.

A marking in the **interior of an edge** -- a vertex with only two edges, so
internally 3-valent with one contracted end -- is not a vertex of the curve at
all: balancing makes its two edge directions opposite, their wedge vanishes, so
``mu = 0`` and it contributes a factor of 1, leaving the multiplicity alone.
(Written ``[0]^+``, though note the formula above gives ``2/(q^(1/2) +
q^(-1/2))`` at ``a = 0``, which is 1 only at ``q = 1``; the factor here is 1
identically, which is what "does not affect the multiplicity" means.) The same
goes for a bare two-valent vertex with no marking: it is a subdivision point,
not a vertex, so it too contributes 1 rather than the ``[0]^- = 0`` the formula
would give.

Anything else -- a vertex of another shape, or a trivalent one whose dual
triangle is degenerate -- leaves the multiplicity undefined, and
:class:`MultiplicityError` says which vertex and why.

Everything is exact. Values are Laurent polynomials in ``t = q^(1/2)`` over the
integers, except that ``[a]^+`` with ``a`` even is not a polynomial at all: it
keeps a factor of ``1 + t^2`` in the denominator, and nothing else ever can, so
a value is carried as ``num / (1 + t^2)^k`` in lowest terms. That makes equality
exact and addition closed, which the balanced-split search below relies on.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Tuple

from .curve import Curve, EdgeKind
from .geometry import cross


class MultiplicityError(ValueError):
    """The refined multiplicity is not defined for this curve."""


# ---------------------------------------------------------------------------
# Laurent polynomials in t = q^(1/2)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Laurent:
    """``sum coeffs[i] * t^(low + i)``, with no leading or trailing zeros."""

    low: int = 0
    coeffs: Tuple[int, ...] = ()

    @staticmethod
    def of(low: int, coeffs: Sequence[int]) -> "Laurent":
        c = list(coeffs)
        while c and c[-1] == 0:
            c.pop()
        start = 0
        while start < len(c) and c[start] == 0:
            start += 1
        c = c[start:]
        return Laurent(0, ()) if not c else Laurent(low + start, tuple(c))

    @staticmethod
    def mono(exponent: int, coeff: int = 1) -> "Laurent":
        return Laurent.of(exponent, [coeff])

    @property
    def is_zero(self) -> bool:
        return not self.coeffs

    def __add__(self, other: "Laurent") -> "Laurent":
        if self.is_zero:
            return other
        if other.is_zero:
            return self
        low = min(self.low, other.low)
        high = max(self.low + len(self.coeffs), other.low + len(other.coeffs))
        out = [0] * (high - low)
        for i, c in enumerate(self.coeffs):
            out[self.low + i - low] += c
        for i, c in enumerate(other.coeffs):
            out[other.low + i - low] += c
        return Laurent.of(low, out)

    def __neg__(self) -> "Laurent":
        return Laurent(self.low, tuple(-c for c in self.coeffs))

    def __sub__(self, other: "Laurent") -> "Laurent":
        return self + (-other)

    def __mul__(self, other: "Laurent") -> "Laurent":
        if self.is_zero or other.is_zero:
            return Laurent(0, ())
        out = [0] * (len(self.coeffs) + len(other.coeffs) - 1)
        for i, a in enumerate(self.coeffs):
            if a:
                for j, b in enumerate(other.coeffs):
                    out[i + j] += a * b
        return Laurent.of(self.low + other.low, out)

    def shift(self, by: int) -> "Laurent":
        return self if self.is_zero else Laurent(self.low + by, self.coeffs)

    def halve(self) -> Optional["Laurent"]:
        """This divided by 2, or None if some coefficient is odd."""
        if any(c % 2 for c in self.coeffs):
            return None
        return Laurent.of(self.low, [c // 2 for c in self.coeffs])

    def at_t(self, t: Fraction) -> Fraction:
        return sum((Fraction(c) * t ** (self.low + i) for i, c in enumerate(self.coeffs)),
                   Fraction(0))

    def text(self) -> str:
        """As a sum of powers of q, highest first (``t^e`` is ``q^(e/2)``)."""
        if self.is_zero:
            return "0"
        parts = []
        for i in range(len(self.coeffs) - 1, -1, -1):
            c = self.coeffs[i]
            if not c:
                continue
            power = _q_power_text(self.low + i)
            if power:
                body = power if abs(c) == 1 else f"{abs(c)}{power}"
            else:
                body = str(abs(c))
            parts.append(("- " if c < 0 else "+ ") + body)
        head = parts[0]
        head = head[2:] if head.startswith("+ ") else "-" + head[2:]
        return " ".join([head] + parts[1:])


def _q_power_text(exp_in_t: int) -> str:
    """``t^e`` written as a power of ``q`` (empty for the constant term)."""
    if exp_in_t == 0:
        return ""
    if exp_in_t % 2:
        return f"q^({exp_in_t}/2)"
    n = exp_in_t // 2
    return "q" if n == 1 else f"q^{n}"


ONE = Laurent.mono(0, 1)
ONE_PLUS_T2 = Laurent.of(0, [1, 0, 1])


def _divide_by_one_plus_t2(p: Laurent) -> Optional[Laurent]:
    """``p / (1 + t^2)`` when it divides exactly, else None."""
    if p.is_zero:
        return p
    rem = list(p.coeffs)
    n = len(rem)
    if n < 3:
        return None
    out = [0] * (n - 2)
    for i in range(n - 3, -1, -1):
        c = rem[i + 2]
        out[i] = c
        rem[i + 2] -= c
        rem[i] -= c
    if any(rem):
        return None
    return Laurent.of(p.low, out)


# ---------------------------------------------------------------------------
# values: num / (1 + t^2)^k, in lowest terms
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RefinedValue:
    num: Laurent
    den_power: int = 0

    @staticmethod
    def of(num: Laurent, den_power: int = 0) -> "RefinedValue":
        """Reduce: ``1 + t^2`` is irreducible, so cancelling it is lowest terms."""
        while den_power > 0:
            divided = _divide_by_one_plus_t2(num)
            if divided is None:
                break
            num, den_power = divided, den_power - 1
        if num.is_zero:
            return RefinedValue(num, 0)
        return RefinedValue(num, den_power)

    @staticmethod
    def one() -> "RefinedValue":
        return RefinedValue(ONE, 0)

    @property
    def is_polynomial(self) -> bool:
        return self.den_power == 0

    def __mul__(self, other: "RefinedValue") -> "RefinedValue":
        return RefinedValue.of(self.num * other.num, self.den_power + other.den_power)

    def __add__(self, other: "RefinedValue") -> "RefinedValue":
        k = max(self.den_power, other.den_power)
        return RefinedValue.of(self._lift(k) + other._lift(k), k)

    def _lift(self, k: int) -> Laurent:
        """The numerator over ``(1 + t^2)^k`` (k at least this value's power)."""
        out = self.num
        for _ in range(k - self.den_power):
            out = out * ONE_PLUS_T2
        return out

    def at_q(self, q: Fraction) -> Fraction:
        """The value at a rational ``q`` (needs a rational ``q^(1/2)``)."""
        t = _sqrt_fraction(q)
        if t is None:
            raise ValueError(f"q = {q} has no rational square root")
        den = (1 + t * t) ** self.den_power
        return self.num.at_t(t) / den

    def text(self) -> str:
        """Readable form; a leftover denominator is shown symmetrically."""
        if self.den_power == 0:
            return self.num.text()
        # num / (1+t^2)^k = (num * t^-k) / (t + t^-1)^k, which reads in q
        top = self.num.shift(-self.den_power).text()
        bottom = "(q^(1/2) + q^(-1/2))"
        if self.den_power > 1:
            bottom += f"^{self.den_power}"
        return f"({top}) / {bottom}"


def _sqrt_fraction(q: Fraction) -> Optional[Fraction]:
    def isqrt_exact(n: int) -> Optional[int]:
        if n < 0:
            return None
        r = int(n ** 0.5)
        for cand in (r - 1, r, r + 1):
            if cand >= 0 and cand * cand == n:
                return cand
        return None
    a, b = isqrt_exact(q.numerator), isqrt_exact(q.denominator)
    return None if a is None or b is None else Fraction(a, b)


# ---------------------------------------------------------------------------
# the q-integers
# ---------------------------------------------------------------------------
def q_integer_minus(a: int) -> RefinedValue:
    """``[a]^- = (q^(a/2) - q^(-a/2)) / (q^(1/2) - q^(-1/2))``.

    Always a polynomial: ``t^-(a-1) (1 + t^2 + ... + t^(2a-2))``.
    """
    if a < 0:
        return RefinedValue.of(-q_integer_minus(-a).num)
    if a == 0:
        return RefinedValue(Laurent(0, ()), 0)
    return RefinedValue.of(Laurent.of(-(a - 1), [1 if i % 2 == 0 else 0
                                                 for i in range(2 * a - 1)]))


def q_integer_plus(a: int) -> RefinedValue:
    """``[a]^+ = (q^(a/2) + q^(-a/2)) / (q^(1/2) + q^(-1/2))``.

    Multiplying through by ``t`` gives ``(t^(a+1) + t^(1-a)) / (1 + t^2)``; for
    odd ``a`` the numerator is divisible and the value is a polynomial, for even
    ``a`` it genuinely is not.
    """
    if a < 0:
        a = -a
    return RefinedValue.of(Laurent.mono(a + 1) + Laurent.mono(1 - a), 1)


# ---------------------------------------------------------------------------
# the multiplicity of a curve
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VertexMultiplicity:
    vertex: str
    mu: int
    marked: bool
    interior: bool = False      # a point in the interior of an edge, not a vertex

    def factor(self) -> RefinedValue:
        """What this vertex contributes to the product."""
        if self.interior:
            return RefinedValue.one()
        return q_integer_plus(self.mu) if self.marked else q_integer_minus(self.mu)

    def label(self) -> str:
        """The factor as written, e.g. ``[3]-``."""
        if self.interior:
            return "[0]+" if self.marked else "1"
        return f"[{self.mu}]{'+' if self.marked else '-'}"


def vertex_multiplicity(curve: Curve, vertex: str) -> VertexMultiplicity:
    """Mikhalkin multiplicity of a vertex, and whether it is marked.

    Accepts a trivalent vertex, or a 4-valent one carrying a single marking --
    a marked trivalent vertex -- or a point in the interior of an edge (two
    edges, with or without a marking), which is not a vertex of the curve and
    contributes nothing. Anything else raises.
    """
    flags = curve.incident(vertex)
    marks = [f for f in flags if f.kind is EdgeKind.MARKING]
    real = [f for f in flags if f.kind is not EdgeKind.MARKING]
    if len(real) == 2 and len(marks) <= 1:
        # balancing makes the two directions opposite, so mu = 0 either way
        return VertexMultiplicity(vertex=vertex, mu=0, marked=bool(marks), interior=True)
    if len(real) != 3 or len(marks) > 1:
        has = f"{len(real)} edge{'' if len(real) == 1 else 's'}"
        if marks:
            has += f" and {len(marks)} marking{'' if len(marks) == 1 else 's'}"
        raise MultiplicityError(
            f"the vertex where {_flag_names(flags)} meet has {has}; the refined "
            "multiplicity needs every vertex to be trivalent, or trivalent with "
            "one marking"
        )
    a, b = real[0].outgoing(vertex), real[1].outgoing(vertex)
    mu = abs(cross(a, b))
    if mu == 0:
        raise MultiplicityError(
            f"the vertex where {_flag_names(flags)} meet is degenerate: "
            "its dual triangle has zero area"
        )
    return VertexMultiplicity(vertex=vertex, mu=mu, marked=bool(marks))


def _flag_names(flags) -> str:
    return ", ".join(f.name or f.id for f in flags)


def vertex_multiplicities(curve: Curve) -> List[VertexMultiplicity]:
    return [vertex_multiplicity(curve, v) for v in curve.vertices]


def refined_multiplicity(curve: Curve) -> RefinedValue:
    """The refined multiplicity of a trivalent (possibly marked) curve."""
    out = RefinedValue.one()
    for vm in vertex_multiplicities(curve):
        out = out * vm.factor()
    return out


# ---------------------------------------------------------------------------
# splitting a set of curves into two halves of equal total multiplicity
# ---------------------------------------------------------------------------
MAX_SPLIT_ITEMS = 26


def balanced_split(values: Sequence[RefinedValue]) -> Optional[List[int]]:
    """Indices of a subset whose total equals that of its complement, or None.

    Both halves total the same exactly when the chosen half totals half of
    everything, so the whole total must be divisible by two to begin with.
    The search is meet in the middle: every subset sum of one half is tabled,
    then each subset of the other half looks up the remainder it needs -- 2^(n/2)
    work rather than 2^n.
    """
    n = len(values)
    if n > MAX_SPLIT_ITEMS:
        raise ValueError(f"too many curves to search ({n}; the limit is {MAX_SPLIT_ITEMS})")
    if n == 0:
        return []
    k = max(v.den_power for v in values)
    nums = [v._lift(k) for v in values]
    total = _sum_laurent(nums)
    target = total.halve()
    if target is None:
        return None            # an odd coefficient: no subset can be half of it

    half = n // 2
    table: Dict[Tuple, int] = {}
    for mask in range(1 << half):
        s = _sum_laurent([nums[i] for i in range(half) if mask >> i & 1])
        table.setdefault(_key(s), mask)
    rest = n - half
    for mask in range(1 << rest):
        s = _sum_laurent([nums[half + i] for i in range(rest) if mask >> i & 1])
        want = target - s
        found = table.get(_key(want))
        if found is None:
            continue
        chosen = [i for i in range(half) if found >> i & 1]
        chosen += [half + i for i in range(rest) if mask >> i & 1]
        return chosen
    return None


def _sum_laurent(items: Sequence[Laurent]) -> Laurent:
    out = Laurent(0, ())
    for p in items:
        out = out + p
    return out


def _key(p: Laurent) -> Tuple:
    return (p.low, p.coeffs)
