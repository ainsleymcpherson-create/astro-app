"""
app.py

Entrypoint for the Tenth House Readings app. Uses Streamlit's native
multi-page navigation (st.navigation + st.Page) to switch between the
"Readings" page (the full chart calculator — everything the app has
always done, unchanged, living in readings_page.py) and the new
"Resources" page (a signs/planets/houses glossary, in
resources_page.py).

This file itself stays intentionally small — it's just the router.
All the actual logic lives in the two page files.
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

readings = st.Page("readings_page.py", title="Readings", icon="🔭")
resources = st.Page("resources_page.py", title="Resources", icon="📖")

pg = st.navigation([readings, resources])
pg.run()
