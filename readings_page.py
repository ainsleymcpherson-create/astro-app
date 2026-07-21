"""
app.py

Streamlit frontend for the astrology chart engine. Lets you type in a
birth date/time and location, computes the full chart (points, aspects,
patterns, dignity, houses), and generates the LLM interpretation prompt.
Optionally generates the written reading live via the Claude API — this
is OFF by default and clearly labeled, since it makes a real, billed API
call each time it's used.

Run locally:
    streamlit run app.py

This same file is what you'd deploy to Streamlit Community Cloud later
for a public version — no code changes needed, just push this repo to
GitHub and point Streamlit Cloud at it.
"""

import os
import re
import io
from datetime import date as date_type, datetime, timezone
import streamlit as st
import pandas as pd
import swisseph as swe
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

# --- Ephemeris setup ---
# Points at a local ./ephe folder (relative to this file) rather than
# Colab's /content/ephe, since this now runs on your own machine.
# Run download_ephemeris.py once (see README) to populate this folder.
EPHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")
swe.set_ephe_path(EPHE_PATH)

from chart_points import compute_full_chart, extract_speeds
from aspect_engine import compute_aspects, find_all_patterns
from dignity import compute_chart_dignities
from house_interpretation import build_house_readings
from transit_engine import compute_transiting_points, assign_transit_houses, compute_transit_aspects
from synastry_engine import compute_full_synastry
from prompt_builder import (
    build_interpretation_prompt,
    build_interpretation_prompt_no_time,
    build_career_interpretation_prompt,
    build_career_interpretation_prompt_no_time,
    build_transit_prompt,
    build_professional_synastry_prompt,
)
from birth_input import resolve_birth_data
from chart_wheel import (
    draw_chart_wheel, draw_bi_wheel,
    build_chart_data_table_html, build_synastry_data_table_html,
    get_table_rows, get_synastry_table_rows,
)

# --- Session state persistence safeguard ---
# Streamlit's own docs say session state "persists across apps inside a
# multipage app," but there are real, sometimes still-open reports of
# state loss specifically during page switches via st.navigation/
# st.switch_page (see streamlit/streamlit#5689 and #11115). Re-touching
# every existing key on each run is the standard, low-risk workaround —
# it forces Streamlit to resend the current value to the frontend rather
# than risk it silently reverting on the next page visit. This is what
# keeps a computed chart (st.session_state.results) intact when you
# navigate to Resources and back, rather than losing it.
for _k in list(st.session_state.keys()):
    st.session_state[_k] = st.session_state[_k]


# --- Optional: live Claude interpretation ---
# Requires: pip install anthropic (already in requirements.txt)
# Requires an ANTHROPIC_API_KEY available either as:
#   - a Colab secret (accessed via google.colab.userdata), or
#   - an environment variable, for local/non-Colab runs
# IMPORTANT: the key is only ever READ from these two places. It is never
# hardcoded anywhere in this file, and should never be pasted directly
# into any file that gets committed to a public repo.
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def get_api_key():
    """Try Colab secrets first, then Streamlit Cloud's secrets manager,
    then fall back to a plain environment variable — so the same code
    works unchanged across Colab, Streamlit Community Cloud, and local
    runs."""
    try:
        from google.colab import userdata
        key = userdata.get("ANTHROPIC_API_KEY")
        if key:
            return key
    except Exception:
        pass
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY")


st.title("🔭 Tenth House Readings")
st.caption("Computes birth charts with full support for Part of Fortune, "
           "Nodes, Vertex, Chiron, dignity, and house-ruler interpretation "
           "of empty houses — not just the standard 10 planets.")

COFFEE_URL = "https://buymeacoffee.com/tenthhousereadings"

# Small floating top-right coffee button — always present regardless
# of page state (before or after a chart is computed). CSS position:fixed
# keeps it pinned to the same spot in the browser viewport regardless of
# scroll position or which tab is active.
st.markdown(
    f"""
    <style>
    .floating-coffee-btn {{
        position: fixed;
        top: 65px;
        right: 20px;
        z-index: 9999;
        background-color: #FFDD00;
        color: #000000 !important;
        padding: 6px 12px;
        border-radius: 6px;
        text-decoration: none !important;
        font-weight: 600;
        font-size: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    .floating-coffee-btn:hover {{
        background-color: #FFCC00;
        transform: translateY(-2px);
        box-shadow: 0 3px 10px rgba(0,0,0,0.35);
    }}
    </style>
    <a href="{COFFEE_URL}" target="_blank" class="floating-coffee-btn">☕ Buy me a coffee</a>
    """,
    unsafe_allow_html=True,
)

# --- Input form ---
reading_type = st.selectbox(
    "Reading focus",
    options=["General", "Career / Work", "Transits", "Professional Synastry"],
    index=0,
    help="General covers the whole chart. Career/Work focuses "
         "specifically on workplace happiness, colleague dynamics, "
         "work style, and professional strengths/weaknesses. Transits "
         "answers 'what's happening right now' — how today's sky is "
         "currently interacting with this natal chart. Professional "
         "Synastry compares TWO people's charts to analyze their working "
         "dynamic — not romantic compatibility.",
)

