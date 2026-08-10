"""
profiles_db.py

Saved birth-profile storage, backed by Render's PostgreSQL. Lets a
logged-in user save a birth profile once (name, date/time, location —
already-resolved coordinates included, so loading a saved profile
never needs to re-geocode) and reuse it across visits and across
reading types, instead of retyping birth data every single time.

Entirely additive to the app's existing anonymous flow: nothing here
is required to generate a reading. Every function in this module is
only ever called when someone is logged in (checked at the call site
in each page file), so an anonymous visitor's experience is completely
unaffected by any of this.

Uses Streamlit's native SQL connection (st.connection("sql", ...)),
which handles connection pooling and query caching on its own, rather
than managing a raw psycopg2 connection by hand.
"""

from __future__ import annotations
import os
import secrets
from datetime import date as date_type, time as time_type

import streamlit as st
import pandas as pd
from sqlalchemy import text


def safe_user_email() -> str | None:
    """
    st.user.email has been observed to raise AttributeError even when
    st.user.is_logged_in is True — seen in production right alongside
    a "stale or replayed OAuth callback" warning, apparently a brief
    window where Streamlit's session carries a valid login cookie but
    hasn't yet fully populated the OIDC claims dict behind it. Every
    call site that needs the logged-in user's email should go through
    this rather than touching st.user.email directly, so that one
    unlucky rerun during that window degrades gracefully (saved
    profiles just don't load for that rerun) instead of taking down
    the entire page with an uncaught exception.

    Also resolves through account_email_aliases (see
    resolve_account_email): the raw email Auth0 asserts on login is
    NOT necessarily the same email every other table in this file
    keys on. If this person has confirmed an "add another login
    email" request, the raw login email gets swapped out here for
    their account's canonical primary_email, so saved profiles, the
    subscription, and purchase history all stay reachable no matter
    which linked email they actually logged in with. Every existing
    call site gets this for free, with no changes needed elsewhere.
    Falls back to the raw email unresolved if DATABASE_URL isn't set,
    or if the lookup itself fails for any reason — a broken alias
    lookup should degrade to "no aliasing," never to "can't tell who's
    logged in."
    """
    try:
        raw_email = st.user.email
    except AttributeError:
        return None
    if not raw_email or "DATABASE_URL" not in os.environ:
        return raw_email
    try:
        return resolve_account_email(raw_email)
    except Exception:
        return raw_email


