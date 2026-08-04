"""
home_page.py

The site's actual landing page — set as the default page (loads at
the bare root URL), replacing what used to just be whichever reading
page happened to load first in the navigation list by accident of
ordering.

Deliberately "slightly fuller than a bare splash page, but not
pushy": a short, confident intro explaining what makes this different
from a sun-sign horoscope, one clear path into a free reading, and
brief, honest mentions of what else exists (Advanced Readings,
Astrology Services) without foregrounding a sales pitch before
someone's seen a single actual reading.
"""

import streamlit as st

st.title("🔭 Tenth House Readings")
st.write(
    "Real astrology, computed for you. Every reading comes from your "
    "full chart to ensure that the reading is as true-to-you as "
    "possible."
)

st.divider()

st.subheader("Start with a free reading")
st.write(
    "Pick a focus: Personal, Career, Relationship Synastry, "
    "Professional Synastry, or dig into one of our Deep Dive "
    "Readings for an understanding of some of the lesser known "
    "chart components. Sometimes a quick summary is all you need!"
)
st.page_link("personal_readings_page.py", label="Personal Readings", icon="🔭")
st.page_link("synastry_readings_page.py", label="Synastry Readings", icon="👥")
st.page_link("deep_dive_readings_page.py", label="Deep Dive Readings", icon="🔍")

st.divider()

st.subheader("Want more?")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Advanced Readings**")
    st.write(
        "Access the in-depth details. Perfect for enhanced personal "
        "understanding and deeper synastry conversations."
    )
    st.page_link("advanced_readings_page.py", label="Advanced Readings", icon="✨")
with col2:
    st.markdown("**Astrology Services**")
    st.write(
        "We also provide one-time or weekly transit readings straight "
        "to your inbox. Stay up-to-date on how your chart is "
        "interacting with current planetary locations and transits. "
        "Choose from one of three focuses: General, Relationship, or "
        "Career. Change the focus at any time! Looking for something "
        "you don't see offered already? Ask an astrologer something "
        "specific, and receive the detailed response in your email "
        "inbox."
    )
    st.page_link("weekly_transits_signup_page.py", label="Astrology Services", icon="🌙")

st.divider()
st.caption("New to some of the terms used throughout? The Resources page has a "
           "plain-language glossary of signs, planets, and houses.")
st.page_link("resources_page.py", label="Resources", icon="📖")
