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
    "Chiron": "⚷", "North Node": "☊", "South Node": "☋", "Lilith": "⚸",
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
    # Muted, antique-toned rather than bright web colors, so aspect
    # lines read as part of the same brass/parchment palette as the
    # rest of the chart instead of clashing neon against the indigo
    # background. Warm tones (rust/brick) for hard aspects, cool tones
    # (dusty blue/sage) for soft ones -- keeps the functional soft-vs-
    # hard distinction the original bright red/green/blue scheme had.
    "Conjunction": "#9B9488",
    "Sextile": "#6B8CAE",
    "Square": "#B2543D",
    "Trine": "#7A9B7A",
    "Opposition": "#9B4A42",
}

# Points shown in the linear data table — everything the wheel itself
# plots (PLANET_GLYPHS + FALLBACK_LABELS), not just the 10 standard
# planets, so the table stays consistent with what's actually on the
# chart wheel image.
TABLE_POINTS = [
    "Ascendant", "Sun", "Moon", "Mercury", "Venus", "Mars",
    "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    "Chiron", "North Node", "South Node", "Lilith",
    "Part of Fortune", "Part of Spirit", "Vertex", "Anti-Vertex",
]
TABLE_GLYPHS = {**PLANET_GLYPHS, **FALLBACK_LABELS, "Ascendant": "↑"}

# One-sentence sign descriptions for the data table's description column.
SIGN_ONE_LINE = {
    "Aries": "Direct and instinctive — acts first and asks questions later.",
    "Taurus": "Grounded and steady — values comfort, stability, and things built to last.",
    "Gemini": "Curious and quick — gathers information from many angles at once.",
    "Cancer": "Protective and emotionally attuned — oriented around safety and belonging.",
    "Leo": "Warm and expressive — wants to be genuinely seen and valued.",
    "Virgo": "Precise and service-oriented — notices what's off and works to improve it.",
    "Libra": "Relational and fairness-oriented — seeks balance and genuine partnership.",
    "Scorpio": "Intense and private — drawn to what's beneath the surface.",
    "Sagittarius": "Expansive and meaning-seeking — oriented toward the big picture.",
    "Capricorn": "Disciplined and long-game oriented — builds structure and earns authority over time.",
    "Aquarius": "Independent-minded — values being genuinely original over following the crowd.",
    "Pisces": "Absorptive and imaginative — dissolves boundaries between self and others.",
}

# One-sentence point/planet descriptions for the data table's second
# description column (after the point name, before the house).
POINT_ONE_LINE = {
    "Sun": "Core identity and what this person is fundamentally expressing.",
    "Moon": "Emotional instinct and what feels safe on a gut level.",
    "Mercury": "Communication and thinking style.",
    "Venus": "Values, aesthetic sense, and how this person relates to others.",
    "Mars": "Drive, assertion, and how this person pursues goals.",
    "Jupiter": "Growth, expansion, and where this person finds opportunity.",
    "Saturn": "Structure, discipline, and where sustained effort is required.",
    "Uranus": "Disruption, independence, and a drive toward originality.",
    "Neptune": "Imagination, idealism, and a dissolving of boundaries.",
    "Pluto": "Deep transformation and what must be faced rather than avoided.",
    "Chiron": "The 'wounded healer' — a core sensitivity that becomes a source of insight.",
    "Lilith": "Raw instinct and desire — what's been repressed or shamed rather than owned.",
    "North Node": "The direction of growth this person is meant to develop toward.",
    "South Node": "Familiar, innate patterns this person naturally falls back on.",
    "Ascendant": "How this person initiates and comes across to others.",
    "Part of Fortune": "Where ease and good fortune tend to show up most naturally.",
    "Part of Spirit": "Conscious will — where deliberate effort tends to pay off.",
    "Vertex": "Sometimes tied to fated encounters or significant turning points.",
    "Anti-Vertex": "The point directly opposite the Vertex, completing that axis.",
}


def _order_points_from_ascendant(chart: dict, asc_lon: float) -> list:
    """Returns [(name, point), ...] for the points in TABLE_POINTS that
    exist in this chart, ordered by their position going around the
    wheel starting from the Ascendant (matches the reference image's
    ordering — not alphabetical, not the usual Sun-Moon-Mercury... order)."""
    available = [(name, chart[name]) for name in TABLE_POINTS if name in chart]
    available.sort(key=lambda item: (item[1].longitude - asc_lon) % 360)
    return available


