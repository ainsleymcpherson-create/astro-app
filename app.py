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

# --- One-click unsubscribe from weekly transit emails ---
# Deliberately independent of login -- the whole point of a one-click
# unsubscribe link is that someone can act on it without needing to
# sign back in first. The token in the URL is the entire
# authentication for this action (see profiles_db.unsubscribe_by_token
# for why that's safe to do). Checked here, at the very top of the
# router, before any page renders, so it works regardless of which
# page the link happens to land on.
if "unsubscribe" in st.query_params and "DATABASE_URL" in os.environ:
    from profiles_db import unsubscribe_by_token
    _unsub_result = unsubscribe_by_token(st.query_params["unsubscribe"])
    del st.query_params["unsubscribe"]
    if _unsub_result:
        # For paid (Stripe) subscribers, turning off the email flag
        # alone isn't enough -- their card would keep getting charged
        # $5/month even though the emails stopped. Cancel the actual
        # subscription too, so unsubscribing here genuinely stops
        # billing, not just delivery.
        _sub_id = _unsub_result.get("stripe_subscription_id")
        if _sub_id and "STRIPE_SECRET_KEY" in os.environ:
            try:
                import stripe
                stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
                stripe.Subscription.cancel(_sub_id)
            except Exception as e:
                st.warning(
                    "Emails are turned off, but there was a problem canceling "
                    f"the associated subscription automatically ({e}). Please "
                    "contact support to confirm billing has stopped."
                )
        st.success(f"Weekly transit emails turned off for \"{_unsub_result['label']}\".", icon="✅")
    else:
        st.info("That unsubscribe link has already been used or is no longer valid.")

# --- Manage subscription (change theme, or unsubscribe) ---
# Same private-token authentication as the unsubscribe link above --
# no login required, since paid weekly-transit subscribers never go
# through Auth0 at all. Linked from the weekly email itself alongside
# the unsubscribe link.
if "manage" in st.query_params and "DATABASE_URL" in os.environ:
    from profiles_db import get_profile_by_token, set_theme_by_token
    _manage_token = st.query_params["manage"]
    _managed_profile = get_profile_by_token(_manage_token)
    if _managed_profile:
        st.subheader(f"Manage weekly transits for \"{_managed_profile['label']}\"")
        _theme_options = ["General", "Romantic", "Career"]
        _current_theme = _managed_profile.get("transit_theme") or "General"
        _new_theme = st.radio(
            "Reading theme",
            options=_theme_options,
            index=_theme_options.index(_current_theme) if _current_theme in _theme_options else 0,
            help="Changes what your weekly transit reading focuses on going forward.",
        )
        if st.button("Save theme"):
            _updated_label = set_theme_by_token(_manage_token, _new_theme)
            if _updated_label:
                st.success(f"Theme updated to {_new_theme} for \"{_updated_label}\".", icon="✅")
            else:
                st.error("That link is no longer valid.")
        st.divider()
        st.caption("Want to stop weekly transit emails entirely?")
        st.markdown(f"[Unsubscribe](?unsubscribe={_manage_token})")
    else:
        st.info("That management link has already been used or is no longer valid.")

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

