"""
advanced_readings_page.py

A direct path to paying for a full reading, without first needing to
generate a free summary elsewhere. The $3-per-reading unlock also
exists as a follow-on prompt after a free summary on Personal,
Synastry, and Deep Dive -- this page exists because that placement
alone wasn't a real purchase path for someone who already knows they
want the full version and doesn't want to go through the free flow
first to get there.

Covers all three reading categories (Personal, Synastry, Deep Dive)
in one place, with two ways to pay:
  - $3, one-time, unlocks just the specific reading configured here
  - $10/month, requires login (so there's an account to manage it
    under), unlocks unlimited full readings across all three
    categories going forward

Deliberately does NOT include the Astrology Services products
(Weekly Transits, One-Time Transit, Ask an Astrologer) -- those stay
on their own page with their own pricing.
"""

import os
from datetime import date as date_type, time as time_type

import streamlit as st

from birth_input import geocode_location_quick
from profiles_db import safe_user_email

st.title("✨ Advanced Readings")
st.write(
    "Get the complete, in-depth version of any reading — emailed to you. "
    "**\\$3** unlocks a single reading, or **\\$10/month** (requires logging "
    "in) unlocks unlimited full readings across Personal, Synastry, and "
    "Deep Dive."
)

if "STRIPE_SECRET_KEY" not in os.environ or "STRIPE_ONE_TIME_READING_UNLOCK_PRICE_ID" not in os.environ:
    st.warning("Advanced readings aren't available right now — check back soon.")
    st.stop()

if st.query_params.get("signup") == "success":
    st.success("Payment received! Check your inbox shortly.", icon="🎉")
elif st.query_params.get("signup") == "cancelled":
    st.info("Checkout was cancelled — no charge was made.")

st.divider()

CATEGORIES = {
    "Personal": ["General", "Career / Work"],
    "Synastry": ["Professional Synastry", "Relationship Synastry", "Parent/Child Synastry"],
    "Deep Dive": ["Lilith", "Chiron", "North/South Node"],
}
SYNASTRY_READING_TYPES = ("Professional Synastry", "Relationship Synastry", "Parent/Child Synastry")

category = st.radio("Category", options=list(CATEGORIES.keys()), horizontal=True)
reading_type = st.radio("Reading type", options=CATEGORIES[category])

st.divider()

label_a = st.text_input("Your name" if category != "Synastry" else "Person A's name")
email = st.text_input("Email address", help="Your reading gets sent here.")

col1, col2, col3 = st.columns([1, 1.3, 1])
with col1:
    birth_date = st.date_input(
        "Birth date", value=date_type(1990, 1, 1),
        min_value=date_type(1900, 1, 1), max_value=date_type.today(),
    )
with col2:
    birth_time_val = st.time_input("Birth time", value=time_type(12, 0))
with col3:
    location_str = st.text_input("Birth location", placeholder="City, State/Country")
    if location_str.strip():
        _found, _address = geocode_location_quick(location_str)
        st.caption(f"✓ {_address}" if _found else "Location not yet confirmed — checked before payment.")
unknown_time = st.checkbox(
    "I don't know my exact birth time",
    help="Works for General and Career/Work only — every other reading type "
         "here needs an exact birth time to compute houses correctly.",
)

relationship_stage = None
if reading_type in SYNASTRY_READING_TYPES:
    st.divider()
    st.subheader("Person B")
    label_b = st.text_input("Person B's name")
    colb1, colb2, colb3 = st.columns([1, 1.3, 1])
    with colb1:
        birth_date_b = st.date_input(
            "Birth date", value=date_type(1990, 1, 1),
            min_value=date_type(1900, 1, 1), max_value=date_type.today(),
            key="birth_date_b_adv",
        )
    with colb2:
        birth_time_val_b = st.time_input("Birth time", value=time_type(12, 0), key="birth_time_b_adv")
    with colb3:
        location_str_b = st.text_input("Birth location", placeholder="City, State/Country", key="location_str_b_adv")
        if location_str_b.strip():
            _found_b, _address_b = geocode_location_quick(location_str_b)
            st.caption(f"✓ {_address_b}" if _found_b else "Location not yet confirmed — checked before payment.")
    unknown_time_b = st.checkbox("I don't know Person B's exact birth time", key="unknown_time_b_adv")
    if reading_type == "Relationship Synastry":
        relationship_stage = st.selectbox(
            "How long have you been together?",
            options=["New (under 1 year)", "Established (1-5 years)", "Long-term (5+ years)"],
        )
