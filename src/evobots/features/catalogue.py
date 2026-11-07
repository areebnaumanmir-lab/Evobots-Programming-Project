"""The feature catalogue: the 25 inputs a trader may read (`docs/design_spec.md` §8).

One registry entry per feature: code name, display name, unit, level, kind, one-line meaning
and the data it needs. The GP unit checker, the hindsight check, the app's labels and
`docs/features.md` all read from here, so a feature is described in exactly one place.

**Levels** (§8, "three tables at three granularities", plus calendar):
- `location-hour`: one value per location, hour and day;
- `location`: one value per location and day;
- `region`: one value per hub area and day, broadcast to that area's locations;
- `global`: one value per day;
- `calendar`: known in advance (hour, weekday, holiday).

**Kinds:** `number` (unit-typed), `category` (used only inside `in {…}`), `boolean`.

Example:
    >>> len(FEATURES)
    25
    >>> FEATURE_BY_NAME["spread_mean_7d"].display_name
    'Average DA − RT spread, last 7 visible days ($/MWh)'
    >>> FEATURE_BY_NAME["cdd_fcst"].unit.label()
    '°F·day'
"""

import dataclasses

from evobots.units import (
    DEGF,
    DEGF_DAY,
    FRACTION,
    FRACTION_PER_DAY,
    HOUR,
    INDEX_POINTS,
    MPH,
    MW,
    USD_PER_MMBTU,
    USD_PER_MWH,
)

LEVELS = ("location-hour", "location", "region", "global", "calendar")
KINDS = ("number", "category", "boolean")
# Location types as MISO's files name them (obs., data/store/locations.csv).
LOCATION_TYPES = ("Hub", "Loadzone", "Gennode", "Interface")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# The hub areas, in the order of `evobots.config.capital.STAGE_A_HUBS`.
REGIONS = (
    "ARKANSAS.HUB",
    "ILLINOIS.HUB",
    "INDIANA.HUB",
    "LOUISIANA.HUB",
    "MICHIGAN.HUB",
    "MINN.HUB",
    "MS.HUB",
    "TEXAS.HUB",
)


@dataclasses.dataclass(frozen=True)
class Feature:
    """One catalogue entry.

    Attributes:
        name: code name, e.g. "spread_mean_7d".
        display_name: the app's label, with its unit.
        unit: a `evobots.units.Unit` (FRACTION for categories and booleans).
        level: one of LEVELS.
        kind: one of KINDS.
        meaning: one line in plain English.
        sources: the data it needs, e.g. ("MISO DA LMP", "MISO RT LMP").
        categories: for a category feature, its members in code order; else ().
        typical_range: (low, high) used to draw constants before data ranges are measured.
        is_hindsight_check: True for features re-scored as missing in the hindsight check
            (§8: `epu` and the `gas_*` features).
    """

    name: str
    display_name: str
    unit: object
    level: str
    kind: str
    meaning: str
    sources: tuple
    categories: tuple = ()
    typical_range: tuple = (0.0, 1.0)
    is_hindsight_check: bool = False

    def __post_init__(self):
        """Reject an unknown level or kind, and categories on a non-category feature."""
        if self.level not in LEVELS or self.kind not in KINDS:
            raise ValueError(f"{self.name}: bad level or kind")
        if (self.kind == "category") != bool(self.categories):
            raise ValueError(f"{self.name}: categories are for category features only")


