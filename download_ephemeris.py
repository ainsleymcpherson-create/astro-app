"""
download_ephemeris.py

One-time setup script: downloads the Chiron ephemeris file (seas_18.se1)
into a local ./ephe folder. The standard planets work fine without this
(pyswisseph's built-in Moshier approximation covers them), but Chiron
specifically requires this file.

Run once:
    python3 download_ephemeris.py
"""

import os
import urllib.request

EPHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")
TARGET_FILE = os.path.join(EPHE_DIR, "seas_18.se1")

# GitHub mirror tends to be more reliable for scripted downloads than
# astro.com directly, which sometimes blocks non-browser requests.
SOURCE_URL = "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/seas_18.se1"


def main():
    os.makedirs(EPHE_DIR, exist_ok=True)

    if os.path.exists(TARGET_FILE) and os.path.getsize(TARGET_FILE) > 1000:
        print(f"Already present: {TARGET_FILE} ({os.path.getsize(TARGET_FILE)} bytes)")
        return

    print(f"Downloading {SOURCE_URL} ...")
    urllib.request.urlretrieve(SOURCE_URL, TARGET_FILE)

    size = os.path.getsize(TARGET_FILE)
    if size < 1000:
        raise RuntimeError(
            f"Download appears corrupt or incomplete ({size} bytes). "
            f"Try re-running this script, or download manually from "
            f"https://www.astro.com/ftp/swisseph/ephe/ and place the file "
            f"at {TARGET_FILE}"
        )

    print(f"Downloaded successfully: {TARGET_FILE} ({size} bytes)")


if __name__ == "__main__":
    main()
