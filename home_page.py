"""
home_page.py

The site's actual landing page — set as the default page (loads at
the bare root URL).

Restructured Aug 2026 to lead with education rather than the paid
offerings grid: hero with a real, computed example chart wheel (in
this brand's own indigo/brass style, not generic zodiac clipart) --
the one thing only this product can authentically show -- followed by
plain-language explanations of what a birth chart actually is and
what someone can learn from one. Paid offerings are still reachable,
just de-emphasized into a simple link row near the bottom rather than
leading with a shopping-style grid.
"""

import streamlit as st

st.title("🔭 Tenth House Readings")
st.caption(
    "Real astrology, real insights. Every reading comes from your "
    "full chart, so it's true to you."
)

# --- Hero: description + primary CTA alongside a real computed chart ---
hero_col1, hero_col2 = st.columns([3, 2], vertical_alignment="top")
with hero_col1:
    st.write(
        "In astrology, the Tenth House is where your chart meets the world: "
        "your direction, your reputation, and what you're ultimately drawn "
        "to building. That's the spirit behind every reading here; helping "
        "you figure out where you are headed, and what (and what not) to "
        "do in the process. Our readings are grounded in your actual chart "
        "rather than vague affirmations dressed up in cosmic language. Real "
        "astrology to help you find your direction."
    )
    if st.button("Get Your Free Reading →", type="primary", key="hero_cta"):
        st.switch_page("personal_readings_page.py")
with hero_col2:
    import base64
    with open("assets/hero_chart_wheel.png", "rb") as _img_f:
        _hero_img_b64 = base64.b64encode(_img_f.read()).decode("ascii")
    st.markdown(
        f'<img src="data:image/png;base64,{_hero_img_b64}" '
        f'style="width: 100%; margin-top: -70px;" />',
        unsafe_allow_html=True,
    )

st.divider()

# --- Education: what a birth chart actually is ---
st.subheader("What is a birth chart?")
st.markdown(
    "A birth chart is a map of exactly where the "
    "[Sun, Moon, and planets](/resources_page) were at the moment you "
    "were born. Your chart is computed from your precise birth date, "
    "time, and location, down to the degree. It's organized into "
    "[12 houses](/resources_page) and shaped by the angles planets "
    "form with each other, called [aspects](/resources_page). Every "
    "placement means something specific: a chart that's actually, "
    "mathematically yours."
)

st.divider()

# --- Education: what you can actually learn from one ---
st.subheader("What you can learn")

learn_col1, learn_col2, learn_col3 = st.columns(3)
with learn_col1:
    with st.container(border=True):
        st.markdown("**Yourself**")
        st.write(
            "Your personality, strengths, and life direction, drawn "
            "from your whole chart, not just your sun sign."
        )
with learn_col2:
    with st.container(border=True):
        st.markdown("**Your relationships**")
        st.write(
            "How you and someone else actually mesh: where the "
            "connection flows, where friction shows up, what to "
            "watch for."
        )
with learn_col3:
    with st.container(border=True):
        st.markdown("**Deeper patterns**")
        st.write(
            "Specific placements worth a closer look — Lilith, "
            "Chiron, your Lunar Nodes — each tied to a particular "
            "kind of self-understanding."
        )

st.divider()

# --- De-emphasized: paid offerings, simple link row instead of a grid ---
st.caption("Want to go deeper?")
deep_col1, deep_col2 = st.columns(2)
with deep_col1:
    st.page_link(
        "advanced_readings_page.py",
        label="✨ Advanced Readings — in-depth details, weekly and one-time transit readings",
    )
with deep_col2:
    st.page_link(
        "weekly_transits_signup_page.py",
        label="💬 Ask an Astrologer — one question, answered personally",
    )

st.divider()

if st.button("Get Your Free Reading →", type="primary", key="bottom_cta"):
    st.switch_page("personal_readings_page.py")
