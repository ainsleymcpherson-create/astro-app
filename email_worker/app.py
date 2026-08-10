"""
email_worker/app.py

A small, standalone Flask app deployed separately (on Render) from the
main Streamlit app. QStash calls this whenever someone requests the
full reading by email — it regenerates the chart and full reading
from scratch (rather than trying to pass the whole computed chart
through the queue, which keeps the QStash payload small and simple),
then emails the result via Resend.

This folder has its own copies of the shared chart-computation
modules (chart_points.py, aspect_engine.py, dignity.py,
house_interpretation.py, birth_input.py, prompt_builder.py,
synastry_engine.py, transit_engine.py) rather than importing from the
main app — Render deploys this as its own independent service, so it
needs to be self-contained. If you change any chart/prompt logic in
the main app, copy the updated file(s) here too.

Required environment variables (set these in Render's dashboard under
your service's Environment tab):
    ANTHROPIC_API_KEY       — same key used by the main Streamlit app
    RESEND_API_KEY          — from resend.com
    RESEND_FROM_ADDRESS     — e.g. "readings@yourdomain.com" (must be
                               on a domain verified in Resend)
    QSTASH_CURRENT_SIGNING_KEY  — from the Upstash QStash console
    QSTASH_NEXT_SIGNING_KEY     — from the Upstash QStash console
    ASTROLOGER_NOTIFICATION_EMAIL — where Ask an Astrologer drafts get
                               sent for review before being personally
                               replied to the customer (see the "ask"
                               branch in stripe_webhook below)
"""

import os
import re
import base64
import traceback
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify
from qstash import Receiver
from pdf_utils import markdown_to_pdf_bytes, build_pdf_title_and_subtitle

from sqlalchemy import create_engine, text as sql_text

from chart_points import compute_full_chart, extract_speeds
from aspect_engine import compute_aspects, find_all_patterns
from dignity import compute_chart_dignities
from house_interpretation import build_house_readings
from birth_input import resolve_birth_data
from synastry_engine import compute_full_synastry
from transit_engine import compute_transiting_points, assign_transit_houses, compute_transit_aspects
from prompt_builder import (
    build_interpretation_prompt,
    build_interpretation_prompt_no_time,
    build_career_interpretation_prompt,
    build_career_interpretation_prompt_no_time,
    build_transit_prompt,
    build_transit_summary_only_prompt,
    build_professional_synastry_prompt,
    build_relationship_synastry_prompt,
    build_parent_child_synastry_prompt,
    build_lilith_deep_dive_prompt,
    build_chiron_deep_dive_prompt,
    build_lunar_nodes_deep_dive_prompt,
    build_ask_an_astrologer_prompt,
    split_prompt_for_caching,
)

app = Flask(__name__)

HOUSE_SYSTEM_MAP = {
    "Placidus": b"P", "Whole Sign": b"W", "Equal": b"E", "Koch": b"K",
    "Campanus": b"C", "Regiomontanus": b"R", "Alcabitius": b"B",
}


def _ensure_chiron_ephemeris_file():
    """
    Chiron specifically requires an external ephemeris data file
    (seas_18.se1) that isn't bundled with the pyswisseph pip package —
    unlike the standard planets, which pyswisseph can approximate
    internally (Moshier) without any extra files. Without this file,
    swe.calc_ut(..., swe.CHIRON) raises a hard error rather than
    falling back gracefully.

    Downloads it once into a local ./ephe directory on first startup
    and points swisseph at it — Render's servers have normal internet
    access for this, even in environments (like this sandbox) that
    don't. Safe to call on every startup: it's a no-op if the file's
    already there from a previous deploy.
    """
    ephe_dir = os.path.join(os.path.dirname(__file__), "ephe")
    ephe_file = os.path.join(ephe_dir, "seas_18.se1")
    os.makedirs(ephe_dir, exist_ok=True)

    if not os.path.exists(ephe_file):
        print("[email_worker] Downloading Chiron ephemeris file (seas_18.se1)...")
        url = "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/seas_18.se1"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(ephe_file, "wb") as f:
            f.write(response.content)
        print(f"[email_worker] Saved ephemeris file to {ephe_file}")

    import swisseph as swe
    swe.set_ephe_path(ephe_dir)


_ensure_chiron_ephemeris_file()

receiver = Receiver(
    current_signing_key=os.environ["QSTASH_CURRENT_SIGNING_KEY"],
    next_signing_key=os.environ["QSTASH_NEXT_SIGNING_KEY"],
)


def markdown_to_html(text: str) -> str:
    """
    Minimal markdown-to-HTML for the email body — handles the ##,
    **bold**, and [text](url) link structure our readings and
    transactional emails actually use, nothing more. Not a
    general-purpose markdown renderer; matches the same simple subset
    readings_page.py's PDF generator assumes (plus links, needed for
    the weekly-transit unsubscribe line).

    Emits inline styles directly on each element rather than relying
    on unstyled <h2>/<p> tags — most email clients (Gmail, Outlook)
    strip <style> blocks or override defaults, so inline styling is
    the only reliable way to keep the branded look.
    """
    html_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" style="color:#C9A66B;">\1</a>', line)
        if line.startswith("## "):
            html_lines.append(
                f'<h2 style="color:#C9A66B;font-size:17px;margin:24px 0 10px 0;'
                f"font-family:Georgia,'Times New Roman',serif;\">{line[3:]}</h2>"
            )
        else:
            html_lines.append(f'<p style="margin:0 0 12px 0;">{line}</p>')
    return "\n".join(html_lines)


