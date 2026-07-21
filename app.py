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

readings = st.Page("readings_page.py", title="Readings", icon="🔭")
resources = st.Page("resources_page.py", title="Resources", icon="📖")

pg = st.navigation([readings, resources])
pg.run()