# Read the checkbox's stored value BEFORE the checkbox widget itself is
# defined further down (it's rendered after the birth time fields, to
# match the requested layout). This works because Streamlit updates a
# keyed widget's session_state value as soon as it changes, before the
# script reruns from the top — so this early read always reflects the
# current, live value despite reading it "ahead of" where the widget
# actually appears on the page.
unknown_time = (
    st.session_state.get("unknown_time_cb", False)
    if reading_type != "Transits" else False
)

if reading_type == "Professional Synastry":
    st.subheader("Person A")

person_name = st.text_input(
    "Name (optional)",
    value="",
    help="If provided, the reading will address this person by name "
         "occasionally instead of only using \"you\" throughout.",
    key="person_name_a",
)

col1, col2, col3 = st.columns([1, 1.3, 1])
with col1:
    birth_date = st.date_input(
        "Birth date",
        value=date_type(1981, 12, 24),
        min_value=date_type(1900, 1, 1),
        max_value=date_type.today(),
        help="Tap to open the calendar picker.",
    )
with col2:
    st.write("Birth time" + (" (disabled — unknown birth time selected)" if unknown_time else ""))
    hour_col, minute_col, ampm_col = st.columns(3)
    with hour_col:
        birth_hour = st.selectbox(
            "Hour", options=list(range(1, 13)), index=0,
            label_visibility="collapsed", disabled=unknown_time,
        )
    with minute_col:
        birth_minute = st.selectbox(
            "Minute", options=[f"{m:02d}" for m in range(60)], index=30,
            label_visibility="collapsed", disabled=unknown_time,
        )
    with ampm_col:
        birth_ampm = st.selectbox(
            "AM/PM", options=["AM", "PM"], index=1,
            label_visibility="collapsed", disabled=unknown_time,
        )
with col3:
    location_str = st.text_input(
        "Birth location",
        value="Brooklyn, New York, USA",
        help="Be specific — add state/country if the place name is common",
    )

align_col1, align_col2, align_col3 = st.columns([1, 1.3, 1])
with align_col2:
    if reading_type != "Transits":
        unknown_time = st.checkbox(
            "🕐 I don't know my exact birth time",
            value=False,
            key="unknown_time_cb",
            help="The Ascendant, Midheaven, house placements, Vertex, and Part "
                 "of Fortune/Spirit all require an exact birth time to "
                 "calculate correctly — a noon guess doesn't approximate them, "
                 "it effectively randomizes them (the Ascendant alone shifts "
                 "about 1° every 4 minutes). Checking this excludes all of "
                 "those and works only with what's reliable regardless of "
                 "time: the planets, Chiron, the Nodes, and aspects between "
                 "them. Works for General and Career/Work readings. The birth "
                 "time fields above are disabled while this is checked, since "
                 "they won't be used.",
        )
    else:
        unknown_time = False  # not applicable to Transits

# --- Person B (Professional Synastry only) ---
if reading_type == "Professional Synastry":
    st.divider()
    st.subheader("Person B")

    person_name_b = st.text_input(
        "Name (optional)",
        value="",
        help="If provided, the reading will use this name instead of "
             "\"Person B\" throughout.",
        key="person_name_b",
    )

    unknown_time_b = st.session_state.get("unknown_time_cb_b", False)

    colb1, colb2, colb3 = st.columns([1, 1.3, 1])
    with colb1:
        birth_date_b = st.date_input(
            "Birth date",
            value=date_type(1989, 7, 5),
            min_value=date_type(1900, 1, 1),
            max_value=date_type.today(),
            help="Tap to open the calendar picker.",
            key="birth_date_b",
        )
    with colb2:
        st.write("Birth time" + (" (disabled — unknown birth time selected)" if unknown_time_b else ""))
        hour_col_b, minute_col_b, ampm_col_b = st.columns(3)
        with hour_col_b:
            birth_hour_b = st.selectbox(
                "Hour", options=list(range(1, 13)), index=0,
                label_visibility="collapsed", disabled=unknown_time_b,
                key="birth_hour_b",
            )
        with minute_col_b:
            birth_minute_b = st.selectbox(
                "Minute", options=[f"{m:02d}" for m in range(60)], index=30,
                label_visibility="collapsed", disabled=unknown_time_b,
                key="birth_minute_b",
            )
        with ampm_col_b:
            birth_ampm_b = st.selectbox(
                "AM/PM", options=["AM", "PM"], index=1,
                label_visibility="collapsed", disabled=unknown_time_b,
                key="birth_ampm_b",
            )
    with colb3:
        location_str_b = st.text_input(
            "Birth location",
            value="Washington, D.C., USA",
            help="Be specific — add state/country if the place name is common",
            key="location_str_b",
        )

    align_colb1, align_colb2, align_colb3 = st.columns([1, 1.3, 1])
    with align_colb2:
        unknown_time_b = st.checkbox(
            "🕐 I don't know Person B's exact birth time",
            value=False,
            key="unknown_time_cb_b",
            help="Same effect as the Person A checkbox above — excludes "
                 "Person B's Ascendant, houses, Vertex, and Arabic Parts, "
                 "keeping only their planets, Chiron, Nodes, and aspects. "
                 "Note: if Person B's time is unknown, house-overlay analysis "
                 "involving Person B's houses isn't possible (Person A's "
                 "planets in Person B's houses), but overlays in the other "
                 "direction still work fine if Person A's time is known.",
        )