def get_table_rows(chart: dict) -> list[dict]:
    """
    Plain-data companion to build_chart_data_table_html() — same point
    ordering and content, but as a list of dicts (Sign, Point, House)
    instead of HTML, for CSV export. Unlike the HTML table, this
    doesn't merge repeated signs/houses into banded cells — each row
    lists its own sign and house directly, which is the more useful
    and natural shape for a spreadsheet.
    """
    if "Ascendant" not in chart:
        return []
    asc_lon = chart["Ascendant"].longitude
    ordered = _order_points_from_ascendant(chart, asc_lon)
    return [
        {
            "Sign": point.sign,
            "Point": name,
            "House": point.house if point.house is not None else "",
        }
        for name, point in ordered
    ]


def get_synastry_table_rows(chart_a: dict, chart_b: dict) -> list[dict]:
    """Plain-data companion to build_synastry_data_table_html() — same
    merged ordering, as a list of dicts for CSV export."""
    if "Ascendant" in chart_a:
        anchor_chart = chart_a
    elif "Ascendant" in chart_b:
        anchor_chart = chart_b
    else:
        return []
    asc_lon = anchor_chart["Ascendant"].longitude

    combined = (
        [(name, point, "A") for name, point in _order_points_from_ascendant(chart_a, asc_lon)] +
        [(name, point, "B") for name, point in _order_points_from_ascendant(chart_b, asc_lon)]
    )
    combined.sort(key=lambda item: (item[1].longitude - asc_lon) % 360)

    return [
        {
            "Sign": point.sign,
            "Person": who,
            "Point": name,
            "House (own chart)": point.house if point.house is not None else "",
        }
        for name, point, who in combined
    ]


