"""
home_page.py

The site's actual landing page — set as the default page (loads at
the bare root URL).

Restructured after reviewing a reference site's FLOW (not its colors
or copy, both of which stay entirely this brand's own): one clear
primary action instead of several competing links, and every paid
offering shown together in one consistent grid instead of scattered
across sections with different visual treatments.
"""

import streamlit as st

st.title("🔭 Tenth House Readings")
st.write(
    "Real astrology, computed for you. Every reading comes from your "
    "full chart to ensure that the reading is as true-to-you as "
    "possible."
)

# --- One primary action, not several competing ones ---
if st.button("Get Your Free Reading →", type="primary"):
    st.switch_page("personal_readings_page.py")

col_a, col_b = st.columns(2)
with col_a:
    st.page_link("synastry_readings_page.py", label="Synastry Readings", icon="👥")
with col_b:
    st.page_link("deep_dive_readings_page.py", label="Deep Dive Readings", icon="🔍")

st.divider()

# --- Every paid offering shown together, same format, same weight ---
st.subheader("Want more? Check out our premium tier options")

OFFERINGS = [
    {
        "icon": "✨",
        "name": "Advanced Readings",
        "desc": "Access the in-depth details. Perfect for enhanced personal "
                "understanding and deeper synastry conversations.",
        "page": "advanced_readings_page.py",
        "link_label": "Explore Advanced Readings",
    },
    {
        "icon": "🌙",
        "name": "Weekly Transits",
        "desc": "A short reading of that week's transits against your own "
                "chart, delivered every Monday. Choose General, Romantic, "
                "or Career — change it anytime.",
        "page": "weekly_transits_signup_page.py",
        "link_label": "Explore Astrology Services",
    },
    {
        "icon": "🪐",
        "name": "One-Time Transit Reading",
        "desc": "A full reading of the current transits against your "
                "chart — a single reading, emailed shortly after payment.",
        "page": "weekly_transits_signup_page.py",
        "link_label": "Explore Astrology Services",
    },
    {
        "icon": "💬",
        "name": "Ask an Astrologer",
        "desc": "Ask one specific question — anything from \"should I take "
                "this job\" to \"what does this transit mean\" — and get a "
                "real, focused answer.",
        "page": "weekly_transits_signup_page.py",
        "link_label": "Explore Astrology Services",
    },
]

row1 = st.columns(2)
row2 = st.columns(2)
for offering, col in zip(OFFERINGS, row1 + row2):
    with col:
        with st.container(border=True):
            st.markdown(f"**{offering['icon']} {offering['name']}**")
            st.write(offering["desc"])
            st.page_link(offering["page"], label=offering["link_label"])

st.divider()
st.write("New to some of the terms used throughout? The Resources page has a "
          "plain-language glossary of signs, planets, and houses.")
st.page_link("resources_page.py", label="Resources", icon="📖")
