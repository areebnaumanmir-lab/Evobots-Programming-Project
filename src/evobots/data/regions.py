"""The eight hub areas: each hub's forecast town, and which area a place belongs to.

Decided in round 28 (`docs/rounds/round28_answers.md` §7):
- **Weather:** each hub's regional weather inputs (features 10–16) come from one fixed
  NWS forecast town, its office's town nearest the hub's load centre (round 23's
  nearest-load rule). If that town is missing from an issue, the input is missing that day.
- **Areas:** a place (e.g. a generator, for features 17–18) belongs to the hub whose
  forecast town is nearest by great-circle distance.

Towns are identified by NWS zone code and the start of their printed name, because the
printed coordinates were re-surveyed by 0.01–0.03° over the years (obs., round 28). NWS
renumbered two zones, so those towns list both codes (obs., round 31, same name and
coordinates before and after): New Orleans LAZ061 → LAZ077 from 2022-04-06, Beaumont
TXZ215 → TXZ515 from 2023-03-09. The coordinates below are those printed in the forecasts
(obs.).

Example:
    >>> nearest_hub(46.9, -96.8)  # Fargo, North Dakota
    'MINN.HUB'
    >>> nearest_hub(30.45, -91.19)  # Baton Rouge
    'LOUISIANA.HUB'
"""

import dataclasses
import math

# Mean Earth radius for great-circle distances, km (IUGG mean radius).
EARTH_RADIUS_KILOMETRES = 6371.0088


@dataclasses.dataclass(frozen=True)
class ForecastTown:
    """One hub's forecast town.

    Attributes:
        office: the NWS office that forecasts for it, e.g. "MPX".
        zone_codes: its NWS zone codes, e.g. ("MNZ060",); more than one when NWS renumbered it.
        name_prefix: the start of its printed name, upper case, e.g. "MINNEAPOLIS".
        latitude_degrees: printed latitude, north.
        longitude_degrees: printed longitude, negative west.
    """

    office: str
    zone_codes: tuple
    name_prefix: str
    latitude_degrees: float
    longitude_degrees: float

    def is_town(self, zone_code, name):
        """True when a parsed town block is this town."""
        return zone_code in self.zone_codes and name.upper().startswith(self.name_prefix)


# Each hub's forecast town (round 28). Zone codes and coordinates as printed (obs.).
FORECAST_TOWN_BY_HUB = {
    "MINN.HUB": ForecastTown("MPX", ("MNZ060",), "MINNEAPOLIS", 44.88, -93.22),
    "MICHIGAN.HUB": ForecastTown("DTX", ("MIZ076",), "DETROIT", 42.43, -83.02),
    "INDIANA.HUB": ForecastTown("IND", ("INZ047",), "INDIANAPOLIS", 39.73, -86.28),
    "ILLINOIS.HUB": ForecastTown("ILX", ("ILZ029",), "CITY OF PEORIA", 40.67, -89.68),
    "ARKANSAS.HUB": ForecastTown("LZK", ("ARZ044",), "LITTLE ROCK", 34.73, -92.24),
    "MS.HUB": ForecastTown("JAN", ("MSZ049",), "JACKSON", 32.32, -90.08),
    "LOUISIANA.HUB": ForecastTown("LIX", ("LAZ061", "LAZ077"), "NEW ORLEANS", 29.98, -90.25),
    "TEXAS.HUB": ForecastTown("LCH", ("TXZ215", "TXZ515"), "BEAUMONT", 29.95, -94.03),
}


def great_circle_kilometres(first_latitude, first_longitude, second_latitude, second_longitude):
    """Great-circle distance between two points, in kilometres (haversine formula).

    Args:
        first_latitude: degrees north.
        first_longitude: degrees, negative west.
        second_latitude: degrees north.
        second_longitude: degrees, negative west.

    Returns:
        Distance along the Earth's surface, km.

    Example:
        >>> round(great_circle_kilometres(0.0, 0.0, 0.0, 1.0), 1)
        111.2
    """
    first_latitude_radians = math.radians(first_latitude)
    second_latitude_radians = math.radians(second_latitude)
    latitude_change_radians = second_latitude_radians - first_latitude_radians
    longitude_change_radians = math.radians(second_longitude - first_longitude)
    haversine = (
        math.sin(latitude_change_radians / 2) ** 2
        + math.cos(first_latitude_radians)
        * math.cos(second_latitude_radians)
        * math.sin(longitude_change_radians / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KILOMETRES * math.asin(math.sqrt(haversine))


def nearest_hub(latitude_degrees, longitude_degrees):
    """The hub whose forecast town is nearest to a place.

    Args:
        latitude_degrees: the place's latitude, north.
        longitude_degrees: the place's longitude, negative west.

    Returns:
        A hub name, e.g. "MINN.HUB"; ties go to the hub first in alphabetical order.
    """
    return min(
        sorted(FORECAST_TOWN_BY_HUB),
        key=lambda hub: great_circle_kilometres(
            latitude_degrees,
            longitude_degrees,
            FORECAST_TOWN_BY_HUB[hub].latitude_degrees,
            FORECAST_TOWN_BY_HUB[hub].longitude_degrees,
        ),
    )