def build_chart_data_table_html(chart: dict) -> str:
    """
    Builds the vertical banded data table in the reference image's
    style: SIGNS (left) and HOUSES (right) each merge into ONE cell per
    contiguous run via HTML rowspan — not repeated text, and not blank
    cells that could look like missing data. Point glyph + name (middle)
    ordered from the Ascendant.
    """
    if "Ascendant" not in chart:
        return (
            '<div style="color:#999; padding:20px; font-family:sans-serif;">'
            "This table requires a known birth time (Ascendant unavailable)."
            "</div>"
        )
    asc_lon = chart["Ascendant"].longitude
    ordered = _order_points_from_ascendant(chart, asc_lon)

    def _group_sizes(key_fn):
        """Groups consecutive items sharing the same key into runs, for
        rowspan merging. None values (e.g. angles with no house) never
        merge with each other — each stays its own single-row group,
        since a run of blank cells looks like missing data."""
        sizes = []
        for item in ordered:
            key = key_fn(item)
            if key is not None and sizes and sizes[-1][0] == key:
                sizes[-1][1] += 1
            else:
                sizes.append([key, 1])
        return sizes

    sign_groups = _group_sizes(lambda item: item[1].sign)
    house_groups = _group_sizes(lambda item: item[1].house)

    row_html = ""
    sign_idx = sign_row = house_idx = house_row = 0
    for name, point in ordered:
        sign_rowspan = sign_groups[sign_idx][1]
        if sign_row == 0:
            sign_td = (
                f'<td rowspan="{sign_rowspan}" style="background:#1c1c1c;color:#eee;'
                f'padding:14px 20px;border:1px solid #333;font-size:15px;'
                f'vertical-align:middle;width:140px;">{point.sign}</td>'
            )
            desc_td = (
                f'<td rowspan="{sign_rowspan}" style="background:#161616;color:#aaa;'
                f'padding:14px 16px;border:1px solid #333;font-size:12px;'
                f'font-style:italic;vertical-align:middle;width:140px;">'
                f'{SIGN_ONE_LINE.get(point.sign, "")}</td>'
            )
        else:
            sign_td = ""  # covered by the rowspan cell above
            desc_td = ""  # covered by the rowspan cell above
        sign_row += 1
        if sign_row >= sign_rowspan:
            sign_idx += 1
            sign_row = 0

        house_rowspan = house_groups[house_idx][1]
        if house_row == 0:
            house_val = point.house if point.house is not None else ""
            house_inner = (
                f'<span style="font-family:Georgia,serif;font-size:26px;">{house_val}</span>'
                if house_val != "" else ""
            )
            house_td = (
                f'<td rowspan="{house_rowspan}" style="background:#1c1c1c;color:#eee;'
                f'padding:14px 20px;border:1px solid #333;text-align:center;'
                f'vertical-align:middle;width:70px;">{house_inner}</td>'
            )
        else:
            house_td = ""  # covered by the rowspan cell above
        house_row += 1
        if house_row >= house_rowspan:
            house_idx += 1
            house_row = 0

        row_html += (
            '<tr>'
            f'{sign_td}'
            f'{desc_td}'
            f'<td style="background:#0a0a0a;color:#eee;padding:14px 20px;'
            f'border:1px solid #333;font-size:14px;letter-spacing:1px;">'
            f'{TABLE_GLYPHS.get(name, "?")} {name.upper()}</td>'
            f'<td style="background:#161616;color:#aaa;padding:14px 16px;'
            f'border:1px solid #333;font-size:12px;font-style:italic;'
            f'max-width:220px;">{POINT_ONE_LINE.get(name, "")}</td>'
            f'{house_td}'
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

    def _group_sizes(key_fn):
        """Groups consecutive items sharing the same key into runs, for
        rowspan merging. None values never merge with each other."""
        sizes = []
        for item in combined:
            key = key_fn(item)
            if key is not None and sizes and sizes[-1][0] == key:
                sizes[-1][1] += 1
            else:
                sizes.append([key, 1])
        return sizes

    sign_groups = _group_sizes(lambda item: item[1].sign)
    house_groups = _group_sizes(lambda item: item[1].house)

    row_html = ""
    sign_idx = sign_row = house_idx = house_row = 0
    for name, point, who in combined:
        # Note: the house shown here is each person's OWN house
        # placement within their OWN chart (not the cross-chart
        # overlay — "Person A's planet in Person B's house" — which is
        # already covered separately in the Houses tab).
        sign_rowspan = sign_groups[sign_idx][1]
        if sign_row == 0:
            sign_td = (
                f'<td rowspan="{sign_rowspan}" style="background:#1c1c1c;color:#eee;'
                f'padding:14px 20px;border:1px solid #333;font-size:15px;'
                f'vertical-align:middle;width:140px;">{point.sign}</td>'
            )
            desc_td = (
                f'<td rowspan="{sign_rowspan}" style="background:#161616;color:#aaa;'
                f'padding:14px 16px;border:1px solid #333;font-size:12px;'
                f'font-style:italic;vertical-align:middle;width:140px;">'
                f'{SIGN_ONE_LINE.get(point.sign, "")}</td>'
            )
        else:
            sign_td = ""
            desc_td = ""
        sign_row += 1
        if sign_row >= sign_rowspan:
            sign_idx += 1
            sign_row = 0

        house_rowspan = house_groups[house_idx][1]
        if house_row == 0:
            house_val = point.house if point.house is not None else ""
            house_inner = (
                f'<span style="font-family:Georgia,serif;font-size:26px;">{house_val}</span>'
                if house_val != "" else ""
            )
            house_td = (
                f'<td rowspan="{house_rowspan}" style="background:#1c1c1c;color:#eee;'
                f'padding:14px 20px;border:1px solid #333;text-align:center;'
                f'vertical-align:middle;width:70px;">{house_inner}</td>'
            )
        else:
            house_td = ""
        house_row += 1
        if house_row >= house_rowspan:
            house_idx += 1
            house_row = 0

        name_bg = "#0a0a0a" if who == "A" else "#0d1b2a"
        row_html += (
            '<tr>'
            f'{sign_td}'
            f'{desc_td}'
            f'<td style="background:{name_bg};color:#eee;padding:14px 20px;'
            f'border:1px solid #333;font-size:14px;letter-spacing:1px;">'
            f'{TABLE_GLYPHS.get(name, "?")} {name.upper()} ({who})</td>'
            f'<td style="background:#161616;color:#aaa;padding:14px 16px;'
            f'border:1px solid #333;font-size:12px;font-style:italic;'
            f'max-width:220px;">{POINT_ONE_LINE.get(name, "")}</td>'
            f'{house_td}'
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
    fig.patch.set_facecolor("#1B2036")
    ax.set_facecolor("#1B2036")
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.35, 1.35)
    ax.set_aspect("equal")
    ax.axis("off")

    _draw_wheel_content(ax, chart, aspects, min_aspect_tightness, asc_lon)

    plt.tight_layout()
    return fig


def _draw_wheel_content(ax, chart: dict, aspects: list, min_aspect_tightness: float, asc_lon: float):
    """
    Draws the zodiac ring, house ring, angle labels, aspect lines, and
    planets onto an existing axes. Extracted out of draw_chart_wheel()
    so draw_chart_wheel_art() (the poster/card export) can reuse the
    exact same drawing logic rather than duplicating ~90 lines of it —
    the two just wrap it in different figure layouts (draw_chart_wheel
    is a single square axes; the art export adds a title block below).
    """
    # --- Zodiac ring (outer) ---
    zodiac_outer_r = 1.25
    zodiac_inner_r = 1.05
    for i in range(12):
        sign_start_lon = i * 30
        start_angle = _lon_to_math_angle(sign_start_lon, asc_lon)
        wedge = mpatches.Wedge(
            (0, 0), zodiac_outer_r, start_angle, start_angle + 30,
            width=zodiac_outer_r - zodiac_inner_r,
            facecolor="#252B47" if i % 2 == 0 else "#1B2036",
            edgecolor="#5A5470", linewidth=0.5,
        )
        ax.add_patch(wedge)
        mid_lon = sign_start_lon + 15
        label_x, label_y = _to_xy(mid_lon, asc_lon, (zodiac_outer_r + zodiac_inner_r) / 2)
        ax.text(label_x, label_y, SIGN_GLYPHS[i], ha="center", va="center", fontsize=16, color="#C9A66B")

    # --- House ring (uses REAL computed cusp longitudes, not assumed
    #     even spacing, since Placidus/Koch/etc. produce unequal houses) ---
    house_r = zodiac_inner_r
    for house_num in range(1, 13):
        cusp_lon = chart[f"House {house_num}"].longitude
        x1, y1 = _to_xy(cusp_lon, asc_lon, 0.15)
        x2, y2 = _to_xy(cusp_lon, asc_lon, house_r)
        is_angle = house_num in (1, 4, 7, 10)
        ax.plot([x1, x2], [y1, y2],
                color="#C9A66B" if is_angle else "#5A5470",
                linewidth=2.0 if is_angle else 0.7)
        next_cusp_lon = chart[f"House {(house_num % 12) + 1}"].longitude
        mid_lon = cusp_lon + ((next_cusp_lon - cusp_lon) % 360) / 2
        lx, ly = _to_xy(mid_lon, asc_lon, house_r * 0.88)
        ax.text(lx, ly, str(house_num), ha="center", va="center",
                fontsize=9, color="#8B87A8")

    # --- Angle labels (Asc/Desc/MC/IC) ---
    for label, point_name in [("ASC", "Ascendant"), ("DSC", "Descendant"),
                               ("MC", "Midheaven"), ("IC", "Imum Coeli")]:
        lon = chart[point_name].longitude
        lx, ly = _to_xy(lon, asc_lon, zodiac_outer_r + 0.08)
        ax.text(lx, ly, label, ha="center", va="center", fontsize=10,
                fontweight="bold", color="#C9A66B")

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
        color = ASPECT_COLORS.get(a.aspect_name, "#5A5470")
        style = "--" if a.aspect_name in ("Sextile", "Trine") else "-"
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=0.8,
                linestyle=style, alpha=0.6, zorder=1)

    inner_circle = plt.Circle((0, 0), aspect_r, fill=False, color="#5A5470", linewidth=0.8)
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
                color="#EDE6D6", zorder=3,
                bbox=dict(boxstyle="circle,pad=0.15", facecolor="#252B47",
                           edgecolor="#C9A66B", linewidth=0.5))
        if point.retrograde:
            ax.text(x + 0.05, y + 0.05, "℞", fontsize=7, color="#D1495B")