def resolve_account_email(logged_in_email: str) -> str:
    """
    Maps a raw, freshly-asserted login email to its account's
    canonical primary_email via account_email_aliases, if a confirmed
    email-change request has ever linked them. Returns the input
    unchanged if there's no alias row for it, which is the case for
    every account that's never used the "add another login email"
    feature — the vast majority of users, so this is a no-op for them.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT primary_email FROM account_email_aliases WHERE alias_email = :alias_email",
        params={"alias_email": logged_in_email},
        ttl=0,
    )
    if df.empty:
        return logged_in_email
    return df.iloc[0]["primary_email"]


def _get_conn():
    """
    Returns the cached SQL connection, built from the DATABASE_URL
    environment variable (set directly on the Render service, same
    pattern as every other secret in this app — not through
    secrets.toml, since this one's an env var, not part of the OIDC
    auth secrets file).

    Three independent safeguards against the "stuck running
    sql.query(...)" symptom observed in production, each covering a
    different point where a hang can happen:

    pool_pre_ping tests each pooled connection with a cheap "SELECT 1"
    before handing it back out, rather than assuming a connection
    that's been sitting idle is still good. Without this, a
    connection the database has already closed server-side (managed
    Postgres services commonly do this after a period of inactivity)
    looks fine to the pool but hangs the next real query sent over it.

    connect_timeout caps how long establishing a brand-new TCP
    connection to the database is allowed to take, in seconds. This is
    NOT the same failure mode pool_pre_ping guards against -- pre-ping
    only re-tests connections already sitting in the pool; this covers
    a hang while opening a connection that was never established in
    the first place (a network hiccup, DNS taking too long, the
    database temporarily unreachable). Without this, that kind of
    stall has no ceiling at all.

    statement_timeout caps how long a query is allowed to run once
    it's actually executing on an already-open connection -- for
    example if it gets stuck behind a lock held by some other
    uncommitted transaction. This is the one added first; keeping it
    alongside connect_timeout now covers the connection-establishment
    stage too, not just the query-execution stage.

    Together these turn every flavor of "hang with no error" into a
    real, catchable error within about 10 seconds, rather than an
    indefinite spinner.
    """
    database_url = os.environ["DATABASE_URL"]
    return st.connection(
        "profiles_db", type="sql", url=database_url,
        pool_pre_ping=True,
        connect_args={
            "options": "-c statement_timeout=10000",
            "connect_timeout": 10,
        },
    )


def init_schema() -> None:
    """
    Creates the saved_profiles table if it doesn't already exist, and
    adds any columns introduced after the table's original creation
    (currently just person_name) to tables that already exist from
    before that column was added -- ADD COLUMN IF NOT EXISTS is
    idempotent, safe to run on every startup regardless of whether the
    table is brand new or has been running for a while already.
    """
    conn = _get_conn()
    with conn.session as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS saved_profiles (
                id SERIAL PRIMARY KEY,
                owner_email TEXT NOT NULL,
                label TEXT NOT NULL,
                birth_date DATE NOT NULL,
                birth_time TIME,
                unknown_time BOOLEAN NOT NULL DEFAULT FALSE,
                location_str TEXT NOT NULL,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                resolved_address TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        session.execute(text(
            "ALTER TABLE saved_profiles ADD COLUMN IF NOT EXISTS person_name TEXT"
        ))
        session.execute(text(
            "ALTER TABLE saved_profiles ADD COLUMN IF NOT EXISTS weekly_transits "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        session.execute(text(
            "ALTER TABLE saved_profiles ADD COLUMN IF NOT EXISTS unsubscribe_token TEXT"
        ))
        session.execute(text(
            "ALTER TABLE saved_profiles ADD COLUMN IF NOT EXISTS transit_theme TEXT "
            "NOT NULL DEFAULT 'General'"
        ))
        session.execute(text(
            "ALTER TABLE saved_profiles ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT"
        ))
        session.execute(text(
            "ALTER TABLE saved_profiles ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT"
        ))
        session.execute(text(
            "ALTER TABLE saved_profiles ADD COLUMN IF NOT EXISTS is_paid_subscriber "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        # Separate table, deliberately -- this tracks the $10/month
        # "full access" plan, which is an ACCOUNT-level entitlement
        # (unlocks full readings across Personal and Synastry, for as
        # long as it's active), not tied to any one saved birth
        # profile the way weekly_transits is. owner_email is the
        # primary key since each account has at most one active plan.
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS account_subscriptions (
                owner_email TEXT PRIMARY KEY,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        # One row per one-time purchase (reading unlocks, one-time
        # transit readings, ask-an-astrologer questions) -- these
        # previously left no trace anywhere once the email went out.
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS purchase_history (
                id SERIAL PRIMARY KEY,
                owner_email TEXT NOT NULL,
                product_type TEXT NOT NULL,
                detail TEXT,
                amount_cents INTEGER,
                stripe_session_id TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        # Cosmetic account-level info that doesn't belong keyed to any
        # single saved birth profile -- currently just a display name.
        # Keyed by primary_email (see account_email_aliases below),
        # never used to look anything else up.
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS account_profile (
                primary_email TEXT PRIMARY KEY,
                display_name TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        # Lets one account be reachable by logging in with more than
        # one email (e.g. after a confirmed "change my email"
        # request). alias_email is a login email that resolves to
        # primary_email -- see resolve_account_email/safe_user_email,
        # which every other table's owner_email lookups go through.
        # Deliberately does NOT touch saved_profiles/
        # account_subscriptions/purchase_history's schema at all:
        # those keep using owner_email exactly as today, they just
        # always receive an already-resolved canonical email now.
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS account_email_aliases (
                alias_email TEXT PRIMARY KEY,
                primary_email TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        # Pending "add another login email" requests. A row here does
        # NOT grant anything by itself -- account_email_aliases only
        # gets a new row once someone actually clicks the confirmation
        # link sent to new_email, proving they control that inbox.
        # used_at makes each token single-use; expires_at bounds how
        # long a stale, unconfirmed request stays valid.
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS email_change_requests (
                token TEXT PRIMARY KEY,
                primary_email TEXT NOT NULL,
                new_email TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP
            )
        """))
        session.commit()