def render_branded_email_html(title: str, subtitle: str, body_text: str) -> str:
    """
    Wraps the reading's converted HTML in a branded shell matching the
    app's indigo/brass visual identity — table-based layout, since
    many email clients ignore modern CSS (flex/grid) but consistently
    respect table layout with inline styles.
    """
    body_html = markdown_to_html(body_text)
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F4F1EA;padding:32px 0;">
  <tr>
    <td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background-color:#FFFFFF;border-radius:8px;overflow:hidden;font-family:Georgia,'Times New Roman',serif;">
        <tr>
          <td style="background-color:#1B2036;padding:28px 32px;">
            <div style="color:#C9A66B;font-size:13px;letter-spacing:1px;text-transform:uppercase;font-family:Arial,Helvetica,sans-serif;">Tenth House Readings</div>
            <div style="color:#FFFFFF;font-size:22px;margin-top:6px;">{title}</div>
            <div style="color:#9AA0C0;font-size:13px;margin-top:6px;font-family:Arial,Helvetica,sans-serif;">{subtitle}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:32px;color:#1B2036;font-size:15px;line-height:1.6;">
            {body_html}
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px;background-color:#F4F1EA;text-align:center;">
            <div style="color:#3A4266;font-size:11px;font-family:Arial,Helvetica,sans-serif;">Tenth House Readings &middot; <a href="https://tenthhousereadings.com" style="color:#C9A66B;">tenthhousereadings.com</a></div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
