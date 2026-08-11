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
st.info("✨ All-Access subscriptions coming soon.")
