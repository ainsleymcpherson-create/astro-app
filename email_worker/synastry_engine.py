"""
synastry_engine.py

Computes cross-chart synastry: aspects between two people's natal
placements, and house overlays (whose planets fall in whose houses).
Distinct from aspect_engine.py (aspects within ONE chart) and
transit_engine.py (a fixed natal chart vs. the moving "now" sky) —
this compares two FIXED natal charts against each other.

Respects each person's known/unknown birth time independently:
  - If a person's birth time is unknown, their Ascendant, Midheaven,
    Descendant, Imum Coeli, houses, Vertex, and Arabic Parts are
    excluded from calculations (same convention used throughout
    prompt_builder.py's no-time variants) — these require an exact
    time to be meaningful even when computed against someone else's
    houses.
  - Planet-to-planet cross aspects remain valid regardless of either
    person's birth time status.
  - House overlays are only computed in a given direction if the
    HOUSE-OWNING person's time is known (e.g. "Person A's planets in
    Person B's houses" requires Person B's time to be known, but does
    NOT require Person A's time to be known).
"""

from __future__ import annotations
from dataclasses import dataclass

from chart_points import ChartPoint, assign_house
from aspect_engine import ASPECT_DEFINITIONS, ORB_MULTIPLIER, DEFAULT_MULTIPLIER


# ---------------------------------------------------------------------------
# Birth-time-dependent filtering (same convention as prompt_builder.py)
# ---------------------------------------------------------------------------

TIME_DEPENDENT_POINTS = {
    "Ascendant", "Descendant", "Midheaven", "Imum Coeli",
    "Vertex", "Anti-Vertex", "Part of Fortune", "Part of Spirit",
}


def _is_time_dependent(name: str) -> bool:
    return name in TIME_DEPENDENT_POINTS or name.startswith("House ")


def filter_chart_for_synastry(
    chart: dict[str, ChartPoint], time_known: bool,
) -> dict[str, ChartPoint]:
    """Strips time-dependent points if this person's birth time is
    unknown; returns the chart unchanged if it's known."""
    if time_known:
        return chart
    return {name: point for name, point in chart.items() if not _is_time_dependent(name)}


# ---------------------------------------------------------------------------
# Cross-chart aspects
# ---------------------------------------------------------------------------

DEFAULT_SYNASTRY_POINTS = [
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
    "Uranus", "Neptune", "Pluto", "Chiron", "North Node", "South Node",
    "Ascendant", "Descendant", "Midheaven", "Imum Coeli",
    "Part of Fortune", "Part of Spirit", "Vertex", "Anti-Vertex",
]


@dataclass
class SynastryAspect:
    person_a_point: str
    person_b_point: str
    aspect_name: str
    orb: float
    max_orb: float
    nature: str

    @property
    def tightness(self) -> float:
        """0.0 = exact hit, 1.0 = right at the orb limit. Lower = stronger."""
        return self.orb / self.max_orb if self.max_orb else 0.0

    def __repr__(self):
        return (f"Person A's {self.person_a_point} {self.aspect_name} "
                f"Person B's {self.person_b_point} [orb {self.orb:.2f}°]")


def _angular_separation(lon1: float, lon2: float) -> float:
    diff = abs(lon1 - lon2) % 360
    return min(diff, 360 - diff)


def compute_synastry_aspects(
    chart_a: dict[str, ChartPoint],
    chart_b: dict[str, ChartPoint],
    points_to_check: list[str] | None = None,
) -> list[SynastryAspect]:
    """
    Finds aspects between Person A's points and Person B's points.
    Pass charts already filtered via filter_chart_for_synastry() if
    either person's birth time is unknown, so only reliable points get
    compared — this function itself doesn't know about birth-time
    status, it just compares whatever's actually present in each dict.
    """
    if points_to_check is None:
        points_to_check = DEFAULT_SYNASTRY_POINTS

    results: list[SynastryAspect] = []
    for name_a in points_to_check:
        if name_a not in chart_a:
            continue
        point_a = chart_a[name_a]
        for name_b in points_to_check:
            if name_b not in chart_b:
                continue
            point_b = chart_b[name_b]
            sep = _angular_separation(point_a.longitude, point_b.longitude)

            for aspect_def in ASPECT_DEFINITIONS:
                m1 = ORB_MULTIPLIER.get(name_a, DEFAULT_MULTIPLIER)
                m2 = ORB_MULTIPLIER.get(name_b, DEFAULT_MULTIPLIER)
                max_orb = aspect_def.default_orb * min(m1, m2)
                orb = abs(sep - aspect_def.angle)
                if orb <= max_orb:
                    results.append(SynastryAspect(
                        person_a_point=name_a,
                        person_b_point=name_b,
                        aspect_name=aspect_def.name,
                        orb=orb,
                        max_orb=max_orb,
                        nature=aspect_def.nature,
                    ))
                    break  # closest matching aspect only, same as aspect_engine

    results.sort(key=lambda a: a.tightness)
    return results


