"""The hub forecast table: each hub's town forecast for its target days, per decision day.

For decision day X (bids for operating day X+1), the downloaded file of each hub's office
holds the newest PFM issue in the 24 hours before 10:30 Eastern on X
(`tools/fetch_nws_forecasts.py`). From it this module keeps, for the hub's forecast town
(`regions.FORECAST_TOWN_BY_HUB`, decided round 28), two target days:
- X+1, the operating day the bids are for (features 10, 11, 13–16);
- X+2, which the next decision day compares with its own forecast for the same day
  (feature 12, `temp_fcst_change`, aligned by target date).

Per target day (local calendar date): the forecast high and low from the max/min row (the
high sits under the ~7 p.m. column, the low under the ~7 a.m. column), and the mean
temperature and wind speed, plus the cloud codes, over that day's 3-hourly columns. Turning
cloud codes into fractions and highs and lows into degree-days is the feature layer's job
(M2). Missing stays missing: a missing file, town or value gives an empty cell and a status.

Target days after 2025-09-21 are never stored (the hold-out, `docs/design_spec.md` §7.2).

Example:
    >>> from evobots.data.sources.nws_pfm import parse_product, EXAMPLE_PRODUCT
    >>> town = parse_product(EXAMPLE_PRODUCT).towns[0]
    >>> summary = target_day_summary(town, datetime.date(2005, 4, 1))
    >>> summary["max_temp_degf"], summary["min_temp_degf"]
    (52.0, None)
"""

import csv
import datetime
import gzip
from pathlib import Path

from evobots.data.periods import EVOLUTION_LAST_DAY, HOLDOUT_LAST_DAY, MARKET_FIRST_DAY
from evobots.data.regions import FORECAST_TOWN_BY_HUB
from evobots.data.sources.nws_pfm import ForecastFormatError, parse_product
from evobots.data.visible import decision_time

NWS_RAW_DIRECTORY = Path("data/raw/nws")
# The fetch keeps the newest issue in the 24 hours before the decision time; an issue time
# printed outside that window is a typo in the source (obs.: "4305" for 2005 in LIX's
# 2005-06-20 issue), so the row is marked "bad issue time" and left empty, never repaired.
ISSUE_WINDOW = datetime.timedelta(hours=24)
FORECAST_TABLE_FILE_NAME = "hub_forecasts.csv.gz"
# Local hours from noon onward carry the day's high; earlier hours carry the morning low.
NOON_LOCAL_HOUR = 12
TARGET_OFFSETS_DAYS = (1, 2)
FORECAST_COLUMNS = (
    "decision_day",
    "hub",
    "target_day",
    "status",
    "issued_at_utc",
    "max_temp_degf",
    "min_temp_degf",
    "mean_temp_degf",
    "mean_wind_mph",
    "cloud_codes",
    "three_hour_columns",
)


def target_day_summary(town, target_day):
    """One town's forecast for one local calendar day.

    Args:
        town: a parsed TownForecast.
        target_day: the local date wanted.

    Returns:
        A dict with max_temp_degf, min_temp_degf, mean_temp_degf, mean_wind_mph (None when
        the issue has no value), cloud_codes (space-separated, time order) and
        three_hour_columns (how many 3-hourly columns fall on that day).
    """
    highs, lows = [], []
    for label in ("MAX/MIN", "MIN/MAX"):
        for column, value in town.values(label):
            if column.local_date() == target_day:
                (highs if column.local_hour >= NOON_LOCAL_HOUR else lows).append(value)

    def three_hourly(label):
        return [
            value
            for column, value in town.values(label)
            if column.step_hours == 3 and column.local_date() == target_day
        ]

    temperatures = three_hourly("TEMP")
    winds = three_hourly("WIND SPD")
    return {
        "max_temp_degf": highs[0] if highs else None,
        "min_temp_degf": lows[0] if lows else None,
        "mean_temp_degf": sum(temperatures) / len(temperatures) if temperatures else None,
        "mean_wind_mph": sum(winds) / len(winds) if winds else None,
        "cloud_codes": " ".join(three_hourly("CLOUDS")),
        "three_hour_columns": len(temperatures),
    }


def forecast_rows_for_decision_day(raw_directory, decision_day, holdout_permission=None):
    """Rows of the forecast table for one decision day: each hub × each target day.

    Args:
        raw_directory: data/raw/nws (offices as subfolders, files named YYYYMMDD.txt).
        decision_day: the day the bids are decided.
        holdout_permission: the hold-out accessor's permission; without it, target days after
            2025-09-21 are never produced.

    Returns:
        A list of dicts keyed by FORECAST_COLUMNS. status is "ok", "missing file",
        "unparsed issue" or "missing town".
    """
    rows = []
    towns_by_office = {}
    for hub, town_spec in sorted(FORECAST_TOWN_BY_HUB.items()):
        targets = [
            decision_day + datetime.timedelta(days=offset)
            for offset in TARGET_OFFSETS_DAYS
            if decision_day + datetime.timedelta(days=offset)
            <= (EVOLUTION_LAST_DAY if holdout_permission is None else HOLDOUT_LAST_DAY)
        ]
        if town_spec.office not in towns_by_office:
            path = Path(raw_directory) / town_spec.office / f"{decision_day:%Y%m%d}.txt"
            if not path.exists():
                towns_by_office[town_spec.office] = "missing file"
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
                try:
                    towns_by_office[town_spec.office] = parse_product(text).towns
                except ForecastFormatError:
                    towns_by_office[town_spec.office] = "unparsed issue"
        towns = towns_by_office[town_spec.office]
        town = None
        status = towns if isinstance(towns, str) else "missing town"
        if not isinstance(towns, str):
            town = next(
                (item for item in towns if town_spec.is_town(item.zone_code, item.name)), None
            )
            if town is not None:
                status = "ok"
                cutoff = decision_time(decision_day + datetime.timedelta(days=1))
                if not cutoff - ISSUE_WINDOW <= town.issued_at_utc <= cutoff:
                    status, town = "bad issue time", None
        for target_day in targets:
            row = {column: "" for column in FORECAST_COLUMNS}
            row.update(
                decision_day=decision_day.isoformat(),
                hub=hub,
                target_day=target_day.isoformat(),
                status=status,
            )
            if town is not None:
                row["issued_at_utc"] = town.issued_at_utc.isoformat()
                for key, value in target_day_summary(town, target_day).items():
                    row[key] = "" if value is None else value
            rows.append(row)
    return rows


def build_forecast_table(
    raw_directory=NWS_RAW_DIRECTORY,
    output_path=Path("data/store") / FORECAST_TABLE_FILE_NAME,
    first_decision_day=MARKET_FIRST_DAY - datetime.timedelta(days=1),
    last_decision_day=EVOLUTION_LAST_DAY - datetime.timedelta(days=1),
):
    """Write the hub forecast table (gzip CSV, write-then-rename).

    Returns:
        A dict counting rows by status.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_name(output_path.name + ".part")
    count_by_status = {}
    with gzip.open(partial_path, "wt", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FORECAST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        decision_day = first_decision_day
        while decision_day <= last_decision_day:
            for row in forecast_rows_for_decision_day(raw_directory, decision_day):
                writer.writerow(row)
                count_by_status[row["status"]] = count_by_status.get(row["status"], 0) + 1
            decision_day += datetime.timedelta(days=1)
    partial_path.replace(output_path)
    return count_by_status
