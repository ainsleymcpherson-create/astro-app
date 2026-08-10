"""
my_account_page.py

A dedicated, full-width account page -- everything that used to live
cramped inside the sidebar's "My Profiles" section, given proper room:
an editable display name, the account's login email (plus a verified
flow for adding a second login email -- see profiles_db.py's
account_email_aliases/email_change_requests tables), Full Access
subscription status (with a real cancel button, not just a status
readout), saved birth profiles, and one-time purchase history.

Requires login -- this is explicitly account-level, unlike most of
the rest of this app which works fully anonymously. Fails safe (shows
a login prompt rather than crashing) if auth or the database aren't
configured, same pattern as everywhere else in this app.

Deliberately avoids st.stop() for these guard conditions, using
nested if/else instead -- app.py's sidebar-building code runs inside
a finally block specifically so it survives whatever happens on the
active page, but that depends on exceptions (including the one
st.stop() raises internally) actually propagating back out through
pg.run() the way plain Python exceptions do. Since that wasn't
reliably true in production, this sidesteps the question entirely:
a page that never raises anything can't be the reason the sidebar
goes missing.
"""

import os

import streamlit as st

from profiles_db import safe_user_email


def _get_secret(name: str):
    """Same lookup pattern used in the reading pages (Colab secret,
    then Streamlit secrets, then a plain env var) -- duplicated here
    rather than imported, since importing another page file would
    also execute all of ITS top-level st.* calls (Streamlit runs each
    page file as its own standalone script)."""
    try:
        from google.colab import userdata
        val = userdata.get(name)
        if val:
            return val
    except Exception:
        pass
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name)


def _enqueue_email_change_confirmation(new_email: str, token: str) -> tuple[bool, str]:
    """
    Publishes a job to QStash asking the email worker to send the
    "confirm your new email" link -- reuses the exact same
    /generate-and-email endpoint and QStash credentials the reading-
    delivery emails already use (see enqueue_full_reading_email in
    personal_readings_page.py), just with a different "kind" in the
    payload so the worker sends a plain confirmation email instead of
    generating a reading. Returns (success, message) rather than
    raising, matching that same pattern.
    """
    qstash_token = _get_secret("QSTASH_TOKEN")
    worker_url = _get_secret("EMAIL_WORKER_URL")
    if not qstash_token or not worker_url:
        return False, (
            "Email delivery isn't configured yet (missing QSTASH_TOKEN "
            "or EMAIL_WORKER_URL in secrets), so a confirmation email "
            "can't be sent right now."
        )
    try:
        qstash_url = _get_secret("QSTASH_URL") or "https://qstash-us-east-1.upstash.io"
        os.environ["QSTASH_URL"] = qstash_url

        from qstash import QStash
        client = QStash(qstash_token)
        client.message.publish_json(
            url=worker_url,
            body={"kind": "email_change_confirmation", "to_email": new_email, "token": token},
            timeout="60s",
        )
        return True, f"Check {new_email} for a confirmation link — it expires in 24 hours."
    except Exception as e:
        return False, f"Couldn't send the confirmation email ({type(e).__name__}: {e})."


st.title("👤 My Account")

if "auth" not in st.secrets or not st.user.is_logged_in:
    st.info("Log in from the sidebar to see your account, subscriptions, and "
             "saved profiles.")
elif not safe_user_email():
    st.info("Still finishing signing you in — try refreshing in a moment.")
elif "DATABASE_URL" not in os.environ:
    st.warning("Account features aren't available right now — check back soon.")
else:
    user_email = safe_user_email()

    # --- Name and email ---
    st.subheader("Account")
    from profiles_db import (
        get_display_name, set_display_name, list_linked_emails, request_email_change,
    )

    _current_name = get_display_name(user_email) or ""
    with st.form("account_name_form"):
        _name_input = st.text_input("Name", value=_current_name, placeholder="Add your name")
        if st.form_submit_button("Save name"):
            set_display_name(user_email, _name_input.strip())
            st.success("Name updated.", icon="✅")
            st.rerun()

    st.text_input("Email", value=user_email, disabled=True,
                   help="This is the email you're currently logged in with.")
    _linked = list_linked_emails(user_email)
    if _linked:
        st.caption("Also linked to this account: " + ", ".join(_linked))

    with st.expander("Add another login email"):
        st.caption("Useful if you sign in with more than one Google account, "
                   "or want a backup way to log in. We'll send a confirmation "
                   "link to the new address before it's linked — nothing "
                   "changes until you click it.")
        with st.form("add_email_form"):
            _new_email_input = st.text_input("New email address", placeholder="you@example.com")
            if st.form_submit_button("Send confirmation email"):
                if not _new_email_input.strip():
                    st.error("Enter an email address first.")
                else:
                    _ok, _result = request_email_change(user_email, _new_email_input.strip())
                    if not _ok:
                        st.error(_result)
                    else:
                        _sent_ok, _sent_msg = _enqueue_email_change_confirmation(
                            _new_email_input.strip().lower(), _result,
                        )
                        if _sent_ok:
                            st.success(_sent_msg, icon="✅")
                        else:
                            st.error(_sent_msg)

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

    # --- Admin-only: active database connections ---
    # Temporary diagnostic tool, not meant to be a permanent feature --
    # added specifically to track down what's holding a lock during the
    # "stuck running sql.query(...)" freeze. Queries Postgres's own
    # pg_stat_activity system view, so it isn't affected by whatever might
    # be blocking this app's own tables. Gated to the admin account only,
    # same pattern used elsewhere in this app for admin-only tools.
    if user_email == "amcpherson89@gmail.com":
        st.divider()
        st.subheader("🔧 Active DB Connections (admin)")
        st.caption("Look for a row with state = \"idle in transaction\" and a "
                   "large duration — that's a connection holding a lock open "
                   "without an active query.")
        from profiles_db import list_active_db_connections
        try:
            connections = list_active_db_connections()
            if not connections:
                st.caption("No active connections found.")
            for c in connections:
                with st.container(border=True):
                    st.write(f"**pid {c.get('pid')}** — state: `{c.get('state')}` — "
                             f"duration: {c.get('duration')}")
                    if c.get("query"):
                        st.code(c["query"], language="sql")
        except Exception as e:
            st.error(f"Couldn't fetch connection info: {e}")
