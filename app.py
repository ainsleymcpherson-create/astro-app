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

import os
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

# --- Optional login (saved profiles) ---
# Anonymous use is always fully available everywhere else in the app —
# this only adds an optional "log in to save birth profiles"
# convenience layer, per an explicit product decision to never gate
# the core reading experience behind an account. Guarded by an "auth"
# secrets check so the app runs identically whether or not Auth0
# credentials have actually been configured yet (e.g. during initial
# rollout, or in a local dev environment without them) — this check
# fails safe, just hiding the login UI entirely, rather than crashing.
if "auth" in st.secrets:
    with st.sidebar:
        st.divider()
        if st.user.is_logged_in:
            st.caption(f"Signed in as {st.user.email}")
            if st.button("Log out", width="stretch"):
                st.logout()

            # --- Saved profiles management ---
            # Guarded separately from the login block above, since
            # login can exist without the database being configured
            # yet (e.g. mid-rollout) -- fails safe to just not
            # showing this section, same pattern as everywhere else
            # this app checks for optional infrastructure.
            if "DATABASE_URL" in os.environ:
                from profiles_db import init_schema, list_profiles, delete_profile
                init_schema()
                with st.expander("My Profiles"):
                    saved = list_profiles(st.user.email)
                    if not saved:
                        st.caption("No saved profiles yet.")
                    for p in saved:
                        col_label, col_delete = st.columns([3, 1])
                        with col_label:
                            st.write(p["label"])
                        with col_delete:
                            if st.button("🗑️", key=f"del_profile_{p['id']}", help=f"Delete \"{p['label']}\""):
                                delete_profile(p["id"], st.user.email)
                                st.rerun()
        else:
            if st.button("Log in to save profiles", width="stretch"):
                st.login("auth0")

pg = st.navigation([personal_readings, synastry_readings, deep_dive_readings, resources])
pg.run()