"""


def send_email(
    to_address: str, subject: str, body_text: str,
    email_title: str | None = None, email_subtitle: str | None = None,
    pdf_bytes: bytes | None = None, pdf_filename: str | None = None,
    reply_to: str | None = None,
) -> None:
    """
    Sends the finished reading via Resend's API, wrapped in the
    branded HTML shell rather than plain unstyled markdown-to-HTML.
    If email_title/email_subtitle aren't given, falls back to `subject`
    with no subtitle — keeps this backward-compatible with call sites
    sending a plain transactional message (welcome emails, etc.).

    If pdf_bytes is given, attaches it as a PDF (base64-encoded, per
    Resend's attachments API) alongside the styled HTML body — the
    email stays readable without opening anything, and the PDF is
    there for saving/printing/sharing.

    If reply_to is given, replying to this email goes to that address
    instead of RESEND_FROM_ADDRESS — used for Ask an Astrologer, where
    the astrologer receives the draft and just hits reply to answer
    the customer directly.

    Raises on failure so the caller can return a non-2xx response to
    QStash, triggering QStash's automatic retry.
    """
    html = render_branded_email_html(
        title=email_title or subject,
        subtitle=email_subtitle or "",
        body_text=body_text,
    )
    payload = {
        "from": os.environ["RESEND_FROM_ADDRESS"],
        "to": [to_address],
        "subject": subject,
        "html": html,
    }
    if pdf_bytes is not None:
        payload["attachments"] = [{
            "filename": pdf_filename or "reading.pdf",
            "content": base64.b64encode(pdf_bytes).decode("ascii"),
        }]
    if reply_to:
        payload["reply_to"] = reply_to
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if not response.ok:
        # requests' raise_for_status() only reports the status code,
        # not Resend's actual error message — logging the real
        # response body here is what actually tells us WHY a 4xx
        # happened (unverified domain, bad key, disallowed recipient,
        # etc.) instead of just that it happened.
        print(f"[email_worker] Resend rejected the send: {response.status_code} {response.text}")
    response.raise_for_status()


def _process_reading_job(job: dict) -> tuple[bool, str]:
    """
    Does the actual work — chart computation, Claude generation, and
    emailing. Runs synchronously as part of the request/response cycle
    (see the note in generate_and_email() for why this is deliberate).
    Returns (success, message) so the caller can respond to QStash
    with the right status code — a non-2xx response tells QStash to
    retry, which matters if something here fails transiently.
    """
    try:
        reading_type = job["reading_type"]
        datetime_str = job["datetime_str"]
        location_str = job["location_str"]
        unknown_time = job.get("unknown_time", False)
        house_system_label = job.get("house_system", "Placidus")
        person_name = job.get("person_name") or None
        email_address = job["email"]
        house_system = HOUSE_SYSTEM_MAP.get(house_system_label, b"P")

        birth = resolve_birth_data(datetime_str, location_str, verbose=False)
        chart = compute_full_chart(birth, house_system=house_system)
        aspects = compute_aspects(chart, speeds=extract_speeds(chart))
        patterns = find_all_patterns(chart, aspects)
        dignities = compute_chart_dignities(chart)
        house_readings = build_house_readings(chart)

        # Current age, used for the General reading's age-based emphasis
        # (see prompt_builder.py's _age_guidance) — added emphasis only,
        # never exclusion. Computed from birth.dt_utc (already resolved
        # above) rather than re-parsing datetime_str, using UTC "today"
        # since this worker doesn't have a meaningful local timezone of
        # its own. Matches the same day/month comparison formula used in
        # the main app's personal_readings_page.py.
        _today = datetime.utcnow().date()
        _birth_date = birth.dt_utc.date()
        current_age = (
            _today.year - _birth_date.year
            - ((_today.month, _today.day) < (_birth_date.month, _birth_date.day))
        )

        if reading_type == "Lilith":
            prompt = build_lilith_deep_dive_prompt(
                chart, aspects, patterns, dignities, house_readings, person_name=person_name,
            )

        elif reading_type == "Chiron":
            prompt = build_chiron_deep_dive_prompt(
                chart, aspects, patterns, dignities, house_readings, person_name=person_name,
            )

        elif reading_type == "North/South Node":
            prompt = build_lunar_nodes_deep_dive_prompt(
                chart, aspects, patterns, dignities, house_readings, person_name=person_name,
            )

        elif reading_type == "Transits":
            transit_date_str = job.get("transit_date")
            if transit_date_str:
                transit_dt = datetime.strptime(transit_date_str, "%Y-%m-%d")
            else:
                transit_dt = datetime.utcnow()
            transit_dt_utc = transit_dt.replace(
                hour=12, minute=0, second=0, tzinfo=timezone.utc
            )
            transiting_points = compute_transiting_points(transit_dt_utc)
            natal_house_cusps = [chart[f"House {i}"] for i in range(1, 13)]
            assign_transit_houses(transiting_points, natal_house_cusps)
            transit_aspects = compute_transit_aspects(
                chart, transiting_points,
                transiting_speeds=extract_speeds(transiting_points),
            )
            prompt = build_transit_prompt(
                transiting_points, transit_aspects, dignities, person_name=person_name,
                theme=job.get("theme", "General"),
            )

        elif reading_type in ("Professional Synastry", "Relationship Synastry", "Parent/Child Synastry"):
            datetime_str_b = job["datetime_str_b"]
            location_str_b = job["location_str_b"]
            unknown_time_b = job.get("unknown_time_b", False)
            person_name_b = job.get("person_name_b") or None

            birth_b = resolve_birth_data(datetime_str_b, location_str_b, verbose=False)
            chart_b = compute_full_chart(birth_b, house_system=house_system)

            synastry_result = compute_full_synastry(
                chart, chart_b,
                person_a_time_known=not unknown_time,
                person_b_time_known=not unknown_time_b,
            )
            dignities_b = compute_chart_dignities(chart_b)

            if reading_type == "Professional Synastry":
                prompt = build_professional_synastry_prompt(
                    synastry_result, dignities, dignities_b,
                    person_a_name=person_name, person_b_name=person_name_b,
                )
            elif reading_type == "Parent/Child Synastry":
                prompt = build_parent_child_synastry_prompt(
                    synastry_result, dignities, dignities_b,
                    person_a_name=person_name, person_b_name=person_name_b,
                )
            else:
                prompt = build_relationship_synastry_prompt(
                    synastry_result, dignities, dignities_b,
                    person_a_name=person_name, person_b_name=person_name_b,
                    relationship_stage=job.get("relationship_stage"),
                )

        elif reading_type == "Career / Work" and unknown_time:
            prompt = build_career_interpretation_prompt_no_time(
                chart, aspects, patterns, dignities, person_name=person_name,
            )
        elif reading_type == "Career / Work":
            prompt = build_career_interpretation_prompt(
                chart, aspects, patterns, dignities, house_readings, person_name=person_name,
            )
        elif unknown_time:
            prompt = build_interpretation_prompt_no_time(
                chart, aspects, patterns, dignities, person_name=person_name, age=current_age,
            )
        else:
            prompt = build_interpretation_prompt(
                chart, aspects, patterns, dignities, house_readings, person_name=person_name, age=current_age,
            )

        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        # Split into a static, cache_control-eligible prefix (the bulk
        # of the instructional template, identical across every call
        # for this reading type/variant) and a dynamic suffix (this
        # person's name/age/chart data). See
        # prompt_builder.shared.split_prompt_for_caching.
        static_prefix, dynamic_suffix = split_prompt_for_caching(prompt)
        message_content = [
            {"type": "text", "text": static_prefix, "cache_control": {"type": "ephemeral"}},
        ]
        if dynamic_suffix:
            message_content.append({"type": "text", "text": dynamic_suffix})

        # Streaming for the same reason the main app uses it: with a
        # max_tokens this high, the SDK's non-streaming path refuses to
        # run without it, since generation could exceed the 10-minute
        # non-streaming timeout.
        accumulated_text = ""
        with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=32000,
            messages=[{"role": "user", "content": message_content}],
        ) as stream:
            for text_chunk in stream.text_stream:
                accumulated_text += text_chunk

        if not accumulated_text:
            msg = "Claude returned no usable text"
            print(f"[email_worker] {msg}")
            return False, msg

        title, subtitle = build_pdf_title_and_subtitle(
            reading_type, person_name, datetime_str, location_str,
            person_name_b=job.get("person_name_b"),
            datetime_str_b=job.get("datetime_str_b"),
            location_str_b=job.get("location_str_b"),
        )
        pdf_bytes = markdown_to_pdf_bytes(accumulated_text, title, subtitle)
        subject = f"Your Full {reading_type} Reading — Tenth House Readings"
        send_email(
            email_address, subject, accumulated_text,
            email_title=title, email_subtitle=subtitle,
            pdf_bytes=pdf_bytes,
            pdf_filename=f"{reading_type.replace('/', '-')}_reading.pdf",
        )
        print(f"[email_worker] Sent reading to {email_address}")
        return True, "sent"

    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"[email_worker] Job failed: {msg}")
        print(traceback.format_exc())
        return False, msg


def _send_email_change_confirmation(job: dict) -> tuple[bool, str]:
    """
    Sends the "confirm your new email" link for the My Account "add
    another login email" flow. The link itself does the actual
    linking (see profiles_db.confirm_email_change / app.py's
    ?confirm_email= handler) -- this function only ever sends mail,
    it never touches the database, keeping the actual account-linking
    decision entirely in the main app's hands.
    """
    to_email = job.get("to_email")
    token = job.get("token")
    if not to_email or not token:
        return False, "Missing to_email or token in job payload"

    app_base_url = os.environ.get("APP_BASE_URL", "https://tenthhousereadings.com")
    confirm_url = f"{app_base_url}/?confirm_email={token}"

    body = (
        f"Click the link below to confirm this email for your Tenth "
        f"House Readings account. Once confirmed, you'll be able to "
        f"log in with either this email or the one you're currently "
        f"using — both reach the same saved profiles, subscription, "
        f"and purchase history.\n\n"
        f"[Confirm this email]({confirm_url})\n\n"
        f"This link expires in 24 hours. If you didn't request this, "
        f"you can safely ignore this email — nothing will change."
    )
    try:
        send_email(
            to_email,
            "Confirm your new email — Tenth House Readings",
            body,
            email_title="Confirm Your Email",
        )
        return True, "sent"
    except Exception as e:
        return False, f"Couldn't send confirmation email: {type(e).__name__}: {e}"


@app.route("/generate-and-email", methods=["POST"])
def generate_and_email():
    # Verify this request genuinely came from QStash, not some random
    # request to this URL — without this, anyone who finds this
    # endpoint could trigger paid Claude API calls and emails at will.
    signature = request.headers.get("Upstash-Signature", "")
    body_raw = request.get_data(as_text=True)
    try:
        receiver.verify(
            signature=signature,
            body=body_raw,
            url=request.url,
        )
    except Exception as e:
        return jsonify({"error": f"Signature verification failed: {e}"}), 401

    try:
        job = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid job payload: {e}"}), 400

    # Not every job on this endpoint is "generate a reading" -- the
    # My Account "add another login email" flow reuses this same
    # QStash-signed endpoint to send a lightweight confirmation email,
    # since RESEND_API_KEY/RESEND_FROM_ADDRESS only live here, not in
    # the main Streamlit app's secrets. Dispatch on "kind" rather than
    # adding a whole second route, so this stays the one signature-
    # verified entry point QStash needs to know about.
    if job.get("kind") == "email_change_confirmation":
        success, message = _send_email_change_confirmation(job)
        if success:
            return jsonify({"status": "sent"}), 200
        else:
            return jsonify({"error": message}), 500

    # Deliberately BLOCKING, not backgrounded. An earlier version of
    # this endpoint responded immediately and did the real work in a
    # background thread — that actually caused a worse bug: Render's
    # free tier spins the service down after ~15 minutes with no
    # ACTIVE incoming request, and it does this based on connection
    # activity, not internal CPU usage. The fast-response design meant
    # Render saw the request as "done" immediately, and could kill the
    # container mid-generation with zero warning, silently dropping
    # the job. Blocking here keeps the connection open and active for
    # the whole generation, which Render does NOT treat as idle — and
    # the corresponding `timeout="..."` set on the QStash publish call
    # (see readings_page.py) tells QStash to actually wait that long
    # rather than assuming failure and retrying early.
    success, message = _process_reading_job(job)
    if success:
        return jsonify({"status": "sent"}), 200
    else:
        return jsonify({"error": message}), 500


def _get_weekly_subscribers() -> list[dict]:
    """
    Flask-compatible equivalent of the main app's
    profiles_db.list_weekly_subscribers() -- can't use Streamlit's
    st.connection here since this is a plain Flask app, not a
    Streamlit one. Uses a fresh SQLAlchemy engine against the same
    DATABASE_URL instead. Row values come back as native Python
    date/time objects directly from psycopg2 (no pandas involved),
    so this doesn't need the Timestamp-normalization dance the
    Streamlit side needs.
    """
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        result = conn.execute(sql_text(
            "SELECT * FROM saved_profiles WHERE weekly_transits = TRUE"
        ))
        return [dict(row._mapping) for row in result]


def _profile_exists_for_subscription(stripe_subscription_id: str) -> bool:
    """
    Checks whether a profile already exists for this Stripe
    subscription id -- used to guard against duplicate webhook
    deliveries. Stripe explicitly documents that the same event can
    be delivered more than once (network retries, etc.), and without
    this check, a duplicate checkout.session.completed would create a
    second profile row and send a second welcome email for the same
    single payment -- then keep sending duplicate weekly readings
    every Monday after that, not just once.
    """
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        result = conn.execute(sql_text(
            "SELECT 1 FROM saved_profiles WHERE stripe_subscription_id = :sub_id LIMIT 1"
        ), {"sub_id": stripe_subscription_id})
        return result.fetchone() is not None


def _create_paid_subscriber_profile_worker(
    label: str, birth_date, birth_time, location_str: str,
    latitude: float, longitude: float, resolved_address: str, theme: str,
    owner_email: str, stripe_customer_id: str, stripe_subscription_id: str,
) -> str:
    """
    Flask-compatible equivalent of profiles_db.create_paid_subscriber_profile
    -- called from the Stripe webhook handler once checkout.session.completed
    confirms a real payment, never from the signup page itself. Returns
    the generated unsubscribe_token, included in the welcome email.
    """
    import secrets as secrets_module
    token = secrets_module.token_urlsafe(32)
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sql_text("""
            INSERT INTO saved_profiles
                (owner_email, label, birth_date, birth_time, unknown_time,
                 location_str, latitude, longitude, resolved_address,
                 transit_theme, weekly_transits, is_paid_subscriber,
                 stripe_customer_id, stripe_subscription_id, unsubscribe_token)
            VALUES
                (:owner_email, :label, :birth_date, :birth_time, FALSE,
                 :location_str, :latitude, :longitude, :resolved_address,
                 :theme, TRUE, TRUE,
                 :stripe_customer_id, :stripe_subscription_id, :token)
        """), {
            "owner_email": owner_email, "label": label, "birth_date": birth_date,
            "birth_time": birth_time, "location_str": location_str,
            "latitude": latitude, "longitude": longitude,
            "resolved_address": resolved_address, "theme": theme,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id, "token": token,
        })
    return token


def _deactivate_by_subscription_id_worker(stripe_subscription_id: str) -> None:
    """
    Flask-compatible equivalent of profiles_db.deactivate_by_subscription_id
    -- called on customer.subscription.deleted (canceled via Stripe's own
    Customer Portal, not just this app's unsubscribe link) and
    invoice.payment_failed (card stopped working).

    Checks BOTH saved_profiles (weekly transits) and account_subscriptions
    (the $10/month full-access plan) -- both are ordinary Stripe
    subscriptions, and Stripe fires the exact same event types for a
    canceled/failed payment regardless of which product it was for, so
    this needs to cover both rather than assuming which one a given
    subscription id belongs to. Silently does nothing wherever no row
    matches.
    """
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sql_text(
            "UPDATE saved_profiles SET weekly_transits = FALSE "
            "WHERE stripe_subscription_id = :sub_id"
        ), {"sub_id": stripe_subscription_id})
        conn.execute(sql_text(
            "UPDATE account_subscriptions SET active = FALSE "
            "WHERE stripe_subscription_id = :sub_id"
        ), {"sub_id": stripe_subscription_id})


def _activate_account_subscription_worker(owner_email: str, stripe_customer_id: str, stripe_subscription_id: str) -> None:
    """
    Flask-compatible equivalent of profiles_db.activate_subscription --
    marks an account's $10/month full-access plan active. Upserts, since
    someone could subscribe, cancel, and re-subscribe later.
    """
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sql_text("""
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


def _record_purchase_worker(owner_email: str, product_type: str, detail: str,
                             amount_cents: int, stripe_session_id: str) -> None:
    """
    Records a one-time purchase (reading unlock, one-time transit
    reading, or ask-an-astrologer question) so it shows up in the
    account's purchase history later. Previously these left no trace
    anywhere once the confirmation email went out.
    """
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sql_text("""
            INSERT INTO purchase_history
                (owner_email, product_type, detail, amount_cents, stripe_session_id)
            VALUES (:owner_email, :product_type, :detail, :amount_cents, :stripe_session_id)
        """), {
            "owner_email": owner_email,
            "product_type": product_type,
            "detail": detail,
            "amount_cents": amount_cents,
            "stripe_session_id": stripe_session_id,
        })


def _process_weekly_transit_profile(profile: dict) -> tuple[bool, str]:
    """
    Builds and sends one profile's weekly transit email. Mirrors
    _process_reading_job's shape, but for a single saved profile
    rather than a live form submission -- reconstructs the natal
    chart from the profile's stored birth data, computes today's
    transits against it, and emails a short summary with an
    unsubscribe link.

    Profiles with unknown_time are skipped entirely (not treated as a
    failure) -- transit readings need house cusps to place transiting
    planets in the natal chart, which requires a known birth time,
    the same reason the in-app unknown-time path never offered
    Transits as an option to begin with.
    """
    if profile.get("unknown_time"):
        return True, "skipped (unknown birth time)"

    label = profile["label"]
    owner_email = profile["owner_email"]
    try:
        birth_date = profile["birth_date"]
        birth_time = profile["birth_time"]
        datetime_str = f"{birth_date.strftime('%B %d, %Y')} {birth_time.strftime('%I:%M %p')}"
        birth = resolve_birth_data(datetime_str, profile["location_str"], verbose=False)

        chart = compute_full_chart(birth, house_system=b"P")
        dignities = compute_chart_dignities(chart)

        transit_dt_utc = datetime.utcnow().replace(hour=12, minute=0, second=0, tzinfo=timezone.utc)
        transiting_points = compute_transiting_points(transit_dt_utc)
        natal_house_cusps = [chart[f"House {i}"] for i in range(1, 13)]
        assign_transit_houses(transiting_points, natal_house_cusps)
        transit_aspects = compute_transit_aspects(
            chart, transiting_points,
            transiting_speeds=extract_speeds(transiting_points),
        )

        prompt = build_transit_summary_only_prompt(
            transiting_points, transit_aspects, dignities,
            person_name=profile.get("person_name"),
            theme=profile.get("transit_theme", "General"),
        )

        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        static_prefix, dynamic_suffix = split_prompt_for_caching(prompt)
        message_content = [
            {"type": "text", "text": static_prefix, "cache_control": {"type": "ephemeral"}},
        ]
        if dynamic_suffix:
            message_content.append({"type": "text", "text": dynamic_suffix})
        accumulated_text = ""
        with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": message_content}],
        ) as stream:
            for text_chunk in stream.text_stream:
                accumulated_text += text_chunk

        app_base_url = os.environ.get("APP_BASE_URL", "https://tenthhousereadings.com")
        unsubscribe_url = f"{app_base_url}/?unsubscribe={profile['unsubscribe_token']}"
        accumulated_text += (
            f"\n\n---\n\n[Turn off weekly transit emails for {label}]({unsubscribe_url})"
        )

        weekly_title = f"{label}'s Weekly Transits" if label else "Your Weekly Transits"
        weekly_subtitle = f"Week of {datetime.utcnow().strftime('%B %d, %Y')}"
        pdf_bytes = markdown_to_pdf_bytes(accumulated_text, weekly_title, weekly_subtitle)
        send_email(
            owner_email,
            f"Your Week Ahead — {label} — Tenth House Readings",
            accumulated_text,
            email_title=weekly_title, email_subtitle=weekly_subtitle,
            pdf_bytes=pdf_bytes, pdf_filename="weekly_transits.pdf",
        )
        return True, "sent"
    except Exception as e:
        print(f"[email_worker] Weekly transit failed for \"{label}\" ({owner_email}): "
              f"{traceback.format_exc()}")
        return False, str(e)


