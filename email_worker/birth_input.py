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
import time
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

import requests
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
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)
def _geocode_with_retry(geolocator, location_str: str):
    return geolocator.geocode(location_str)


def _geocode_with_locationiq(location_str: str, api_key: str) -> tuple[float, float, str]:
    """
    Fallback geocoder used only when Nominatim (the primary, free
    geocoder above) has already exhausted its own retries. LocationIQ
    is built on the same OpenStreetMap data Nominatim uses, so results
    should closely match what this app already produces — the
    difference is a dedicated API key rather than Nominatim's free,
    publicly-shared IP pool, which is what actually gets rate-limited
    during a shared-infrastructure traffic spike.

    Only two quick attempts here, not its own long backoff sequence —
    by the time this runs, the primary lookup has already spent a
    while retrying, and this is meant to be a fast last resort, not a
    second multi-minute wait.
    """
    last_error = None
    for _attempt in range(2):
        try:
            response = requests.get(
                "https://us1.locationiq.com/v1/search",
                params={"key": api_key, "q": location_str, "format": "json"},
                timeout=10,
            )
            response.raise_for_status()
            results = response.json()
            if not results:
                raise ValueError(f"LocationIQ found no match for {location_str!r}")
            top = results[0]
            return float(top["lat"]), float(top["lon"]), top["display_name"]
        except Exception as e:
            last_error = e
    raise last_error


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
        geolocator = Nominatim(
            user_agent="tenth-house-readings-astro-app (contact: via GitHub repo)",
            timeout=10,
        )
        nominatim_error = None
        location = None
        try:
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
            nominatim_error = e

        if nominatim_error is not None:
            locationiq_key = os.environ.get("LOCATIONIQ_API_KEY")
            if locationiq_key:
                try:
                    lat, lon, address = _geocode_with_locationiq(location_str, locationiq_key)
                    _GEOCODE_CACHE[cache_key] = (lat, lon, address)
                except Exception as fallback_error:
                    raise ValueError(
                        f"The location lookup service is temporarily rate-limited "
                        f"or unavailable, and the backup geocoder also failed "
                        f"(primary: {type(nominatim_error).__name__}: "
                        f"{nominatim_error}; backup: "
                        f"{type(fallback_error).__name__}: {fallback_error}). "
                        f"This is an external service issue, not a problem with "
                        f"your input — please wait a minute and try again."
                    ) from fallback_error
            else:
                raise ValueError(
                    f"The location lookup service is temporarily rate-limited "
                    f"or unavailable after several retries "
                    f"({type(nominatim_error).__name__}: {nominatim_error}). "
                    f"This is an external service issue, not a problem with "
                    f"your input — please wait a minute and try again."
                ) from nominatim_error
        else:
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


_LAST_LIVE_GEOCODE_CALL: dict[str, float] = {"time": 0.0}
_LIVE_GEOCODE_MIN_INTERVAL = 1.5  # seconds


def geocode_location_quick(location_str: str) -> tuple[bool, str | None]:
    """
    Quick, single-attempt geocode check meant for live UI feedback as
    someone types a location. Deliberately NOT the same robust,
    retrying lookup resolve_birth_data uses (including its LocationIQ
    fallback) — this makes exactly one attempt with a short timeout,
    debounced so rapid typing can't hammer Nominatim with a request
    per keystroke.

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
