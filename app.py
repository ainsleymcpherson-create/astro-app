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
# simple, reliably-available parameter across versions (a newer
# int-based initial_sidebar_state exists in some recent releases, but
# isn't guaranteed present in every deployed version), so this uses the
# well-established, broadly-compatible CSS override instead. 190px is
# just wide enough for "🔭 Readings" / "📖 Resources" to sit on one
# line each without the large empty space at the default width.
st.markdown(
    """
    <style>
    [data-testid="stSidebar"][aria-expanded="true"] > div:first-child {
        width: 190px;
    }
    [data-testid="stSidebar"][aria-expanded="false"] > div:first-child {
        width: 190px;
        margin-left: -190px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

readings = st.Page("readings_page.py", title="Readings", icon="🔭")
resources = st.Page("resources_page.py", title="Resources", icon="📖")

pg = st.navigation([readings, resources])
pg.run()
