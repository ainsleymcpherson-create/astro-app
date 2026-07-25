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
"""

import os
import re
import traceback

import requests
from flask import Flask, request, jsonify
from qstash import Receiver

from chart_points import compute_full_chart, extract_speeds
from aspect_engine import compute_aspects, find_all_patterns
from dignity import compute_chart_dignities
from house_interpretation import build_house_readings
from birth_input import resolve_birth_data
from prompt_builder import (
    build_interpretation_prompt,
    build_interpretation_prompt_no_time,
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
    Minimal markdown-to-HTML for the email body — handles the ## and
    **bold** structure our readings actually use, nothing more. Not a
    general-purpose markdown renderer; matches the same simple subset
    readings_page.py's PDF generator assumes.
    """
    html_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            html_lines.append("<br>")
            continue
        line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        if line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        else:
            html_lines.append(f"<p>{line}</p>")
    return "\n".join(html_lines)


def send_email(to_address: str, subject: str, body_text: str) -> None:
    """Sends the finished reading via Resend's API. Raises on failure
    so the caller can return a non-2xx response to QStash, triggering
    QStash's automatic retry."""
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "from": os.environ["RESEND_FROM_ADDRESS"],
            "to": [to_address],
            "subject": subject,
            "html": markdown_to_html(body_text),
        },
        timeout=30,
    )
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

        if reading_type != "General":
            msg = f"Unsupported reading_type: {reading_type}"
            print(f"[email_worker] {msg}")
            return False, msg

        birth = resolve_birth_data(datetime_str, location_str, verbose=False)
        house_system = HOUSE_SYSTEM_MAP.get(house_system_label, b"P")

        chart = compute_full_chart(birth, house_system=house_system)
        aspects = compute_aspects(chart, speeds=extract_speeds(chart))
        patterns = find_all_patterns(chart, aspects)
        dignities = compute_chart_dignities(chart)
        house_readings = build_house_readings(chart)

        if unknown_time:
            prompt = build_interpretation_prompt_no_time(
                chart, aspects, patterns, dignities, person_name=person_name,
            )
        else:
            prompt = build_interpretation_prompt(
                chart, aspects, patterns, dignities, house_readings, person_name=person_name,
            )

        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        # Streaming for the same reason the main app uses it: with a
        # max_tokens this high, the SDK's non-streaming path refuses to
        # run without it, since generation could exceed the 10-minute
        # non-streaming timeout.
        accumulated_text = ""
        with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=32000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text_chunk in stream.text_stream:
                accumulated_text += text_chunk

        if not accumulated_text:
            msg = "Claude returned no usable text"
            print(f"[email_worker] {msg}")
            return False, msg

        subject = f"Your Full {reading_type} Reading — Tenth House Readings"
        send_email(email_address, subject, accumulated_text)
        print(f"[email_worker] Sent reading to {email_address}")
        return True, "sent"

    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"[email_worker] Job failed: {msg}")
        print(traceback.format_exc())
        return False, msg


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


@app.route("/health", methods=["GET"])
def health():
    """Simple endpoint to confirm the service is up — useful for
    Render's health checks and for manually confirming deployment."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
