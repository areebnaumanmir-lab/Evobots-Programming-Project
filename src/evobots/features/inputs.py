"""The non-price inputs of the feature layer: forecasts, capacity, gas and EPU.

Each input arrives here in one plain structure, whether it was read from the built store or
generated for a test, so the features are computed by one code path:

- forecasts: {(decision_day, hub, target_day): (high °F, low °F, wind mph, cloud fraction)},
  from `data/store/hub_forecasts.csv.gz` (round 31);
- capacity: {(year, month, hub): (wind MW, solar MW)}, from
  `docs/data/hub_capacity_monthly.csv`, built from EIA-860M;
- gas: DailySeries "henry_hub_usd_per_mmbtu", from the newest
  `data/raw/series/eia_henry_hub/*.xls`;
- epu: DailySeries "epu_index", from the newest `data/raw/series/epu/*.csv`.

A missing file gives an empty input, so its features are missing (never filled).

**Cloud cover** (feature 16): the PFM sky-cover codes, as eighths of the sky (NWS Directive
10-503's PFM code table [verify]): CL clear 0/8, FW few 1–2/8, SC scattered 3–4/8, B1 5–6/8,
B2 7/8, BK broken 5–7/8 (older products), OV overcast 8/8. Each code counts at its
midpoint; MM (missing) is skipped; a day with no known code is missing.

**Capacity by hub area** (features 17–18, decided round 28): each MISO generator in the
newest EIA-860M workbook is assigned to the hub whose forecast town is nearest; units in the
four MISO South areas count only from December 2013, when MISO South joined.

Example:
    >>> cloud_fraction("CL OV MM")
    0.5
    >>> cloud_fraction("MM") is None
    True
"""

import csv
import dataclasses
import datetime
import gzip
from pathlib import Path

import numpy as np

from evobots.data.periods import EVOLUTION_LAST_DAY
from evobots.data.regions import FORECAST_TOWN_BY_HUB, nearest_hub
from evobots.data.sources.series import (
    DailySeries,
    read_eia_daily_spot,
    read_epu,
    series_from_observations,
)

FORECAST_TABLE_PATH = Path("data/store/hub_forecasts.csv.gz")
CAPACITY_TABLE_PATH = Path("docs/data/hub_capacity_monthly.csv")
GAS_DIRECTORY = Path("data/raw/series/eia_henry_hub")
EPU_DIRECTORY = Path("data/raw/series/epu")
GENERATOR_INVENTORY_DIRECTORY = Path("data/raw/series/eia_860m")
# Midpoint sky cover of each PFM code, as a fraction of the sky (eighths ÷ 8).
CLOUD_FRACTION_BY_CODE = {
    "CL": 0.0,
    "FW": 1.5 / 8,
    "SC": 3.5 / 8,
    "B1": 5.5 / 8,
    "B2": 7.0 / 8,
    "BK": 6.0 / 8,
    "OV": 1.0,
}
# MISO South (Arkansas, Louisiana, Mississippi, Texas areas) joined in December 2013.
MISO_SOUTH_HUBS = ("ARKANSAS.HUB", "LOUISIANA.HUB", "MS.HUB", "TEXAS.HUB")
MISO_SOUTH_FIRST_MONTH = (2013, 12)
CAPACITY_FIRST_MONTH = (2005, 1)


@dataclasses.dataclass(frozen=True)
class FeatureInputs:
    """Everything the feature layer reads besides prices.

    Attributes:
        forecasts: {(decision_day, hub, target_day): (high_degf, low_degf, wind_mph,
            cloud_fraction)}, each element a float or None.
        capacity: {(year, month, hub): (wind_mw, solar_mw)}.
        gas: DailySeries of Henry Hub spot prices, or None.
        epu: DailySeries of the EPU index, or None.
        description: where the inputs came from, for reports.
    """

    forecasts: dict
    capacity: dict
    gas: DailySeries | None
    epu: DailySeries | None
    description: str = ""