def list_profiles(owner_email: str) -> list[dict]:
    """
    Returns every saved profile belonging to this owner, most
    recently created first. ttl=0 (no caching) since this needs to
    reflect saves/deletes from the same session immediately — a
    profile someone just saved should show up in the picker on the
    very next rerun, not after some cache window expires.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT * FROM saved_profiles WHERE owner_email = :owner_email "
        "ORDER BY created_at DESC",
        params={"owner_email": owner_email},
        ttl=0,
    )
    records = df.to_dict("records")

    # pandas' exact return type for SQL DATE/TIME columns isn't fully
    # consistent across driver/pandas-version combinations -- it can
    # come back as a plain date/time, a pandas.Timestamp, or (for
    # TIME columns via psycopg2) a datetime.timedelta from midnight.
    # st.date_input/st.time_input need exact date/time objects, so
    # normalize explicitly here rather than risk a type mismatch
    # surfacing downstream in every page that loads a saved profile.
    for r in records:
        bd = r.get("birth_date")
        if isinstance(bd, pd.Timestamp):
            r["birth_date"] = bd.date()
        bt = r.get("birth_time")
        if bt is not None:
            if isinstance(bt, pd.Timedelta):
                total_seconds = int(bt.total_seconds())
                r["birth_time"] = time_type(
                    (total_seconds // 3600) % 24, (total_seconds // 60) % 60, total_seconds % 60
                )
            elif isinstance(bt, pd.Timestamp):
                r["birth_time"] = bt.time()

    return records


def save_profile(
    owner_email: str,
    label: str,
    person_name: str | None,
    birth_date: date_type,
    birth_time: time_type | None,
    unknown_time: bool,
    location_str: str,
    latitude: float | None,
    longitude: float | None,
    resolved_address: str | None,
) -> None:
    """Saves a new profile. Does not check for duplicate labels —
    someone might reasonably want two entries both called "Mom" at
    different points, or just re-save with corrected data; the label
    is a convenience name, not a unique identifier."""
    conn = _get_conn()
    with conn.session as session:
        session.execute(text("""
            INSERT INTO saved_profiles
                (owner_email, label, person_name, birth_date, birth_time, unknown_time,
                 location_str, latitude, longitude, resolved_address)
            VALUES
                (:owner_email, :label, :person_name, :birth_date, :birth_time, :unknown_time,
                 :location_str, :latitude, :longitude, :resolved_address)
        """), {
            "owner_email": owner_email,
            "label": label,
            "person_name": person_name,
            "birth_date": birth_date,
            "birth_time": birth_time,
            "unknown_time": unknown_time,
            "location_str": location_str,
            "latitude": latitude,
            "longitude": longitude,
            "resolved_address": resolved_address,
        })
        session.commit()


def update_profile(
    profile_id: int,
    owner_email: str,
    label: str,
    person_name: str | None,
    birth_date: date_type,
    birth_time: time_type | None,
    unknown_time: bool,
    location_str: str,
    latitude: float | None,
    longitude: float | None,
    resolved_address: str | None,
) -> None:
    """Updates an existing profile in place, rather than requiring a
    delete-and-resave to fix a typo'd label or correct a detail.
    Scoped to owner_email as well as id, same reasoning as
    delete_profile — never touch another user's row even if an id
    were somehow guessed."""
    conn = _get_conn()
    with conn.session as session:
        session.execute(text("""
            UPDATE saved_profiles
            SET label = :label,
                person_name = :person_name,
                birth_date = :birth_date,
                birth_time = :birth_time,
                unknown_time = :unknown_time,
                location_str = :location_str,
                latitude = :latitude,
                longitude = :longitude,
                resolved_address = :resolved_address
            WHERE id = :id AND owner_email = :owner_email
        """), {
            "id": profile_id,
            "owner_email": owner_email,
            "label": label,
            "person_name": person_name,
            "birth_date": birth_date,
            "birth_time": birth_time,
            "unknown_time": unknown_time,
            "location_str": location_str,
            "latitude": latitude,
            "longitude": longitude,
            "resolved_address": resolved_address,
        })
        session.commit()


def delete_profile(profile_id: int, owner_email: str) -> None:
    """Deletes a profile — scoped to owner_email as well as id, so
    someone can never delete another user's profile even if they
    somehow guessed or manipulated an id."""
    conn = _get_conn()
    with conn.session as session:
        session.execute(text(
            "DELETE FROM saved_profiles WHERE id = :id AND owner_email = :owner_email"
        ), {"id": profile_id, "owner_email": owner_email})
        session.commit()


def set_weekly_transits(profile_id: int, owner_email: str, enabled: bool) -> None:
    """
    Turns weekly transit emails on or off for a profile. Scoped to
    owner_email, same reasoning as delete_profile/update_profile.

    Generates an unsubscribe_token the FIRST time a profile is turned
    on, if it doesn't already have one -- lazily, rather than giving
    every saved profile a token whether or not it's ever actually
    used for weekly emails. The token is a long, unguessable random
    string (not sequential, not derived from anything predictable)
    since it doubles as the entire authentication for the one-click
    unsubscribe link -- anyone who has it can turn off weekly emails
    for that profile without logging in, by design, so it needs to be
    infeasible to guess or enumerate.
    """
    conn = _get_conn()
    with conn.session as session:
        if enabled:
            session.execute(text("""
                UPDATE saved_profiles
                SET weekly_transits = TRUE,
                    unsubscribe_token = COALESCE(unsubscribe_token, :new_token)
                WHERE id = :id AND owner_email = :owner_email
            """), {
                "id": profile_id,
                "owner_email": owner_email,
                "new_token": secrets.token_urlsafe(32),
            })
        else:
            session.execute(text("""
                UPDATE saved_profiles SET weekly_transits = FALSE
                WHERE id = :id AND owner_email = :owner_email
            """), {"id": profile_id, "owner_email": owner_email})
        session.commit()


def unsubscribe_by_token(token: str) -> dict | None:
    """
    Turns off weekly transit emails for whichever profile owns this
    token, with NO login required -- this is the one-click email-link
    path, deliberately independent of the in-app toggle so someone
    can opt out without needing to sign back in first.

    Returns a dict with the profile's label and stripe_subscription_id
    if a match was found, or None if the token didn't match anything
    (e.g. an already-used/stale link, or a stray guess). The
    stripe_subscription_id is included specifically so the caller can
    also cancel the actual Stripe subscription for paid subscribers --
    this function only ever touches the database; it deliberately
    doesn't call Stripe's API itself, keeping this module free of any
    payment-provider dependency. Turning off the email flag without
    also canceling billing would leave someone still being charged
    $5/month after they've unsubscribed, which is a real problem, not
    just a rough edge.
    """
    conn = _get_conn()
    with conn.session as session:
        result = session.execute(text("""
            UPDATE saved_profiles SET weekly_transits = FALSE
            WHERE unsubscribe_token = :token
            RETURNING label, stripe_subscription_id
        """), {"token": token})
        row = result.fetchone()
        session.commit()
        return {"label": row[0], "stripe_subscription_id": row[1]} if row else None


def list_weekly_subscribers() -> list[dict]:
    """
    Returns every profile (across ALL users) currently opted into
    weekly transit emails, with everything the weekly job needs to
    actually compute and send a reading -- birth data, resolved
    coordinates, owner_email to send to, and unsubscribe_token to
    include in the email. Used only by the worker's weekly job, never
    by the main app.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT * FROM saved_profiles WHERE weekly_transits = TRUE",
        ttl=0,
    )
    records = df.to_dict("records")
    for r in records:
        bd = r.get("birth_date")
        if isinstance(bd, pd.Timestamp):
            r["birth_date"] = bd.date()
        bt = r.get("birth_time")
        if bt is not None:
            if isinstance(bt, pd.Timedelta):
                total_seconds = int(bt.total_seconds())
                r["birth_time"] = time_type(
                    (total_seconds // 3600) % 24, (total_seconds // 60) % 60, total_seconds % 60
                )
            elif isinstance(bt, pd.Timestamp):
                r["birth_time"] = bt.time()
    return records


def create_paid_subscriber_profile(
    label: str,
    birth_date: date_type,
    birth_time: time_type | None,
    unknown_time: bool,
    location_str: str,
    latitude: float | None,
    longitude: float | None,
    resolved_address: str | None,
    theme: str,
    owner_email: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
) -> str:
    """
    Creates a profile from a confirmed Stripe payment -- called ONLY
    from the webhook handler after Stripe's checkout.session.completed
    event, never from the checkout-initiation step itself (a redirect
    to Stripe is not the same as a completed payment; see the
    worker's webhook handler for why this distinction matters).

    Sets weekly_transits and is_paid_subscriber TRUE from the start,
    generates a fresh unsubscribe_token, and returns it directly so
    the webhook handler can include it in the welcome email without a
    second round-trip to look it up.
    """
    conn = _get_conn()
    token = secrets.token_urlsafe(32)
    with conn.session as session:
        session.execute(text("""
            INSERT INTO saved_profiles
                (owner_email, label, birth_date, birth_time, unknown_time,
                 location_str, latitude, longitude, resolved_address,
                 transit_theme, weekly_transits, is_paid_subscriber,
                 stripe_customer_id, stripe_subscription_id, unsubscribe_token)
            VALUES
                (:owner_email, :label, :birth_date, :birth_time, :unknown_time,
                 :location_str, :latitude, :longitude, :resolved_address,
                 :theme, TRUE, TRUE,
                 :stripe_customer_id, :stripe_subscription_id, :token)
        """), {
            "owner_email": owner_email,
            "label": label,
            "birth_date": birth_date,
            "birth_time": birth_time,
            "unknown_time": unknown_time,
            "location_str": location_str,
            "latitude": latitude,
            "longitude": longitude,
            "resolved_address": resolved_address,
            "theme": theme,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "token": token,
        })
        session.commit()
    return token


def deactivate_by_subscription_id(stripe_subscription_id: str) -> None:
    """
    Turns off weekly transit emails for whichever profile has this
    Stripe subscription ID -- called from the webhook handler on
    customer.subscription.deleted (someone canceled, including via
    Stripe's own Customer Portal, not just this app's unsubscribe
    link) and on invoice.payment_failed (a card stopped working; keep
    emailing someone who isn't actually paying anymore is wrong
    regardless of why the payment failed). Silently does nothing if
    no profile matches -- not every subscription in Stripe necessarily
    corresponds to a row here (e.g. test events, unrelated products
    on the same Stripe account).
    """
    conn = _get_conn()
    with conn.session as session:
        session.execute(text("""
            UPDATE saved_profiles SET weekly_transits = FALSE
            WHERE stripe_subscription_id = :sub_id
        """), {"sub_id": stripe_subscription_id})
        session.commit()


def get_profile_by_token(token: str) -> dict | None:
    """
    Looks up a profile by its unsubscribe_token WITHOUT modifying
    anything -- used by the token-authenticated "manage my
    subscription" page to show someone their current theme before
    they decide whether to change it. Returns None if the token
    doesn't match anything.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT * FROM saved_profiles WHERE unsubscribe_token = :token",
        params={"token": token},
        ttl=0,
    )
    if df.empty:
        return None
    return df.to_dict("records")[0]


def set_theme_by_token(token: str, theme: str) -> str | None:
    """
    Changes a profile's transit theme, authenticated by the same
    private token as unsubscribe -- no login required, consistent
    with the rest of this paid-subscriber flow being deliberately
    account-free. Returns the profile's label on success (for a
    friendly confirmation message), or None if the token didn't match.
    """
    conn = _get_conn()
    with conn.session as session:
        result = session.execute(text("""
            UPDATE saved_profiles SET transit_theme = :theme
            WHERE unsubscribe_token = :token
            RETURNING label
        """), {"token": token, "theme": theme})
        row = result.fetchone()
        session.commit()
        return row[0] if row else None


def has_active_subscription(owner_email: str) -> bool:
    """
    Checks whether this account currently has an active $10/month
    full-access plan -- this is what actually gates the "Full
    Reading"/"Generate Summary and Email" options on Personal and
    Synastry Readings for a logged-in user, replacing the old
    "logged in = free full access" rule. Being logged in with no
    active subscription now only unlocks saved profiles, not full
    readings.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT active FROM account_subscriptions WHERE owner_email = :owner_email",
        params={"owner_email": owner_email},
        ttl=0,
    )
    if df.empty:
        return False
    return bool(df.iloc[0]["active"])