else:
    label_b = birth_date_b = birth_time_val_b = location_str_b = unknown_time_b = None

st.divider()

# --- Purchase options ---
col_unlock, col_sub = st.columns(2)

with col_unlock:
    st.subheader("Just this reading")
    st.write("**$3**, one-time.")
    if st.button("Unlock this reading — $3", width="stretch", type="primary"):
        errors = []
        if not label_a.strip():
            errors.append("Please enter a name.")
        if not email.strip() or "@" not in email:
            errors.append("Please enter a valid email address.")
        if not location_str.strip():
            errors.append("Please enter a birth location.")
        elif not geocode_location_quick(location_str)[0]:
            errors.append("Couldn't confirm that location — please check it and try again.")
        if reading_type in SYNASTRY_READING_TYPES:
            if not (label_b or "").strip():
                errors.append("Please enter Person B's name.")
            if not (location_str_b or "").strip():
                errors.append("Please enter Person B's birth location.")
            elif not geocode_location_quick(location_str_b)[0]:
                errors.append("Couldn't confirm Person B's location — please check it and try again.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            import stripe
            stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
            try:
                metadata = {
                    "product_type": "reading_unlock",
                    "reading_type": reading_type,
                    "label": label_a.strip(),
                    "birth_date": birth_date.isoformat(),
                    "birth_time": birth_time_val.strftime("%H:%M"),
                    "location_str": location_str.strip(),
                    "unknown_time": "true" if unknown_time else "false",
                }
                if reading_type in SYNASTRY_READING_TYPES:
                    metadata["label_b"] = label_b.strip()
                    metadata["birth_date_b"] = birth_date_b.isoformat()
                    metadata["birth_time_b"] = birth_time_val_b.strftime("%H:%M")
                    metadata["location_str_b"] = location_str_b.strip()
                    metadata["unknown_time_b"] = "true" if unknown_time_b else "false"
                    if reading_type == "Relationship Synastry" and relationship_stage:
                        metadata["relationship_stage"] = relationship_stage
                checkout_session = stripe.checkout.Session.create(
                    mode="payment",
                    line_items=[{"price": os.environ["STRIPE_ONE_TIME_READING_UNLOCK_PRICE_ID"], "quantity": 1}],
                    customer_email=email.strip(),
                    success_url="https://tenthhousereadings.com/advanced-readings?signup=success",
                    cancel_url="https://tenthhousereadings.com/advanced-readings?signup=cancelled",
                    metadata=metadata,
                )
                st.success("Click below to complete your payment securely with Stripe.")
                st.link_button("Proceed to Secure Checkout →", checkout_session.url, width="stretch", type="primary")
            except Exception as e:
                st.error(f"Something went wrong setting up checkout: {e}")

with col_sub:
    st.subheader("Unlimited full readings")
    st.write("**$10/month**, all three categories.")
    _is_logged_in = "auth" in st.secrets and st.user.is_logged_in
    _user_email = safe_user_email() if _is_logged_in else None
    if not _is_logged_in:
        st.info("Log in from the sidebar to subscribe.")
    elif "STRIPE_FULL_ACCESS_PRICE_ID" not in os.environ:
        st.caption("Not available right now.")
    else:
        from profiles_db import has_active_subscription
        if _user_email and has_active_subscription(_user_email):
            st.success("You already have Full Access — just generate the reading "
                       "directly on its own page.", icon="✅")
        elif st.button("Subscribe — $10/month", width="stretch"):
            import stripe
            stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
            try:
                checkout_session = stripe.checkout.Session.create(
                    mode="subscription",
                    line_items=[{"price": os.environ["STRIPE_FULL_ACCESS_PRICE_ID"], "quantity": 1}],
                    customer_email=_user_email,
                    success_url="https://tenthhousereadings.com/advanced-readings?signup=success",
                    cancel_url="https://tenthhousereadings.com/advanced-readings?signup=cancelled",
                    metadata={"product_type": "full_access_subscription", "label": _user_email},
                )
                st.link_button("Proceed to Secure Checkout →", checkout_session.url, width="stretch", type="primary")
            except Exception as e:
                st.error(f"Something went wrong setting up checkout: {e}")