PRICES = ("MISO DA LMP", "MISO RT LMP (final)")
FORECASTS = ("NWS Point Forecast Matrices (IEM archive)",)
FEATURES = (
    Feature(
        "spread_mean_7d",
        "Average DA − RT spread, last 7 visible days ($/MWh)",
        USD_PER_MWH,
        "location-hour",
        "number",
        "mean of DA − RT for this location and hour over the 7 newest days with final RT",
        PRICES,
        typical_range=(-20.0, 20.0),
    ),
    Feature(
        "spread_mean_28d",
        "Average DA − RT spread, last 28 visible days ($/MWh)",
        USD_PER_MWH,
        "location-hour",
        "number",
        "the same over the 28 newest days with final RT",
        PRICES,
        typical_range=(-15.0, 15.0),
    ),
    Feature(
        "spread_std_28d",
        "Spread volatility, last 28 visible days ($/MWh)",
        USD_PER_MWH,
        "location-hour",
        "number",
        "standard deviation of DA − RT over the 28 newest days with final RT",
        PRICES,
        typical_range=(0.0, 80.0),
    ),
    Feature(
        "spread_pos_frac_28d",
        "Share of days with DA above RT, last 28 visible days",
        FRACTION,
        "location-hour",
        "number",
        "share of those 28 days on which DA was above RT",
        PRICES,
        typical_range=(0.0, 1.0),
    ),
    Feature(
        "spread_spike_frac_28d",
        "Share of days with a spread beyond $50, last 28 visible days",
        FRACTION,
        "location-hour",
        "number",
        "share of those 28 days with |DA − RT| above $50/MWh",
        PRICES,
        typical_range=(0.0, 0.3),
    ),
    Feature(
        "da_last",
        "Latest visible DA price, same hour ($/MWh)",
        USD_PER_MWH,
        "location-hour",
        "number",
        "DA price of this location and hour on D−1, published the afternoon before the decision",
        ("MISO DA LMP",),
        typical_range=(0.0, 200.0),
    ),
    Feature(
        "congestion_share_28d",
        "Congestion share of the DA price, last 28 visible days",
        FRACTION,
        "location-hour",
        "number",
        "mean DA congestion component ÷ mean DA price, this hour, days D−28 … D−1",
        ("MISO DA LMP", "MISO DA MCC"),
        typical_range=(-0.5, 0.5),
    ),
    Feature(
        "loc_type",
        "Location type",
        FRACTION,
        "location",
        "category",
        "hub, load zone, generator node or interface",
        ("MISO location list",),
        categories=LOCATION_TYPES,
    ),
    Feature(
        "loc_region",
        "Location's hub area",
        FRACTION,
        "location",
        "category",
        "the hub whose DA price this location tracked most closely over the past 365 days",
        ("MISO DA LMP",),
        categories=REGIONS,
    ),
    Feature(
        "temp_max_fcst",
        "Forecast high for the operating day (°F)",
        DEGF,
        "region",
        "number",
        "NWS forecast high for D at the area's town, newest issue before the decision",
        FORECASTS,
        typical_range=(0.0, 105.0),
    ),
    Feature(
        "temp_min_fcst",
        "Forecast low for the operating day (°F)",
        DEGF,
        "region",
        "number",
        "NWS forecast low for D at the area's town",
        FORECASTS,
        typical_range=(-20.0, 85.0),
    ),
    Feature(
        "temp_fcst_change",
        "Change in the forecast high since yesterday (°F)",
        DEGF,
        "region",
        "number",
        "today's forecast high for D minus yesterday's forecast high for the same day D",
        FORECASTS,
        typical_range=(-15.0, 15.0),
    ),
    Feature(
        "hdd_fcst",
        "Forecast heating degree-days (°F·day)",
        DEGF_DAY,
        "region",
        "number",
        "max(0, 65 °F − (forecast high + low) ÷ 2)",
        FORECASTS,
        typical_range=(0.0, 60.0),
    ),
    Feature(
        "cdd_fcst",
        "Forecast cooling degree-days (°F·day)",
        DEGF_DAY,
        "region",
        "number",
        "max(0, (forecast high + low) ÷ 2 − 65 °F)",
        FORECASTS,
        typical_range=(0.0, 30.0),
    ),
    Feature(
        "wind_fcst",
        "Forecast mean wind speed (mph)",
        MPH,
        "region",
        "number",
        "mean of the 3-hourly forecast wind speeds for D",
        FORECASTS,
        typical_range=(0.0, 30.0),
    ),
    Feature(
        "cloud_fcst",
        "Forecast cloud cover (fraction)",
        FRACTION,
        "region",
        "number",
        "mean of the 3-hourly forecast sky cover for D, as a fraction of the sky",
        FORECASTS,
        typical_range=(0.0, 1.0),
    ),
    Feature(
        "wind_cap_region",
        "Wind capacity operating in the area (MW)",
        MW,
        "region",
        "number",
        "nameplate wind MW operating in the area in the month of D−1 (EIA-860M)",
        ("EIA-860M",),
        typical_range=(0.0, 12000.0),
    ),
    Feature(
        "solar_cap_region",
        "Solar capacity operating in the area (MW)",
        MW,
        "region",
        "number",
        "nameplate solar MW operating in the area in the month of D−1 (EIA-860M)",
        ("EIA-860M",),
        typical_range=(0.0, 8000.0),
    ),
    Feature(
        "gas_price",
        "Henry Hub gas price ($/MMBtu)",
        USD_PER_MMBTU,
        "global",
        "number",
        "Henry Hub spot price on the newest trading day visible at the decision",
        ("EIA Henry Hub spot (RNGWHHD)",),
        typical_range=(1.5, 12.0),
        is_hindsight_check=True,
    ),
    Feature(
        "gas_chg_5d",
        "Change in the gas price over 5 trading days ($/MMBtu)",
        USD_PER_MMBTU,
        "global",
        "number",
        "newest visible Henry Hub price minus the price 5 trading days earlier",
        ("EIA Henry Hub spot (RNGWHHD)",),
        typical_range=(-1.5, 1.5),
        is_hindsight_check=True,
    ),
    Feature(
        "gas_vol_20d",
        "Gas price volatility, 20 trading days (fraction per day)",
        FRACTION_PER_DAY,
        "global",
        "number",
        "standard deviation of daily log changes in Henry Hub over 20 trading days",
        ("EIA Henry Hub spot (RNGWHHD)",),
        typical_range=(0.0, 0.15),
        is_hindsight_check=True,
    ),
    Feature(
        "epu",
        "US economic policy uncertainty (index points)",
        INDEX_POINTS,
        "global",
        "number",
        "Baker–Bloom–Davis daily EPU index, newest value visible at the decision",
        ("policyuncertainty.com daily EPU",),
        typical_range=(20.0, 500.0),
        is_hindsight_check=True,
    ),
    Feature(
        "hour",
        "Hour ending (1–24, Eastern Standard Time)",
        HOUR,
        "calendar",
        "number",
        "the hour ending of the location-hour, in EST all year as MISO's files state",
        (),
        typical_range=(1.0, 24.0),
    ),
    Feature(
        "weekday",
        "Day of week of the operating day",
        FRACTION,
        "calendar",
        "category",
        "Monday to Sunday",
        (),
        categories=WEEKDAYS,
    ),
    Feature(
        "holiday",
        "NERC off-peak holiday",
        FRACTION,
        "calendar",
        "boolean",
        "one of the six NERC holidays; a Sunday holiday also flags the Monday after",
        (),
    ),
)
FEATURE_BY_NAME = {feature.name: feature for feature in FEATURES}
FEATURE_NAMES = tuple(FEATURE_BY_NAME)
NUMBER_FEATURES = tuple(feature.name for feature in FEATURES if feature.kind == "number")
CATEGORY_FEATURES = tuple(feature.name for feature in FEATURES if feature.kind == "category")
BOOLEAN_FEATURES = tuple(feature.name for feature in FEATURES if feature.kind == "boolean")
HINDSIGHT_CHECK_FEATURES = tuple(feature.name for feature in FEATURES if feature.is_hindsight_check)