def activate_subscription(owner_email: str, stripe_customer_id: str, stripe_subscription_id: str) -> None:
    """
    Marks an account's full-access plan as active -- called from the
    webhook on a confirmed subscription payment. Upserts rather than
    always inserting, since someone could subscribe, cancel, and
    re-subscribe later under the same email.
    """
    conn = _get_conn()
    with conn.session as session:
        session.execute(text("""
            INSERT INTO account_subscriptions
                (owner_email, stripe_customer_id, stripe_subscription_id, active)
            VALUES (:owner_email, :stripe_customer_id, :stripe_subscription_id, TRUE)
            ON CONFLICT (owner_email) DO UPDATE SET
                stripe_customer_id = :stripe_customer_id,
                stripe_subscription_id = :stripe_subscription_id,
                active = TRUE
        """), {
            "owner_email": owner_email,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
        })
        session.commit()


def deactivate_subscription_by_id(stripe_subscription_id: str) -> None:
    """
    Turns off an account's full-access plan -- called on
    customer.subscription.deleted (canceled, including via Stripe's
    own Customer Portal) and invoice.payment_failed (card stopped
    working). Silently does nothing if no account matches this
    subscription id.
    """
    conn = _get_conn()
    with conn.session as session:
        session.execute(text(
            "UPDATE account_subscriptions SET active = FALSE "
            "WHERE stripe_subscription_id = :sub_id"
        ), {"sub_id": stripe_subscription_id})
        session.commit()


