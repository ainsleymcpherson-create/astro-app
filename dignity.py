"""
dignity.py

Computes essential dignity — how "at home" or "out of place" a planet is,
based purely on which sign it occupies. This is one of the oldest pieces
of astrological technique (predates modern psychological astrology by
centuries) and is a natural companion to aspect strength: a hard aspect
from a well-dignified planet plays out very differently than the same
aspect from a debilitated one.

Covers the four classical essential dignities:
  - Rulership (Domicile): planet in the sign it rules — most "at home"
  - Exaltation: planet in a sign where its qualities are amplified/honored
  - Detriment: planet in the sign opposite its rulership — friction with
      its natural expression
  - Fall: planet in the sign opposite its exaltation — the most
      uncomfortable placement

Depends on chart_points.py (ChartPoint, SIGNS).
"""

from __future__ import annotations
from dataclasses import dataclass

from chart_points import ChartPoint, SIGNS


# ---------------------------------------------------------------------------
# Rulership tables
# ---------------------------------------------------------------------------
# Traditional (7-planet) rulership — the system essential dignity was
# actually built around, and still the most commonly used baseline.
TRADITIONAL_RULERSHIP = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

# Modern co-rulership, layering the outer planets on top of the
# traditional rulers for Scorpio/Aquarius/Pisces. Many astrologers use
# both simultaneously (a planet can be co-ruler); this module treats
# modern rulers as *additional* rulers of those three signs rather than
# replacements, since that's the more common practice.
MODERN_CO_RULERSHIP = {
    "Scorpio": "Pluto",
    "Aquarius": "Uranus",
    "Pisces": "Neptune",
}

# Exaltation — a planet's placement of honor, generally treated as a
# single planet per sign (unlike rulership, no widely-used modern
# exaltation additions exist, so this table is left as-is).
EXALTATION = {
    "Aries": "Sun", "Taurus": "Moon", "Cancer": "Jupiter",
    "Virgo": "Mercury", "Libra": "Saturn", "Capricorn": "Mars",
    "Pisces": "Venus",
    # Gemini, Leo, Scorpio, Sagittarius, Aquarius have no traditionally
    # assigned exaltation planet.
}


def _opposite_sign(sign: str) -> str:
    idx = SIGNS.index(sign)
    return SIGNS[(idx + 6) % 12]


def _build_detriment_table(rulership: dict[str, str]) -> dict[str, list[str]]:
    """A planet is in detriment in the sign opposite whatever it rules."""
    detriment: dict[str, list[str]] = {}
    for sign, ruler in rulership.items():
        opp = _opposite_sign(sign)
        detriment.setdefault(ruler, []).append(opp)
    return detriment


def _build_fall_table(exaltation: dict[str, str]) -> dict[str, str]:
    """A planet is in fall in the sign opposite its exaltation."""
    return {planet: _opposite_sign(sign) for sign, planet in exaltation.items()}


# planet -> list of signs where it's in detriment (list because modern
# co-rulers give some planets more than one detriment sign, e.g. Pluto
# rules Scorpio, so Pluto is in detriment in Taurus)
_TRAD_DETRIMENT = _build_detriment_table(TRADITIONAL_RULERSHIP)
_MODERN_DETRIMENT = _build_detriment_table(MODERN_CO_RULERSHIP)

# planet -> sign of fall
_FALL = _build_fall_table(EXALTATION)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DignityResult:
    planet: str
    sign: str
    status: str        # "Rulership", "Exaltation", "Detriment", "Fall", "Peregrine"
    score: int          # rough strength: +5 / +4 / -5 / -4 / 0
    note: str = ""

    def __repr__(self):
        return f"{self.planet} in {self.sign}: {self.status} ({self.score:+d})"