def draw_bi_wheel(
    chart_a: dict,
    chart_b: dict,
    synastry_aspects: list,
    min_aspect_tightness: float = 0.6,
    figsize: float = 10,
):
    """
    Draws a synastry bi-wheel with a SEPARATE house ring for each
    person — Person A's houses on the outer ring, Person B's on an
    inner ring, each with their own ASC/DSC/MC/IC angle labels. Both
    rings share the SAME zodiac reference frame (one fixed longitude
    at the 9 o'clock position), so a planet's or a house cusp's actual
    zodiacal position is directly comparable between the two rings —
    this is the standard bi-wheel convention: the two house systems
    are drawn separately, but neither wheel is independently rotated
    to put its own Ascendant at 9 o'clock.

    Whichever person has a known birth time becomes the OUTER ring
    (Person A preferred if both are known, since they're the "primary"
    chart in the UI). If only one person's time is known, that person
    is always the outer ring, so the more prominent ring shows real
    house data. If NEITHER has a known birth time, both house rings
    are omitted (planets and the zodiac ring still draw normally).

    `synastry_aspects` is the list[SynastryAspect] from
    synastry_engine.compute_synastry_aspects() / compute_full_synastry()
    — lines connect Person A's ring position to Person B's ring
    position for the tightest cross-chart aspects.
    """
    a_has_houses = "Ascendant" in chart_a and "House 1" in chart_a
    b_has_houses = "Ascendant" in chart_b and "House 1" in chart_b

    if a_has_houses:
        outer_chart, outer_label = chart_a, "A"
        inner_chart, inner_label, inner_has_houses = chart_b, "B", b_has_houses
        asc_lon = chart_a["Ascendant"].longitude
    elif b_has_houses:
        outer_chart, outer_label = chart_b, "B"
        inner_chart, inner_label, inner_has_houses = chart_a, "A", a_has_houses
        asc_lon = chart_b["Ascendant"].longitude
    else:
        outer_chart = inner_chart = None
        outer_label = inner_label = None
        inner_has_houses = False
        asc_lon = 0.0

    fig, ax = plt.subplots(figsize=(figsize, figsize))
    fig.patch.set_facecolor("#1B2036")
    ax.set_facecolor("#1B2036")
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_aspect("equal")
    ax.axis("off")

    _draw_bi_wheel_content(ax, chart_a, chart_b, synastry_aspects, min_aspect_tightness,
                            asc_lon, outer_chart, inner_chart, outer_label, inner_label,
                            inner_has_houses)

    plt.tight_layout()
    return fig


