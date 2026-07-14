"""
transit_engine.py

Computes transiting planetary positions for a given moment (e.g. right
now) and finds aspects between those transiting positions and a natal
chart — the standard "what's currently activated" astrological
technique. Distinct from aspect_engine.py because:

  1. It compares TWO different charts (transiting vs. natal) rather
     than aspects within one chart.
  2. Transit orbs are conventionally much tighter than natal orbs,
     since a transit is read as "active" only when quite close to
     exact — a transit isn't a permanent configuration the way a natal
     aspect is, it's a temporary window.

Depends on chart_points.py and reuses aspect definitions from
aspect_engine.py so the two stay consistent (same aspect names/angles).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from chart_points import BirthData, ChartPoint, compute_planets, compute_nodes, compute_chiron, assign_house
from aspect_engine import ASPECT_DEFINITIONS


# ---------------------------------------------------------------------------
# Transit orb configuration
# ---------------------------------------------------------------------------
# Transit orbs are tighter than natal orbs — the usual convention is
# roughly 1/3 to 1/2 of the natal orb, applied on top of each aspect's
# default_orb from aspect_engine.ASPECT_DEFINITIONS.
TRANSIT_ORB_MULTIPLIER = 0.4

# Nodes and Chiron get a bit tighter still, matching the spirit of
# aspect_engine's own ORB_MULTIPLIER table for these more sensitive points.
TRANSIT_POINT_MULTIPLIER = {
    "North Node": 0.7, "South Node": 0.7, "Chiron": 0.7,
}

# The natal points transits are conventionally read against. Angles and
# personal planets carry the most weight in traditional transit work;
# this is the default set compute_transit_aspects() checks against.
DEFAULT_NATAL_TARGETS = [
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
    "Uranus", "Neptune", "Pluto", "Ascendant", "Descendant",
    "Midheaven", "Imum Coeli", "North Node", "South Node", "Chiron",
]


# ---------------------------------------------------------------------------
# Computing transiting positions
# ---------------------------------------------------------------------------

def compute_transiting_points(transit_dt_utc: datetime) -> dict[str, ChartPoint]:
    """
    Computes the 10 planets, Chiron, and the Lunar Nodes for a given
    moment — the "transiting" positions (e.g. today). Doesn't compute
    angles/houses of its own; transiting planets get mapped onto the
    NATAL chart's houses separately (see assign_transit_houses), since
    that's how transits are conventionally read — against the natal
    houses, not a fresh chart cast for the transit moment itself.
    """
    # Latitude/longitude don't affect planetary positions (only houses/
    # angles do, which aren't computed here), so placeholder coordinates
    # are fine — this is never used for anything location-dependent.
    dummy_birth = BirthData(dt_utc=transit_dt_utc, latitude=0.0, longitude=0.0)
    points: dict[str, ChartPoint] = {}
    points.update(compute_planets(dummy_birth))
    points.update(compute_nodes(dummy_birth))
    points["Chiron"] = compute_chiron(dummy_birth)
    return points


def assign_transit_houses(
    transiting_points: dict[str, ChartPoint],
    natal_house_cusps: list[ChartPoint],
) -> None:
    """
    Mutates transiting_points in place, setting each point's `.house`
    to whichever NATAL house its current longitude currently falls
    into (e.g. "transiting Saturn is moving through your natal 10th
    house"). Pass the house cusp list from chart_points.compute_houses()
    for the person's natal chart.
    """
    for point in transiting_points.values():
        point.house = assign_house(point.longitude, natal_house_cusps)


# ---------------------------------------------------------------------------
# Transit-to-natal aspects
# ---------------------------------------------------------------------------

@dataclass
class TransitAspect:
    transiting_point: str
    natal_point: str
    aspect_name: str
    orb: float
    max_orb: float
    nature: str
    applying: bool | None = None

    @property
    def tightness(self) -> float:
        """0.0 = exact hit, 1.0 = right at the orb limit. Lower = stronger."""
        return self.orb / self.max_orb if self.max_orb else 0.0

    def __repr__(self):
        app = ""
        if self.applying is True:
            app = " (applying)"
        elif self.applying is False:
            app = " (separating)"
        return (f"Transiting {self.transiting_point} {self.aspect_name} "
                f"natal {self.natal_point} [orb {self.orb:.2f}°{app}]")


def _angular_separation(lon1: float, lon2: float) -> float:
    diff = abs(lon1 - lon2) % 360
    return min(diff, 360 - diff)


def _determine_transit_applying(
    transit_lon: float,
    natal_lon: float,
    transit_speed: float | None,
) -> bool | None:
    """
    For transits, only the transiting point actually moves (the natal
    point is fixed in place) — so applying/separating just depends on
    whether the transiting point's motion is closing or widening the
    gap to that fixed natal point. Returns None if speed isn't provided.
    """
    if transit_speed is None:
        return None
    gap_now = (natal_lon - transit_lon) % 360
    gap_soon = (natal_lon - (transit_lon + transit_speed * 0.5)) % 360

    def shortest(g):
        return min(g, 360 - g)

    return shortest(gap_soon) < shortest(gap_now)


def compute_transit_aspects(
    natal_chart: dict[str, ChartPoint],
    transiting_points: dict[str, ChartPoint],
    natal_points_to_check: list[str] | None = None,
    transiting_speeds: dict[str, float] | None = None,
) -> list[TransitAspect]:
    """
    Finds aspects between transiting planets and natal chart points,
    using tighter (transit-appropriate) orbs than natal-to-natal
    aspects. By default checks transiting planets against the natal
    Sun, Moon, personal planets, angles, Nodes, and Chiron — pass a
    custom natal_points_to_check list to check against something else
    (e.g. just the natal 10th/6th/2nd house rulers for a career-focused
    transit reading).
    """
    if natal_points_to_check is None:
        natal_points_to_check = DEFAULT_NATAL_TARGETS

    results: list[TransitAspect] = []

    for t_name, t_point in transiting_points.items():
        for n_name in natal_points_to_check:
            if n_name not in natal_chart:
                continue
            n_point = natal_chart[n_name]
            sep = _angular_separation(t_point.longitude, n_point.longitude)

            for aspect_def in ASPECT_DEFINITIONS:
                multiplier = TRANSIT_ORB_MULTIPLIER * min(
                    TRANSIT_POINT_MULTIPLIER.get(t_name, 1.0),
                    TRANSIT_POINT_MULTIPLIER.get(n_name, 1.0),
                )
                max_orb = aspect_def.default_orb * multiplier
                orb = abs(sep - aspect_def.angle)
                if orb <= max_orb:
                    speed = transiting_speeds.get(t_name) if transiting_speeds else None
                    applying = _determine_transit_applying(
                        t_point.longitude, n_point.longitude, speed,
                    )
                    results.append(TransitAspect(
                        transiting_point=t_name,
                        natal_point=n_name,
                        aspect_name=aspect_def.name,
                        orb=orb,
                        max_orb=max_orb,
                        nature=aspect_def.nature,
                        applying=applying,
                    ))
                    break  # closest matching aspect only, same as aspect_engine

    results.sort(key=lambda a: a.tightness)
    return results


# ---------------------------------------------------------------------------
# NOTES for extension
# ---------------------------------------------------------------------------
# - Outer planets (Uranus/Neptune/Pluto) move so slowly that their
#     transits can stay "active" for months or years — worth eventually
#     distinguishing "fast transits" (Moon, Sun, Mercury, Venus, Mars —
#     hours to weeks) from "slow transits" (Jupiter onward — weeks to
#     years) in the interpretation layer, since they carry very
#     different practical weight for a "what's happening right now"
#     reading.
# - This module only checks transiting-planet-to-natal-point aspects.
#     Some traditions also track transiting-planet-to-transiting-planet
#     aspects (e.g. "Saturn conjunct Pluto in the sky right now,
#     regardless of anyone's natal chart") — that would just be
#     aspect_engine.compute_aspects() run on compute_transiting_points()
#     directly, no new code needed.
