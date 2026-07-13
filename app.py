"""
app.py

Streamlit frontend for the astrology chart engine. Lets you type in a
birth date/time and location, computes the full chart (points, aspects,
patterns, dignity, houses), and displays everything interactively —
plus generates the LLM interpretation prompt and (optionally) calls
Claude directly to produce the actual written interpretation.

Run locally:
    streamlit run app.py

This same file is what you'd deploy to Streamlit Community Cloud later
for a public version — no code changes needed, just push this repo to
GitHub and point Streamlit Cloud at it.
"""

import os
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
from prompt_builder import build_interpretation_prompt
from birth_input import resolve_birth_data

# --- Optional: live Claude interpretation ---
# Requires: pip install anthropic
# Requires an ANTHROPIC_API_KEY available either as:
#   - a Colab secret (accessed via google.colab.userdata), or
#   - an environment variable, for local/non-Colab runs
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def get_api_key():
    """Try Colab secrets first, then fall back to environment variable."""
    try:
        from google.colab import userdata
        key = userdata.get("ANTHROPIC_API_KEY")
        if key:
            return key
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
    col1, col2 = st.columns(2)
    with col1:
        datetime_str = st.text_input(
            "Birth date & time",
            value="December 24, 1981 1:30pm",
            help="Any reasonably natural format works, e.g. "
                 "'July 5, 1989 11:54am' or '1989-07-05 11:54'",
        )
    with col2:
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

    generate_live = st.checkbox(
        "Generate written interpretation with Claude (uses API credits)",
        value=False,
        help="If unchecked, you'll get the raw prompt to copy/paste yourself instead.",
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
            "House": point.house if point.house else "—",
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


if submitted:
    try:
        with st.spinner("Resolving location and timezone..."):
            birth = resolve_birth_data(datetime_str, location_str, verbose=False)

        house_system = house_system_map[house_system_label]

        with st.spinner("Computing chart..."):
            chart = compute_full_chart(birth, house_system=house_system)
            aspects = compute_aspects(chart, speeds=extract_speeds(chart))
            patterns = find_all_patterns(chart, aspects)
            dignities = compute_chart_dignities(chart)
            house_readings = build_house_readings(chart)
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
                        "secret, or set it as an environment variable."
                    )
                else:
                    with st.spinner("Generating interpretation with Claude..."):
                        try:
                            client = anthropic.Anthropic(api_key=api_key)
                            response = client.messages.create(
                                model="claude-sonnet-5",
                                max_tokens=2000,
                                messages=[{"role": "user", "content": prompt}],
                            )
                            interpretation_text = response.content[0].text
                        except Exception as e:
                            interpretation_error = f"Claude API call failed: {e}"

        st.success(
            f"Chart computed for {datetime_str} in {location_str} "
            f"({house_system_label} houses)"
        )

        tabs = st.tabs(["Interpretation", "Points", "Aspects", "Patterns", "Dignity", "Houses"])

        with tabs[0]:
            if interpretation_error:
                st.warning(interpretation_error)
                st.text_area("Prompt (copy this into Claude yourself instead)",
                             value=prompt, height=400)
            elif interpretation_text:
                st.markdown(interpretation_text)
                st.divider()
                with st.expander("View the raw prompt used"):
                    st.text_area("Prompt", value=prompt, height=300, label_visibility="collapsed")
            else:
                st.info("Check \"Generate written interpretation with Claude\" above, "
                        "then recompute — or copy the prompt below into Claude yourself.")
                st.text_area("Full prompt (copy this into Claude or send via API)",
                             value=prompt, height=400)

            st.download_button(
                "Download prompt as .txt",
                data=prompt,
                file_name="interpretation_prompt.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with tabs[1]:
            st.dataframe(points_to_dataframe(chart), use_container_width=True, hide_index=True)

        with tabs[2]:
            st.dataframe(aspects_to_dataframe(aspects), use_container_width=True, hide_index=True)

        with tabs[3]:
            any_patterns = False
            for kind, plist in patterns.items():
                if not plist:
                    continue
                any_patterns = True
                st.subheader(kind.replace("_", " ").title())
                for p in plist:
                    st.write(f"- {', '.join(p.points)}")
            if not any_patterns:
                st.info("No aspect patterns detected within the configured orbs.")

        with tabs[4]:
            st.dataframe(dignities_to_dataframe(dignities), use_container_width=True, hide_index=True)

        with tabs[5]:
            for num, reading in house_readings.items():
                with st.expander(f"House {num} ({reading.sign_on_cusp})"):
                    st.write(reading.interpretation)

    except ValueError as e:
        st.error(f"Couldn't resolve birth data: {e}")
    except Exception as e:
        st.error(f"Something went wrong: {e}")
        st.exception(e)
