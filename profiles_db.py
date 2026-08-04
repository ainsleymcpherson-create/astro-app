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
    """
    try:
        return st.user.email
    except AttributeError:
        return None


def _get_conn():
    """
    Returns the cached SQL connection, built from the DATABASE_URL
    environment variable (set directly on the Render service, same
    pattern as every other secret in this app — not through
    secrets.toml, since this one's an env var, not part of the OIDC
    auth secrets file).
    """
    database_url = os.environ["DATABASE_URL"]
    return st.connection("profiles_db", type="sql", url=database_url)


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


def unsubscribe_by_token(token: str) -> str | None:
    """
    Turns off weekly transit emails for whichever profile owns this
    token, with NO login required -- this is the one-click email-link
    path, deliberately independent of the in-app toggle so someone
    can opt out without needing to sign back in first. Returns the
    profile's label if a match was found (so the caller can show a
    friendly confirmation), or None if the token didn't match
    anything -- e.g. an already-used/stale link, or a stray guess.
    """
    conn = _get_conn()
    with conn.session as session:
        result = session.execute(text("""
            UPDATE saved_profiles SET weekly_transits = FALSE
            WHERE unsubscribe_token = :token
            RETURNING label
        """), {"token": token})
        row = result.fetchone()
        session.commit()
        return row[0] if row else None


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
