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
from datetime import date as date_type, datetime, timezone
import streamlit as st
import pandas as pd
import swisseph as swe

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
from prompt_builder import (
    build_interpretation_prompt,
    build_interpretation_prompt_no_time,
    build_career_interpretation_prompt,
    build_career_interpretation_prompt_no_time,
    build_transit_prompt,
)
from birth_input import resolve_birth_data

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


st.set_page_config(page_title="Astrology Chart Calculator", layout="wide")
st.title("🔭 Astrology Chart Calculator")
st.caption("Computes birth charts with full support for Part of Fortune, "
           "Nodes, Vertex, Chiron, dignity, and house-ruler interpretation "
           "of empty houses — not just the standard 10 planets.")

# --- Input form ---
with st.form("birth_form"):
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
        st.write("Birth time")
        hour_col, minute_col, ampm_col = st.columns(3)
        with hour_col:
            birth_hour = st.selectbox(
                "Hour", options=list(range(1, 13)), index=0,
                label_visibility="collapsed",
            )
        with minute_col:
            birth_minute = st.selectbox(
                "Minute", options=[f"{m:02d}" for m in range(60)], index=30,
                label_visibility="collapsed",
            )
        with ampm_col:
            birth_ampm = st.selectbox(
                "AM/PM", options=["AM", "PM"], index=1,
                label_visibility="collapsed",
            )
    with col3:
        location_str = st.text_input(
            "Birth location",
            value="Brooklyn, New York, USA",
            help="Be specific — add state/country if the place name is common",
        )

    house_system_label = st.selectbox(
        "House system",
        options=["Placidus", "Whole Sign", "Equal", "Koch", "Campanus", "Regiomontanus", "Alcabitius"],
        index=0,
    )
    house_system_map = {
        "Placidus": b"P", "Whole Sign": b"W", "Equal": b"E", "Koch": b"K",
        "Campanus": b"C", "Regiomontanus": b"R", "Alcabitius": b"B",
    }

    reading_type = st.selectbox(
        "Reading focus",
        options=["General", "Career / Work", "Transits"],
        index=0,
        help="General covers the whole chart. Career/Work focuses "
             "specifically on workplace happiness, colleague dynamics, "
             "work style, and professional strengths/weaknesses. Transits "
             "answers 'what's happening right now' — how today's sky is "
             "currently interacting with this natal chart.",
    )

    transit_date = st.date_input(
        "Transit date (only used for Transits reading)",
        value=date_type.today(),
        help="The date to check transits for — defaults to today. Ignored "
             "for General and Career/Work readings.",
    )

    unknown_time = st.checkbox(
        "🕐 I don't know my exact birth time",
        value=False,
        help="The Ascendant, Midheaven, house placements, Vertex, and Part "
             "of Fortune/Spirit all require an exact birth time to "
             "calculate correctly — a noon guess doesn't approximate them, "
             "it effectively randomizes them (the Ascendant alone shifts "
             "about 1° every 4 minutes). Checking this excludes all of "
             "those and works only with what's reliable regardless of "
             "time: the planets, Chiron, the Nodes, and aspects between "
             "them. Works for General and Career/Work readings (not "
             "applicable to Transits, which always needs a real natal "
             "chart to compare against).",
    )

    generate_live = st.checkbox(
        "🪙 Generate written interpretation with Claude (makes a real, billed API call)",
        value=False,
        help="Unchecked (default): you get the raw prompt to copy/paste into "
             "Claude yourself, for free. Checked: this app calls the Claude "
             "API directly and you're charged for that usage, every time "
             "you click Compute Chart with this box checked.",
    )

    submitted = st.form_submit_button("Compute Chart", use_container_width=True)


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
    return pd.DataFrame(rows)


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
                    prompt = build_transit_prompt(transiting_points, transit_aspects, dignities)
            elif reading_type == "Career / Work" and unknown_time:
                prompt = build_career_interpretation_prompt_no_time(
                    chart, aspects, patterns, dignities
                )
            elif reading_type == "Career / Work":
                prompt = build_career_interpretation_prompt(chart, aspects, patterns, dignities, house_readings)
            elif unknown_time:
                prompt = build_interpretation_prompt_no_time(chart, aspects, patterns, dignities)
            else:
                prompt = build_interpretation_prompt(chart, aspects, patterns, dignities, house_readings)

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
                    with st.spinner("Generating interpretation with Claude "
                                     "(this makes a billed API call — may take "
                                     "a couple minutes for a full reading)..."):
                        try:
                            client = anthropic.Anthropic(api_key=api_key)
                            # Streaming is required here rather than a plain
                            # blocking call: with max_tokens this high, the
                            # SDK estimates generation could exceed its
                            # 10-minute non-streaming timeout and refuses to
                            # run without it. get_final_message() waits for
                            # the stream to finish and hands back a normal
                            # Message object — same .content/.stop_reason
                            # shape as the non-streaming response, so nothing
                            # downstream needs to change.
                            with client.messages.stream(
                                model="claude-sonnet-5",
                                max_tokens=32000,
                                messages=[{"role": "user", "content": prompt}],
                            ) as stream:
                                response = stream.get_final_message()
                            text_parts = [
                                block.text for block in response.content
                                if getattr(block, "type", None) == "text"
                            ]
                            result_text = "".join(text_parts)
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
                                stop_reason = getattr(response, "stop_reason", "unknown")
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
            "chart": chart,
            "aspects": aspects,
            "patterns": patterns,
            "dignities": dignities,
            "house_readings": house_readings,
            "prompt": prompt,
            "interpretation_text": interpretation_text,
            "interpretation_error": interpretation_error,
        }

    except ValueError as e:
        st.error(f"Couldn't resolve birth data: {e}")
    except Exception as e:
        st.error(f"Something went wrong: {e}")
        st.exception(e)


