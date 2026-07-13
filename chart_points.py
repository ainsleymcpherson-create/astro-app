"""
chart_points.py

Computes birth chart positions using Swiss Ephemeris (pyswisseph).
Covers standard planets plus commonly-neglected points:
  - Part of Fortune and Part of Spirit (day/night-sensitive Hellenistic lots)
  - North Node / South Node (mean or true)
  - House cusps (any house system) + house placement for every point
  - Vertex / Anti-Vertex
  - Chiron
  - (Further extensible to Black Moon Lilith, other Arabic Parts — see
    NOTES at bottom)

Install:
    pip install pyswisseph

Requires ephemeris data files for best accuracy (optional but recommended):
    Download from https://www.astro.com/ftp/swisseph/ephe/
    and call swe.set_ephe_path("/path/to/ephe") before use.
    Without this, pyswisseph falls back to a built-in Moshier approximation
    (still quite accurate, ~0.1 arcsec typical error — fine for this use case).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
import math

try:
    import swisseph as swe
except ImportError as e:
    raise ImportError(
        "pyswisseph is required. Install with: pip install pyswisseph"
    ) from e


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

PLANET_IDS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Uranus": swe.URANUS,
    "Neptune": swe.NEPTUNE,
    "Pluto": swe.PLUTO,
}

# swe.TRUE_NODE for the osculating (true) node, swe.MEAN_NODE for the mean node.
# Mean node is smoother/more commonly used in psychological astrology;
# true node is more astronomically literal. Exposed as a parameter below.


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChartPoint:
    name: str
    longitude: float          # 0-360 degrees, ecliptic
    sign: str
    sign_degree: float        # 0-30 degrees within the sign
    house: int | None = None  # filled in if houses are computed
    retrograde: bool = False
    speed: float | None = None  # degrees/day (signed; negative = retrograde
                                 # motion). None for derived/composite points
                                 # (angles, Part of Fortune/Spirit, Vertex,
                                 # house cusps) where true speed isn't a
                                 # simple ephemeris lookup — see NOTES.

    def __repr__(self):
        deg = self.sign_degree
        return f"{self.name}: {deg:.2f}° {self.sign}" + (" (R)" if self.retrograde else "")


@dataclass
class BirthData:
    dt_utc: datetime          # must be timezone-aware, in UTC
    latitude: float           # + North, - South
    longitude: float          # + East, - West


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_julian_day(dt_utc: datetime) -> float:
    if dt_utc.tzinfo is None:
        raise ValueError("dt_utc must be timezone-aware (convert to UTC first)")
    dt_utc = dt_utc.astimezone(timezone.utc)
    hour = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour)


def _longitude_to_sign(lon: float) -> tuple[str, float]:
    lon = lon % 360
    sign_index = int(lon // 30)
    sign_degree = lon % 30
    return SIGNS[sign_index], sign_degree


def _is_daytime_birth(sun_lon: float, asc_lon: float, desc_lon: float) -> bool:
    """
    Day birth: Sun is above the horizon, i.e. between Ascendant and
    Descendant along the diurnal (upper) half of the chart.
    """
    diff = (sun_lon - asc_lon) % 360
    return diff < 180  # Sun in houses 7-12 (above horizon) = day birth


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_planets(birth: BirthData) -> dict[str, ChartPoint]:
    """Returns standard planetary positions."""
    jd = _to_julian_day(birth.dt_utc)
    results = {}
    for name, pid in PLANET_IDS.items():
        pos, _ = swe.calc_ut(jd, pid)
        lon, speed = pos[0], pos[3]
        sign, sign_deg = _longitude_to_sign(lon)
        results[name] = ChartPoint(
            name=name, longitude=lon, sign=sign,
            sign_degree=sign_deg, retrograde=(speed < 0), speed=speed
        )
    return results


def compute_nodes(
    birth: BirthData,
    node_type: Literal["mean", "true"] = "true",
) -> dict[str, ChartPoint]:
    """
    Returns North Node and South Node (exactly 180° apart by definition).

    node_type:
      "true" - the actual osculating node, accounts for lunar wobble.
                Preferred by most modern astrologers for precision.
      "mean" - smoothed average node, more traditional/classical usage.
    """
    jd = _to_julian_day(birth.dt_utc)
    node_id = swe.TRUE_NODE if node_type == "true" else swe.MEAN_NODE
    pos, _ = swe.calc_ut(jd, node_id)
    north_lon, node_speed = pos[0], pos[3]
    south_lon = (north_lon + 180) % 360

    n_sign, n_deg = _longitude_to_sign(north_lon)
    s_sign, s_deg = _longitude_to_sign(south_lon)

    return {
        "North Node": ChartPoint("North Node", north_lon, n_sign, n_deg, speed=node_speed),
        # South Node is rigidly 180° from North Node at all times, so it
        # moves at exactly the same signed rate.
        "South Node": ChartPoint("South Node", south_lon, s_sign, s_deg, speed=node_speed),
    }


def compute_angles(birth: BirthData, house_system: bytes = b"P") -> dict[str, ChartPoint]:
    """
    Returns Ascendant, Descendant, Midheaven (MC), Imum Coeli (IC),
    and Vertex / Anti-Vertex.

    house_system: b"P" = Placidus (default), b"W" = Whole Sign,
                  b"K" = Koch, b"E" = Equal, etc. (see swisseph docs)

    Vertex is a second, less-known "relationship axis" point — often
    described as marking fated encounters/turning points, and used in
    synastry alongside Asc/Dsc. It's the ascmc[3] value returned by
    swe.houses(); Anti-Vertex is simply +180°.

    Note: Vertex becomes unstable/undefined near the polar circles
    (where the ecliptic runs near-parallel to the horizon) — not a
    concern for the vast majority of birth locations.
    """
    jd = _to_julian_day(birth.dt_utc)
    cusps, ascmc = swe.houses(jd, birth.latitude, birth.longitude, house_system)
    asc, mc = ascmc[0], ascmc[1]
    dsc = (asc + 180) % 360
    ic = (mc + 180) % 360
    vertex = ascmc[3]
    anti_vertex = (vertex + 180) % 360

    points = {}
    for name, lon in [
        ("Ascendant", asc), ("Descendant", dsc),
        ("Midheaven", mc), ("Imum Coeli", ic),
        ("Vertex", vertex), ("Anti-Vertex", anti_vertex),
    ]:
        sign, deg = _longitude_to_sign(lon)
        points[name] = ChartPoint(name, lon, sign, deg)
    return points


def compute_houses(birth: BirthData, house_system: bytes = b"P") -> list[ChartPoint]:
    """
    Returns the 12 house cusps as a list (index 0 = House 1 / Ascendant
    cusp, index 11 = House 12), each as a ChartPoint with `.house` set
    to its own house number for convenience.

    house_system byte codes (subset): b"P" Placidus, b"W" Whole Sign,
    b"K" Koch, b"E" Equal, b"C" Campanus, b"R" Regiomontanus,
    b"B" Alcabitius. Whole Sign (b"W") is common in traditional/
    Hellenistic-influenced approaches (relevant since Part of Fortune
    below is a Hellenistic technique) and is a good default if unsure.
    """
    jd = _to_julian_day(birth.dt_utc)
    cusps, ascmc = swe.houses(jd, birth.latitude, birth.longitude, house_system)
    # cusps is a 12-tuple (1-indexed conceptually; cusps[0] == house 1 cusp)
    houses = []
    for i, lon in enumerate(cusps, start=1):
        sign, deg = _longitude_to_sign(lon)
        cp = ChartPoint(f"House {i}", lon, sign, deg, house=i)
        houses.append(cp)
    return houses


def assign_house(longitude: float, house_cusps: list[ChartPoint]) -> int:
    """
    Given a point's longitude and the 12 house cusps (from compute_houses),
    returns which house (1-12) that point falls in.
    """
    cusp_lons = [hp.longitude for hp in house_cusps]
    lon = longitude % 360
    for i in range(12):
        start = cusp_lons[i]
        end = cusp_lons[(i + 1) % 12]
        span = (end - start) % 360
        offset = (lon - start) % 360
        if offset < span:
            return i + 1
    return 12  # fallback, shouldn't normally hit


def compute_chiron(birth: BirthData) -> ChartPoint:
    """
    Chiron — the "wounded healer" asteroid/centaur. Represents core
    wounding and the capacity to heal (self or others) through it;
    widely used in modern psychological astrology despite being absent
    from classical texts.

    Requires the seas_18.se1 (or similar Chiron) ephemeris file for
    dates outside ~1900-2100; without it, calc_ut will raise an error
    or return degraded accuracy for out-of-range dates. Download from
    https://www.astro.com/ftp/swisseph/ephe/ and set via
    swe.set_ephe_path() if you hit this.
    """
    jd = _to_julian_day(birth.dt_utc)
    pos, _ = swe.calc_ut(jd, swe.CHIRON)
    lon, speed = pos[0], pos[3]
    sign, deg = _longitude_to_sign(lon)
    return ChartPoint("Chiron", lon, sign, deg, retrograde=(speed < 0), speed=speed)


def compute_part_of_fortune(
    birth: BirthData,
    planets: dict[str, ChartPoint] | None = None,
    angles: dict[str, ChartPoint] | None = None,
) -> ChartPoint:
    """
    Part of Fortune (Lot of Fortune) — classical Hellenistic formula,
    day/night sensitive:

      Day birth:   Fortune = Asc + Moon - Sun
      Night birth: Fortune = Asc + Sun - Moon

    This distinction is frequently skipped in pop-astrology tools (they
    often just use the day formula regardless), which quietly produces
    wrong results for roughly half of all charts. We compute day/night
    from the actual chart rather than assuming.
    """
    if planets is None:
        planets = compute_planets(birth)
    if angles is None:
        angles = compute_angles(birth)

    sun_lon = planets["Sun"].longitude
    moon_lon = planets["Moon"].longitude
    asc_lon = angles["Ascendant"].longitude
    desc_lon = angles["Descendant"].longitude

    day_birth = _is_daytime_birth(sun_lon, asc_lon, desc_lon)

    if day_birth:
        fortune_lon = (asc_lon + moon_lon - sun_lon) % 360
    else:
        fortune_lon = (asc_lon + sun_lon - moon_lon) % 360

    sign, deg = _longitude_to_sign(fortune_lon)
    point = ChartPoint("Part of Fortune", fortune_lon, sign, deg)
    point.is_day_birth = day_birth  # type: ignore[attr-defined]  (informational)
    return point


def compute_part_of_spirit(
    birth: BirthData,
    planets: dict[str, ChartPoint] | None = None,
    angles: dict[str, ChartPoint] | None = None,
) -> ChartPoint:
    """
    Part of Spirit — the classical counterpart to Part of Fortune,
    representing conscious will/purpose vs. Fortune's more fated/bodily
    significations. Formula is Fortune's mirror:

      Day birth:   Spirit = Asc + Sun - Moon
      Night birth: Spirit = Asc + Moon - Sun
    """
    if planets is None:
        planets = compute_planets(birth)
    if angles is None:
        angles = compute_angles(birth)

    sun_lon = planets["Sun"].longitude
    moon_lon = planets["Moon"].longitude
    asc_lon = angles["Ascendant"].longitude
    desc_lon = angles["Descendant"].longitude

    day_birth = _is_daytime_birth(sun_lon, asc_lon, desc_lon)

    if day_birth:
        spirit_lon = (asc_lon + sun_lon - moon_lon) % 360
    else:
        spirit_lon = (asc_lon + moon_lon - sun_lon) % 360

    sign, deg = _longitude_to_sign(spirit_lon)
    return ChartPoint("Part of Spirit", spirit_lon, sign, deg)


def compute_full_chart(
    birth: BirthData,
    node_type: Literal["mean", "true"] = "true",
    house_system: bytes = b"P",
) -> dict[str, ChartPoint]:
    """
    Convenience function: returns every point this module supports, merged,
    with `.house` filled in on each point (which of the 12 houses it falls in).
    """
    planets = compute_planets(birth)
    angles = compute_angles(birth, house_system)
    nodes = compute_nodes(birth, node_type)
    fortune = compute_part_of_fortune(birth, planets, angles)
    spirit = compute_part_of_spirit(birth, planets, angles)
    chiron = compute_chiron(birth)
    house_cusps = compute_houses(birth, house_system)

    chart: dict[str, ChartPoint] = {}
    chart.update(planets)
    chart.update(angles)
    chart.update(nodes)
    chart["Part of Fortune"] = fortune
    chart["Part of Spirit"] = spirit
    chart["Chiron"] = chiron

    angle_names = {"Ascendant", "Descendant", "Midheaven", "Imum Coeli"}
    for name, point in chart.items():
        if name not in angle_names:
            point.house = assign_house(point.longitude, house_cusps)

    for hp in house_cusps:
        chart[hp.name] = hp

    return chart


def extract_speeds(chart: dict[str, ChartPoint]) -> dict[str, float]:
    """
    Pulls {point_name: speed_degrees_per_day} out of a chart for any point
    that has speed data (planets, Nodes, Chiron). Points without a direct
    ephemeris speed (angles, Part of Fortune/Spirit, Vertex, house cusps)
    are simply omitted — feed this straight into
    aspect_engine.compute_aspects(..., speeds=extract_speeds(chart)) to
    get applying/separating resolved wherever it can be.
    """
    return {
        name: point.speed
        for name, point in chart.items()
        if point.speed is not None
    }


# ---------------------------------------------------------------------------
# NOTES for extension
# ---------------------------------------------------------------------------
# Speed / applying-separating:
#   - Angles (Asc/MC/Dsc/IC), Part of Fortune/Spirit, and Vertex don't have
#       a simple direct ephemeris speed the way planets do — they're all
#       derived from the fast-moving Ascendant/MC, which technically move
#       ~1°/4min due to Earth's rotation (not orbital motion), so "speed"
#       in the orbital sense isn't meaningful for them the same way.
#       Aspects involving these points will have applying=None from the
#       aspect engine unless you compute a numerical derivative (chart at
#       T and T+epsilon, take the difference) — doable but out of scope
#       here since these axis points are usually read as fixed reference
#       points rather than "applying to" something.
#
# Other lesser-used points worth adding later:
#   - Black Moon Lilith (mean or osculating): swe.MEAN_APOG / swe.OSCU_APOG
#   - Other Arabic Parts (Part of Marriage, Part of Death, etc.) all follow
#       the same Asc + X - Y day/night pattern as Fortune/Spirit above.
#   - Other asteroids some astrologers track: Ceres, Pallas, Juno, Vesta
#       (all available via swe.calc_ut with their respective IDs, though
#       Juno/Vesta/etc. need their own ephemeris files for full range).
