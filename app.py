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
# pages with one nested group in the same call -- a dict turns EVERY
# key into its own section header, even for sections with only one
# page, which read as redundant (a header reading "Advanced Readings"
# directly above a single link also reading "Advanced Readings").
# Building the visible menu by hand instead, with position="hidden"
# on st.navigation below so its own auto-menu never renders -- routing
# still works exactly the same, this only replaces what's actually
# drawn in the sidebar.
#
# .run() has to actually execute BEFORE any st.page_link() call that
# references these pages -- merely calling st.navigation() and
# holding onto the returned object isn't enough to populate each
# page's url_pathname internally; that registration genuinely happens
# as part of .run() itself running, confirmed by every one of
# Streamlit's own examples only ever calling st.page_link() from
# INSIDE a sub-page's script (which only executes as part of .run()),
# never from the entrypoint before .run() has run. Sidebar content
# added after .run() still renders normally -- Streamlit doesn't tie
# sidebar elements to a strict "before main content" ordering the way
# this might suggest.
pg = st.navigation(
    [home, personal_readings, synastry_readings, deep_dive_readings,
     advanced_readings, weekly_transits, resources, my_account],
    position="hidden",
)
pg.run()

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