def _draw_bi_wheel_content(ax, chart_a, chart_b, synastry_aspects, min_aspect_tightness,
                            asc_lon, outer_chart, inner_chart, outer_label, inner_label,
                            inner_has_houses):
    """
    Draws the zodiac ring, both house rings, planets, cross-chart
    aspect lines, legend, and ring-info title onto an existing axes.
    Extracted out of draw_bi_wheel() so draw_bi_wheel_art() (the
    synastry poster/card export) can reuse the exact same drawing
    logic rather than duplicating it — the two just wrap it in
    different figure layouts, same relationship as
    draw_chart_wheel / _draw_wheel_content / draw_chart_wheel_art.
    """
    # --- Zodiac ring (shared reference frame for everything else) ---
    zodiac_outer_r = 1.35
    zodiac_inner_r = 1.15
    for i in range(12):
        sign_start_lon = i * 30
        start_angle = _lon_to_math_angle(sign_start_lon, asc_lon)
        wedge = mpatches.Wedge(
            (0, 0), zodiac_outer_r, start_angle, start_angle + 30,
            width=zodiac_outer_r - zodiac_inner_r,
            facecolor="#252B47" if i % 2 == 0 else "#1B2036",
            edgecolor="#5A5470", linewidth=0.5,
        )
        ax.add_patch(wedge)
        mid_lon = sign_start_lon + 15
        label_x, label_y = _to_xy(mid_lon, asc_lon, (zodiac_outer_r + zodiac_inner_r) / 2)
        ax.text(label_x, label_y, SIGN_GLYPHS[i], ha="center", va="center", fontsize=15, color="#C9A66B")

    def _draw_house_ring(chart, ring_outer_r, ring_inner_r, angle_color, num_color, num_fontsize, label_r, label_fontsize, inner_overshoot=0.0, outer_overshoot=0.0):
        """Draws one person's house-cusp spokes and angle labels within
        the given radius band. inner_overshoot/outer_overshoot extend
        just the LINE's endpoints slightly past ring_inner_r/
        ring_outer_r (where the boundary circles are drawn), so the
        spokes clearly overlap the circles rather than merely touching
        them at one exact mathematical point — real gaps can otherwise
        be visible once line width and anti-aliasing are factored in.
        House-number label positions are unaffected, based on the true
        (non-overshot) band."""
        line_inner_r = max(ring_inner_r - inner_overshoot, 0.0)
        line_outer_r = ring_outer_r + outer_overshoot
        for house_num in range(1, 13):
            cusp_lon = chart[f"House {house_num}"].longitude
            x1, y1 = _to_xy(cusp_lon, asc_lon, line_inner_r)
            x2, y2 = _to_xy(cusp_lon, asc_lon, line_outer_r)
            is_angle = house_num in (1, 4, 7, 10)
            ax.plot([x1, x2], [y1, y2],
                    color=angle_color if is_angle else "#5A5470",
                    linewidth=1.8 if is_angle else 0.6, zorder=1)
            next_cusp_lon = chart[f"House {(house_num % 12) + 1}"].longitude
            mid_lon = cusp_lon + ((next_cusp_lon - cusp_lon) % 360) / 2
            lx, ly = _to_xy(mid_lon, asc_lon, (ring_outer_r + ring_inner_r) / 2)
            ax.text(lx, ly, str(house_num), ha="center", va="center",
                    fontsize=num_fontsize, color=num_color)
        for label, point_name in [("ASC", "Ascendant"), ("DSC", "Descendant"),
                                   ("MC", "Midheaven"), ("IC", "Imum Coeli")]:
            lon = chart[point_name].longitude
            lx, ly = _to_xy(lon, asc_lon, label_r)
            ax.text(lx, ly, label, ha="center", va="center", fontsize=label_fontsize,
                    fontweight="bold", color=angle_color)

    # Three boundary circles total, from the center outward: innermost
    # (aspect hub), second (shared meeting point between the two house
    # rings), outermost (zodiac ring's inner edge). The INNER house
    # ring's lines run from the innermost circle to the second circle;
    # the OUTER house ring's lines run from the second circle to the
    # outermost circle — the two rings share that middle circle rather
    # than leaving a gap between them.
    innermost_r = 0.42
    second_r = 0.85
    outermost_r = zodiac_inner_r

    # --- Outer house ring: second circle to outermost circle ---
    outer_ring_outer_r = outermost_r
    outer_ring_inner_r = second_r
    if outer_chart is not None:
        _draw_house_ring(
            outer_chart, outer_ring_outer_r, outer_ring_inner_r,
            angle_color="#C9A66B", num_color="#8B87A8", num_fontsize=8,
            label_r=zodiac_outer_r + 0.08, label_fontsize=9,
        )

    # --- Inner house ring: innermost circle to second circle ---
    inner_ring_outer_r = second_r
    inner_ring_inner_r = innermost_r
    if inner_chart is not None and inner_has_houses:
        _draw_house_ring(
            inner_chart, inner_ring_outer_r, inner_ring_inner_r,
            angle_color="#7A3B3B", num_color="#A67878", num_fontsize=7,
            label_r=(inner_ring_outer_r + inner_ring_inner_r) / 2 - 0.02, label_fontsize=8,
        )

    # --- Second circle (shared boundary between the two rings) ---
    if outer_chart is not None:
        second_boundary_circle = plt.Circle(
            (0, 0), second_r, fill=False, color="#5A5470",
            linewidth=0.8, zorder=1,
        )
        ax.add_patch(second_boundary_circle)

    if outer_chart is None:
        ax.text(0, 0, "Houses unavailable\n(both birth times unknown)",
                ha="center", va="center", fontsize=11, color="#8B87A8")

    def _draw_planets(chart, r, face_color):
        plotted = []
        for name in list(PLANET_GLYPHS) + list(FALLBACK_LABELS):
            if name not in chart:
                continue
            point = chart[name]
            this_r = r
            for prior_lon in plotted:
                if abs(((point.longitude - prior_lon) + 180) % 360 - 180) < 6:
                    this_r += 0.045
            plotted.append(point.longitude)
            x, y = _to_xy(point.longitude, asc_lon, this_r)
            glyph = PLANET_GLYPHS.get(name, FALLBACK_LABELS.get(name, "?"))
            fontsize = 12 if name in PLANET_GLYPHS else 7
            ax.text(x, y, glyph, ha="center", va="center", fontsize=fontsize,
                    color="#EDE6D6", zorder=3,
                    bbox=dict(boxstyle="circle,pad=0.12", facecolor=face_color,
                               edgecolor="#EDE6D6", linewidth=0.5))
            if point.retrograde:
                ax.text(x + 0.04, y + 0.04, "℞", fontsize=6, color="#D1495B")

    # --- Person A's planets and Person B's planets, each within their
    #     own ring's radius band ---
    if outer_chart is chart_a:
        _draw_planets(chart_a, outer_ring_inner_r + (outer_ring_outer_r - outer_ring_inner_r) * 0.4, "#252B47")
        _draw_planets(chart_b, inner_ring_inner_r + (inner_ring_outer_r - inner_ring_inner_r) * 0.4, "#3D2828")
    else:
        _draw_planets(chart_b, outer_ring_inner_r + (outer_ring_outer_r - outer_ring_inner_r) * 0.4, "#3D2828")
        _draw_planets(chart_a, inner_ring_inner_r + (inner_ring_outer_r - inner_ring_inner_r) * 0.4, "#252B47")

    # --- Boundary circle framing the aspect-line hub — without this,
    #     the crisscrossing aspect lines sprawl unbounded across the
    #     whole canvas with no visual frame, which is what made the
    #     first version of this chart hard to read. Drawn at the same
    #     radius as the inner house ring's own inner edge, so the two
    #     read as one continuous boundary. Matches the same pattern
    #     draw_chart_wheel() already uses for its own aspect circle.
    aspect_hub_r = inner_ring_inner_r
    inner_circle = plt.Circle((0, 0), aspect_hub_r, fill=False, color="#5A5470", linewidth=0.8, zorder=1)
    ax.add_patch(inner_circle)

    # --- Cross-chart aspect lines ---
    a_planet_r = (outer_ring_inner_r + (outer_ring_outer_r - outer_ring_inner_r) * 0.4) if outer_chart is chart_a \
        else (inner_ring_inner_r + (inner_ring_outer_r - inner_ring_inner_r) * 0.4)
    b_planet_r = (inner_ring_inner_r + (inner_ring_outer_r - inner_ring_inner_r) * 0.4) if outer_chart is chart_a \
        else (outer_ring_inner_r + (outer_ring_outer_r - outer_ring_inner_r) * 0.4)
    for a in synastry_aspects:
        if a.tightness > min_aspect_tightness:
            continue
        if a.person_a_point not in chart_a or a.person_b_point not in chart_b:
            continue
        x1, y1 = _to_xy(chart_a[a.person_a_point].longitude, asc_lon, a_planet_r)
        x2, y2 = _to_xy(chart_b[a.person_b_point].longitude, asc_lon, b_planet_r)
        color = ASPECT_COLORS.get(a.aspect_name, "#5A5470")
        style = "--" if a.aspect_name in ("Sextile", "Trine") else "-"
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=0.9,
                linestyle=style, alpha=0.6, zorder=2)

    # --- Legend ---
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#252B47",
               markeredgecolor="#EDE6D6", markersize=11, label="Person A"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3D2828",
               markeredgecolor="#EDE6D6", markersize=11, label="Person B"),
        Line2D([0], [0], color="#C9A66B", linewidth=1.8, label="Outer ring angles"),
        Line2D([0], [0], color="#7A3B3B", linewidth=1.8, label="Inner ring angles"),
    ]
    ax.legend(handles=legend_elements, loc="upper right",
              bbox_to_anchor=(1.05, 1.05), frameon=False, fontsize=9,
              labelcolor="#EDE6D6")

    if outer_label and inner_has_houses:
        ax.set_title(f"Outer ring: Person {outer_label}'s houses  •  Inner ring: Person {inner_label}'s houses",
                     fontsize=9, color="#A8A3B8", pad=15)
    elif outer_label:
        ax.set_title(f"House ring shown: Person {outer_label}'s houses "
                      f"(Person {inner_label}'s birth time is unknown)",
                     fontsize=9, color="#A8A3B8", pad=15)


