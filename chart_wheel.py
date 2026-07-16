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

# Points shown in the linear data table (matching the reference format):
# Ascendant plus the 10 standard planets only — no Chiron/Nodes/Parts/
# Vertex, to match the reference exactly.
TABLE_POINTS = ["Ascendant", "Sun", "Moon", "Mercury", "Venus", "Mars",
                "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
TABLE_GLYPHS = {**PLANET_GLYPHS, "Ascendant": "↑"}


def _order_points_from_ascendant(chart: dict, asc_lon: float) -> list:
    """Returns [(name, point), ...] for the points in TABLE_POINTS that
    exist in this chart, ordered by their position going around the
    wheel starting from the Ascendant (matches the reference image's
    ordering — not alphabetical, not the usual Sun-Moon-Mercury... order)."""
    available = [(name, chart[name]) for name in TABLE_POINTS if name in chart]
    available.sort(key=lambda item: (item[1].longitude - asc_lon) % 360)
    return available


def build_chart_data_table_html(chart: dict) -> str:
    """
    Builds the vertical banded data table in the reference image's
    style: SIGNS (left, banded — shown once per contiguous run), point
    glyph + name (middle, ordered from the Ascendant), HOUSES (right,
    banded — shown only where the house number changes).
    """
    if "Ascendant" not in chart:
        return (
            '<div style="color:#999; padding:20px; font-family:sans-serif;">'
            "This table requires a known birth time (Ascendant unavailable)."
            "</div>"
        )
    asc_lon = chart["Ascendant"].longitude
    ordered = _order_points_from_ascendant(chart, asc_lon)

    rows = []
    prev_sign, prev_house = None, object()  # object() so first row always shows house
    for name, point in ordered:
        show_sign = point.sign != prev_sign
        show_house = point.house != prev_house
        rows.append({
            "sign": point.sign if show_sign else "",
            "glyph": TABLE_GLYPHS.get(name, "?"),
            "name": name.upper(),
            "house": point.house if show_house and point.house is not None else "",
        })
        prev_sign, prev_house = point.sign, point.house

    row_html = ""
    for row in rows:
        house_html = (
            f'<span style="font-family:Georgia,serif;font-size:26px;">{row["house"]}</span>'
            if row["house"] != "" else ""
        )
        row_html += (
            '<tr>'
            f'<td style="background:#1c1c1c;color:#eee;padding:14px 20px;'
            f'border:1px solid #333;font-size:15px;">{row["sign"]}</td>'
            f'<td style="background:#0a0a0a;color:#eee;padding:14px 20px;'
            f'border:1px solid #333;font-size:14px;letter-spacing:1px;">'
            f'{row["glyph"]} {row["name"]}</td>'
            f'<td style="background:#1c1c1c;color:#eee;padding:14px 20px;'
            f'border:1px solid #333;text-align:center;width:70px;">{house_html}</td>'
            '</tr>'
        )

    return f"""
    <div style="display:flex;align-items:stretch;font-family:sans-serif;
                background:#141414;border:1px solid #333;">
        <div style="writing-mode:vertical-rl;transform:rotate(180deg);
                    color:#ccc;letter-spacing:5px;padding:14px 8px;
                    font-size:13px;display:flex;align-items:center;
                    justify-content:center;">SIGNS</div>
        <table style="border-collapse:collapse;flex:1;">{row_html}</table>
        <div style="writing-mode:vertical-rl;color:#ccc;letter-spacing:5px;
                    padding:14px 8px;font-size:13px;display:flex;
                    align-items:center;justify-content:center;">HOUSES</div>
    </div>
    """


def build_synastry_data_table_html(chart_a: dict, chart_b: dict) -> str:
    """
    Merged two-person version of the same table: both people's points
    combined into one list, ordered around the SAME shared reference
    frame (whichever person's Ascendant is available, same anchor logic
    as draw_bi_wheel), each row tagged with which person it belongs to.
    Signs and houses shown are the anchor person's, since only one
    house system can meaningfully be shown at once.
    """
    if "Ascendant" in chart_a:
        anchor_chart, anchor_label = chart_a, "A"
    elif "Ascendant" in chart_b:
        anchor_chart, anchor_label = chart_b, "B"
    else:
        return (
            '<div style="color:#999;padding:20px;font-family:sans-serif;">'
            "This table requires at least one person's birth time to be known."
            "</div>"
        )
    asc_lon = anchor_chart["Ascendant"].longitude

    combined = (
        [(name, point, "A") for name, point in _order_points_from_ascendant(chart_a, asc_lon)] +
        [(name, point, "B") for name, point in _order_points_from_ascendant(chart_b, asc_lon)]
    )
    combined.sort(key=lambda item: (item[1].longitude - asc_lon) % 360)

    rows = []
    prev_sign, prev_house = None, object()
    for name, point, who in combined:
        # Houses only meaningfully belong to the anchor person's own
        # points for banding purposes here — but house PLACEMENT of the
        # visiting person's planets (which house of the anchor's chart
        # they fall into) is exactly what synastry_engine's house
        # overlay already computes, so this table just shows position
        # ordering + which sign band each point falls in, consistently.
        show_sign = point.sign != prev_sign
        show_house = point.house != prev_house
        rows.append({
            "sign": point.sign if show_sign else "",
            "glyph": TABLE_GLYPHS.get(name, "?"),
            "name": f"{name.upper()} ({who})",
            "house": point.house if show_house and point.house is not None else "",
            "who": who,
        })
        prev_sign, prev_house = point.sign, point.house

    row_html = ""
    for row in rows:
        house_html = (
            f'<span style="font-family:Georgia,serif;font-size:26px;">{row["house"]}</span>'
            if row["house"] != "" else ""
        )
        name_bg = "#0a0a0a" if row["who"] == "A" else "#0d1b2a"
        row_html += (
            '<tr>'
            f'<td style="background:#1c1c1c;color:#eee;padding:14px 20px;'
            f'border:1px solid #333;font-size:15px;">{row["sign"]}</td>'
            f'<td style="background:{name_bg};color:#eee;padding:14px 20px;'
            f'border:1px solid #333;font-size:14px;letter-spacing:1px;">'
            f'{row["glyph"]} {row["name"]}</td>'
            f'<td style="background:#1c1c1c;color:#eee;padding:14px 20px;'
            f'border:1px solid #333;text-align:center;width:70px;">{house_html}</td>'
            '</tr>'
        )

    return f"""
    <div style="display:flex;align-items:stretch;font-family:sans-serif;
                background:#141414;border:1px solid #333;">
        <div style="writing-mode:vertical-rl;transform:rotate(180deg);
                    color:#ccc;letter-spacing:5px;padding:14px 8px;
                    font-size:13px;display:flex;align-items:center;
                    justify-content:center;">SIGNS</div>
        <table style="border-collapse:collapse;flex:1;">{row_html}</table>
        <div style="writing-mode:vertical-rl;color:#ccc;letter-spacing:5px;
                    padding:14px 8px;font-size:13px;display:flex;
                    align-items:center;justify-content:center;">HOUSES
                    (Person {anchor_label}'s)</div>
    </div>
    """



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


def draw_bi_wheel(
    chart_a: dict,
    chart_b: dict,
    synastry_aspects: list,
    min_aspect_tightness: float = 0.6,
    figsize: float = 10,
):
    """
    Draws a synastry bi-wheel: Person A's planets on an inner ring,
    Person B's planets on an outer ring, both measured against the SAME
    zodiac/house reference frame so their positions are directly
    comparable — this is the standard convention (using two independent
    Ascendants would misalign the two people relative to each other,
    defeating the point of a bi-wheel).

    The reference frame anchors to whichever person's birth time is
    known (preferring Person A if both are known); if NEITHER has a
    known birth time, the zodiac ring is still drawn (using Aries 0° as
    an arbitrary reference) but house cusps and angle labels are
    omitted, since those require a real Ascendant.

    `synastry_aspects` is the list[SynastryAspect] from
    synastry_engine.compute_synastry_aspects() / compute_full_synastry()
    — lines are drawn connecting Person A's inner-ring position to
    Person B's outer-ring position for the tightest cross-chart aspects.
    """
    if "Ascendant" in chart_a:
        anchor_chart, anchor_label = chart_a, "A"
    elif "Ascendant" in chart_b:
        anchor_chart, anchor_label = chart_b, "B"
    else:
        anchor_chart, anchor_label = None, None

    asc_lon = anchor_chart["Ascendant"].longitude if anchor_chart else 0.0
    has_houses = anchor_chart is not None and "House 1" in anchor_chart

    fig, ax = plt.subplots(figsize=(figsize, figsize))
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_aspect("equal")
    ax.axis("off")

    # --- Zodiac ring ---
    zodiac_outer_r = 1.35
    zodiac_inner_r = 1.15
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
        ax.text(label_x, label_y, SIGN_GLYPHS[i], ha="center", va="center", fontsize=15)

    # --- House ring (only if the anchor person's houses are available) ---
    house_r = zodiac_inner_r
    if has_houses:
        for house_num in range(1, 13):
            cusp_lon = anchor_chart[f"House {house_num}"].longitude
            x1, y1 = _to_xy(cusp_lon, asc_lon, 0.1)
            x2, y2 = _to_xy(cusp_lon, asc_lon, house_r)
            is_angle = house_num in (1, 4, 7, 10)
            ax.plot([x1, x2], [y1, y2],
                    color="#333333" if is_angle else "#bbbbbb",
                    linewidth=1.8 if is_angle else 0.6)
            next_cusp_lon = anchor_chart[f"House {(house_num % 12) + 1}"].longitude
            mid_lon = cusp_lon + ((next_cusp_lon - cusp_lon) % 360) / 2
            lx, ly = _to_xy(mid_lon, asc_lon, house_r * 0.9)
            ax.text(lx, ly, str(house_num), ha="center", va="center",
                    fontsize=8, color="#888888")
        for label, point_name in [("ASC", "Ascendant"), ("DSC", "Descendant"),
                                   ("MC", "Midheaven"), ("IC", "Imum Coeli")]:
            lon = anchor_chart[point_name].longitude
            lx, ly = _to_xy(lon, asc_lon, zodiac_outer_r + 0.08)
            ax.text(lx, ly, label, ha="center", va="center", fontsize=9,
                    fontweight="bold", color="#333333")
    else:
        ax.text(0, 0, "Houses unavailable\n(both birth times unknown)",
                ha="center", va="center", fontsize=11, color="#999999")

    # --- Person A's planets (inner ring) ---
    inner_r = 0.55
    plotted_a = []
    for name in list(PLANET_GLYPHS) + list(FALLBACK_LABELS):
        if name not in chart_a:
            continue
        point = chart_a[name]
        r = inner_r
        for prior_lon in plotted_a:
            if abs(((point.longitude - prior_lon) + 180) % 360 - 180) < 6:
                r += 0.055
        plotted_a.append(point.longitude)
        x, y = _to_xy(point.longitude, asc_lon, r)
        glyph = PLANET_GLYPHS.get(name, FALLBACK_LABELS.get(name, "?"))
        fontsize = 13 if name in PLANET_GLYPHS else 7
        ax.text(x, y, glyph, ha="center", va="center", fontsize=fontsize,
                color="#1a1a2e", zorder=3,
                bbox=dict(boxstyle="circle,pad=0.14", facecolor="white",
                           edgecolor="#1a1a2e", linewidth=0.6))
        if point.retrograde:
            ax.text(x + 0.045, y + 0.045, "℞", fontsize=6, color="#c0392b")

    # --- Person B's planets (outer ring, visually distinguished) ---
    outer_r = 0.9
    plotted_b = []
    for name in list(PLANET_GLYPHS) + list(FALLBACK_LABELS):
        if name not in chart_b:
            continue
        point = chart_b[name]
        r = outer_r
        for prior_lon in plotted_b:
            if abs(((point.longitude - prior_lon) + 180) % 360 - 180) < 6:
                r += 0.055
        plotted_b.append(point.longitude)
        x, y = _to_xy(point.longitude, asc_lon, r)
        glyph = PLANET_GLYPHS.get(name, FALLBACK_LABELS.get(name, "?"))
        fontsize = 13 if name in PLANET_GLYPHS else 7
        ax.text(x, y, glyph, ha="center", va="center", fontsize=fontsize,
                color="#1a1a2e", zorder=3,
                bbox=dict(boxstyle="circle,pad=0.14", facecolor="#dbe9ff",
                           edgecolor="#1a1a2e", linewidth=0.6))
        if point.retrograde:
            ax.text(x + 0.045, y + 0.045, "℞", fontsize=6, color="#c0392b")

    # --- Cross-chart aspect lines (Person A's inner position to Person
    #     B's outer position) ---
    for a in synastry_aspects:
        if a.tightness > min_aspect_tightness:
            continue
        if a.person_a_point not in chart_a or a.person_b_point not in chart_b:
            continue
        x1, y1 = _to_xy(chart_a[a.person_a_point].longitude, asc_lon, inner_r)
        x2, y2 = _to_xy(chart_b[a.person_b_point].longitude, asc_lon, outer_r)
        color = ASPECT_COLORS.get(a.aspect_name, "#cccccc")
        style = "--" if a.aspect_name in ("Sextile", "Trine") else "-"
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=0.9,
                linestyle=style, alpha=0.65, zorder=2)

    # --- Legend ---
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor="#1a1a2e", markersize=11, label="Person A"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#dbe9ff",
               markeredgecolor="#1a1a2e", markersize=11, label="Person B"),
    ]
    ax.legend(handles=legend_elements, loc="upper right",
              bbox_to_anchor=(1.05, 1.05), frameon=False, fontsize=10)

    if anchor_label:
        ax.set_title(f"House ring shown: Person {anchor_label}'s houses",
                     fontsize=9, color="#888888", pad=15)

    plt.tight_layout()
    return fig
