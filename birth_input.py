"""
birth_input.py

Shared helper for turning plain-language birth date/time + location
strings into a BirthData object (UTC datetime + coordinates), so this
logic lives in exactly one place rather than being copy-pasted across
every script that needs a birth chart. Anything that needs birth data —
run_chart.py, compare_house_systems.py, future synastry scripts, etc. —
should import resolve_birth_data from here rather than reimplementing it.
"""

import os
import concurrent.futures

# Disable numba's JIT compilation before timezonefinder imports it.
# timezonefinder uses numba to speed up its lookups, but numba's JIT
# compiler can crash in some cloud/notebook environments (Colab included)
# with an unrelated-looking "No such file or directory" error while
# trying to format an error message. Disabling JIT makes timezonefinder
# fall back to plain, un-compiled Python — marginally slower, but this
# only runs once per chart lookup, so the difference isn't noticeable,
# and it sidesteps the crash entirely.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

from zoneinfo import ZoneInfo
from dateutil import parser as date_parser
from geopy.geocoders import Nominatim
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from timezonefinder import TimezoneFinder

from chart_points import BirthData

# Cache geocoding results by location string. Nominatim (OpenStreetMap's
# free geocoding service) rate-limits at 1 request/second, and — since
# Streamlit Community Cloud apps often share outbound IP pools — can
# also temporarily rate-limit or block a shared IP range due to traffic
# from OTHER apps entirely, not just this one. Caching means re-running
# the same location (e.g. re-testing the same birth chart repeatedly,
# which is exactly what happens during normal use and debugging) never
# needs a second network call at all.
_GEOCODE_CACHE: dict[str, tuple[float, float, str]] = {}


@retry(
    # Catch bare Exception, not a specific geopy exception class. The
    # first version of this fix only caught GeopyError, and the same
    # raw "Non-successful status code 429" text kept appearing anyway
    # — meaning whatever geopy actually raises for this particular
    # failure isn't reliably a GeopyError subclass in every code path.
    # Rather than keep guessing at geopy's exact exception hierarchy,
    # this catches everything, so nothing can slip through unretried.
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)
def _geocode_with_retry(geolocator, location_str: str):
    return geolocator.geocode(location_str)


def resolve_birth_data(datetime_str: str, location_str: str, verbose: bool = True) -> BirthData:
    """
    Takes plain-language birth date/time and location strings, and
    resolves them into a BirthData object with correct UTC time and
    coordinates — geocoding the location and looking up the correct
    historical timezone (including DST) automatically, so you don't have
    to manually figure out UTC offsets or look up coordinates by hand.

    Example:
        birth = resolve_birth_data("December 24, 1981 1:30pm", "Brooklyn, New York, USA")
    """
    cache_key = location_str.strip().lower()
    if cache_key in _GEOCODE_CACHE:
        lat, lon, address = _GEOCODE_CACHE[cache_key]
    else:
        # Explicit timeout: geopy defaults to just 1 second, which is fine
        # on some networks (e.g. Colab) but too tight on others (e.g.
        # Streamlit Community Cloud), causing spurious GeocoderUnavailable
        # errors. User-agent identifies this specific app with contact
        # info, per Nominatim's usage policy — a generic/anonymous
        # user-agent is more likely to get caught up in bulk blocking.
        geolocator = Nominatim(
            user_agent="tenth-house-readings-astro-app (contact: via GitHub repo)",
            timeout=10,
        )
        try:
            # Run the (already-retrying) geocode call in a worker thread
            # with a hard outer timeout. geopy's own timeout=10 above is
            # meant to bound each individual attempt, but some real-world
            # network conditions (DNS resolution hanging, certain
            # connection-establishment phases) aren't reliably covered by
            # that parameter on every platform — the underlying call can
            # end up blocking far longer than 10s with no exception ever
            # raised, which previously meant the whole app would hang
            # indefinitely with zero error and zero log output.
            #
            # Deliberately NOT using ThreadPoolExecutor as a context
            # manager here — `with ThreadPoolExecutor() as executor:`
            # calls shutdown(wait=True) on exit, which blocks until the
            # background thread finishes, even after .result(timeout=...)
            # already gave up on it. If the geocode call is genuinely
            # stuck, that would just move the hang from one line to the
            # next. shutdown(wait=False) lets this function actually
            # return once the deadline passes, leaving the background
            # thread to leak harmlessly rather than blocking anything.
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_geocode_with_retry, geolocator, location_str)
            try:
                location = future.result(timeout=75)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    "Location lookup did not respond within 75 seconds"
                )
            finally:
                executor.shutdown(wait=False)
        except Exception as e:
            raise ValueError(
                f"The location lookup service is temporarily rate-limited "
                f"or unavailable after several retries ({type(e).__name__}: "
                f"{e}). This is an external service issue, not a problem "
                f"with your input — please wait a minute and try again."
            ) from e
        if location is None:
            raise ValueError(
                f"Could not find location: {location_str!r}. Try being more "
                f"specific — e.g. add a state/country, or use a nearby larger city."
            )
        lat, lon, address = location.latitude, location.longitude, location.address
        _GEOCODE_CACHE[cache_key] = (lat, lon, address)

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if tz_name is None:
        raise ValueError(
            f"Could not determine timezone for coordinates ({lat}, {lon})."
        )

    naive_dt = date_parser.parse(datetime_str)
    local_dt = naive_dt.replace(tzinfo=ZoneInfo(tz_name))
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

    if verbose:
        print(f"Resolved location: {address}")
        print(f"Coordinates: {lat:.4f}, {lon:.4f}")
        print(f"Timezone: {tz_name}")
        print(f"Local time: {local_dt}")
        print(f"UTC time: {utc_dt}\n")

    return BirthData(dt_utc=utc_dt, latitude=lat, longitude=lon)


