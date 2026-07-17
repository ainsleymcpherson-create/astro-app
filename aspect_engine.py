"""
aspect_engine.py

Detects astrological aspects (angular relationships) between all points in
a chart produced by chart_points.compute_full_chart() — including the
lesser-used points (Part of Fortune, Nodes, Vertex, Chiron), not just the
classical planets.

Also detects common aspect *patterns* (Grand Trine, T-Square, Grand Cross,
Yod, Stellium) since these configurations, not isolated aspects, are often
what actually matters for interpretation — the connections between
aspects is exactly the piece most pop-astrology tools skip.

Depends on chart_points.py (ChartPoint dataclass).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from itertools import combinations

from chart_points import ChartPoint


# ---------------------------------------------------------------------------
# Aspect definitions
# ---------------------------------------------------------------------------
# angle: the ideal separation in degrees
# category: "major" or "minor" — lets callers easily filter to major-only
# default_orb: baseline allowed deviation in degrees before/after the ideal
#              angle, before any per-point-category adjustment is applied

@dataclass
class AspectDef:
    name: str
    angle: float
    category: str
    default_orb: float
    nature: str  # rough qualitative flavor, useful for interpretation layer


ASPECT_DEFINITIONS: list[AspectDef] = [
    AspectDef("Conjunction", 0, "major", 8, "blended/intensified"),
    AspectDef("Sextile", 60, "major", 4, "easy/opportunity"),
    AspectDef("Square", 90, "major", 7, "tension/friction"),
    AspectDef("Trine", 120, "major", 7, "flowing/harmonious"),
    AspectDef("Opposition", 180, "major", 8, "polarity/awareness"),
    AspectDef("Semisextile", 30, "minor", 2, "mild friction"),
    AspectDef("Semisquare", 45, "minor", 2, "low-grade tension"),
    AspectDef("Sesquiquadrate", 135, "minor", 2, "low-grade tension"),
    AspectDef("Quincunx", 150, "minor", 3, "adjustment/awkward fit"),
    AspectDef("Quintile", 72, "minor", 2, "creative/talent"),
]

ASPECT_BY_NAME = {a.name: a for a in ASPECT_DEFINITIONS}

# Points where orb should be tightened relative to the aspect's default_orb,
# because they're more sensitive/derived points rather than physical bodies.
# Multiplier applied to whichever point in the pair is "tighter" (we use the
# minimum multiplier of the two points involved — i.e. the more sensitive
# point governs).
ORB_MULTIPLIER = {
    "Sun": 1.0, "Moon": 1.0,
    "Mercury": 1.0, "Venus": 1.0, "Mars": 1.0,
    "Jupiter": 1.0, "Saturn": 1.0,
    "Uranus": 1.0, "Neptune": 1.0, "Pluto": 1.0,
    "Ascendant": 1.0, "Descendant": 1.0, "Midheaven": 1.0, "Imum Coeli": 1.0,
    "North Node": 0.6, "South Node": 0.6,
    "Part of Fortune": 0.4, "Part of Spirit": 0.4,
    "Vertex": 0.4, "Anti-Vertex": 0.4,
    "Chiron": 0.6,
}
DEFAULT_MULTIPLIER = 0.5  # for anything not listed (e.g. house cusps)


def _effective_orb(aspect: AspectDef, name1: str, name2: str) -> float:
    m1 = ORB_MULTIPLIER.get(name1, DEFAULT_MULTIPLIER)
    m2 = ORB_MULTIPLIER.get(name2, DEFAULT_MULTIPLIER)
    return aspect.default_orb * min(m1, m2)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Aspect:
    point1: str
    point2: str
    aspect_name: str
    exact_angle: float     # the ideal angle for this aspect type
    actual_separation: float
    orb: float              # how far actual is from exact (always >= 0)
    max_orb: float          # the orb threshold that was applied
    nature: str
    applying: bool | None = None  # None if we couldn't determine (no speed data)

    @property
    def tightness(self) -> float:
        """0.0 = exact hit, 1.0 = right at the orb limit. Lower = stronger."""
        if self.max_orb == 0:
            return 0.0
        return self.orb / self.max_orb

    def __repr__(self):
        app = ""
        if self.applying is True:
            app = " (applying)"
        elif self.applying is False:
            app = " (separating)"
        return (f"{self.point1} {self.aspect_name} {self.point2} "
                f"[orb {self.orb:.2f}°{app}]")


@dataclass
class AspectPattern:
    pattern_type: str
    points: list[str]
    aspects: list[Aspect] = field(default_factory=list)

    def __repr__(self):
        return f"{self.pattern_type}: {', '.join(self.points)}"


# ---------------------------------------------------------------------------
# Core aspect detection
# ---------------------------------------------------------------------------

def _angular_separation(lon1: float, lon2: float) -> float:
    """Shortest angular distance between two ecliptic longitudes, 0-180."""
    diff = abs(lon1 - lon2) % 360
    return min(diff, 360 - diff)


def _build_tautological_pairs() -> set:
    """
    Pairs that are mathematically guaranteed by how angles/houses are
    defined, not genuine findings from this specific chart's data —
    e.g. the Ascendant IS the House 1 cusp (same point, two names), and
    the Ascendant and Descendant are ALWAYS exactly 180° apart by
    construction, regardless of birth data. These aren't meaningful
    aspects; they're the same fact restated under a different label.
    """
    pairs = set()
    # Conjunctions: an angle and its own house cusp are literally the
    # same point.
    same_point = [
        ("Ascendant", "House 1"), ("Descendant", "House 7"),
        ("Midheaven", "House 10"), ("Imum Coeli", "House 4"),
    ]
    for a, b in same_point:
        pairs.add(("Conjunction", frozenset({a, b})))
    # Oppositions: always exactly 180° apart by construction — the
    # Asc/Dsc axis, the MC/IC axis (by name or by equivalent house
    # cusp), the Vertex/Anti-Vertex axis, the Node axis, and every pair
    # of houses 6 apart (opposite house cusps are always exactly 180°
    # apart in any house system).
    always_opposite = [
        ("Ascendant", "Descendant"), ("Ascendant", "House 7"),
        ("House 1", "Descendant"), ("House 1", "House 7"),
        ("Midheaven", "Imum Coeli"), ("Midheaven", "House 4"),
        ("House 10", "Imum Coeli"), ("House 10", "House 4"),
        ("Vertex", "Anti-Vertex"), ("North Node", "South Node"),
    ]
    for a, b in always_opposite:
        pairs.add(("Opposition", frozenset({a, b})))
    for n in range(1, 7):
        pairs.add(("Opposition", frozenset({f"House {n}", f"House {n + 6}"})))
    return pairs


TAUTOLOGICAL_ASPECT_PAIRS = _build_tautological_pairs()


def _is_tautological(aspect_name: str, name1: str, name2: str) -> bool:
    return (aspect_name, frozenset({name1, name2})) in TAUTOLOGICAL_ASPECT_PAIRS


def compute_aspects(
    chart: dict[str, ChartPoint],
    include_points: list[str] | None = None,
    exclude_points: list[str] | None = None,
    categories: list[str] | None = None,
    speeds: dict[str, float] | None = None,
) -> list[Aspect]:
    """
    Computes all aspects between pairs of points in `chart`.

    include_points: if given, only consider these point names (whitelist).
    exclude_points: point names to skip — house cusps are typically excluded
                     since "House 5 square House 8" isn't a meaningful
                     aspect statement; pass exclude_points=[f"House {i}"
                     for i in range(1,13)] to filter those out.
    categories: restrict to "major", "minor", or both (default both).
    speeds: optional {point_name: degrees/day} to compute applying/
            separating. Without this, `applying` is left as None.

    Returns aspects sorted by tightness (strongest/most exact first).
    Excludes mathematically tautological relationships (e.g. Ascendant
    conjunct House 1, or Ascendant opposite Descendant) — these are
    guaranteed by how angles and houses are defined, not genuine
    findings from this chart's specific data.
    """
    categories = categories or ["major", "minor"]
    names = list(chart.keys())
    if include_points is not None:
        names = [n for n in names if n in include_points]
    if exclude_points is not None:
        names = [n for n in names if n not in exclude_points]

    results: list[Aspect] = []

    for name1, name2 in combinations(names, 2):
        p1, p2 = chart[name1], chart[name2]
        sep = _angular_separation(p1.longitude, p2.longitude)

        for aspect_def in ASPECT_DEFINITIONS:
            if aspect_def.category not in categories:
                continue
            max_orb = _effective_orb(aspect_def, name1, name2)
            orb = abs(sep - aspect_def.angle)
            if orb <= max_orb:
                if _is_tautological(aspect_def.name, name1, name2):
                    break  # skip — not a genuine finding, don't fall
                           # through to a looser aspect definition either
                applying = _determine_applying(
                    p1.longitude, p2.longitude, name1, name2, speeds
                )
                results.append(Aspect(
                    point1=name1, point2=name2,
                    aspect_name=aspect_def.name,
                    exact_angle=aspect_def.angle,
                    actual_separation=sep,
                    orb=orb, max_orb=max_orb,
                    nature=aspect_def.nature,
                    applying=applying,
                ))
                break  # a pair forms at most one aspect (the closest match)

    results.sort(key=lambda a: a.tightness)
    return results


def _determine_applying(
    lon1: float, lon2: float, name1: str, name2: str,
    speeds: dict[str, float] | None,
) -> bool | None:
    """
    Applying = the faster point is moving toward exactitude with the slower
    one. Requires daily speeds (degrees/day, signed by direction) for both
    points; returns None if unavailable.

    Note: this is a simplified same-day approximation, not a precise
    exact-date-of-aspect calculation. For that, you'd step the ephemeris
    forward/backward in time until the orb hits zero.
    """
    if not speeds or name1 not in speeds or name2 not in speeds:
        return None
    s1, s2 = speeds[name1], speeds[name2]
    # Whichever point moves faster is the "applying" body relative to the slower.
    faster_lon, slower_lon = (lon1, lon2) if abs(s1) >= abs(s2) else (lon2, lon1)
    faster_speed = s1 if abs(s1) >= abs(s2) else s2
    gap_now = (slower_lon - faster_lon) % 360
    gap_soon = (slower_lon - (faster_lon + faster_speed * 0.5)) % 360
    # If the gap (mod 360, shortest-path aware) is shrinking, it's applying.
    def shortest(g):
        return min(g, 360 - g)
    return shortest(gap_soon) < shortest(gap_now)


def get_point_aspects(point_name: str, aspects: list[Aspect]) -> list[Aspect]:
    """Filters an aspect list down to only those touching a given point."""
    return [a for a in aspects if point_name in (a.point1, a.point2)]


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------
# These look for specific multi-point configurations that carry their own
# well-established interpretive meaning beyond the sum of individual
# aspects — this is the "how aspects connect to each other" layer.

def _aspect_between(aspects: list[Aspect], p1: str, p2: str, name: str) -> Aspect | None:
    for a in aspects:
        if a.aspect_name == name and {a.point1, a.point2} == {p1, p2}:
            return a
    return None


def find_grand_trines(aspects: list[Aspect]) -> list[AspectPattern]:
    """Three points, each trine (120°) the other two — a closed triangle."""
    trine_aspects = [a for a in aspects if a.aspect_name == "Trine"]
    points = sorted({p for a in trine_aspects for p in (a.point1, a.point2)})
    patterns = []
    for a, b, c in combinations(points, 3):
        ab = _aspect_between(trine_aspects, a, b, "Trine")
        bc = _aspect_between(trine_aspects, b, c, "Trine")
        ac = _aspect_between(trine_aspects, a, c, "Trine")
        if ab and bc and ac:
            patterns.append(AspectPattern("Grand Trine", [a, b, c], [ab, bc, ac]))
    return patterns


def find_t_squares(aspects: list[Aspect]) -> list[AspectPattern]:
    """
    Two points in opposition, both square to a third (the "apex"/focal point).
    """
    oppositions = [a for a in aspects if a.aspect_name == "Opposition"]
    squares = [a for a in aspects if a.aspect_name == "Square"]
    patterns = []
    all_points = {p for a in aspects for p in (a.point1, a.point2)}
    for opp in oppositions:
        p1, p2 = opp.point1, opp.point2
        for apex in all_points:
            if apex in (p1, p2):
                continue
            sq1 = _aspect_between(squares, apex, p1, "Square")
            sq2 = _aspect_between(squares, apex, p2, "Square")
            if sq1 and sq2:
                patterns.append(AspectPattern(
                    "T-Square", [p1, p2, apex], [opp, sq1, sq2]
                ))
    return patterns


def find_grand_crosses(aspects: list[Aspect]) -> list[AspectPattern]:
    """Two oppositions at right angles to each other (four square legs)."""
    oppositions = [a for a in aspects if a.aspect_name == "Opposition"]
    squares = [a for a in aspects if a.aspect_name == "Square"]
    patterns = []
    seen = set()
    for opp1, opp2 in combinations(oppositions, 2):
        pts1 = {opp1.point1, opp1.point2}
        pts2 = {opp2.point1, opp2.point2}
        if pts1 & pts2:
            continue  # must be four distinct points
        legs = []
        ok = True
        for a in pts1:
            for b in pts2:
                sq = _aspect_between(squares, a, b, "Square")
                if sq:
                    legs.append(sq)
        if len(legs) == 4:
            key = frozenset(pts1 | pts2)
            if key not in seen:
                seen.add(key)
                patterns.append(AspectPattern(
                    "Grand Cross", sorted(pts1 | pts2), [opp1, opp2] + legs
                ))
    return patterns


def find_yods(aspects: list[Aspect]) -> list[AspectPattern]:
    """
    Two points sextile each other, both quincunx (150°) a third apex point.
    Sometimes called the "Finger of Fate/God".
    """
    sextiles = [a for a in aspects if a.aspect_name == "Sextile"]
    quincunxes = [a for a in aspects if a.aspect_name == "Quincunx"]
    patterns = []
    all_points = {p for a in aspects for p in (a.point1, a.point2)}
    for sx in sextiles:
        p1, p2 = sx.point1, sx.point2
        for apex in all_points:
            if apex in (p1, p2):
                continue
            q1 = _aspect_between(quincunxes, apex, p1, "Quincunx")
            q2 = _aspect_between(quincunxes, apex, p2, "Quincunx")
            if q1 and q2:
                patterns.append(AspectPattern(
                    "Yod", [p1, p2, apex], [sx, q1, q2]
                ))
    return patterns


def find_stelliums(
    chart: dict[str, ChartPoint],
    min_points: int = 3,
    orb: float = 8.0,
    exclude_points: list[str] | None = None,
) -> list[AspectPattern]:
    """
    A stellium = min_points or more points clustered within `orb` degrees
    of each other (typically within one sign, but this checks actual
    proximity rather than sign membership, which is more precise near
    sign boundaries).
    """
    exclude_points = exclude_points or [f"House {i}" for i in range(1, 13)]
    names = [n for n in chart if n not in exclude_points]
    names.sort(key=lambda n: chart[n].longitude)

    patterns = []
    used = set()
    n = len(names)
    for i in range(n):
        if names[i] in used:
            continue
        cluster = [names[i]]
        for j in range(i + 1, n):
            if _angular_separation(chart[names[i]].longitude, chart[names[j]].longitude) <= orb:
                cluster.append(names[j])
            else:
                break
        if len(cluster) >= min_points:
            patterns.append(AspectPattern("Stellium", cluster))
            used.update(cluster)
    return patterns


def find_all_patterns(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
) -> dict[str, list[AspectPattern]]:
    """Convenience: runs every pattern detector and returns them grouped."""
    return {
        "grand_trines": find_grand_trines(aspects),
        "t_squares": find_t_squares(aspects),
        "grand_crosses": find_grand_crosses(aspects),
        "yods": find_yods(aspects),
        "stelliums": find_stelliums(chart),
    }


# ---------------------------------------------------------------------------
# NOTES for extension
# ---------------------------------------------------------------------------
# - Applying/separating currently uses a coarse same-day approximation.
#     For precision (e.g. "exact on March 3rd"), step compute_full_chart
#     across nearby dates and find where orb crosses zero.
# - Antiscia (mirror points across the 0° Cancer/Capricorn axis) are another
#     under-used technique some traditional astrologers track — could be
#     added as a companion function that reflects longitudes and re-runs
#     compute_aspects against the reflected set.
# - Consider exposing a `min_tightness` filter on compute_aspects() output
#     for interpretation layers that only want to discuss the strongest
#     few aspects rather than every point within orb.
