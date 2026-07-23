"""
house_interpretation.py

Provides interpretive scaffolding for the 12 houses: baseline themes,
which points occupy which house, and — the part most tools skip —
what an EMPTY house actually means.

The common misconception is that an empty house means "nothing happens
in that area of life." Traditional technique says otherwise: a house
with no planets in it is read through its RULER — the planet that rules
the sign sitting on that house's cusp. Wherever that ruler sits (its own
sign, house, and dignity condition) tells the story of how that empty
house's themes actually show up for the person.

Depends on chart_points.py (ChartPoint) and dignity.py (get_house_ruler,
get_dignity).
"""

from __future__ import annotations
from dataclasses import dataclass, field

from chart_points import ChartPoint
from dignity import get_house_ruler, get_dignity, DignityResult


# ---------------------------------------------------------------------------
# House themes (baseline significations)
# ---------------------------------------------------------------------------

HOUSE_THEMES = {
    1: "Self and identity",
    2: "Money and self-worth",
    3: "Communication and everyday learning",
    4: "Home and family",
    5: "Creativity and romance",
    6: "Daily work and health",
    7: "Partnership and marriage",
    8: "Intimacy and transformation",
    9: "Philosophy and travel",
    10: "Career and public reputation",
    11: "Community and friendship",
    12: "The unconscious and solitude",
}

# Points that count as "occupying" a house for the purposes of
# empty-house detection. Angles (Ascendant/Descendant/Midheaven/Imum
# Coeli) and the house cusps themselves are intentionally excluded —
# they define the boundaries rather than occupy a house. Everything
# else (planets, Nodes, Chiron, the Lots, Vertex) counts, since all of
# those carry independent interpretive weight when placed in a house.
_EXCLUDED_FROM_OCCUPANCY = {"Ascendant", "Descendant", "Midheaven", "Imum Coeli"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HouseReading:
    house_number: int
    sign_on_cusp: str
    theme: str
    occupants: list[str] = field(default_factory=list)
    is_empty: bool = False
    rulers: list[str] = field(default_factory=list)
    ruler_placements: list[dict] = field(default_factory=list)  # only for empty houses
    interpretation: str = ""

    def __repr__(self):
        occ = ", ".join(self.occupants) if self.occupants else "empty"
        return f"House {self.house_number} ({self.sign_on_cusp}): {occ}"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def get_house_occupants(chart: dict[str, ChartPoint]) -> dict[int, list[str]]:
    """
    Groups every eligible chart point by which house it falls in
    (using each point's `.house` attribute, set by
    chart_points.compute_full_chart()).
    """
    occupants: dict[int, list[str]] = {i: [] for i in range(1, 13)}
    for name, point in chart.items():
        if name in _EXCLUDED_FROM_OCCUPANCY:
            continue
        if name.startswith("House "):
            continue  # skip the house cusp points themselves
        if point.house is not None:
            occupants[point.house].append(name)
    return occupants


def _describe_ruler_placement(
    chart: dict[str, ChartPoint],
    ruler_name: str,
    include_modern: bool,
) -> dict:
    """Builds a small summary dict of where a ruling planet sits."""
    if ruler_name not in chart:
        return {"planet": ruler_name, "found": False}

    ruler_point = chart[ruler_name]
    dignity = get_dignity(ruler_name, ruler_point.sign, include_modern=include_modern)
    return {
        "planet": ruler_name,
        "found": True,
        "sign": ruler_point.sign,
        "house": ruler_point.house,
        "retrograde": ruler_point.retrograde,
        "dignity": dignity,
    }


def _interpret_empty_house(
    house_number: int,
    sign_on_cusp: str,
    ruler_placements: list[dict],
) -> str:
    theme = HOUSE_THEMES[house_number]
    parts = [
        f"House {house_number} ({sign_on_cusp} on the cusp) has no planets "
        f"directly in it, but that doesn't mean this area of life — {theme.lower()} "
        f"— is inactive. Its story is told through the ruling planet(s):"
    ]
    for placement in ruler_placements:
        if not placement.get("found"):
            parts.append(f"  - {placement['planet']}: position not available in this chart.")
            continue
        d: DignityResult = placement["dignity"]
        retro = " (retrograde)" if placement["retrograde"] else ""
        strength = {
            "Rulership": "very strong, operating comfortably and directly",
            "Exaltation": "strong, expressing with ease and some prominence",
            "Peregrine": "unremarkable in essential strength — its house/aspects matter more here",
            "Detriment": "somewhat strained, may express this house's themes in a roundabout way",
            "Fall": "weakened, this house's themes may take more conscious effort to access",
        }[d.status]
        parts.append(
            f"  - {placement['planet']} rules this house and sits in {placement['sign']}"
            f" in House {placement['house']}{retro} — {d.status} ({strength}). "
            f"How {placement['planet']} operates there is effectively how this "
            f"house's themes play out."
        )
    return "\n".join(parts)


def build_house_readings(
    chart: dict[str, ChartPoint],
    include_modern: bool = True,
) -> dict[int, HouseReading]:
    """
    Produces a full HouseReading for all 12 houses: theme, occupants (or
    lack thereof), and — for empty houses — the ruler-based interpretation.
    """
    occupants = get_house_occupants(chart)
    readings: dict[int, HouseReading] = {}

    for house_num in range(1, 13):
        cusp_point = chart.get(f"House {house_num}")
        sign_on_cusp = cusp_point.sign if cusp_point else "Unknown"
        house_occupants = occupants[house_num]
        is_empty = len(house_occupants) == 0

        reading = HouseReading(
            house_number=house_num,
            sign_on_cusp=sign_on_cusp,
            theme=HOUSE_THEMES[house_num],
            occupants=house_occupants,
            is_empty=is_empty,
        )

        if is_empty and cusp_point is not None:
            rulers = get_house_ruler(sign_on_cusp, include_modern=include_modern)
            reading.rulers = rulers
            reading.ruler_placements = [
                _describe_ruler_placement(chart, r, include_modern) for r in rulers
            ]
            reading.interpretation = _interpret_empty_house(
                house_num, sign_on_cusp, reading.ruler_placements
            )
        elif not is_empty:
            occ_str = ", ".join(house_occupants)
            reading.interpretation = (
                f"House {house_num} ({sign_on_cusp} on the cusp) is occupied by "
                f"{occ_str} — this area of life ({reading.theme.lower()}) is "
                f"directly activated and likely to be a focal point."
            )

        readings[house_num] = reading

    return readings


def find_empty_houses(chart: dict[str, ChartPoint]) -> list[int]:
    """Convenience: just the list of empty house numbers."""
    occupants = get_house_occupants(chart)
    return [h for h, occs in occupants.items() if len(occs) == 0]


# ---------------------------------------------------------------------------
# NOTES for extension
# ---------------------------------------------------------------------------
# - Some traditions also read a house's condition partly from what
#     ASPECTS its ruler receives (not just sign/house placement) — e.g.
#     "House 7 is empty, ruled by Venus in the 10th, which is squared by
#     Saturn" tells a richer story than placement alone. Wiring
#     aspect_engine.get_point_aspects(ruler_name, aspects) into
#     _describe_ruler_placement() would be the natural next step.
# - House systems that don't produce equal-ish houses (e.g. Placidus at
#     high latitudes) can occasionally produce a sign appearing on no
#     cusp at all ("intercepted"), which has its own interpretive
#     tradition (a theme that's present but harder to access) — not yet
#     handled here.