# --- Display results ---
# Runs on every script rerun where results exist in session_state — not
# just the run where the form was submitted — so the tabs (and their
# download/copy buttons) stay visible across reruns instead of vanishing.
if st.session_state.get("results"):
    r = st.session_state.results

    if r["reading_type"] == "Transits":
        st.success(
            f"Natal chart: {r['datetime_str']} in {r['location_str']} "
            f"({r['house_system_label']} houses) — Transits for {r['transit_date'].isoformat()}"
        )
    else:
        st.success(
            f"Chart computed for {r['datetime_str']} in {r['location_str']} "
            f"({r['house_system_label']} houses, {r['reading_type']} reading)"
        )

    tabs = st.tabs(["Interpretation", "Prompt", "Points", "Aspects", "Patterns", "Dignity", "Houses"])

    with tabs[0]:
        if r["interpretation_text"]:
            render_interpretation(r["interpretation_text"])
            st.divider()
            st.download_button(
                "Download reading as .txt",
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
        points_df = points_to_dataframe(r["chart"])
        st.dataframe(points_df, use_container_width=True, hide_index=True)
        dataframe_download_and_copy(points_df, f"points_{r['birth_date'].isoformat()}.csv", "points")

    with tabs[3]:
        aspects_df = aspects_to_dataframe(r["aspects"])
        st.dataframe(aspects_df, use_container_width=True, hide_index=True)
        dataframe_download_and_copy(aspects_df, f"aspects_{r['birth_date'].isoformat()}.csv", "aspects")

    with tabs[4]:
        any_patterns = False
        pattern_lines = []
        for kind, plist in r["patterns"].items():
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
            text_download_and_copy(
                "\n".join(pattern_lines),
                f"patterns_{r['birth_date'].isoformat()}.txt",
                "patterns",
            )

    with tabs[5]:
        dignity_df = dignities_to_dataframe(r["dignities"])
        st.dataframe(dignity_df, use_container_width=True, hide_index=True)
        dataframe_download_and_copy(dignity_df, f"dignity_{r['birth_date'].isoformat()}.csv", "dignity")

    with tabs[6]:
        house_lines = []
        for num, reading in r["house_readings"].items():
            with st.expander(f"House {num} ({reading.sign_on_cusp})"):
                st.write(reading.interpretation)
            house_lines.append(f"House {num} ({reading.sign_on_cusp}):\n{reading.interpretation}\n")
        text_download_and_copy(
            "\n".join(house_lines),
            f"houses_{r['birth_date'].isoformat()}.txt",
            "houses",
        )