def get_subscription_details(owner_email: str) -> dict | None:
    """
    Returns the full account_subscriptions row for this email (including
    stripe_subscription_id, needed to actually cancel the subscription
    via Stripe's API), or None if no row exists. has_active_subscription
    only returns a bool -- this is for callers that need the rest of
    the row, like the account page's cancel button.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT * FROM account_subscriptions WHERE owner_email = :owner_email",
        params={"owner_email": owner_email},
        ttl=0,
    )
    if df.empty:
        return None
    return df.to_dict("records")[0]


def list_purchase_history(owner_email: str) -> list[dict]:
    """
    Returns every one-time purchase (reading unlocks, one-time
    transit readings, ask-an-astrologer questions) made under this
    email, most recent first. Matched purely by email -- someone
    doesn't need to have been logged in at purchase time, only for
    the email on the purchase to match their logged-in account now.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT * FROM purchase_history WHERE owner_email = :owner_email "
        "ORDER BY created_at DESC",
        params={"owner_email": owner_email},
        ttl=0,
    )
    return df.to_dict("records")


def list_active_db_connections() -> list[dict]:
    """
    Diagnostic helper -- returns every current entry in Postgres's own
    pg_stat_activity view: what every active connection is doing right
    now, and how long it's been in that state. Built specifically to
    track down a "stuck running sql.query(...)" symptom that turned
    out to be a genuine statement_timeout cancellation (see the
    QueryCanceled error this app started raising once that timeout
    was added) -- the leading theory is some other connection sitting
    "idle in transaction," holding a lock this app's own queries then
    have to wait behind. Queries the system catalog itself, not any
    of this app's own tables, so it isn't affected by whatever lock
    might be blocking those.
    """
    conn = _get_conn()
    df = conn.query(
        "SELECT pid, state, query, query_start, "
        "now() - COALESCE(state_change, query_start) AS duration "
        "FROM pg_stat_activity "
        "WHERE datname = current_database() "
        "ORDER BY query_start",
        ttl=0,
    )
    return df.to_dict("records")