def cloud_fraction(codes_text):
    """Mean sky cover of a space-separated list of PFM cloud codes, or None."""
    fractions = [
        CLOUD_FRACTION_BY_CODE[code]
        for code in codes_text.split()
        if code in CLOUD_FRACTION_BY_CODE
    ]
    return sum(fractions) / len(fractions) if fractions else None


def float_or_none(text):
    """A float, or None for an empty cell."""
    return float(text) if text not in ("", None) else None


def read_forecasts(path=FORECAST_TABLE_PATH):
    """The forecast table as {(decision_day, hub, target_day): (high, low, wind, cloud)}."""
    path = Path(path)
    if not path.exists():
        return {}
    forecasts = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as table:
        for row in csv.DictReader(table):
            if row["status"] != "ok":
                continue
            key = (
                datetime.date.fromisoformat(row["decision_day"]),
                row["hub"],
                datetime.date.fromisoformat(row["target_day"]),
            )
            forecasts[key] = (
                float_or_none(row["max_temp_degf"]),
                float_or_none(row["min_temp_degf"]),
                float_or_none(row["mean_wind_mph"]),
                cloud_fraction(row["cloud_codes"]),
            )
    return forecasts


def months_between(first_month, last_month):
    """Every (year, month) from first_month to last_month inclusive."""
    year, month = first_month
    months = []
    while (year, month) <= last_month:
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def capacity_table_from_units(
    units, last_month=(EVOLUTION_LAST_DAY.year, EVOLUTION_LAST_DAY.month)
):
    """Wind and solar MW operating per hub area and month, from EIA-860M units.

    Args:
        units: `evobots.data.sources.eia860m.GeneratorUnit`s of MISO.
        last_month: the newest month to include (the evolution period ends 2025-09).

    Returns:
        {(year, month, hub): (wind_mw, solar_mw)} for every month from 2005-01.
    """
    from evobots.data.sources.eia860m import technology_group

    months = months_between(CAPACITY_FIRST_MONTH, last_month)
    month_index = {month: index for index, month in enumerate(months)}
    hubs = sorted(FORECAST_TOWN_BY_HUB)
    hub_index = {hub: index for index, hub in enumerate(hubs)}
    totals = np.zeros((len(months), len(hubs), 2))
    for unit in units:
        group = technology_group(unit.technology)
        if group not in ("Wind", "Solar") or unit.latitude_degrees is None:
            continue
        hub = nearest_hub(unit.latitude_degrees, unit.longitude_degrees)
        first = unit.first_month
        if hub in MISO_SOUTH_HUBS:
            first = max(first, MISO_SOUTH_FIRST_MONTH)
        first = max(first, CAPACITY_FIRST_MONTH)
        if first > last_month:
            continue
        start = month_index[first]
        end = len(months)
        if unit.retirement_month is not None:
            if unit.retirement_month <= first:
                continue
            end = month_index.get(unit.retirement_month, end)
        totals[start:end, hub_index[hub], 0 if group == "Wind" else 1] += unit.nameplate_mw
    return {
        (year, month, hub): (
            float(totals[month_position, hub_position, 0]),
            float(totals[month_position, hub_position, 1]),
        )
        for month_position, (year, month) in enumerate(months)
        for hub_position, hub in enumerate(hubs)
    }


def write_capacity_table(capacity, path=CAPACITY_TABLE_PATH):
    """Write the capacity table as CSV (year, month, hub, wind_mw, solar_mw)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as table:
        writer = csv.writer(table, lineterminator="\n")
        writer.writerow(["year", "month", "hub", "wind_mw", "solar_mw"])
        for (year, month, hub), (wind, solar) in sorted(capacity.items()):
            writer.writerow([year, month, hub, f"{wind:.1f}", f"{solar:.1f}"])


def read_capacity_table(path=CAPACITY_TABLE_PATH):
    """The capacity table written by `write_capacity_table`, or {} when absent."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as table:
        return {
            (int(row["year"]), int(row["month"]), row["hub"]): (
                float(row["wind_mw"]),
                float(row["solar_mw"]),
            )
            for row in csv.DictReader(table)
        }