def draw_chart_wheel_art(
    chart: dict,
    aspects: list,
    person_name: str | None,
    datetime_str: str,
    location_str: str,
    format: str = "poster",
    min_aspect_tightness: float = 0.6,
):
    """
    Draws a standalone, presentation-quality version of the chart
    wheel meant to be downloaded and kept or shared, rather than the
    working reference view shown inline in the app. Adds a title
    block below the wheel (name, birth date/time, location, and a
    small brand line) and composes the whole figure at a size/aspect
    suited to the given format, rather than just being a bigger export
    of the inline wheel.

    format:
      "poster" - taller, portrait aspect ratio suited to printing.
                  Caller should save at dpi=300 for actual print use.
      "card"   - more compact, closer to square, suited to sharing on
                  a phone screen. dpi=150 is already plenty for that.

    Both formats reuse the exact same wheel-drawing logic as the
    inline chart (_draw_wheel_content) and the same indigo/brass
    palette as the rest of the app, so this feels like a piece of the
    product's own visual identity rather than a generic export.
    """
    asc_lon = chart["Ascendant"].longitude

    if format == "card":
        fig = plt.figure(figsize=(8, 9.5))
        wheel_ax = fig.add_axes([0.06, 0.22, 0.88, 0.74])
        text_y_start = 0.15
    else:
        fig = plt.figure(figsize=(8.5, 11))
        wheel_ax = fig.add_axes([0.08, 0.30, 0.84, 0.62])
        text_y_start = 0.20

    fig.patch.set_facecolor("#1B2036")
    wheel_ax.set_facecolor("#1B2036")
    wheel_ax.set_xlim(-1.35, 1.35)
    wheel_ax.set_ylim(-1.35, 1.35)
    wheel_ax.set_aspect("equal")
    wheel_ax.axis("off")

    _draw_wheel_content(wheel_ax, chart, aspects, min_aspect_tightness, asc_lon)

    # --- Title block ---
    title_ax = fig.add_axes([0, 0, 1, text_y_start])
    title_ax.set_facecolor("#1B2036")
    title_ax.axis("off")
    title_ax.set_xlim(0, 1)
    title_ax.set_ylim(0, 1)

    display_name = person_name.strip() if person_name and person_name.strip() else "Birth Chart"

    # A thin brass rule above the text block, echoing the same
    # wheel-fragment motif used for dividers elsewhere in the app --
    # ties this standalone export back to the rest of the product
    # rather than reading as a disconnected image.
    title_ax.plot([0.15, 0.85], [0.92, 0.92], color="#C9A66B", linewidth=0.8, alpha=0.6)

    title_ax.text(0.5, 0.68, display_name, ha="center", va="center",
                   fontsize=26, fontweight="bold", color="#EDE6D6",
                   family="serif")
    title_ax.text(0.5, 0.44, datetime_str, ha="center", va="center",
                   fontsize=13, color="#C9A66B")
    title_ax.text(0.5, 0.30, location_str, ha="center", va="center",
                   fontsize=13, color="#C9A66B")
    title_ax.text(0.5, 0.08, "TENTH HOUSE READINGS", ha="center", va="center",
                   fontsize=9, color="#5A5470", family="sans-serif")

    return fig


