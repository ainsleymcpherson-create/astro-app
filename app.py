"""
app.py

Entrypoint for the Tenth House Readings app. Uses Streamlit's native
multi-page navigation (st.navigation + st.Page) to switch between
pages. This file itself stays intentionally small -- it's just the
router. All the actual logic lives in the page files.
"""

import os
import streamlit as st

st.set_page_config(page_title="Tenth House Readings", layout="wide")

# --- One-click unsubscribe from weekly transit emails ---
if "unsubscribe" in st.query_params and "DATABASE_URL" in os.environ:
    from profiles_db import unsubscribe_by_token
    _unsub_result = unsubscribe_by_token(st.query_params["unsubscribe"])
    del st.query_params["unsubscribe"]
    if _unsub_result:
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

# Narrow the sidebar and style the signature arc divider.
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
advanced_readings = st.Page(
    "advanced_readings_page.py", title="Advanced Readings", icon="✨",
    url_path="advanced-readings",
)
weekly_transits = st.Page(
    "weekly_transits_signup_page.py", title="Astrology Services", icon="🌙",
    url_path="weekly-transits",
)
resources = st.Page("resources_page.py", title="Resources", icon="📖")
my_account = st.Page("my_account_page.py", title="My Account", icon="👤")

# --- Custom sidebar menu ---
# st.navigation's own auto-generated menu can't mix flat top-level
# pages with one nested group in the same call. Building the visible
# menu by hand instead, with position="hidden" below so its own
# auto-menu never renders.
#
# .run() has to actually execute BEFORE any st.page_link() call that
# references these pages -- that registration genuinely happens as
# part of .run() itself running, not merely from calling
# st.navigation() and holding the returned object.
pg = st.navigation(
    [home, personal_readings, synastry_readings, deep_dive_readings,
     advanced_readings, weekly_transits, resources, my_account],
    position="hidden",
)
try:
    pg.run()
except Exception as e:
    if type(e).__name__ == "StopException":
        raise
    st.exception(e)
finally:
    with st.sidebar:
        st.page_link("home_page.py", label="Home")
        st.write("READINGS")
        _indent, _nested = st.columns([1, 9])
        with _nested:
            st.page_link("personal_readings_page.py", label="Personal", icon="🔭")
            st.page_link("synastry_readings_page.py", label="Synastry", icon="👥")
            st.page_link("deep_dive_readings_page.py", label="Deep Dive", icon="🔍")
        st.page_link("advanced_readings_page.py", label="Advanced Readings")
        st.page_link("weekly_transits_signup_page.py", label="Astrology Services")
        st.page_link("resources_page.py", label="Resources")
        st.page_link("my_account_page.py", label="My Account")

    # --- Optional login (saved profiles) ---
    if "auth" in st.secrets:
        with st.sidebar:
            st.divider()
            if st.user.is_logged_in:
                from profiles_db import safe_user_email
                user_email = safe_user_email()

                # safe_user_email() can transiently return None even while
                # is_logged_in is True (see its docstring) -- without this
                # fallback, that brief window makes every user_email-gated
                # section below (including the All Access Tier / Get Full
                # Access button) flicker in and out on whichever rerun
                # happens to land during it. Once resolved successfully
                # once this session, keep using that value through any
                # later transient gap rather than losing it.
                if user_email:
                    st.session_state["_cached_user_email"] = user_email
                elif "_cached_user_email" in st.session_state:
                    user_email = st.session_state["_cached_user_email"]

                if user_email:
                    st.caption(f"Signed in as {user_email}")
                else:
                    st.caption("Signed in")
                if st.button("Log out", width="stretch"):
                    st.logout()

                # Runs once here, right after login is confirmed -- needed
                # before anything on this app (including other pages, like
                # Advanced Readings and My Account) queries a table this
                # migration is responsible for creating.
                if user_email and "DATABASE_URL" in os.environ:
                    from profiles_db import init_schema, has_active_subscription
                    init_schema()
                    # Gold "All Access Tier" is a status indicator for
                    # people who already have the subscription --
                    # type="primary" picks up the theme's brass color
                    # automatically, same technique used for the
                    # homepage's main CTA. "Get Full Access" is the actual
                    # purchase path for people who don't have it yet.
                    if has_active_subscription(user_email):
                        if st.button("All Access Tier", width="stretch", type="primary"):
                            st.switch_page("my_account_page.py")
                    elif "STRIPE_SECRET_KEY" in os.environ and "STRIPE_FULL_ACCESS_PRICE_ID" in os.environ:
                        if st.button("Get Full Access", width="stretch"):
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
            else:
                st.caption("Log in to unlock full readings, email delivery, and saved profiles.")
                if st.button("Log in", width="stretch"):
                    st.login("auth0")