else:
    # Placeholders so these variables always exist, even for reading
    # types that don't use a second person.
    birth_date_b = birth_hour_b = birth_minute_b = birth_ampm_b = None
    location_str_b = None
    person_name_b = None
    unknown_time_b = False

house_system_label = st.selectbox(
    "House system",
    options=["Placidus", "Whole Sign", "Equal", "Koch", "Campanus", "Regiomontanus", "Alcabitius"],
    index=0,
)
house_system_map = {
    "Placidus": b"P", "Whole Sign": b"W", "Equal": b"E", "Koch": b"K",
    "Campanus": b"C", "Regiomontanus": b"R", "Alcabitius": b"B",
}

if reading_type == "Transits":
    transit_date = st.date_input(
        "Transit date",
        value=date_type.today(),
        help="The date to check transits for — defaults to today.",
    )
else:
    transit_date = date_type.today()  # unused placeholder for non-Transit readings

generate_live = st.checkbox(
    "🪙 Generate written interpretation with Claude (makes a real, billed API call)",
    value=False,
    help="Unchecked (default): you get the raw prompt to copy/paste into "
         "Claude yourself, for free. Checked: this app calls the Claude "
         "API directly and you're charged for that usage, every time "
         "you click Compute Chart with this box checked.",
)

submitted = st.button(
    "Compute Chart", use_container_width=True,
    disabled=st.session_state.get("processing", False),
)


def points_to_dataframe(chart):
    rows = []
    for name, point in sorted(chart.items(), key=lambda x: x[1].longitude):
        if name.startswith("House "):
            continue
        rows.append({
            "Point": name,
            "Sign": point.sign,
            "Degree": f"{point.sign_degree:.2f}°",
            "House": str(point.house) if point.house else "—",
            "Retrograde": "R" if point.retrograde else "",
        })
    return pd.DataFrame(rows)