DIGNITY_SCORES = {
    "Rulership": 5,
    "Exaltation": 4,
    "Peregrine": 0,
    "Detriment": -5,
    "Fall": -4,
}


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def get_dignity(
    planet: str,
    sign: str,
    include_modern: bool = True,
) -> DignityResult:
    """
    Determines a single planet's essential dignity in a given sign.

    include_modern: if True, also checks modern co-rulership (Pluto/
        Scorpio, Uranus/Aquarius, Neptune/Pisces) for rulership and the
        corresponding detriment. Traditional rulership/detriment is
        always checked regardless of this flag.

    Note on precedence: a planet can't simultaneously be ruler and in
    detriment (they're always opposite signs by construction), but a
    planet CAN be, in principle, both "ruler of sign X" under one system
    and "exalted" is impossible to co-occur with rulership since no sign
    has the same planet for both in these tables — so precedence isn't
    actually ambiguous here. Order checked: Rulership -> Exaltation ->
    Detriment -> Fall -> Peregrine (none of the above).
    """
    if TRADITIONAL_RULERSHIP.get(sign) == planet:
        return DignityResult(planet, sign, "Rulership", DIGNITY_SCORES["Rulership"],
                              note="Traditional domicile")
    if include_modern and MODERN_CO_RULERSHIP.get(sign) == planet:
        return DignityResult(planet, sign, "Rulership", DIGNITY_SCORES["Rulership"],
                              note="Modern co-rulership")

    if EXALTATION.get(sign) == planet:
        return DignityResult(planet, sign, "Exaltation", DIGNITY_SCORES["Exaltation"])

    if sign in _TRAD_DETRIMENT.get(planet, []):
        return DignityResult(planet, sign, "Detriment", DIGNITY_SCORES["Detriment"],
                              note="Opposite traditional domicile")
    if include_modern and sign in _MODERN_DETRIMENT.get(planet, []):
        return DignityResult(planet, sign, "Detriment", DIGNITY_SCORES["Detriment"],
                              note="Opposite modern co-rulership")

    if _FALL.get(planet) == sign:
        return DignityResult(planet, sign, "Fall", DIGNITY_SCORES["Fall"])

    return DignityResult(planet, sign, "Peregrine", DIGNITY_SCORES["Peregrine"],
                          note="No essential dignity in this sign")


def compute_chart_dignities(
    chart: dict[str, ChartPoint],
    include_modern: bool = True,
    points: list[str] | None = None,
) -> dict[str, DignityResult]:
    """
    Computes dignity for every eligible point in a chart. By default,
    checks the 10 classical+modern planets (Sun through Pluto) — dignity
    as a concept doesn't traditionally apply to angles, house cusps,
    Nodes, Vertex, or the Arabic Parts (those describe *sensitivity/
    fatedness*, not planetary "comfort" in a sign), so those are skipped
    unless you explicitly pass them via `points`.
    """
    default_points = [
        "Sun", "Moon", "Mercury", "Venus", "Mars",
        "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    ]
    target_points = points if points is not None else default_points

    results = {}
    for name in target_points:
        if name not in chart:
            continue
        cp = chart[name]
        results[name] = get_dignity(name, cp.sign, include_modern=include_modern)
    return results


def get_house_ruler(
    house_sign: str,
    include_modern: bool = True,
) -> list[str]:
    """
    Returns the ruling planet(s) of whatever sign sits on a house cusp.
    Returns a list because with modern co-rulership enabled, Scorpio/
    Aquarius/Pisces cusps have two rulers (e.g. Scorpio -> [Mars, Pluto]).
    """
    rulers = [TRADITIONAL_RULERSHIP[house_sign]]
    if include_modern and house_sign in MODERN_CO_RULERSHIP:
        rulers.append(MODERN_CO_RULERSHIP[house_sign])
    return rulers


# ---------------------------------------------------------------------------
# NOTES for extension
# ---------------------------------------------------------------------------
# This module implements the two strongest/most commonly-used essential
# dignities. The full classical five-fold system also includes:
#   - Triplicity: rulership by element (fire/earth/air/water), with
#       separate day/night rulers — another day/night-sensitive
#       technique, similar in spirit to Part of Fortune.
#   - Term (Bound): each sign divided into 5 unequal segments, each
#       ruled by a different planet — much finer-grained, rarely used
#       outside traditional/Hellenistic practice.
#   - Face (Decan): each sign divided into 3 equal 10° segments.
# Adding these would let you compute a full 5-point dignity score per
# Hellenistic/medieval convention rather than just the 2-point version here.