home = st.Page("home_page.py", title="Home", icon="🏠", default=True, url_path="")
personal_readings = st.Page("personal_readings_page.py", title="Personal", icon="🔭")
synastry_readings = st.Page("synastry_readings_page.py", title="Synastry", icon="👥")
deep_dive_readings = st.Page("deep_dive_readings_page.py", title="Deep Dive", icon="🔍")
advanced_readings = st.Page("advanced_readings_page.py", title="Advanced Readings", icon="✨")
weekly_transits = st.Page(
    "weekly_transits_signup_page.py", title="Astrology Services", icon="🌙",
    url_path="weekly-transits",
)
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
            from profiles_db import safe_user_email
            user_email = safe_user_email()

            if user_email:
                st.caption(f"Signed in as {user_email}")
            else:
                # is_logged_in was True but the email claim wasn't
                # available this rerun (see safe_user_email's
                # docstring) -- degrade gracefully rather than crash;
                # a rerun a moment later almost always resolves it.
                st.caption("Signed in")
            if st.button("Log out", width="stretch"):
                st.logout()

            # Runs once here, before either section below queries a
            # table it's responsible for creating -- account_subscriptions
            # didn't exist until this migration ran, and the Full Access
            # section (which queries it) previously ran BEFORE My
            # Profiles' own init_schema() call further down, causing a
            # "relation does not exist" error the first time this
            # table was ever needed.
            if user_email and "DATABASE_URL" in os.environ:
                from profiles_db import init_schema
                init_schema()

            # --- Full Access subscription ($10/month) ---
            # Account-level entitlement, checked here (not per-profile)
            # since it unlocks full readings across Personal, Synastry,
            # and Deep Dive for the whole account, not any one saved
            # profile. Deliberately separate from the Astrology Services
            # products (Weekly Transits, One-Time Transit, Ask an
            # Astrologer), which stay individually priced.
            if user_email and "DATABASE_URL" in os.environ:
                from profiles_db import has_active_subscription
                if has_active_subscription(user_email):
                    st.caption("✅ Full Access active — unlimited full readings across "
                               "Personal, Synastry, and Deep Dive.")
                elif "STRIPE_SECRET_KEY" in os.environ and "STRIPE_FULL_ACCESS_PRICE_ID" in os.environ:
                    st.caption("Get unlimited full readings + email delivery across "
                               "Personal, Synastry, and Deep Dive.")
                    if st.button("Get Full Access — $10/month", width="stretch"):
                        import stripe
                        stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
                        try:
                            checkout_session = stripe.checkout.Session.create(
                                mode="subscription",
                                line_items=[{
                                    "price": os.environ["STRIPE_FULL_ACCESS_PRICE_ID"],
                                    "quantity": 1,
                                }],
                                customer_email=user_email,
                                success_url="https://tenthhousereadings.com/?signup=success",
                                cancel_url="https://tenthhousereadings.com/?signup=cancelled",
                                metadata={
                                    "product_type": "full_access_subscription",
                                    "label": user_email,
                                },
                            )
                            st.link_button(
                                "Proceed to Secure Checkout →",
                                checkout_session.url,
                                width="stretch",
                                type="primary",
                            )
                        except Exception as e:
                            st.error(f"Something went wrong setting up checkout: {e}")

            # --- Saved profiles management ---
            # Guarded separately from the login block above, since
            # login can exist without the database being configured
            # yet (e.g. mid-rollout) -- fails safe to just not
            # showing this section, same pattern as everywhere else
            # this app checks for optional infrastructure. Also
            # skipped (rather than crashing) if user_email came back
            # None for the reason noted above.
            if user_email and "DATABASE_URL" in os.environ:
                from profiles_db import list_profiles, delete_profile, set_weekly_transits
                with st.expander("My Profiles"):
                    saved = list_profiles(user_email)
                    if not saved:
                        st.caption("No saved profiles yet.")
                    for p in saved:
                        with st.container(border=True):
                            col_label, col_delete = st.columns([3, 1])
                            with col_label:
                                st.write(f"**{p['label']}**")
                            with col_delete:
                                if st.button("🗑️", key=f"del_profile_{p['id']}", help=f"Delete \"{p['label']}\""):
                                    delete_profile(p["id"], user_email)
                                    st.rerun()
                            _weekly_on = st.checkbox(
                                "📅 Email me weekly transits",
                                value=bool(p.get("weekly_transits")),
                                key=f"weekly_{p['id']}",
                                help=f"A short Monday-morning reading of that week's transits "
                                     f"against {p['label']}'s chart, emailed automatically.",
                            )
                            if _weekly_on != bool(p.get("weekly_transits")):
                                set_weekly_transits(p["id"], user_email, _weekly_on)
                                st.rerun()
        else:
            st.caption("Log in to unlock full readings, email delivery, and saved profiles.")
            if st.button("Log in", width="stretch"):
                st.login("auth0")

pg = st.navigation({
    "Home": [home],
    "Readings": [personal_readings, synastry_readings, deep_dive_readings],
    "Advanced Readings": [advanced_readings],
    "Astrology Services": [weekly_transits],
    "Resources": [resources],
})
pg.run()