def aspects_to_dataframe(aspects):
    rows = []
    for a in aspects:
        motion = ""
        if a.applying is True:
            motion = "applying"
        elif a.applying is False:
            motion = "separating"
        rows.append({
            "Point 1": a.point1,
            "Aspect": a.aspect_name,
            "Point 2": a.point2,
            "Orb": f"{a.orb:.2f}°",
            "Motion": motion,
            "Nature": a.nature,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Point 1", kind="stable").reset_index(drop=True)
    return df


def synastry_aspects_to_dataframe(synastry_aspects):
    rows = []
    for a in synastry_aspects:
        rows.append({
            "Person A's Point": a.person_a_point,
            "Aspect": a.aspect_name,
            "Person B's Point": a.person_b_point,
            "Orb": f"{a.orb:.2f}°",
            "Nature": a.nature,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Person A's Point", kind="stable").reset_index(drop=True)
    return df


def dignities_to_dataframe(dignities):
    rows = []
    for planet, d in dignities.items():
        rows.append({
            "Planet": planet,
            "Sign": d.sign,
            "Status": d.status,
            "Score": d.score,
        })
    return pd.DataFrame(rows)


def markdown_to_pdf_bytes(markdown_text: str, title: str) -> bytes:
    """
    Converts the simple markdown structure our readings use (## headers,
    **bold** inline, plain paragraphs) into a nicely formatted PDF —
    real headers and bold text instead of raw ## and ** symbols. Doesn't
    need a full markdown library since our reading format is
    intentionally simple and predictable. Uses reportlab, which is pure
    Python with no system-level dependencies (unlike some PDF libraries),
    so it won't risk the kind of compiled-dependency build failures we
    hit with pyswisseph on Streamlit Cloud.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReadingTitle", parent=styles["Title"], spaceAfter=16,
    )
    heading_style = ParagraphStyle(
        "ReadingHeading", parent=styles["Heading2"],
        spaceBefore=16, spaceAfter=8, textColor=colors.HexColor("#2c3e50"),
    )
    body_style = ParagraphStyle(
        "ReadingBody", parent=styles["Normal"], spaceAfter=10, leading=15,
    )

    story = [Paragraph(title, title_style), Spacer(1, 12)]

    def inline_format(text: str) -> str:
        # Escape XML-special characters first (reportlab's Paragraph
        # parses a small XML-like markup), then convert markdown bold
        # syntax into reportlab's own <b> tag.
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        return text

    for raw_line in markdown_text.split("\n"):
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 6))
            continue
        if line.startswith("## "):
            story.append(Paragraph(inline_format(line[3:]), heading_style))
        elif line.startswith("### "):
            story.append(Paragraph(inline_format(line[4:]), heading_style))
        else:
            story.append(Paragraph(inline_format(line), body_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def render_interpretation(text: str):
    """
    Renders an AI-generated reading with each section's 'Astrological
    Basis' part collapsed into an expander — the plain-language
    interpretation stays visible by default, and the technical detail
    (planet placements, aspect names, dignity terms) is available on
    tap for readers who want it, without cluttering the main view for
    readers who don't. Falls back to plain rendering if the text
    doesn't match the expected section structure (e.g. if the LLM
    didn't follow the formatting instructions exactly).
    """
    section_pattern = re.compile(r"(?m)^## (.+)$")
    matches = list(section_pattern.finditer(text))

    if not matches:
        st.markdown(text)
        return

    if matches[0].start() > 0:
        st.markdown(text[:matches[0].start()].strip())

    basis_pattern = re.compile(r"\*\*Astrological Basis:?\*\*", re.IGNORECASE)

    for i, match in enumerate(matches):
        header = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        st.markdown(f"### {header}")

        basis_match = basis_pattern.search(body)
        if basis_match:
            before_basis = body[:basis_match.start()].strip()
            basis_content = body[basis_match.end():].strip()
            if before_basis:
                st.markdown(before_basis)
            with st.expander("📐 Astrological Basis (tap to expand)"):
                st.markdown(basis_content)
        else:
            # Overview, Conclusion, or any section that didn't include
            # a basis split — just render the whole thing normally.
            st.markdown(body)


def dataframe_download_and_copy(df: pd.DataFrame, filename: str, key_prefix: str):
    """Adds a CSV download button and a copy-friendly text area below a
    dataframe. key_prefix keeps widget keys unique across tabs, since
    Streamlit requires unique keys for repeated widgets on one page."""
    csv_data = df.to_csv(index=False)
    st.download_button(
        f"Download as .csv",
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
        key=f"{key_prefix}_download",
    )
    with st.expander("Copy as plain text"):
        st.text_area(
            "Data (tap inside, select all, copy)",
            value=csv_data,
            height=300,
            label_visibility="collapsed",
            key=f"{key_prefix}_copy",
        )


def text_download_and_copy(text: str, filename: str, key_prefix: str):
    """Adds a .txt download button and a copy-friendly text area below
    any plain-text tab content."""
    st.download_button(
        "Download as .txt",
        data=text,
        file_name=filename,
        mime="text/plain",
        use_container_width=True,
        key=f"{key_prefix}_download",
    )
    with st.expander("Copy as plain text"):
        st.text_area(
            "Content (tap inside, select all, copy)",
            value=text,
            height=300,
            label_visibility="collapsed",
            key=f"{key_prefix}_copy",
        )


if submitted:
    # Two-phase pattern: set processing=True and rerun IMMEDIATELY,
    # before doing any actual work. This lets the "Compute Chart"
    # button (which reads st.session_state.processing to decide its
    # disabled state) actually render as grayed-out on the very next
    # frame — a button can't disable itself retroactively within the
    # same run it was clicked in, since Streamlit renders top-to-bottom
    # in one pass per run.
    st.session_state.processing = True
    st.rerun()

if st.session_state.get("processing", False):
    try:
        st.caption(f"🐛 Debug: generate_live={generate_live}, "
                   f"ANTHROPIC_AVAILABLE={ANTHROPIC_AVAILABLE}, "
                   f"api_key_found={bool(get_api_key())}")

        # Combine the two separate picker widgets into the plain-language
        # string resolve_birth_data() expects (e.g. "December 24, 1981
        # 01:30 PM") — keeps birth_input.py's parsing logic unchanged.
        datetime_str = f"{birth_date.strftime('%B %d, %Y')} {birth_hour:02d}:{birth_minute} {birth_ampm}"

        with st.spinner("Resolving location and timezone..."):
            birth = resolve_birth_data(datetime_str, location_str, verbose=False)

        house_system = house_system_map[house_system_label]

        with st.spinner("Computing chart..."):
            chart = compute_full_chart(birth, house_system=house_system)
            aspects = compute_aspects(chart, speeds=extract_speeds(chart))
            patterns = find_all_patterns(chart, aspects)
            dignities = compute_chart_dignities(chart)
            house_readings = build_house_readings(chart)

            # Placeholders so these always exist, even for reading types
            # that don't use a second person.
            chart_b = aspects_b = patterns_b = dignities_b = house_readings_b = None
            synastry_result = None

            if reading_type == "Transits":
                with st.spinner("Computing current transits..."):
                    # Transits are read for a specific moment; noon UTC on
                    # the chosen date is a reasonable default (matches
                    # standard daily-ephemeris convention). Faster points
                    # like the Moon can shift within a day, but this is
                    # fine for a "what's the current climate" reading.
                    transit_dt_utc = datetime(
                        transit_date.year, transit_date.month, transit_date.day,
                        12, 0, 0, tzinfo=timezone.utc,
                    )
                    transiting_points = compute_transiting_points(transit_dt_utc)

                    # Map transiting planets onto this person's NATAL
                    # houses (transits are read against natal houses, not
                    # a fresh chart for the transit moment).
                    natal_house_cusps = [
                        chart[f"House {i}"] for i in range(1, 13)
                    ]
                    assign_transit_houses(transiting_points, natal_house_cusps)

                    transit_aspects = compute_transit_aspects(
                        chart, transiting_points,
                        transiting_speeds=extract_speeds(transiting_points),
                    )
                    prompt = build_transit_prompt(transiting_points, transit_aspects, dignities, person_name=person_name)
            elif reading_type == "Professional Synastry":
                with st.spinner("Resolving Person B's location and computing their chart..."):
                    datetime_str_b = f"{birth_date_b.strftime('%B %d, %Y')} {birth_hour_b:02d}:{birth_minute_b} {birth_ampm_b}"
                    birth_b = resolve_birth_data(datetime_str_b, location_str_b, verbose=False)
                    chart_b = compute_full_chart(birth_b, house_system=house_system)
                    aspects_b = compute_aspects(chart_b, speeds=extract_speeds(chart_b))
                    patterns_b = find_all_patterns(chart_b, aspects_b)
                    dignities_b = compute_chart_dignities(chart_b)
                    house_readings_b = build_house_readings(chart_b)

                with st.spinner("Computing synastry between the two charts..."):
                    synastry_result = compute_full_synastry(
                        chart, chart_b,
                        person_a_time_known=not unknown_time,
                        person_b_time_known=not unknown_time_b,
                    )
                    prompt = build_professional_synastry_prompt(
                        synastry_result, dignities, dignities_b,
                        person_a_name=person_name, person_b_name=person_name_b,
                    )
            elif reading_type == "Career / Work" and unknown_time:
                prompt = build_career_interpretation_prompt_no_time(
                    chart, aspects, patterns, dignities, person_name=person_name,
                )
            elif reading_type == "Career / Work":
                prompt = build_career_interpretation_prompt(chart, aspects, patterns, dignities, house_readings, person_name=person_name)
            elif unknown_time:
                prompt = build_interpretation_prompt_no_time(chart, aspects, patterns, dignities, person_name=person_name)
            else:
                prompt = build_interpretation_prompt(chart, aspects, patterns, dignities, house_readings, person_name=person_name)

        interpretation_text = None
        interpretation_error = None

        if generate_live:
            if not ANTHROPIC_AVAILABLE:
                interpretation_error = (
                    "The `anthropic` package isn't installed. Run "
                    "`pip install anthropic` and restart the app."
                )
            else:
                api_key = get_api_key()
                if not api_key:
                    interpretation_error = (
                        "No API key found. Add ANTHROPIC_API_KEY as a Colab "
                        "secret, or set it as an environment variable. The "
                        "prompt below is still available to copy manually."
                    )
                else:
                    try:
                        client = anthropic.Anthropic(api_key=api_key)
                        with st.spinner("Generating interpretation with Claude "
                                         "(this makes a billed API call — may take "
                                         "a couple minutes for a full reading). "
                                         "Keep this tab open and in the foreground "
                                         "until it finishes."):
                            # Streaming is required here rather than a plain
                            # blocking call: with max_tokens this high, the
                            # SDK estimates generation could exceed its
                            # 10-minute non-streaming timeout and refuses to
                            # run without it.
                            #
                            # IMPORTANT: we iterate the RAW stream events
                            # (not just stream.text_stream) so we can show
                            # live progress during BOTH phases of
                            # generation — this model does a lot of internal
                            # "thinking" before writing any visible text,
                            # and stream.text_stream only yields the text
                            # portion, leaving the thinking phase completely
                            # silent. A long silent gap either way is what
                            # can get killed by an infrastructure-level
                            # idle-connection timeout — tearing down this
                            # whole script AFTER Claude has already
                            # generated (and billed) the tokens, but BEFORE
                            # we ever get to save or show the result. That
                            # was the actual cause of "the API runs but
                            # returns nothing."
                            live_preview = st.empty()
                            accumulated_text = ""
                            thinking_chars = 0
                            update_counter = 0
                            with client.messages.stream(
                                model="claude-sonnet-5",
                                max_tokens=32000,
                                messages=[{"role": "user", "content": prompt}],
                            ) as stream:
                                for event in stream:
                                    if event.type != "content_block_delta":
                                        continue
                                    delta_type = getattr(event.delta, "type", None)
                                    update_counter += 1
                                    if delta_type == "thinking_delta":
                                        thinking_chars += len(event.delta.thinking)
                                        if update_counter % 5 == 0:
                                            live_preview.markdown(
                                                f"🤔 *Thinking through the chart... "
                                                f"({thinking_chars} characters of "
                                                f"reasoning so far — this part "
                                                f"doesn't show in the final reading, "
                                                f"it's just to confirm this is "
                                                f"actively working.)*"
                                            )
                                    elif delta_type == "text_delta":
                                        accumulated_text += event.delta.text
                                        if update_counter % 3 == 0:
                                            live_preview.markdown(accumulated_text + " ▌")
                                live_preview.markdown(accumulated_text)
                                response = stream.get_final_message()

                        result_text = accumulated_text
                        stop_reason = getattr(response, "stop_reason", "unknown")

                        if result_text and stop_reason == "max_tokens":
                            # There IS text, but the response was cut
                            # off mid-generation before finishing — show
                            # it with a clear warning rather than
                            # silently presenting partial content as if
                            # it were the complete reading.
                            interpretation_text = (
                                result_text +
                                "\n\n---\n\n⚠️ **This response was cut off before finishing** "
                                "(hit the token limit). What's above may be incomplete — "
                                "increase max_tokens in app.py if this keeps happening."
                            )
                        elif result_text:
                            interpretation_text = result_text
                        else:
                            # The call succeeded but returned no usable
                            # text — surface this as an error rather
                            # than silently falling back to the generic
                            # "check the box" message, which would hide
                            # a real problem. Summarize block types/sizes
                            # instead of dumping raw content, since a
                            # thinking block's signature can be tens of
                            # thousands of characters of base64 — useless
                            # for debugging and unreadable in the UI.
                            block_summary = ", ".join(
                                f"{getattr(b, 'type', 'unknown')} "
                                f"({len(getattr(b, 'thinking', '') or getattr(b, 'text', '') or '')} chars)"
                                for b in response.content
                            )
                            interpretation_error = (
                                f"Claude ran out of room before writing the answer "
                                f"(stop_reason: {stop_reason}). This model spent its "
                                f"whole token budget on internal reasoning first. "
                                f"Content blocks received: {block_summary}. "
                                f"Try increasing max_tokens further in app.py if this "
                                f"keeps happening."
                            )
                        # Clear the raw live-typing preview now that the
                        # final, nicely-formatted version will render below
                        # via the normal results display.
                        live_preview.empty()
                    except Exception as e:
                        import traceback
                        interpretation_error = (
                            f"Claude API call failed: {type(e).__name__}: {e}\n\n"
                            f"Full traceback:\n{traceback.format_exc()}"
                        )

        # Persist everything needed for display in st.session_state.
        # Streamlit reruns the ENTIRE script on every widget interaction —
        # including clicking a download button — and `submitted` is only
        # True on the exact run where "Compute Chart" was clicked. Without
        # this, clicking any download button would make all the results
        # disappear on the next rerun, since the display code below would
        # no longer be reachable.
        st.session_state.results = {
            "datetime_str": datetime_str,
            "location_str": location_str,
            "house_system_label": house_system_label,
            "reading_type": reading_type,
            "birth_date": birth_date,
            "transit_date": transit_date,
            "person_name": person_name,
            "person_name_b": person_name_b if reading_type == "Professional Synastry" else None,
            "datetime_str_b": datetime_str_b if reading_type == "Professional Synastry" else None,
            "location_str_b": location_str_b if reading_type == "Professional Synastry" else None,
            "chart": chart,
            "aspects": aspects,
            "patterns": patterns,
            "dignities": dignities,
            "house_readings": house_readings,
            "chart_b": chart_b,
            "aspects_b": aspects_b,
            "patterns_b": patterns_b,
            "dignities_b": dignities_b,
            "house_readings_b": house_readings_b,
            "synastry_result": synastry_result,
            "prompt": prompt,
            "interpretation_text": interpretation_text,
            "interpretation_error": interpretation_error,
        }

    except ValueError as e:
        st.error(f"Couldn't resolve birth data: {e}")
    except Exception as e:
        st.error(f"Something went wrong: {e}")
        st.exception(e)

    # Processing is done (successfully or not) — reset the flag and do
    # one final rerun so the "Compute Chart" button re-renders as
    # enabled again, and the results display block below picks up
    # whatever landed in st.session_state.results.
    st.session_state.processing = False
    st.rerun()


# --- Display results ---
# Runs on every script rerun where results exist in session_state — not
# just the run where the form was submitted — so the tabs (and their
# download/copy buttons) stay visible across reruns instead of vanishing.
if st.session_state.get("results"):
    r = st.session_state.results

    label_a = r["person_name"].strip() if r["person_name"] and r["person_name"].strip() else None
    label_b = r["person_name_b"].strip() if r.get("person_name_b") and r["person_name_b"].strip() else None

    if r["reading_type"] == "Transits":
        who = label_a if label_a else r['datetime_str']
        st.success(
            f"Natal chart: {who} in {r['location_str']} "
            f"({r['house_system_label']} houses) — Transits for {r['transit_date'].isoformat()}"
        )
    elif r["reading_type"] == "Professional Synastry":
        who_a = label_a if label_a else f"Person A ({r['datetime_str']})"
        who_b = label_b if label_b else f"Person B ({r['datetime_str_b']})"
        st.success(
            f"{who_a} in {r['location_str']} — "
            f"{who_b} in {r['location_str_b']} "
            f"({r['house_system_label']} houses)"
        )
    else:
        who = label_a if label_a else r['datetime_str']
        st.success(
            f"Chart computed for {who} in {r['location_str']} "
            f"({r['house_system_label']} houses, {r['reading_type']} reading)"
        )

    tabs = st.tabs(["Interpretation", "Prompt", "Chart Wheel", "Points", "Aspects", "Patterns", "Dignity", "Houses"])

    with tabs[0]:
        if r["interpretation_text"]:
            render_interpretation(r["interpretation_text"])
            st.divider()

            if r["reading_type"] == "Professional Synastry":
                title_who = f"{label_a or 'Person A'} & {label_b or 'Person B'}"
            else:
                title_who = label_a if label_a else r['datetime_str']
            pdf_title = f"{r['reading_type']} Reading — {title_who}"
            pdf_bytes = markdown_to_pdf_bytes(r["interpretation_text"], pdf_title)

            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                st.download_button(
                    "📄 Download as .pdf",
                    data=pdf_bytes,
                    file_name=f"reading_{r['birth_date'].isoformat()}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            with dl_col2:
                st.download_button(
                    "Download as .txt",
                    data=r["interpretation_text"],
                    file_name=f"reading_{r['birth_date'].isoformat()}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with st.expander("Copy as plain text"):
                st.text_area(
                    "Reading (tap inside, select all, copy)",
                    value=r["interpretation_text"],
                    height=400,
                    label_visibility="collapsed",
                )
        elif r["interpretation_error"]:
            st.warning("Something went wrong generating the live interpretation:")
            st.code(r["interpretation_error"])
        else:
            st.info("Check the \"Generate written interpretation\" box above "
                     "and recompute to get a live reading here — or use the "
                     "Prompt tab to copy it into Claude yourself for free.")

    with tabs[1]:
        st.write("Copy this into Claude.ai (or send it via the API yourself) "
                 "to get the full written reading — free, no API call from this app.")
        st.text_area("Full prompt", value=r["prompt"], height=500, label_visibility="collapsed")
        st.download_button(
            "Download prompt as .txt",
            data=r["prompt"],
            file_name="interpretation_prompt.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with tabs[2]:
        def show_wheel_with_download(fig, filename_suffix):
            st.pyplot(fig, use_container_width=True)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=150, facecolor="white", bbox_inches="tight")
            st.download_button(
                "Download chart wheel as .png",
                data=buf.getvalue(),
                file_name=f"chart_wheel_{filename_suffix}_{r['birth_date'].isoformat()}.png",
                mime="image/png",
                use_container_width=True,
                key=f"wheel_dl_{filename_suffix}",
            )

        if r["reading_type"] == "Professional Synastry":
            label_a = r["person_name"] or "Person A"
            label_b = r["person_name_b"] or "Person B"

            st.subheader("Synastry Bi-Wheel")
            st.write(f"{label_a}'s planets on the inner ring, {label_b}'s planets "
                     "on the outer ring (shaded background), both measured "
                     "against the same house reference frame so their positions "
                     "are directly comparable. Lines connect the tightest "
                     "cross-chart aspects between the two.")
            fig_bi = draw_bi_wheel(
                r["chart"], r["chart_b"], r["synastry_result"]["aspects"],
                min_aspect_tightness=0.6,
            )
            show_wheel_with_download(fig_bi, "synastry")
            st.markdown(build_synastry_data_table_html(r["chart"], r["chart_b"]), unsafe_allow_html=True)
            synastry_table_df = pd.DataFrame(get_synastry_table_rows(r["chart"], r["chart_b"]))
            dataframe_download_and_copy(
                synastry_table_df, f"synastry_table_{r['birth_date'].isoformat()}.csv", "synastry_table"
            )

            st.divider()
            st.subheader(f"{label_a}'s Chart")
            fig_a = draw_chart_wheel(r["chart"], r["aspects"], min_aspect_tightness=0.6)
            show_wheel_with_download(fig_a, "person_a")
            st.markdown(build_chart_data_table_html(r["chart"]), unsafe_allow_html=True)
            table_df_a = pd.DataFrame(get_table_rows(r["chart"]))
            dataframe_download_and_copy(
                table_df_a, f"table_a_{r['birth_date'].isoformat()}.csv", "table_a"
            )

            st.divider()
            st.subheader(f"{label_b}'s Chart")
            fig_b = draw_chart_wheel(r["chart_b"], r["aspects_b"], min_aspect_tightness=0.6)
            show_wheel_with_download(fig_b, "person_b")
            st.markdown(build_chart_data_table_html(r["chart_b"]), unsafe_allow_html=True)
            table_df_b = pd.DataFrame(get_table_rows(r["chart_b"]))
            dataframe_download_and_copy(
                table_df_b, f"table_b_{r['birth_date'].isoformat()}.csv", "table_b"
            )
        else:
            st.write("The classic circular chart wheel — zodiac ring, house divisions "
                     "(drawn from the actual computed cusps, not evenly spaced), the "
                     "four angles, planets, and the tightest aspects.")
            fig = draw_chart_wheel(r["chart"], r["aspects"], min_aspect_tightness=0.6)
            show_wheel_with_download(fig, "chart")
            st.markdown(build_chart_data_table_html(r["chart"]), unsafe_allow_html=True)
            table_df = pd.DataFrame(get_table_rows(r["chart"]))
            dataframe_download_and_copy(
                table_df, f"table_{r['birth_date'].isoformat()}.csv", "table"
            )

    with tabs[3]:
        if r["reading_type"] == "Professional Synastry":
            st.subheader("Person A")
            points_df_a = points_to_dataframe(r["chart"])
            st.dataframe(points_df_a, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(points_df_a, f"points_a_{r['birth_date'].isoformat()}.csv", "points_a")

            st.subheader("Person B")
            points_df_b = points_to_dataframe(r["chart_b"])
            st.dataframe(points_df_b, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(points_df_b, f"points_b_{r['birth_date'].isoformat()}.csv", "points_b")
        else:
            points_df = points_to_dataframe(r["chart"])
            st.dataframe(points_df, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(points_df, f"points_{r['birth_date'].isoformat()}.csv", "points")

    with tabs[4]:
        if r["reading_type"] == "Professional Synastry":
            st.write("**Cross-chart aspects** — Person A's point to Person B's point. "
                     "This is the actual synastry data the reading is built from.")
            synastry_aspects_df = synastry_aspects_to_dataframe(r["synastry_result"]["aspects"])
            st.dataframe(synastry_aspects_df, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(
                synastry_aspects_df, f"synastry_aspects_{r['birth_date'].isoformat()}.csv", "synastry_aspects"
            )

            st.subheader("Person A's own aspects (within their own chart)")
            aspects_df_a = aspects_to_dataframe(r["aspects"])
            st.dataframe(aspects_df_a, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(aspects_df_a, f"aspects_a_{r['birth_date'].isoformat()}.csv", "aspects_a")

            st.subheader("Person B's own aspects (within their own chart)")
            aspects_df_b = aspects_to_dataframe(r["aspects_b"])
            st.dataframe(aspects_df_b, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(aspects_df_b, f"aspects_b_{r['birth_date'].isoformat()}.csv", "aspects_b")
        else:
            aspects_df = aspects_to_dataframe(r["aspects"])
            st.dataframe(aspects_df, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(aspects_df, f"aspects_{r['birth_date'].isoformat()}.csv", "aspects")

    with tabs[5]:
        def render_patterns_section(patterns, key_prefix, filename):
            any_patterns = False
            pattern_lines = []
            for kind, plist in patterns.items():
                if not plist:
                    continue
                any_patterns = True
                label = kind.replace("_", " ").title()
                st.subheader(label)
                pattern_lines.append(f"{label}:")
                for p in plist:
                    line = ", ".join(p.points)
                    st.write(f"- {line}")
                    pattern_lines.append(f"  - {line}")
            if not any_patterns:
                st.info("No aspect patterns detected within the configured orbs.")
            else:
                text_download_and_copy("\n".join(pattern_lines), filename, key_prefix)

        if r["reading_type"] == "Professional Synastry":
            st.subheader("Person A's Patterns")
            render_patterns_section(r["patterns"], "patterns_a", f"patterns_a_{r['birth_date'].isoformat()}.txt")
            st.divider()
            st.subheader("Person B's Patterns")
            render_patterns_section(r["patterns_b"], "patterns_b", f"patterns_b_{r['birth_date'].isoformat()}.txt")
        else:
            render_patterns_section(r["patterns"], "patterns", f"patterns_{r['birth_date'].isoformat()}.txt")

    with tabs[6]:
        if r["reading_type"] == "Professional Synastry":
            st.subheader("Person A")
            dignity_df_a = dignities_to_dataframe(r["dignities"])
            st.dataframe(dignity_df_a, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(dignity_df_a, f"dignity_a_{r['birth_date'].isoformat()}.csv", "dignity_a")

            st.subheader("Person B")
            dignity_df_b = dignities_to_dataframe(r["dignities_b"])
            st.dataframe(dignity_df_b, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(dignity_df_b, f"dignity_b_{r['birth_date'].isoformat()}.csv", "dignity_b")
        else:
            dignity_df = dignities_to_dataframe(r["dignities"])
            st.dataframe(dignity_df, use_container_width=True, hide_index=True)
            dataframe_download_and_copy(dignity_df, f"dignity_{r['birth_date'].isoformat()}.csv", "dignity")

    with tabs[7]:
        def render_house_readings_section(house_readings, key_prefix, filename):
            house_lines = []
            for num, reading in house_readings.items():
                with st.expander(f"House {num} ({reading.sign_on_cusp})"):
                    st.write(reading.interpretation)
                house_lines.append(f"House {num} ({reading.sign_on_cusp}):\n{reading.interpretation}\n")
            text_download_and_copy("\n".join(house_lines), filename, key_prefix)

        if r["reading_type"] == "Professional Synastry":
            st.write("**House overlays** — whose planets fall in whose houses. "
                     "Only available in a direction where the house-owning "
                     "person's birth time is known.")

            overlay_a_in_b = r["synastry_result"]["overlay_a_in_b"]
            overlay_b_in_a = r["synastry_result"]["overlay_b_in_a"]

            st.subheader("Person A's planets in Person B's houses")
            if not overlay_a_in_b:
                st.info("Not available — Person B's birth time is unknown.")
            else:
                for o in overlay_a_in_b:
                    st.write(f"- {o}")

            st.subheader("Person B's planets in Person A's houses")
            if not overlay_b_in_a:
                st.info("Not available — Person A's birth time is unknown.")
            else:
                for o in overlay_b_in_a:
                    st.write(f"- {o}")

            overlay_text = "PERSON A'S PLANETS IN PERSON B'S HOUSES:\n" + (
                "\n".join(f"- {o}" for o in overlay_a_in_b) or "Not available."
            ) + "\n\nPERSON B'S PLANETS IN PERSON A'S HOUSES:\n" + (
                "\n".join(f"- {o}" for o in overlay_b_in_a) or "Not available."
            )
            text_download_and_copy(overlay_text, f"house_overlays_{r['birth_date'].isoformat()}.txt", "overlays")

            st.divider()
            st.subheader("Person A's own house readings")
            render_house_readings_section(
                r["house_readings"], "houses_a", f"houses_a_{r['birth_date'].isoformat()}.txt"
            )
            st.subheader("Person B's own house readings")
            render_house_readings_section(
                r["house_readings_b"], "houses_b", f"houses_b_{r['birth_date'].isoformat()}.txt"
            )
        else:
            render_house_readings_section(
                r["house_readings"], "houses", f"houses_{r['birth_date'].isoformat()}.txt"
            )
