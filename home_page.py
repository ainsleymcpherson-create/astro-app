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
    "Real astrology, computed from your actual birth chart — not a "
    "generic sun-sign horoscope. Every reading here comes from your "
    "full chart: all the planets, the houses (including the empty "
    "ones), and the aspects between them, the same way a working "
    "astrologer would actually read it."
)

st.divider()

st.subheader("Start with a free reading")
st.write(
    "Pick Personal, Synastry (compatibility between two people), or "
    "Deep Dive (a focused look at one specific point in your chart) — "
    "each gives you a real, substantive summary at no cost."
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
        "The complete, in-depth version of any reading above, emailed "
        "to you — $3 for a single reading, or $10/month for unlimited "
        "full readings across Personal, Synastry, and Deep Dive."
    )
    st.page_link("advanced_readings_page.py", label="Advanced Readings", icon="✨")
with col2:
    st.markdown("**Astrology Services**")
    st.write(
        "Weekly transit readings by email ($5/month), a one-time "
        "transit reading ($7), or ask an astrologer one specific "
        "question about your chart ($10)."
    )
    st.page_link("weekly_transits_signup_page.py", label="Astrology Services", icon="🌙")

st.divider()
st.caption("New to some of the terms used throughout? The Resources page has a "
           "plain-language glossary of signs, planets, and houses.")
st.page_link("resources_page.py", label="Resources", icon="📖")