@app.route("/send-weekly-transits", methods=["POST"])
def send_weekly_transits():
    """
    Triggered by a QStash Schedule (set up once, in Upstash's
    console, pointed at this endpoint on a weekly cron) rather than
    an individual publish per request like /generate-and-email —
    this single trigger fans out to every currently opted-in profile
    across all users. Each profile is wrapped in its own try/except
    (inside _process_weekly_transit_profile) so one person's failure
    never blocks anyone else's email from going out.
    """
    signature = request.headers.get("Upstash-Signature", "")
    body_raw = request.get_data(as_text=True)
    try:
        receiver.verify(
            signature=signature,
            body=body_raw,
            url=request.url,
        )
    except Exception as e:
        return jsonify({"error": f"Signature verification failed: {e}"}), 401

    subscribers = _get_weekly_subscribers()
    sent, skipped, failed = 0, 0, 0
    for profile in subscribers:
        success, message = _process_weekly_transit_profile(profile)
        if not success:
            failed += 1
        elif "skipped" in message:
            skipped += 1
        else:
            sent += 1

    summary = {"total": len(subscribers), "sent": sent, "skipped": skipped, "failed": failed}
    print(f"[email_worker] Weekly transits run: {summary}")
    return jsonify(summary), 200


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """
    Handles Stripe's webhook events for the weekly-transits paid
    subscription. This is the ONLY place a paid subscriber profile
    ever gets created or deactivated -- deliberately never on the
    signup page's own submission, and never based on Stripe's
    success_url redirect, since a redirect can fire without payment
    actually completing. Only a verified, signed webhook event from
    Stripe itself is trusted to grant or revoke access.

    Events handled:
      checkout.session.completed  -- payment confirmed, create the
                                      profile and send a welcome email
      customer.subscription.deleted -- canceled (including via
                                      Stripe's own Customer Portal,
                                      not just this app's unsubscribe
                                      link) -- deactivate
      invoice.payment_failed      -- card stopped working --
                                      deactivate; someone who isn't
                                      actually paying shouldn't keep
                                      getting emails regardless of why
    """
    import stripe
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

    payload = request.get_data()  # raw bytes -- signature verification
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ["STRIPE_WEBHOOK_SECRET"]
        )
    except Exception as e:
        # This specific failure was previously silent in Render's logs
        # -- the response told Stripe what happened, but nothing was
        # printed here, making this exact problem invisible from the
        # Render side even though the request was actually arriving.
        print(f"[email_worker] Stripe webhook signature verification failed: {e}")
        return jsonify({"error": f"Webhook signature verification failed: {e}"}), 400

    event_type = event["type"]
    # Logged unconditionally, not just on error -- a single Checkout
    # completion fires many different Stripe event types (invoice.paid,
    # customer.subscription.created, etc.), and this handler only acts
    # on three of them. Without this, every one of those other events
    # shows up in Render's logs as an identical, silent 200 with
    # nothing to distinguish which event it actually was.
    print(f"[email_worker] Stripe webhook received: {event_type}")
    # stripe-python v15 removed dict inheritance from StripeObject --
    # .get(), .items(), etc. no longer work directly on these SDK
    # objects even though they still support bracket access. Convert
    # to a real plain dict immediately so every .get() call below
    # (including on the nested "metadata" dict) works as written,
    # rather than fixing each individual access site separately.
    data_object = event["data"]["object"].to_dict()

    try:
        if event_type == "checkout.session.completed":
            metadata = data_object.get("metadata", {})
            product_type = metadata.get("product_type", "weekly")  # default covers any in-flight test purchases from before this existed
            label = metadata.get("label", "Customer")
            customer_email = data_object.get("customer_email") or (data_object.get("customer_details") or {}).get("email")
            stripe_customer_id = data_object.get("customer")
            stripe_subscription_id = data_object.get("subscription")

            if stripe_subscription_id and _profile_exists_for_subscription(stripe_subscription_id):
                print(f"[email_worker] Duplicate checkout.session.completed for "
                      f"subscription {stripe_subscription_id} -- already processed, skipping.")
                return jsonify({"status": "duplicate, skipped"}), 200

            # full_access_subscription is the one product here that
            # ISN'T tied to any birth data at all -- it's an
            # account-level entitlement, not a specific reading -- so
            # its metadata never includes birth_date/birth_time/
            # location_str, and this whole block is skipped for it.
            if product_type != "full_access_subscription":
                birth_date_str = metadata["birth_date"]  # YYYY-MM-DD, from date.isoformat()
                birth_time_str = metadata["birth_time"]  # HH:MM, 24-hour
                location_str = metadata["location_str"]
                # Reparse into the "Month DD, YYYY HH:MM" style
                # resolve_birth_data expects, and geocode for real (the
                # signup page only did a quick check, not the full
                # resolution needed to actually compute a chart).
                _bd = datetime.strptime(birth_date_str, "%Y-%m-%d")
                _bt = datetime.strptime(birth_time_str, "%H:%M")
                datetime_str = f"{_bd.strftime('%B %d, %Y')} {_bt.strftime('%I:%M %p')}"
                birth = resolve_birth_data(datetime_str, location_str, verbose=False)

            if product_type == "weekly":
                theme = metadata.get("theme", "General")
                token = _create_paid_subscriber_profile_worker(
                    label=label,
                    birth_date=_bd.date(),
                    birth_time=_bt.time(),
                    location_str=location_str,
                    latitude=birth.latitude,
                    longitude=birth.longitude,
                    resolved_address=location_str,
                    theme=theme,
                    owner_email=customer_email,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                )
                app_base_url = os.environ.get("APP_BASE_URL", "https://tenthhousereadings.com")
                manage_url = f"{app_base_url}/?manage={token}"
                welcome_body = (
                    f"## Welcome, {label}!\n\n"
                    f"Your weekly transits subscription is confirmed — your first "
                    f"reading arrives this coming Monday, focused on your "
                    f"**{theme}** theme.\n\n"
                    f"[Manage your subscription (change theme, or unsubscribe)]({manage_url})"
                )
                send_email(customer_email, "You're signed up — Tenth House Readings", welcome_body)
                print(f"[email_worker] Weekly transits welcome email sent to {customer_email}")

            elif product_type == "one_time":
                # A single, comprehensive reading -- uses the FULL
                # transit prompt rather than the lean summary-only one
                # the weekly job uses, since a one-time $7 purchase
                # calls for more depth than a quick recurring check-in.
                chart = compute_full_chart(birth, house_system=b"P")
                dignities = compute_chart_dignities(chart)
                transit_dt_utc = datetime.utcnow().replace(hour=12, minute=0, second=0, tzinfo=timezone.utc)
                transiting_points = compute_transiting_points(transit_dt_utc)
                natal_house_cusps = [chart[f"House {i}"] for i in range(1, 13)]
                assign_transit_houses(transiting_points, natal_house_cusps)
                transit_aspects = compute_transit_aspects(
                    chart, transiting_points,
                    transiting_speeds=extract_speeds(transiting_points),
                )
                prompt = build_transit_prompt(
                    transiting_points, transit_aspects, dignities, person_name=label,
                    theme=metadata.get("theme", "General"),
                )
                import anthropic
                client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
                static_prefix, dynamic_suffix = split_prompt_for_caching(prompt)
                message_content = [
                    {"type": "text", "text": static_prefix, "cache_control": {"type": "ephemeral"}},
                ]
                if dynamic_suffix:
                    message_content.append({"type": "text", "text": dynamic_suffix})
                accumulated_text = ""
                with client.messages.stream(
                    model="claude-sonnet-5",
                    max_tokens=32000,
                    messages=[{"role": "user", "content": message_content}],
                ) as stream:
                    for text_chunk in stream.text_stream:
                        accumulated_text += text_chunk
                one_time_title = f"{label}'s Transit Reading" if label else "Your Transit Reading"
                one_time_pdf = markdown_to_pdf_bytes(accumulated_text, one_time_title, "")
                send_email(
                    customer_email, "Your Transit Reading — Tenth House Readings", accumulated_text,
                    email_title=one_time_title, pdf_bytes=one_time_pdf,
                    pdf_filename="transit_reading.pdf",
                )
                _record_purchase_worker(
                    customer_email, "one_time_transit", f"One-Time Transit Reading — {label}",
                    700, data_object.get("id"),
                )
                print(f"[email_worker] One-time transit reading sent to {customer_email}")

            elif product_type == "ask":
                question = metadata.get("question", "").strip()

                # Sent immediately, before AI generation even starts, so
                # the customer gets fast confirmation rather than waiting
                # on Claude -- the actual personalized answer comes later,
                # by reply, once the astrologer reviews the AI draft below.
                confirmation_body = (
                    f"Thanks for your question — payment received!\n\n"
                    f"**Your question:** \"{question}\"\n\n"
                    f"Your birth chart has been pulled in, and your question "
                    f"is now with Ainsley for a personal answer. You'll hear "
                    f"back within 2-3 business days — no need to do anything "
                    f"else in the meantime."
                )
                try:
                    send_email(
                        customer_email,
                        "We've got your question — Tenth House Readings",
                        confirmation_body,
                        email_title="Your Question Has Been Received",
                    )
                    print(f"[email_worker] Confirmation sent to {customer_email}")
                except Exception as e:
                    # A failed confirmation shouldn't block the actual
                    # answer generation below -- log it and keep going.
                    print(f"[email_worker] Confirmation email failed for "
                          f"{customer_email}: {e}")

                chart = compute_full_chart(birth, house_system=b"P")
                aspects = compute_aspects(chart, speeds=extract_speeds(chart))
                patterns = find_all_patterns(chart, aspects)
                dignities = compute_chart_dignities(chart)
                house_readings = build_house_readings(chart)
                prompt = build_ask_an_astrologer_prompt(
                    chart, aspects, patterns, dignities, house_readings,
                    question=question, person_name=label,
                )
                import anthropic
                client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
                static_prefix, dynamic_suffix = split_prompt_for_caching(prompt)
                message_content = [
                    {"type": "text", "text": static_prefix, "cache_control": {"type": "ephemeral"}},
                ]
                if dynamic_suffix:
                    message_content.append({"type": "text", "text": dynamic_suffix})
                accumulated_text = ""
                with client.messages.stream(
                    model="claude-sonnet-5",
                    max_tokens=32000,
                    messages=[{"role": "user", "content": message_content}],
                ) as stream:
                    for text_chunk in stream.text_stream:
                        accumulated_text += text_chunk

                # Sent to the astrologer for review, NOT directly to the
                # customer -- Ask an Astrologer is a manually-reviewed
                # service, not a fully automated one. The customer's
                # email is set as reply_to, so replying to this email
                # goes straight to them without needing to copy/paste
                # anything.
                ask_title = f"{label}'s Question, Answered" if label else "Your Question, Answered"
                ask_pdf = markdown_to_pdf_bytes(accumulated_text, ask_title, "")
                astrologer_email = os.environ.get("ASTROLOGER_NOTIFICATION_EMAIL")
                if not astrologer_email:
                    print("[email_worker] ASTROLOGER_NOTIFICATION_EMAIL not set — "
                          "Ask an Astrologer draft has nowhere to go!")
                else:
                    notification_body = (
                        f"**New Ask an Astrologer submission**\n\n"
                        f"**From:** {label} ({customer_email})\n\n"
                        f"**Their question:** \"{question}\"\n\n"
                        f"**AI-drafted answer below** — review, personalize, and reply "
                        f"directly to this email to send it to {customer_email}.\n\n"
                        f"{accumulated_text}"
                    )
                    send_email(
                        astrologer_email,
                        f"New Ask an Astrologer question from {label}",
                        notification_body,
                        email_title=ask_title, pdf_bytes=ask_pdf,
                        pdf_filename="ask_an_astrologer_draft.pdf",
                        reply_to=customer_email,
                    )
                    print(f"[email_worker] Ask an Astrologer draft sent for review "
                          f"(customer: {customer_email})")

                _question_preview = question if len(question) <= 100 else question[:97] + "..."
                _record_purchase_worker(
                    customer_email, "ask_an_astrologer", f"Ask an Astrologer: \"{_question_preview}\"",
                    1000, data_object.get("id"),
                )

            elif product_type == "reading_unlock":
                # The $3 one-off unlock. Two delivery paths, chosen by
                # the person BEFORE paying (stored in metadata, not
                # decided here): "email" (default -- covers any
                # in-flight purchases from before "delivery" existed
                # in metadata) generates and emails the reading right
                # here, same as always. "in_app" is handled entirely
                # client-side instead -- the person gets redirected
                # back to the app after paying, app.py re-verifies the
                # payment against Stripe's API, and the matching
                # reading page streams the full reading live on the
                # page. This webhook has no live connection back to
                # that browser tab, so for "in_app" there's nothing
                # for it to generate or send -- it just records the
                # purchase and gets out of the way.
                reading_type = metadata.get("reading_type", "General")
                delivery = metadata.get("delivery", "email")

                if delivery == "in_app":
                    _record_purchase_worker(
                        customer_email, "reading_unlock", f"{reading_type} — {label}",
                        300, data_object.get("id"),
                    )
                    print(f"[email_worker] Reading unlock ({reading_type}) chose in-app "
                          f"delivery -- skipping email, purchase recorded for {customer_email}")
                else:
                    # reuses _process_reading_job wholesale rather than
                    # re-implementing chart computation and prompt
                    # dispatch for every reading type here. That
                    # function already handles every reading type this
                    # app supports (Personal, Synastry, Deep Dive) via
                    # its own internal dispatch, since it's the exact
                    # same code path the "Generate Summary and Email
                    # Full Reading" in-app flow already uses.
                    job = {
                        "reading_type": reading_type,
                        "datetime_str": datetime_str,
                        "location_str": location_str,
                        "unknown_time": metadata.get("unknown_time") == "true",
                        "person_name": label,
                        "email": customer_email,
                    }
                    if reading_type in ("Professional Synastry", "Relationship Synastry", "Parent/Child Synastry"):
                        _bd_b = datetime.strptime(metadata["birth_date_b"], "%Y-%m-%d")
                        _bt_b = datetime.strptime(metadata["birth_time_b"], "%H:%M")
                        job["datetime_str_b"] = f"{_bd_b.strftime('%B %d, %Y')} {_bt_b.strftime('%I:%M %p')}"
                        job["location_str_b"] = metadata["location_str_b"]
                        job["unknown_time_b"] = metadata.get("unknown_time_b") == "true"
                        job["person_name_b"] = metadata.get("label_b")
                        if metadata.get("relationship_stage"):
                            job["relationship_stage"] = metadata["relationship_stage"]

                    success, message = _process_reading_job(job)
                    if success:
                        _record_purchase_worker(
                            customer_email, "reading_unlock", f"{reading_type} — {label}",
                            300, data_object.get("id"),
                        )
                        print(f"[email_worker] Reading unlock ({reading_type}) sent to {customer_email}")
                    else:
                        print(f"[email_worker] Reading unlock ({reading_type}) FAILED: {message}")

            elif product_type == "full_access_subscription":
                # Account-level entitlement, not tied to any specific
                # reading -- unlocks Full Reading/Email on Personal,
                # Synastry, and Deep Dive for as long as it's active.
                # Deliberately does NOT cover the Astrology Services
                # products (Weekly Transits, One-Time Transit, Ask an
                # Astrologer) -- those stay separately priced.
                _activate_account_subscription_worker(customer_email, stripe_customer_id, stripe_subscription_id)
                welcome_body = (
                    f"## Welcome to Full Access, {label}!\n\n"
                    f"Your subscription is confirmed — you now have unlimited "
                    f"full readings and email delivery across Personal, "
                    f"Synastry, and Deep Dive readings. Just log in with this "
                    f"same email ({customer_email}) on the site to use it."
                )
                send_email(customer_email, "Full Access Confirmed — Tenth House Readings", welcome_body)
                print(f"[email_worker] Full access subscription activated for {customer_email}")

        elif event_type == "customer.subscription.deleted":
            _deactivate_by_subscription_id_worker(data_object.get("id"))

        elif event_type == "invoice.payment_failed":
            sub_id = data_object.get("subscription")
            if sub_id:
                _deactivate_by_subscription_id_worker(sub_id)

    except Exception:
        print(f"[email_worker] Stripe webhook processing failed for {event_type}: "
              f"{traceback.format_exc()}")
        # Still return 200 -- Stripe would otherwise retry an event
        # that failed for a reason a retry won't fix (e.g. bad
        # metadata), and this is logged above for manual follow-up.

    return jsonify({"status": "received"}), 200


@app.route("/health", methods=["GET"])
def health():
    """Simple endpoint to confirm the service is up — useful for
    Render's health checks and for manually confirming deployment."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