def get_display_name(primary_email: str) -> str | None:
    """Returns the account's display name, or None if never set."""
    conn = _get_conn()
    df = conn.query(
        "SELECT display_name FROM account_profile WHERE primary_email = :primary_email",
        params={"primary_email": primary_email},
        ttl=0,
    )
    if df.empty:
        return None
    return df.iloc[0]["display_name"]


def set_display_name(primary_email: str, display_name: str) -> None:
    """Upserts the account's display name. Purely cosmetic -- shown on
    the account page, never used to key any other table."""
    conn = _get_conn()
    with conn.session as session:
        session.execute(text("""
            INSERT INTO account_profile (primary_email, display_name, updated_at)
            VALUES (:primary_email, :display_name, NOW())
            ON CONFLICT (primary_email) DO UPDATE
                SET display_name = EXCLUDED.display_name, updated_at = NOW()
        """), {"primary_email": primary_email, "display_name": display_name})
        session.commit()


def list_linked_emails(primary_email: str) -> list[str]:
    """Every additional email confirmed to log into this account,
    beyond the primary_email itself -- shown on the account page so
    it's clear which emails currently work."""
    conn = _get_conn()
    df = conn.query(
        "SELECT alias_email FROM account_email_aliases "
        "WHERE primary_email = :primary_email ORDER BY created_at",
        params={"primary_email": primary_email},
        ttl=0,
    )
    return df["alias_email"].tolist()


