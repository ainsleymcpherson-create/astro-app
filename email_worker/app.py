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

        reading_type = job["reading_type"]
        datetime_str = job["datetime_str"]
        location_str = job["location_str"]
        unknown_time = job.get("unknown_time", False)
        house_system_label = job.get("house_system", "Placidus")
        person_name = job.get("person_name") or None
        email_address = job["email"]

        if reading_type != "General":
            # Only General has both a quick-summary AND full-reading
            # path wired up right now — see readings_page.py.
            return jsonify({"error": f"Unsupported reading_type: {reading_type}"}), 400

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
            return jsonify({"error": "Claude returned no usable text"}), 502

        who = person_name if person_name else "your"
        subject = f"Your Full {reading_type} Reading — Tenth House Readings"
        send_email(email_address, subject, accumulated_text)

        return jsonify({"status": "sent", "email": email_address}), 200

    except Exception as e:
        return jsonify({
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }), 500


@app.route("/health", methods=["GET"])
def health():
    """Simple endpoint to confirm the service is up — useful for
    Render's health checks and for manually confirming deployment."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
