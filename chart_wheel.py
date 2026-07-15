"""
chart_wheel.py

Draws a traditional circular astrology chart wheel using matplotlib:
zodiac ring, house divisions (using actual computed cusp longitudes,
not assumed even spacing), the four angles (Asc/Desc/MC/IC), planet
positions, and aspect lines. Returns a matplotlib Figure that Streamlit
can display directly with st.pyplot().

Convention: the Ascendant is fixed at the 9 o'clock (left) position,
and zodiac longitude increases counterclockwise from there — this is
the standard layout most astrology software uses.
"""

import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# Unicode glyphs for the points we can reliably render with standard
# fonts. Points without a well-supported single-glyph symbol (Part of
# Fortune/Spirit, Vertex/Anti-Vertex) fall back to short text labels.
PLANET_GLYPHS = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀", "Mars": "♂",
    "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", "Neptune": "♆", "Pluto": "♇",
    "Chiron": "⚷", "North Node": "☊", "South Node": "☋",
}
FALLBACK_LABELS = {
    "Part of Fortune": "PoF", "Part of Spirit": "PoS",
    "Vertex": "Vx", "Anti-Vertex": "AVx",
}

SIGN_GLYPHS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]
SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

ASPECT_COLORS = {
    "Conjunction": "#888888",
    "Sextile": "#3498db",
    "Square": "#e74c3c",
    "Trine": "#27ae60",
    "Opposition": "#e74c3c",
}


def _lon_to_math_angle(longitude: float, ascendant_longitude: float) -> float:
    """The core angle formula, shared by point placement and wedge drawing."""
    return (180 + (longitude - ascendant_longitude)) % 360


def _to_xy(longitude: float, ascendant_longitude: float, radius: float) -> tuple[float, float]:
    """Converts an ecliptic longitude to (x, y) on the wheel, with the
    Ascendant fixed at 9 o'clock and longitude increasing counterclockwise."""
    math_angle_deg = _lon_to_math_angle(longitude, ascendant_longitude)
    rad = math.radians(math_angle_deg)
    return radius * math.cos(rad), radius * math.sin(rad)


def draw_chart_wheel(
    chart: dict,
    aspects: list,
    min_aspect_tightness: float = 0.6,
    figsize: float = 9,
):
    """
    Draws a full chart wheel. `chart` is the dict[str, ChartPoint] from
    chart_points.compute_full_chart(); `aspects` is the list[Aspect]
    from aspect_engine.compute_aspects(). Only aspects with tightness
    <= min_aspect_tightness are drawn, to keep the wheel readable
    rather than cluttered with every loose minor aspect.
    """
    asc_lon = chart["Ascendant"].longitude

    fig, ax = plt.subplots(figsize=(figsize, figsize))
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.35, 1.35)
    ax.set_aspect("equal")
    ax.axis("off")

    # --- Zodiac ring (outer) ---
    zodiac_outer_r = 1.25
    zodiac_inner_r = 1.05
    for i in range(12):
        sign_start_lon = i * 30
        start_angle = _lon_to_math_angle(sign_start_lon, asc_lon)
        wedge = mpatches.Wedge(
            (0, 0), zodiac_outer_r, start_angle, start_angle + 30,
            width=zodiac_outer_r - zodiac_inner_r,
            facecolor="#f5f0e8" if i % 2 == 0 else "#e8dfd0",
            edgecolor="#999999", linewidth=0.5,
        )
        ax.add_patch(wedge)
        mid_lon = sign_start_lon + 15
        label_x, label_y = _to_xy(mid_lon, asc_lon, (zodiac_outer_r + zodiac_inner_r) / 2)
        ax.text(label_x, label_y, SIGN_GLYPHS[i], ha="center", va="center", fontsize=16)

    # --- House ring (uses REAL computed cusp longitudes, not assumed
    #     even spacing, since Placidus/Koch/etc. produce unequal houses) ---
    house_r = zodiac_inner_r
    for house_num in range(1, 13):
        cusp_lon = chart[f"House {house_num}"].longitude
        x1, y1 = _to_xy(cusp_lon, asc_lon, 0.15)
        x2, y2 = _to_xy(cusp_lon, asc_lon, house_r)
        is_angle = house_num in (1, 4, 7, 10)
        ax.plot([x1, x2], [y1, y2],
                color="#333333" if is_angle else "#aaaaaa",
                linewidth=2.0 if is_angle else 0.7)
        next_cusp_lon = chart[f"House {(house_num % 12) + 1}"].longitude
        mid_lon = cusp_lon + ((next_cusp_lon - cusp_lon) % 360) / 2
        lx, ly = _to_xy(mid_lon, asc_lon, house_r * 0.88)
        ax.text(lx, ly, str(house_num), ha="center", va="center",
                fontsize=9, color="#666666")

    # --- Angle labels (Asc/Desc/MC/IC) ---
    for label, point_name in [("ASC", "Ascendant"), ("DSC", "Descendant"),
                               ("MC", "Midheaven"), ("IC", "Imum Coeli")]:
        lon = chart[point_name].longitude
        lx, ly = _to_xy(lon, asc_lon, zodiac_outer_r + 0.08)
        ax.text(lx, ly, label, ha="center", va="center", fontsize=10,
                fontweight="bold", color="#333333")

    # --- Aspect lines (inner circle) ---
    aspect_r = 0.75
    for a in aspects:
        if a.tightness > min_aspect_tightness:
            continue
        if a.point1 not in chart or a.point2 not in chart:
            continue
        if a.point1.startswith("House ") or a.point2.startswith("House "):
            continue
        x1, y1 = _to_xy(chart[a.point1].longitude, asc_lon, aspect_r)
        x2, y2 = _to_xy(chart[a.point2].longitude, asc_lon, aspect_r)
        color = ASPECT_COLORS.get(a.aspect_name, "#cccccc")
        style = "--" if a.aspect_name in ("Sextile", "Trine") else "-"
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=0.8,
                linestyle=style, alpha=0.6, zorder=1)

    inner_circle = plt.Circle((0, 0), aspect_r, fill=False, color="#cccccc", linewidth=0.8)
    ax.add_patch(inner_circle)

    # --- Planets (and other points) ---
    planet_r = 0.9
    plotted_lons = []  # for simple collision avoidance
    for name in list(PLANET_GLYPHS) + list(FALLBACK_LABELS):
        if name not in chart:
            continue
        point = chart[name]
        r = planet_r
        # Simple collision avoidance: nudge radius outward slightly for
        # each prior point plotted within 6 degrees of this one.
        for prior_lon in plotted_lons:
            diff = abs(((point.longitude - prior_lon) + 180) % 360 - 180)
            if diff < 6:
                r += 0.06
        plotted_lons.append(point.longitude)

        x, y = _to_xy(point.longitude, asc_lon, r)
        glyph = PLANET_GLYPHS.get(name, FALLBACK_LABELS.get(name, "?"))
        fontsize = 14 if name in PLANET_GLYPHS else 8
        ax.text(x, y, glyph, ha="center", va="center", fontsize=fontsize,
                color="#1a1a2e", zorder=3,
                bbox=dict(boxstyle="circle,pad=0.15", facecolor="white",
                           edgecolor="#1a1a2e", linewidth=0.5))
        if point.retrograde:
            ax.text(x + 0.05, y + 0.05, "℞", fontsize=7, color="#c0392b")

    plt.tight_layout()
    return fig