def request_email_change(primary_email: str, new_email: str) -> tuple[bool, str]:
    """
    Starts an email-change request: generates a confirmation token
    good for 24 hours and stores it, but does NOT touch
    account_email_aliases yet -- that only happens once the new
    email's actual owner clicks the confirmation link (see
    confirm_email_change), so nobody can link an email they don't
    control just by typing it into this form.

    Refuses upfront if new_email already has history anywhere (saved
    profiles, a subscription, purchases) or is already linked to any
    account (including this one) -- silently merging two people's
    paid history together needs a human, not an automatic guess, so
    this points to contacting support instead.

    Returns (True, token) on success, or (False, a user-facing
    explanation) if the new email can't be used right now.
    """
    new_email = new_email.strip().lower()
    if not new_email or "@" not in new_email or "." not in new_email.split("@")[-1]:
        return False, "That doesn't look like a valid email address."
    if new_email == primary_email.strip().lower():
        return False, "That's already your current email."

    conn = _get_conn()

    already_linked = conn.query(
        "SELECT 1 FROM account_email_aliases WHERE alias_email = :email "
        "UNION SELECT 1 FROM account_email_aliases WHERE primary_email = :email",
        params={"email": new_email},
        ttl=0,
    )
    if not already_linked.empty:
        return False, (
            "That email is already linked to an account. If this is "
            "your own other account, contact support to merge them."
        )

    existing_history = conn.query(
        "SELECT 1 FROM saved_profiles WHERE owner_email = :email "
        "UNION SELECT 1 FROM account_subscriptions WHERE owner_email = :email "
        "UNION SELECT 1 FROM purchase_history WHERE owner_email = :email",
        params={"email": new_email},
        ttl=0,
    )
    if not existing_history.empty:
        return False, (
            "That email already has its own saved profiles or purchase "
            "history. Contact support if you'd like these accounts merged."
        )

    token = secrets.token_urlsafe(32)
    with conn.session as session:
        session.execute(text("""
            INSERT INTO email_change_requests (token, primary_email, new_email, expires_at)
            VALUES (:token, :primary_email, :new_email, NOW() + INTERVAL '24 hours')
        """), {"token": token, "primary_email": primary_email, "new_email": new_email})
        session.commit()
    return True, token


def confirm_email_change(token: str) -> tuple[bool, str]:
    """
    Completes an email-change request -- called when someone clicks
    the confirmation link sent to the NEW email address. Only links
    the new email as an alias of the requesting account once the
    token itself is confirmed valid, unused, and not expired, which is
    proof whoever clicked actually controls that inbox.

    The UPDATE ... RETURNING marks the token used atomically with the
    validity check, so two near-simultaneous clicks on the same link
    can't both succeed. The alias INSERT's own ON CONFLICT DO NOTHING
    + RETURNING covers the rarer race of two different accounts
    requesting the same new_email concurrently -- whichever gets
    confirmed first wins, the second reports failure instead of
    silently doing nothing.

    Returns (True, the newly-linked email) on success, or (False, a
    user-facing explanation) otherwise.
    """
    conn = _get_conn()
    with conn.session as session:
        result = session.execute(text("""
            UPDATE email_change_requests
            SET used_at = NOW()
            WHERE token = :token AND used_at IS NULL AND expires_at > NOW()
            RETURNING primary_email, new_email
        """), {"token": token})
        row = result.fetchone()
        if row is None:
            check = session.execute(text(
                "SELECT used_at FROM email_change_requests WHERE token = :token"
            ), {"token": token}).fetchone()
            session.commit()
            if check is None:
                return False, "This confirmation link isn't valid."
            elif check[0] is not None:
                return False, "This confirmation link has already been used."
            else:
                return False, "This confirmation link has expired — request a new one from My Account."

        primary_email, new_email = row[0], row[1]
        insert_result = session.execute(text("""
            INSERT INTO account_email_aliases (alias_email, primary_email)
            VALUES (:alias_email, :primary_email)
            ON CONFLICT (alias_email) DO NOTHING
            RETURNING alias_email
        """), {"alias_email": new_email, "primary_email": primary_email})
        inserted = insert_result.fetchone()
        session.commit()
        if inserted is None:
            return False, (
                "That email was already linked to a different account "
                "in the meantime — contact support if this seems wrong."
            )
        return True, new_email
