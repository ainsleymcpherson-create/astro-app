"""
birth_input.py

Shared helper for turning plain-language birth date/time + location
strings into a BirthData object (UTC datetime + coordinates), so this
logic lives in exactly one place rather than being copy-pasted across
every script that needs a birth chart. Anything that needs birth data —
run_chart.py, compare_house_systems.py, future synastry scripts, etc. —
should import resolve_birth_data from here rather than reimplementing it.
"""

from zoneinfo import ZoneInfo
from dateutil import parser as date_parser
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

from chart_points import BirthData


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
    geolocator = Nominatim(user_agent="astro_chart_app")
    location = geolocator.geocode(location_str)
    if location is None:
        raise ValueError(
            f"Could not find location: {location_str!r}. Try being more "
            f"specific — e.g. add a state/country, or use a nearby larger city."
        )
    lat, lon = location.latitude, location.longitude

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
        print(f"Resolved location: {location.address}")
        print(f"Coordinates: {lat:.4f}, {lon:.4f}")
        print(f"Timezone: {tz_name}")
        print(f"Local time: {local_dt}")
        print(f"UTC time: {utc_dt}\n")

    return BirthData(dt_utc=utc_dt, latitude=lat, longitude=lon)
