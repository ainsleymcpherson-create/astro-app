"""
advanced_readings_page.py

A direct path to paying for a full reading, without first needing to
generate a free summary elsewhere.

Covers four reading categories in one place:
  - Personal, Synastry, Deep Dive: $3 one-time unlock for a single
    reading, or $10/month (requires login) for unlimited full
    readings across all three
  - Transits: moved here from the Astrology Services page, since it
    fits the same "pick a category, fill in birth data, pay" shape --
    Weekly Transits ($5/month, with a theme choice) or a One-Time
    Transit reading ($7). These keep their own separate pricing and
    Stripe products; they were never part of the $3/$10 unlock
    structure and still aren't.

Ask an Astrologer stays on its own page (Astrology Services) -- it
needs an open-ended question field that doesn't fit this page's
birth-data-plus-category shape.
"""

import os
from datetime import date as date_type, time as time_type

import streamlit as st

from birth_input import geocode_location_quick
from profiles_db import safe_user_email


def get_secret(name: str):
    """Same lookup pattern used throughout this app -- Streamlit
    secrets first, falling back to a plain environment variable."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name)


def enqueue_full_reading_email(job_payload: dict) -> tuple[bool, str]:
    """
    Publishes a job to QStash, which calls the email worker to
    generate the full reading and email it -- same mechanism already
    used on Personal/Synastry/Deep Dive for "Generate Summary and
    Email Full Reading", reused here so a subscriber can generate a
    reading directly on this page instead of being told to go
    elsewhere.
    """
    qstash_token = get_secret("QSTASH_TOKEN")
    worker_url = get_secret("EMAIL_WORKER_URL")
    if not qstash_token or not worker_url:
        return False, "Email delivery isn't configured yet — please try again later."
    try:
        qstash_url = get_secret("QSTASH_URL") or "https://qstash-us-east-1.upstash.io"
        os.environ["QSTASH_URL"] = qstash_url
        from qstash import QStash
        client = QStash(qstash_token)
        client.message.publish_json(url=worker_url, body=job_payload, timeout="300s")
        return True, "Your full reading is on its way — check your email in a few minutes."
    except Exception as e:
        return False, f"Couldn't queue the full reading ({type(e).__name__}: {e})."

st.title("✨ Advanced Readings")
st.write(
    "Get the complete, in-depth version of any reading — emailed to you. "
    "**\\$3** unlocks a single reading, or **\\$10/month** (requires logging "
    "in) unlocks unlimited full readings across Personal, Synastry, and "
    "Deep Dive. Weekly and one-time transit readings are also available "
    "here, with their own separate pricing."
)

if "STRIPE_SECRET_KEY" not in os.environ:
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
    "Transits": ["Weekly Transits", "One-Time Transit"],
}
SYNASTRY_READING_TYPES = ("Professional Synastry", "Relationship Synastry", "Parent/Child Synastry")

_selector_col, _ = st.columns([2, 1])
with _selector_col:
    category = st.segmented_control(
        "Category", options=list(CATEGORIES.keys()), default="Personal", required=True,
    )
    reading_type = st.segmented_control(
        "Reading type", options=CATEGORIES[category],
        default=CATEGORIES[category][0], required=True,
        key=f"reading_type_{category}",
    )
    transit_theme = None
    if reading_type == "Weekly Transits":
        transit_theme = st.segmented_control(
            "Reading theme", options=["General", "Romantic", "Career"],
            default="General", required=True,
            help="What your weekly reading focuses on. Changeable anytime "
                 "later via a link included in your emails.",
        )

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
         "here, including both transit options, needs an exact birth time "
         "to compute houses correctly.",
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
if category == "Transits":
    # Weekly Transits always stays separately priced, even for Full
    # Access subscribers -- it's a recurring email product, not a
    # one-time reading, and was explicitly excluded from what the
    # subscription covers. One-Time Transit is different: it's a
    # single, in-app-style reading like Personal/Synastry/Deep Dive,
    # so Full Access covers it the same way.
    _is_logged_in = "auth" in st.secrets and st.user.is_logged_in
    _user_email = safe_user_email() if _is_logged_in else None
    _has_full_access = False
    if _user_email and "DATABASE_URL" in os.environ:
        from profiles_db import has_active_subscription
        _has_full_access = has_active_subscription(_user_email)

    if reading_type == "One-Time Transit" and _has_full_access:
        st.subheader("One-Time Transit Reading")
        st.success("✅ You have Full Access — generate this reading directly, no charge.")
        if st.button("Generate Full Reading", width="stretch", type="primary"):
            errors = []
            if not label_a.strip():
                errors.append("Please enter your name.")
            if not email.strip() or "@" not in email:
                errors.append("Please enter a valid email address.")
            if not location_str.strip():
                errors.append("Please enter your birth location.")
            elif not geocode_location_quick(location_str)[0]:
                errors.append("Couldn't confirm that location — please check it and try again.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                # "Transits" (not "One-Time Transit") is the internal
                # reading_type value _process_reading_job on the
                # worker actually recognizes -- confirmed directly
                # against the worker's code before wiring this up.
                job_payload = {
                    "reading_type": "Transits",
                    "datetime_str": f"{birth_date.strftime('%B %d, %Y')} {birth_time_val.strftime('%I:%M %p')}",
                    "location_str": location_str.strip(),
                    "unknown_time": unknown_time,
                    "person_name": label_a.strip() or None,
                    "email": email.strip(),
                }
                success, message = enqueue_full_reading_email(job_payload)
                if success:
                    st.success(message)
                else:
                    st.error(message)

    else:
        # Weekly and one-time transits keep their own separate pricing --
        # never part of the $3/$10 unlock structure below, so this is a
        # genuinely different purchase flow, not a variation of it.
        if reading_type == "Weekly Transits":
            st.subheader("Weekly Transits")
            st.write("**\\$5/month**, cancel anytime.")
            button_label = "Sign me up — $5/month"
            stripe_mode = "subscription"
            price_env = "STRIPE_WEEKLY_TRANSITS_PRICE_ID"
        else:
            st.subheader("One-Time Transit Reading")
            st.write("**\\$7**, one-time.")
            button_label = "Get my reading — $7"
            stripe_mode = "payment"
            price_env = "STRIPE_ONE_TIME_TRANSIT_PRICE_ID"

        if price_env not in os.environ:
            st.error("This option isn't fully configured yet — please try again later.")
        elif st.button(button_label, width="stretch", type="primary"):
            errors = []
            if not label_a.strip():
                errors.append("Please enter your name.")
            if not email.strip() or "@" not in email:
                errors.append("Please enter a valid email address.")
            if not location_str.strip():
                errors.append("Please enter your birth location.")
            elif not geocode_location_quick(location_str)[0]:
                errors.append("Couldn't confirm that location — please check it and try again.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                import stripe
                stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
                try:
                    metadata = {
                        "product_type": "weekly" if reading_type == "Weekly Transits" else "one_time",
                        "label": label_a.strip(),
                        "birth_date": birth_date.isoformat(),
                        "birth_time": birth_time_val.strftime("%H:%M"),
                        "location_str": location_str.strip(),
                    }
                    if reading_type == "Weekly Transits":
                        metadata["theme"] = transit_theme

                    checkout_session = stripe.checkout.Session.create(
                        mode=stripe_mode,
                        line_items=[{"price": os.environ[price_env], "quantity": 1}],
                        customer_email=email.strip(),
                        success_url="https://tenthhousereadings.com/advanced-readings?signup=success",
                        cancel_url="https://tenthhousereadings.com/advanced-readings?signup=cancelled",
                        metadata=metadata,
                    )
                    st.success("Click below to complete your payment securely with Stripe.")
                    st.link_button("Proceed to Secure Checkout →", checkout_session.url, width="stretch", type="primary")
                except Exception as e:
                    st.error(f"Something went wrong setting up checkout: {e}")

else:
    _is_logged_in = "auth" in st.secrets and st.user.is_logged_in
    _user_email = safe_user_email() if _is_logged_in else None
    _has_full_access = False
    if _user_email and "DATABASE_URL" in os.environ:
        from profiles_db import has_active_subscription
        _has_full_access = has_active_subscription(_user_email)

    if _has_full_access:
        # Already paying $10/month for unlimited access -- showing the
        # $3/$10 purchase columns here would be actively confusing
        # (why would a subscriber need to pay again?), so this
        # replaces them entirely with a direct path to the reading
        # itself, reusing the same generate-and-email mechanism
        # Personal/Synastry/Deep Dive already use.
        st.success("✅ You have Full Access — generate this reading directly, no charge.")
        if st.button("Generate Full Reading", width="stretch", type="primary"):
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
                job_payload = {
                    "reading_type": reading_type,
                    "datetime_str": f"{birth_date.strftime('%B %d, %Y')} {birth_time_val.strftime('%I:%M %p')}",
                    "location_str": location_str.strip(),
                    "unknown_time": unknown_time,
                    "person_name": label_a.strip() or None,
                    "email": email.strip(),
                }
                if reading_type in SYNASTRY_READING_TYPES:
                    job_payload["datetime_str_b"] = (
                        f"{birth_date_b.strftime('%B %d, %Y')} {birth_time_val_b.strftime('%I:%M %p')}"
                    )
                    job_payload["location_str_b"] = location_str_b.strip()
                    job_payload["unknown_time_b"] = unknown_time_b
                    job_payload["person_name_b"] = (label_b or "").strip() or None
                    if reading_type == "Relationship Synastry" and relationship_stage:
                        job_payload["relationship_stage"] = relationship_stage

                success, message = enqueue_full_reading_email(job_payload)
                if success:
                    st.success(message)
                else:
                    st.error(message)

    else:
        col_unlock, col_sub = st.columns(2)

        with col_unlock:
            st.subheader("Just this reading")
            st.write("**\\$3**, one-time.")
            if "STRIPE_ONE_TIME_READING_UNLOCK_PRICE_ID" not in os.environ:
                st.caption("Not available right now.")
            elif st.button("Unlock this reading — $3", width="stretch", type="primary"):
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
            st.write("**\\$10/month**, all three categories.")
            if not _is_logged_in:
                st.info("Log in from the sidebar to subscribe.")
            elif "STRIPE_FULL_ACCESS_PRICE_ID" not in os.environ:
                st.caption("Not available right now.")
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
