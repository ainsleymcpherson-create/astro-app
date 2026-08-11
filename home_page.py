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
st.caption(
    "Real astrology, real insights. Every reading comes from your "
    "full chart, so it's true to you."
)

st.write(
    "In astrology, the Tenth House is where your chart meets the world: "
    "your direction, your reputation, and what you're ultimately drawn "
    "to building. That's the spirit behind every reading here; helping "
    "you figure out where you are headed, and what (and what not) to "
    "do in the process. Our readings are grounded in your actual chart "
    "rather than vague affirmations dressed up in cosmic language. Real "
    "astrology to help you find your direction."
)

# --- One primary action, not several competing ones ---
if st.button("Get Your Free Reading →", type="primary"):
    st.switch_page("personal_readings_page.py")

st.divider()

# --- Every paid offering shown together, same format, same weight ---
st.subheader("Want more? Check out our premium tier options")

OFFERINGS = [
    {
        "icon": "✨",
        "name": "Advanced Readings",
        "desc": "Access the in-depth details. Perfect for enhanced personal "
                "understanding and deeper synastry conversations.",
        "url_path": "/advanced-readings",
    },
    {
        "icon": "🌙",
        "name": "Weekly and One-Time Transit Readings",
        "desc": "A short reading of that week's transits delivered every "
                "Monday, or a single full transit reading whenever you "
                "want one — both measured against your own chart.",
        "url_path": "/advanced-readings",
    },
    {
        "icon": "🔓",
        "name": "All-Access Subscription",
        "desc": "✨ Coming soon — unlimited full readings and email "
                "delivery across Personal, Synastry, and Deep Dive, no "
                "per-reading purchases needed.",
        "url_path": "/advanced-readings",
    },
    {
        "icon": "💬",
        "name": "Ask an Astrologer",
        "desc": "Ask one specific question — anything from \"should I take "
                "this job\" to \"what does this transit mean\" — and get a "
                "real, focused answer.",
        "url_path": "/weekly-transits",
    },
]

row1 = st.columns(2)
row2 = st.columns(2)
for offering, col in zip(OFFERINGS, row1 + row2):
    with col:
        with st.container(border=True):
            st.markdown(f"**[{offering['icon']} {offering['name']}]({offering['url_path']})**")
            st.write(offering["desc"])
