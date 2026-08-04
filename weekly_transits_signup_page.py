"""
weekly_transits_signup_page.py

Standalone signup page for the paid weekly transits product ($5/month
via Stripe) — deliberately no login required, since this is meant to
be a simple, newsletter-style commitment (name, birth data, email,
pay) rather than something requiring a full account.

Collects birth data and a reading theme, creates a Stripe Checkout
Session with that data attached as metadata (Stripe hands the same
metadata back on the webhook event, so nothing needs to be held in a
separate "pending signup" table in between), and sends the person to
Stripe's hosted payment page.

IMPORTANT: the actual profile only gets created once Stripe confirms
payment via webhook (see email_worker/app.py's /stripe-webhook route)
— never here, and never based on Stripe's success_url redirect alone,
since that redirect can fire without payment actually completing.
This page's job ends at handing off to Stripe; it doesn't and
shouldn't grant access to anything itself.
"""

import os
from datetime import date as date_type, time as time_type

import streamlit as st

from birth_input import geocode_location_quick

st.title("🌙 Weekly Transits")
st.write(
    "A short reading of that week's transits against your own chart, "
    "delivered to your inbox every Monday morning — **$5/month, cancel "
    "anytime.** No account needed; just your birth details and an email "
    "address."
)

if "STRIPE_SECRET_KEY" not in os.environ or "STRIPE_WEEKLY_TRANSITS_PRICE_ID" not in os.environ \
        or "DATABASE_URL" not in os.environ:
    st.warning("Weekly transit signups aren't available right now — check back soon.")
    st.stop()

if st.query_params.get("signup") == "success":
    st.success(
        "Payment received! Your first weekly transit reading will arrive "
        "this Monday.",
        icon="🎉",
    )
elif st.query_params.get("signup") == "cancelled":
    st.info("Checkout was cancelled — no charge was made.")

st.divider()

name = st.text_input("Your name", help="Used to address you in your readings.")
email = st.text_input("Email address", help="Your weekly reading gets sent here.")

col1, col2, col3 = st.columns([1, 1.3, 1])
with col1:
    birth_date = st.date_input(
        "Birth date",
        value=date_type(1990, 1, 1),
        min_value=date_type(1900, 1, 1),
        max_value=date_type.today(),
        help="Tap to open the calendar picker.",
    )
with col2:
    birth_time = st.time_input(
        "Birth time",
        value=time_type(12, 0),
        help="An exact birth time is required here — weekly transits need "
             "your houses, which can't be computed without one. (This is "
             "different from readings elsewhere on the site, which can "
             "work without a known birth time.)",
    )
with col3:
    location_str = st.text_input(
        "Birth location",
        placeholder="City, State/Country",
        help="Be specific — add state/country if the place name is common.",
    )
    if location_str.strip():
        _loc_found, _loc_address = geocode_location_quick(location_str)
        if _loc_found:
            st.caption(f"✓ {_loc_address}")
        else:
            st.caption("Location not yet confirmed — checked before payment.")

theme = st.radio(
    "Reading theme",
    options=["General", "Romantic", "Career"],
    help="What your weekly reading focuses on. Changeable anytime later "
         "via a link included in your emails.",
)

st.divider()

if st.button("Sign me up — $5/month", width="stretch", type="primary"):
    errors = []
    if not name.strip():
        errors.append("Please enter your name.")
    if not email.strip() or "@" not in email:
        errors.append("Please enter a valid email address.")
    if not location_str.strip():
        errors.append("Please enter your birth location.")
    else:
        _found, _ = geocode_location_quick(location_str)
        if not _found:
            errors.append("Couldn't confirm that location — please check it and try again.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        import stripe
        stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
        try:
            checkout_session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{
                    "price": os.environ["STRIPE_WEEKLY_TRANSITS_PRICE_ID"],
                    "quantity": 1,
                }],
                customer_email=email.strip(),
                success_url="https://tenthhousereadings.com/?signup=success",
                cancel_url="https://tenthhousereadings.com/?signup=cancelled",
                # Carries the collected birth data through to the webhook
                # handler, which is where the actual profile gets created
                # — Stripe returns this same metadata on the confirmed
                # payment event, so nothing needs to be stored separately
                # in the meantime.
                metadata={
                    "label": name.strip(),
                    "birth_date": birth_date.isoformat(),
                    "birth_time": birth_time.strftime("%H:%M"),
                    "location_str": location_str.strip(),
                    "theme": theme,
                },
            )
            st.success("Almost done — click below to complete your payment securely with Stripe.")
            st.link_button(
                "Proceed to Secure Checkout →",
                checkout_session.url,
                width="stretch",
                type="primary",
            )
        except Exception as e:
            st.error(f"Something went wrong setting up checkout: {e}")