def newest_file(directory, pattern):
    """The last file (by name, which starts with the download date) matching a pattern."""
    files = sorted(Path(directory).glob(pattern))
    return files[-1] if files else None


def load_feature_inputs(root=Path("."), is_forward_included=False):
    """Read every non-price input from the store and the downloaded series under root.

    `is_forward_included` also keeps the series' forward dates (2026-09-22 on) for paper
    trading; hold-out dates are never read here.
    """
    root = Path(root)
    gas_path = newest_file(root / GAS_DIRECTORY, "*.xls")
    epu_path = newest_file(root / EPU_DIRECTORY, "*.csv")
    return FeatureInputs(
        forecasts=read_forecasts(root / FORECAST_TABLE_PATH),
        capacity=read_capacity_table(root / CAPACITY_TABLE_PATH),
        gas=(
            read_eia_daily_spot(gas_path, "RNGWHHD", is_forward_included=is_forward_included)
            if gas_path
            else None
        ),
        epu=read_epu(epu_path, is_forward_included=is_forward_included) if epu_path else None,
        description="built store and downloaded series",
    )


def empty_feature_inputs():
    """No non-price inputs: weather, capacity, gas and EPU features are all missing."""
    return FeatureInputs({}, {}, None, None, "no inputs")


def synthetic_feature_inputs(days, hubs, seed=0, forecast_high_degf=None):
    """Seeded synthetic inputs for demos and tests (illustrative values, not data).

    Args:
        days: operating days (datetime.date), consecutive.
        hubs: hub names.
        seed: PCG64 seed.
        forecast_high_degf: optional (days, hubs) array of forecast highs for each operating
            day (e.g. the planted-rule input of `evobots.data.synthetic`); generated if None.

    Returns:
        FeatureInputs whose forecasts, capacity, gas and EPU follow simple seasonal or
        random-walk models.
    """
    generator = np.random.Generator(np.random.PCG64(seed))
    count = len(days)
    season = np.sin(2 * np.pi * np.arange(count) / 365.25 - np.pi / 2)
    if forecast_high_degf is None:
        forecast_high_degf = (
            60 + 25 * season[:, None] + 6 * generator.standard_normal((count, len(hubs)))
        )
    low = forecast_high_degf - 12 - 3 * np.abs(generator.standard_normal((count, len(hubs))))
    wind = np.abs(10 + 4 * generator.standard_normal((count, len(hubs))))
    cloud = np.clip(0.5 + 0.3 * generator.standard_normal((count, len(hubs))), 0, 1)
    forecasts = {}
    for index, day in enumerate(days):
        decision_day = day - datetime.timedelta(days=1)
        for hub_index, hub in enumerate(hubs):
            values = (
                float(forecast_high_degf[index, hub_index]),
                float(low[index, hub_index]),
                float(wind[index, hub_index]),
                float(cloud[index, hub_index]),
            )
            forecasts[(decision_day, hub, day)] = values
            # Yesterday's forecast for the same day: today's plus a small revision.
            revised = (values[0] - generator.normal(0, 2),) + values[1:]
            forecasts[(decision_day - datetime.timedelta(days=1), hub, day)] = revised
    capacity = {}
    first, last = days[0], days[-1]
    for year, month in months_between((first.year, first.month), (last.year, last.month)):
        years = (year - first.year) + month / 12
        for hub_index, hub in enumerate(hubs):
            capacity[(year, month, hub)] = (300.0 * years * (1 + hub_index % 3), 50.0 * years**1.5)
    gas_values = 4.0 * np.exp(np.cumsum(0.03 * generator.standard_normal(count)))
    epu_values = np.exp(4.7 + 0.4 * generator.standard_normal(count))
    gas = series_from_observations(
        "henry_hub_usd_per_mmbtu",
        "$/MMBtu",
        "synthetic",
        [(day, float(value)) for day, value in zip(days, gas_values) if day.weekday() < 5],
    )
    epu = series_from_observations(
        "epu_index", "index points", "synthetic", list(zip(days, map(float, epu_values)))
    )
    return FeatureInputs(forecasts, capacity, gas, epu, "synthetic demo inputs")