# ---------------------------------------------------------------------------
# House overlays
# ---------------------------------------------------------------------------

DEFAULT_OVERLAY_POINTS = [
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
    "Uranus", "Neptune", "Pluto", "Chiron", "North Node", "South Node",
]


@dataclass
class HouseOverlay:
    visiting_point: str
    visiting_person: str   # "A" or "B" — whose planet this is
    house_number: int
    house_owner: str       # "A" or "B" — whose houses it's landing in

    def __repr__(self):
        return (f"Person {self.visiting_person}'s {self.visiting_point} "
                f"falls in Person {self.house_owner}'s House {self.house_number}")


def compute_house_overlay(
    visiting_chart: dict[str, ChartPoint],
    house_owner_chart: dict[str, ChartPoint],
    visiting_person_label: str,
    house_owner_label: str,
    points_to_check: list[str] | None = None,
) -> list[HouseOverlay]:
    """
    Places visiting_chart's planets into house_owner_chart's houses —
    e.g. "where do Person A's planets fall in Person B's houses."

    Pass visiting_chart already filtered via filter_chart_for_synastry()
    if the visiting person's own birth time is unknown, so unreliable
    points of theirs (Part of Fortune, Vertex, etc.) don't get placed.

    Requires house_owner_chart to actually have house cusps (i.e. the
    house-owning person's birth time must be known) — raises a clear
    error if not, so callers don't silently get empty/wrong results
    from calling this in the wrong direction.
    """
    house_cusp_names = [f"House {i}" for i in range(1, 13)]
    if not all(name in house_owner_chart for name in house_cusp_names):
        raise ValueError(
            f"Cannot compute house overlay: Person {house_owner_label}'s "
            f"chart is missing house cusps (birth time is likely unknown "
            f"for this person — house overlays require the HOUSE-OWNING "
            f"person's birth time specifically, regardless of the "
            f"visiting person's time status)."
        )

    if points_to_check is None:
        points_to_check = DEFAULT_OVERLAY_POINTS

    house_cusps = [house_owner_chart[name] for name in house_cusp_names]
    results = []
    for name in points_to_check:
        if name not in visiting_chart:
            continue
        point = visiting_chart[name]
        house_num = assign_house(point.longitude, house_cusps)
        results.append(HouseOverlay(
            visiting_point=name,
            visiting_person=visiting_person_label,
            house_number=house_num,
            house_owner=house_owner_label,
        ))
    return results


# ---------------------------------------------------------------------------
# Convenience: compute everything a synastry reading needs at once
# ---------------------------------------------------------------------------

def compute_full_synastry(
    chart_a: dict[str, ChartPoint],
    chart_b: dict[str, ChartPoint],
    person_a_time_known: bool,
    person_b_time_known: bool,
) -> dict:
    """
    Computes everything a professional synastry reading needs, handling
    each person's known/unknown birth time correctly and independently.

    Returns a dict with:
      - filtered_chart_a, filtered_chart_b: charts with time-dependent
        points stripped if that person's time is unknown
      - aspects: list[SynastryAspect] between the two filtered charts
      - overlay_a_in_b: list[HouseOverlay] (Person A's planets in
        Person B's houses) — empty if Person B's time is unknown
      - overlay_b_in_a: list[HouseOverlay] (Person B's planets in
        Person A's houses) — empty if Person A's time is unknown
    """
    filtered_a = filter_chart_for_synastry(chart_a, person_a_time_known)
    filtered_b = filter_chart_for_synastry(chart_b, person_b_time_known)

    aspects = compute_synastry_aspects(filtered_a, filtered_b)

    overlay_a_in_b: list[HouseOverlay] = []
    if person_b_time_known:
        overlay_a_in_b = compute_house_overlay(filtered_a, chart_b, "A", "B")

    overlay_b_in_a: list[HouseOverlay] = []
    if person_a_time_known:
        overlay_b_in_a = compute_house_overlay(filtered_b, chart_a, "B", "A")

    return {
        "filtered_chart_a": filtered_a,
        "filtered_chart_b": filtered_b,
        "aspects": aspects,
        "overlay_a_in_b": overlay_a_in_b,
        "overlay_b_in_a": overlay_b_in_a,
        "person_a_time_known": person_a_time_known,
        "person_b_time_known": person_b_time_known,
    }


# ---------------------------------------------------------------------------
# NOTES for extension
# ---------------------------------------------------------------------------
# - Dignity for each person's own chart is unaffected by any of this —
#     just call dignity.compute_chart_dignities() on each person's
#     chart independently, same as for a natal reading.
# - Composite/midpoint charts (a third, "combined" chart representing
#     the relationship itself) are a different technique from synastry
#     and would need their own module if wanted later.
