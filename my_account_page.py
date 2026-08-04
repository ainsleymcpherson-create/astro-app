"""
my_account_page.py

A dedicated, full-width account page -- everything that used to live
cramped inside the sidebar's "My Profiles" section, given proper room:
account info, Full Access subscription status (with a real cancel
button, not just a status readout), saved birth profiles, and
one-time purchase history.

Requires login -- this is explicitly account-level, unlike most of
the rest of this app which works fully anonymously. Fails safe (shows
a login prompt rather than crashing) if auth or the database aren't
configured, same pattern as everywhere else in this app.
"""

import os

import streamlit as st

from profiles_db import safe_user_email

st.title("👤 My Account")

if "auth" not in st.secrets or not st.user.is_logged_in:
    st.info("Log in from the sidebar to see your account, subscriptions, and "
             "saved profiles.")
    st.stop()

user_email = safe_user_email()
if not user_email:
    st.info("Still finishing signing you in — try refreshing in a moment.")
    st.stop()

if "DATABASE_URL" not in os.environ:
    st.warning("Account features aren't available right now — check back soon.")
    st.stop()

st.caption(f"Signed in as {user_email}")
st.divider()

# --- Full Access subscription ---
st.subheader("Full Access Subscription")
from profiles_db import get_subscription_details
sub = get_subscription_details(user_email)
if sub and sub.get("active"):
    st.success("Active — unlimited full readings across Personal, Synastry, "
               "and Deep Dive.", icon="✅")
    if st.button("Cancel subscription"):
        if "STRIPE_SECRET_KEY" in os.environ and sub.get("stripe_subscription_id"):
            import stripe
            stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
            try:
                stripe.Subscription.cancel(sub["stripe_subscription_id"])
                from profiles_db import deactivate_subscription_by_id
                deactivate_subscription_by_id(sub["stripe_subscription_id"])
                st.success("Subscription cancelled.")
                st.rerun()
            except Exception as e:
                st.error(f"Something went wrong cancelling: {e}")
        else:
            st.error("Couldn't find a subscription to cancel.")
else:
    st.write("Not subscribed. Get unlimited full readings + email delivery "
             "across Personal, Synastry, and Deep Dive for $10/month.")
    st.page_link("advanced_readings_page.py", label="Get Full Access", icon="✨")

st.divider()

# --- Saved profiles ---
st.subheader("Saved Profiles")
from profiles_db import list_profiles, delete_profile
saved = list_profiles(user_email)
if not saved:
    st.caption("No saved profiles yet — save one from any reading page.")
for p in saved:
    with st.container(border=True):
        col_label, col_delete = st.columns([3, 1])
        with col_label:
            st.write(f"**{p['label']}**")
            _time_str = p["birth_time"].strftime("%I:%M %p") if p.get("birth_time") else "time unknown"
            _bd = p["birth_date"]
            _bd_str = f"{_bd.strftime('%B')} {_bd.day}, {_bd.year}" if hasattr(_bd, "strftime") else str(_bd)
            st.caption(f"{_bd_str} "
                       f"at {_time_str} — {p['location_str']}")
        with col_delete:
            if st.button("🗑️", key=f"acct_del_{p['id']}", help=f"Delete \"{p['label']}\""):
                delete_profile(p["id"], user_email)
                st.rerun()
        if p.get("weekly_transits"):
            st.caption(f"📅 Weekly transits: active ({p.get('transit_theme', 'General')})")

st.divider()

# --- Purchase history ---
st.subheader("Purchase History")
from profiles_db import list_purchase_history
history = list_purchase_history(user_email)
if not history:
    st.caption("No one-time purchases yet.")
for h in history:
    with st.container(border=True):
        col_detail, col_amount = st.columns([3, 1])
        with col_detail:
            st.write(h.get("detail") or h.get("product_type"))
            _created = h.get("created_at")
            _date_str = f"{_created.strftime('%B')} {_created.day}, {_created.year}" if hasattr(_created, "strftime") else str(_created)
            st.caption(_date_str)
        with col_amount:
            _cents = h.get("amount_cents")
            if _cents:
                st.write(f"${_cents / 100:.2f}")
