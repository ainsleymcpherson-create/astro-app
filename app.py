"""
app.py

Entrypoint for the Tenth House Readings app. Uses Streamlit's native
multi-page navigation (st.navigation + st.Page) to switch between
pages. This file itself stays intentionally small -- it's just the
router. All the actual logic lives in the page files.
"""

import os

# Loads .env into os.environ for local development. In production
# (Streamlit Cloud/Render), .env won't exist -- load_dotenv() just
# does nothing in that case, since real environment variables are
# already set by the platform. This makes it safe to leave in
# permanently rather than needing to strip it out before deploying.
from dotenv import load_dotenv
load_dotenv()

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

# --- Confirm an "add another login email" request from My Account ---
# The email-change request itself never modifies anything -- clicking
# this link is the actual proof the person controls the new inbox, so
# this is where the new email actually gets linked (see
# profiles_db.confirm_email_change).
if "confirm_email" in st.query_params and "DATABASE_URL" in os.environ:
    from profiles_db import confirm_email_change
    _confirm_token = st.query_params["confirm_email"]
    del st.query_params["confirm_email"]
    _confirmed, _confirm_result = confirm_email_change(_confirm_token)
    if _confirmed:
        st.success(
            f"Email confirmed! You can now log in with {_confirm_result} too — "
            f"both reach the same account.",
            icon="✅",
        )
    else:
        st.info(_confirm_result)

# --- Claim a $3 reading unlock chosen for in-app delivery ---
# Stripe's success_url redirect is NEVER trusted on its own to grant
# anything -- same rule the webhook itself follows (see
# email_worker/app.py's stripe_webhook docstring). This block
# re-verifies the payment directly against Stripe's API using the
# Checkout Session ID before it stores anything in session_state or
# hands control to a reading page, so a forged or guessed query
# param can't grant a free reading.
if "unlock_session_id" in st.query_params and "STRIPE_SECRET_KEY" in os.environ:
    _unlock_session_id = st.query_params["unlock_session_id"]
    del st.query_params["unlock_session_id"]
    # Session-scoped, not a database record -- good enough to stop the
    # obvious "hit refresh/back and claim it twice" case within one
    # browser session without needing new persistent storage for a $3
    # product. It does not stop the link being reused from a different
    # browser/session; that's an accepted tradeoff at this price point.
    _claimed_ids = st.session_state.setdefault("_claimed_unlock_session_ids", set())
    if _unlock_session_id in _claimed_ids:
        st.info("That reading has already been generated. Check the "
                "page you were on, or your email if you chose that "
                "delivery option instead.")
    else:
        try:
            import stripe
            stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
            _checkout_session = stripe.checkout.Session.retrieve(_unlock_session_id)
        except Exception as e:
            _checkout_session = None
            st.error(f"Couldn't verify that payment ({type(e).__name__}: {e}). "
                      "If you were just charged, contact support and we'll sort it out.")
        if _checkout_session is not None:
            _metadata = _checkout_session.get("metadata") or {}
            _paid = _checkout_session.get("payment_status") == "paid"
            _is_unlock = _metadata.get("product_type") == "reading_unlock"
            _is_in_app = _metadata.get("delivery") == "in_app"
            if not (_paid and _is_unlock and _is_in_app):
                # Covers: payment didn't actually complete, this session
                # ID belongs to a different product, or the person chose
                # email delivery (in which case there's nothing to claim
                # here -- the webhook already handles it separately).
                st.info("Nothing to claim here. If you chose email "
                        "delivery, check your inbox in a few minutes.")
            else:
                _claimed_ids.add(_unlock_session_id)
                _reading_type = _metadata.get("reading_type", "General")
                _target_page = {
                    "General": "personal_readings_page.py",
                    "Career / Work": "personal_readings_page.py",
                    "Professional Synastry": "synastry_readings_page.py",
                    "Relationship Synastry": "synastry_readings_page.py",
                    "Parent/Child Synastry": "synastry_readings_page.py",
                }.get(_reading_type, "deep_dive_readings_page.py")
                st.session_state["_unlock_claim"] = dict(_metadata)
                st.switch_page(_target_page)

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
                    try:
                        init_schema()
                    except Exception:
                        # A timeout here (lock contention from another
                        # connection, most plausibly) shouldn't crash
                        # the entire login flow over what's usually a
                        # no-op schema check anyway -- these columns
                        # almost certainly already exist from an
                        # earlier successful run. Deliberately NOT
                        # caught inside init_schema itself: letting the
                        # exception reach here means @st.cache_resource
                        # never caches a false "success," so the next
                        # login attempt genuinely retries the migration
                        # instead of silently skipping it forever.
                        st.warning(
                            "Some account features may be briefly limited "
                            "while the database catches up — try refreshing "
                            "in a moment."
                        )
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
