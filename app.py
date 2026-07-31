"""
app.py

Entrypoint for the Tenth House Readings app. Uses Streamlit's native
multi-page navigation (st.navigation + st.Page) to switch between
four pages:
  - "Personal Readings" (General, Career/Work, Transits — single-
    person readings), in personal_readings_page.py
  - "Synastry Readings" (Professional, Relationship, and Parent/Child
    Synastry — two-person readings), in synastry_readings_page.py
  - "Deep Dive Readings" (focused single-point readings, e.g. Lilith
    — more topics to be added over time), in deep_dive_readings_page.py
  - "Resources" (signs/planets/houses glossary, unchanged), in
    resources_page.py

The readings pages are near-identical copies of what used to be a
single readings_page.py — same shared logic throughout (birth input,
tabs, downloads, the email pipeline), just with each page's dropdown
restricted to its own subset of reading types. Any change to shared
logic needs to be made across ALL of personal_readings_page.py,
synastry_readings_page.py, AND deep_dive_readings_page.py to stay in
sync.

This file itself stays intentionally small — it's just the router.
All the actual logic lives in the page files.
"""

import streamlit as st

st.set_page_config(page_title="Tenth House Readings", layout="wide")

# Narrow the sidebar. Streamlit doesn't expose sidebar width as a
# simple, reliably-available parameter across versions, so this uses
# CSS instead. Recent Streamlit versions made the sidebar user-
# resizable via a drag handle, which sets its width as an INLINE style
# — inline styles override plain CSS rules, which is why a simple
# width rule alone doesn't stick. Using !important on every relevant
# property (and disabling the resize handle) forces it to actually
# take effect and stay put.
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        width: 240px !important;
        min-width: 240px !important;
        max-width: 240px !important;
        resize: none !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        width: 240px !important;
        min-width: 240px !important;
        max-width: 240px !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] {
        margin-left: -240px !important;
    }

    /* Signature element: every st.divider() renders a plain <hr> by
       default. Replacing it with a shallow brass arc -- a fragment of
       the same wheel this app actually computes for every chart --
       instead of a generic flat line ties a structural, everyday UI
       element back to the product's real subject rather than using it
       as pure decoration. */
    hr {
        border: none !important;
        height: 20px !important;
        margin: 1.5rem 0 !important;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 20'%3E%3Cpath d='M0,15 Q100,-5 200,15' stroke='%23C9A66B' stroke-width='1' fill='none' opacity='0.55'/%3E%3C/svg%3E") !important;
        background-repeat: no-repeat !important;
        background-position: center !important;
        background-size: 100% 100% !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

personal_readings = st.Page("personal_readings_page.py", title="Personal Readings", icon="🔭")
synastry_readings = st.Page("synastry_readings_page.py", title="Synastry Readings", icon="👥")
deep_dive_readings = st.Page("deep_dive_readings_page.py", title="Deep Dive Readings", icon="🔍")
resources = st.Page("resources_page.py", title="Resources", icon="📖")

pg = st.navigation([personal_readings, synastry_readings, deep_dive_readings, resources])
pg.run()
