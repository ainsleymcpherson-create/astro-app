"""
app.py

Entrypoint for the Tenth House Readings app. Uses Streamlit's native
multi-page navigation (st.navigation + st.Page) to switch between
three pages:
  - "Personal Readings" (General, Career/Work, Transits — single-
    person readings), in personal_readings_page.py
  - "Synastry Readings" (Professional and Relationship Synastry —
    two-person readings), in synastry_readings_page.py
  - "Resources" (signs/planets/houses glossary, unchanged), in
    resources_page.py

The two readings pages are near-identical copies of what used to be a
single readings_page.py — same shared logic throughout, just with each
page's "Reading focus" dropdown restricted to its own subset of
reading types. Any change to shared logic (tabs, downloads, the email
pipeline, etc.) needs to be made in BOTH personal_readings_page.py and
synastry_readings_page.py to stay in sync.

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
        width: 190px !important;
        min-width: 190px !important;
        max-width: 190px !important;
        resize: none !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        width: 190px !important;
        min-width: 190px !important;
        max-width: 190px !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] {
        margin-left: -190px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

personal_readings = st.Page("personal_readings_page.py", title="Personal Readings", icon="🔭")
synastry_readings = st.Page("synastry_readings_page.py", title="Synastry Readings", icon="👥")
resources = st.Page("resources_page.py", title="Resources", icon="📖")

pg = st.navigation([personal_readings, synastry_readings, resources])
pg.run()