import time

# Debounce for the live "as you type" checker specifically — Streamlit
# reruns the whole script on every keystroke, so without this,
# geocode_location_quick would fire a fresh network request for every
# partial string someone types ("W", "Wa", "Was", ...), easily exceeding
# Nominatim's 1-request-per-second limit well before anyone finishes
# typing a real location. This caps live checks to roughly once every
# 1.5 seconds regardless of typing speed, across all concurrent users
# on this process — a live check that's skipped just means "not
# confirmed yet" for a moment, which is harmless UI feedback, not a
# real failure the way a rate-limited submission-time lookup would be.
_LAST_LIVE_GEOCODE_CALL: dict[str, float] = {"time": 0.0}
_LIVE_GEOCODE_MIN_INTERVAL = 1.5  # seconds


def geocode_location_quick(location_str: str) -> tuple[bool, str | None]:
    """
    Quick, single-attempt geocode check meant for live UI feedback as
    someone types a location — e.g. showing a checkmark and the
    resolved address once it's recognized, before the reading is
    actually generated.

    Deliberately NOT the same robust, retrying lookup resolve_birth_data
    uses above. That one is built to be patient — several attempts with
    exponential backoff — because it runs once, at the moment a reading
    is actually being generated, and a real, if temporary, service
    hiccup shouldn't cause the whole thing to fail. A live-typing check
    needs the opposite property: if it hung for the same up-to-a-minute
    retry window on every rerun while someone's mid-typing, the UI
    would feel broken. So this makes exactly one attempt with a short
    timeout — a "not confirmed yet" here isn't a verdict that the
    location is invalid, just that this quick check didn't confirm it
    yet. The real, patient lookup with full retry logic still runs
    when the reading is generated, and is the actual source of truth.

    Shares the same _GEOCODE_CACHE as resolve_birth_data — a location
    confirmed here is already cached by the time the real submission
    happens, so nothing gets geocoded twice.

    Debounced (see _LIVE_GEOCODE_MIN_INTERVAL above) so rapid typing
    can't hammer Nominatim with a request per keystroke — a skipped
    check just returns "not confirmed yet," which is fine here since
    this function's whole job is soft, live feedback, not a source of
    truth.

    Returns (found, resolved_display_address_or_None).
    """
    cache_key = location_str.strip().lower()
    if not cache_key:
        return False, None
    if cache_key in _GEOCODE_CACHE:
        _, _, address = _GEOCODE_CACHE[cache_key]
        return True, address

    now = time.monotonic()
    if now - _LAST_LIVE_GEOCODE_CALL["time"] < _LIVE_GEOCODE_MIN_INTERVAL:
        # Too soon since the last live network call — skip this one
        # rather than risk piling onto a rate limit. Not cached as a
        # negative result, so the very next rerun (e.g. once typing
        # pauses) will try again normally.
        return False, None
    _LAST_LIVE_GEOCODE_CALL["time"] = now

    try:
        geolocator = Nominatim(
            user_agent="tenth-house-readings-astro-app (contact: via GitHub repo)",
            timeout=6,
        )
        location = geolocator.geocode(location_str)
    except Exception:
        return False, None
    if location is None:
        return False, None
    _GEOCODE_CACHE[cache_key] = (location.latitude, location.longitude, location.address)
    return True, location.address
