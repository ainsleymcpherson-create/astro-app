"""
weekly_transits_signup_page.py

Ask an Astrologer ($3, one specific question answered) -- the last
of what used to be three products on this page. Weekly Transits and
One-Time Transit Reading moved to Advanced Readings, since they fit
that page's "pick a category, fill in birth data, pay" shape once it
grew a Transits category of its own. Ask an Astrologer stays here on
its own, since its open-ended question field doesn't fit that shape.

Deliberately no login required -- meant to be a simple purchase
(name, birth data, question, email, pay), not something requiring a
full account.

Creates a Stripe Checkout Session with the collected data attached as
metadata (Stripe hands the same metadata back on the webhook event,
so nothing needs to be held in a separate "pending signup" table in
between).

IMPORTANT: nothing here ever grants access to anything itself -- not
even a successful-looking redirect back to this page. The reading
only actually gets generated once Stripe confirms payment via webhook
(see email_worker/app.py's /stripe-webhook route). This page's job
ends at handing off to Stripe.
"""

import os
from datetime import date as date_type, time as time_type

import streamlit as st

from birth_input import geocode_location_quick

st.title("🌙 Astrology Services")
st.write("**Ask an Astrologer** — one specific question, answered using your "
         "actual chart. **$3**, one-time.")

if "STRIPE_SECRET_KEY" not in os.environ or "STRIPE_ASK_ASTROLOGER_PRICE_ID" not in os.environ:
    st.warning("This isn't available right now — check back soon.")
    st.stop()

if st.query_params.get("signup") == "success":
    st.success("Payment received! Check your inbox shortly.", icon="🎉")
elif st.query_params.get("signup") == "cancelled":
    st.info("Checkout was cancelled — no charge was made.")

st.divider()

name = st.text_input("Your name", help="Used to address you in your reading.")
email = st.text_input("Email address", help="Your reading gets sent here.")

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
        help="An exact birth time is required here — this needs your houses.",
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

question = st.text_area(
    "Your question",
    max_chars=500,
    placeholder="e.g. \"Should I take the job offer I just received?\"",
    help="One specific question — this purchase covers one question, "
         "answered once.",
)

st.divider()

if st.button("Ask my question — $3", width="stretch", type="primary"):
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
    if not question.strip():
        errors.append("Please enter your question.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        import stripe
        stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
        try:
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price": os.environ["STRIPE_ASK_ASTROLOGER_PRICE_ID"],
                    "quantity": 1,
                }],
                customer_email=email.strip(),
                success_url="https://tenthhousereadings.com/weekly-transits?signup=success",
                cancel_url="https://tenthhousereadings.com/weekly-transits?signup=cancelled",
                metadata={
                    "product_type": "ask",
                    "label": name.strip(),
                    "birth_date": birth_date.isoformat(),
                    "birth_time": birth_time.strftime("%H:%M"),
                    "location_str": location_str.strip(),
                    "question": question.strip(),
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