def draw_bi_wheel_art(
    chart_a: dict,
    chart_b: dict,
    synastry_aspects: list,
    person_a_name: str | None,
    person_b_name: str | None,
    datetime_str_a: str,
    datetime_str_b: str,
    format: str = "poster",
    min_aspect_tightness: float = 0.6,
):
    """
    Standalone, presentation-quality version of the synastry bi-wheel
    — same relationship to draw_bi_wheel that draw_chart_wheel_art has
    to draw_chart_wheel. Adds a title block with both people's names
    and birth dates, and composes the whole figure for printing
    ("poster") or sharing ("card") rather than the inline working view.
    """
    a_has_houses = "Ascendant" in chart_a and "House 1" in chart_a
    b_has_houses = "Ascendant" in chart_b and "House 1" in chart_b

    if a_has_houses:
        outer_chart, outer_label = chart_a, "A"
        inner_chart, inner_label, inner_has_houses = chart_b, "B", b_has_houses
        asc_lon = chart_a["Ascendant"].longitude
    elif b_has_houses:
        outer_chart, outer_label = chart_b, "B"
        inner_chart, inner_label, inner_has_houses = chart_a, "A", a_has_houses
        asc_lon = chart_b["Ascendant"].longitude
    else:
        outer_chart = inner_chart = None
        outer_label = inner_label = None
        inner_has_houses = False
        asc_lon = 0.0

    if format == "card":
        fig = plt.figure(figsize=(8.5, 10.5))
        wheel_ax = fig.add_axes([0.06, 0.24, 0.88, 0.72])
        text_y_start = 0.17
    else:
        fig = plt.figure(figsize=(9, 12))
        wheel_ax = fig.add_axes([0.08, 0.30, 0.84, 0.64])
        text_y_start = 0.22

    fig.patch.set_facecolor("#1B2036")
    wheel_ax.set_facecolor("#1B2036")
    wheel_ax.set_xlim(-1.5, 1.5)
    wheel_ax.set_ylim(-1.5, 1.5)
    wheel_ax.set_aspect("equal")
    wheel_ax.axis("off")

    _draw_bi_wheel_content(wheel_ax, chart_a, chart_b, synastry_aspects, min_aspect_tightness,
                            asc_lon, outer_chart, inner_chart, outer_label, inner_label,
                            inner_has_houses)

    # --- Title block ---
    title_ax = fig.add_axes([0, 0, 1, text_y_start])
    title_ax.set_facecolor("#1B2036")
    title_ax.axis("off")
    title_ax.set_xlim(0, 1)
    title_ax.set_ylim(0, 1)

    display_name_a = person_a_name.strip() if person_a_name and person_a_name.strip() else "Person A"
    display_name_b = person_b_name.strip() if person_b_name and person_b_name.strip() else "Person B"

    title_ax.plot([0.1, 0.9], [0.94, 0.94], color="#C9A66B", linewidth=0.8, alpha=0.6)

    title_ax.text(0.5, 0.76, f"{display_name_a} & {display_name_b}", ha="center", va="center",
                   fontsize=22, fontweight="bold", color="#EDE6D6", family="serif")
    title_ax.text(0.27, 0.52, display_name_a, ha="center", va="center",
                   fontsize=11, fontweight="bold", color="#C9A66B")
    title_ax.text(0.27, 0.40, datetime_str_a, ha="center", va="center",
                   fontsize=10, color="#A8A3B8")
    title_ax.text(0.73, 0.52, display_name_b, ha="center", va="center",
                   fontsize=11, fontweight="bold", color="#7A3B3B")
    title_ax.text(0.73, 0.40, datetime_str_b, ha="center", va="center",
                   fontsize=10, color="#A8A3B8")
    title_ax.text(0.5, 0.10, "TENTH HOUSE READINGS", ha="center", va="center",
                   fontsize=9, color="#5A5470", family="sans-serif")

    return fig
