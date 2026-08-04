"""
weekly_transits_signup_page.py

Combined signup page for all three paid, no-login astrology products:
  - Weekly Transits ($5/month, recurring)
  - One-Time Transit Reading ($7, single purchase)
  - Ask an Astrologer ($10, one specific question answered)

Deliberately no login required for any of these -- meant to be simple
purchases (name, birth data, email, pay), not something requiring a
full account. All three share the same birth-data fields; only Ask an
Astrologer adds a question field on top.

Creates a Stripe Checkout Session with the collected data attached as
metadata (Stripe hands the same metadata back on the webhook event,
so nothing needs to be held in a separate "pending signup" table in
between), tagged with which product was purchased so the webhook
handler knows which of the three flows to run.

IMPORTANT: nothing here ever grants access to anything itself -- not
even a successful-looking redirect back to this page. Every one of
these three flows only actually happens once Stripe confirms payment
via webhook (see email_worker/app.py's /stripe-webhook route). This
page's job ends at handing off to Stripe.
"""

import os
from datetime import date as date_type, time as time_type

import streamlit as st

from birth_input import geocode_location_quick

st.title("🌙 Astrology Services")

if "STRIPE_SECRET_KEY" not in os.environ or "DATABASE_URL" not in os.environ:
    st.warning("These aren't available right now — check back soon.")
    st.stop()

if st.query_params.get("signup") == "success":
    st.success(
        "Payment received! Check your inbox shortly.",
        icon="🎉",
    )
elif st.query_params.get("signup") == "cancelled":
    st.info("Checkout was cancelled — no charge was made.")

st.divider()

PRODUCTS = {
    "Weekly Transits — $5/month": {
        "key": "weekly",
        "price_env": "STRIPE_WEEKLY_TRANSITS_PRICE_ID",
        "stripe_mode": "subscription",
        "description": "A short reading of that week's transits against your own "
                        "chart, delivered every Monday morning. Cancel anytime.",
        "button_label": "Sign me up — $5/month",
    },
    "One-Time Transit Reading — $7": {
        "key": "one_time",
        "price_env": "STRIPE_ONE_TIME_TRANSIT_PRICE_ID",
        "stripe_mode": "payment",
        "description": "A full, in-depth reading of the current transits against "
                        "your chart — a single reading, emailed shortly after payment.",
        "button_label": "Get my reading — $7",
    },
    "Ask an Astrologer — $10": {
        "key": "ask",
        "price_env": "STRIPE_ASK_ASTROLOGER_PRICE_ID",
        "stripe_mode": "payment",
        "description": "Ask one specific question — anything from \"should I take "
                        "this job\" to \"what does this transit mean for me\" — and "
                        "get a real, focused answer grounded in your actual chart.",
        "button_label": "Ask my question — $10",
    },
}

product_choice = st.radio("What would you like?", options=list(PRODUCTS.keys()))
product = PRODUCTS[product_choice]
st.caption(product["description"])

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
        help="An exact birth time is required here — none of these three "
             "readings work without one, since they all need your houses.",
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

theme = None
question = None

if product["key"] == "weekly":
    theme = st.radio(
        "Reading theme",
        options=["General", "Romantic", "Career"],
        help="What your weekly reading focuses on. Changeable anytime later "
             "via a link included in your emails.",
    )
elif product["key"] == "ask":
    question = st.text_area(
        "Your question",
        max_chars=500,
        placeholder="e.g. \"Should I take the job offer I just received?\"",
        help="One specific question — this purchase covers one question, "
             "answered once.",
    )

st.divider()

if st.button(product["button_label"], width="stretch", type="primary"):
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
    if product["key"] == "ask" and not (question or "").strip():
        errors.append("Please enter your question.")

    if errors:
        for e in errors:
            st.error(e)
    elif product["price_env"] not in os.environ:
        st.error("This option isn't fully configured yet — please try again later.")
    else:
        import stripe
        stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
        try:
            metadata = {
                "product_type": product["key"],
                "label": name.strip(),
                "birth_date": birth_date.isoformat(),
                "birth_time": birth_time.strftime("%H:%M"),
                "location_str": location_str.strip(),
            }
            if theme:
                metadata["theme"] = theme
            if question:
                metadata["question"] = question.strip()

            checkout_session = stripe.checkout.Session.create(
                mode=product["stripe_mode"],
                line_items=[{
                    "price": os.environ[product["price_env"]],
                    "quantity": 1,
                }],
                customer_email=email.strip(),
                success_url="https://tenthhousereadings.com/weekly-transits?signup=success",
                cancel_url="https://tenthhousereadings.com/weekly-transits?signup=cancelled",
                metadata=metadata,
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
