"""Readers for the daily series: risk-free rate, Henry Hub gas, WTI oil, EPU and GPR.

Each source is one file downloaded by `tools/fetch_series.py` into data/raw/series/
(`CLAUDE.md` §7.5–7.7; FRED DTB3 decided in round 28). Each reader returns `DailySeries`
objects: one value per observation date, in the source's own unit, with no gaps filled. A
day the source leaves blank (a holiday in DTB3, a non-trading day for Henry Hub) is simply
absent.

**Hold-out.** The files run into the sealed hold-out (2025-09-22 → 2026-09-21) and beyond.
Every reader keeps only observations dated on or before the last day of the evolution
period (2025-09-21) unless it is given the hold-out accessor's permission object
(`CLAUDE.md` §7.2, §12.4). An observation dated 2025-09-21 can only inform decisions for
operating days after it, so this cut can never hide data the evolution period needs.

**Publication lags** (when an observation becomes visible) belong to `visible()`, not to
these readers; each series records its lag in `PUBLICATION_LAG_DAYS_BY_SERIES`.

Example:
    >>> import datetime
    >>> series = DailySeries(
    ...     name="example",
    ...     unit="percent",
    ...     source="test",
    ...     days=(datetime.date(2020, 1, 2),),
    ...     values=(1.5,),
    ... )
    >>> series.value_by_day()[datetime.date(2020, 1, 2)]
    1.5
"""

import csv
import dataclasses
import datetime
import math

import xlrd

from evobots.data.periods import EVOLUTION_LAST_DAY

# Days from an observation's date until a trader can see it, by series name. A trading
# or business day counts as one; the visible() layer applies these (M1).
# - DTB3: the Federal Reserve's H.15 release is published the next business day
#   (assumption, round 28; `docs/rounds/round28_answers.md` §3).
# - Henry Hub: lag 1 trading day (`CLAUDE.md` §7.5).
# - EPU: lag 1 day (`CLAUDE.md` §7.6).
# - GPR and WTI are reporting only; their lag is recorded for the reports' event analysis.
PUBLICATION_LAG_DAYS_BY_SERIES = {
    "treasury_bill_3_month_discount_fraction": 1,
    "henry_hub_usd_per_mmbtu": 1,
    "wti_usd_per_barrel": 1,
    "epu_index": 1,
    "gpr_index": 1,
    "gpr_threat_index": 1,
    "gpr_act_index": 1,
}
# The 3-month bill matures in 91 days; discount rates are quoted on a 360-day year.
TREASURY_BILL_DAYS = 91
DISCOUNT_BASIS_YEAR_DAYS = 360
# Accepted first header cells of FRED's CSV download (FRED renamed DATE in 2024-25).
FRED_DATE_HEADERS = ("observation_date", "DATE")
# The EIA spreadsheets' data sheet, and the row index of their first data row.
EIA_DATA_SHEET_NAME = "Data 1"
EIA_FIRST_DATA_ROW = 3
# GPR columns kept, and the series name each becomes.
GPR_SERIES_NAME_BY_COLUMN = {
    "GPRD": "gpr_index",
    "GPRD_THREAT": "gpr_threat_index",
    "GPRD_ACT": "gpr_act_index",
}


@dataclasses.dataclass(frozen=True)
class DailySeries:
    """One daily series as the source published it: observation dates and values.

    Attributes:
        name: code name with its unit, e.g. "henry_hub_usd_per_mmbtu".
        unit: unit of the values, e.g. "$/MMBtu", "percent", "index points".
        source: where the file came from, e.g. "EIA RNGWHHD".
        days: observation dates, strictly increasing.
        values: one float per date, in `unit`.
    """

    name: str
    unit: str
    source: str
    days: tuple
    values: tuple

    def value_by_day(self):
        """The series as a mapping from observation date to value."""
        return dict(zip(self.days, self.values))


class SeriesFormatError(ValueError):
    """A downloaded file doesn't have the layout its reader expects."""


def series_from_observations(name, unit, source, observations, holdout_permission=None):
    """Build a `DailySeries`, keeping only evolution-period dates without permission.

    Args:
        name: code name of the series.
        unit: unit of the values.
        source: the file's origin, for reports.
        observations: (date, value) pairs in any order; value None means "no observation".
        holdout_permission: the hold-out accessor's permission object; None keeps dates up
            to the end of the evolution period only.

    Returns:
        A DailySeries sorted by date.

    Raises:
        SeriesFormatError: when a date occurs twice.

    Example:
        >>> import datetime
        >>> series = series_from_observations(
        ...     "x",
        ...     "percent",
        ...     "test",
        ...     [(datetime.date(2025, 9, 22), 2.0), (datetime.date(2025, 9, 21), 1.0)],
        ... )
        >>> series.days, series.values
        ((datetime.date(2025, 9, 21),), (1.0,))
    """
    kept = sorted(
        (day, value)
        for day, value in observations
        if value is not None and (holdout_permission is not None or day <= EVOLUTION_LAST_DAY)
    )
    days = tuple(day for day, _ in kept)
    if len(set(days)) != len(days):
        raise SeriesFormatError(f"{name}: a date occurs more than once")
    return DailySeries(
        name=name,
        unit=unit,
        source=source,
        days=days,
        values=tuple(value for _, value in kept),
    )


def float_or_none(text):
    """A cell's number, or None for a blank or FRED's "." placeholder.

    Example:
        >>> float_or_none("4.50"), float_or_none(""), float_or_none(".")
        (4.5, None, None)
    """
    if isinstance(text, (int, float)):
        return float(text)
    stripped = text.strip()
    if stripped in ("", "."):
        return None
    return float(stripped)


def read_fred_dtb3(path, holdout_permission=None):
    """Read FRED's DTB3 CSV: the 3-month Treasury bill rate, discount basis.

    FRED quotes percent; the series is stored as a fraction (5 % → 0.05), the project's
    unit for rates (`CLAUDE.md` §14.1).

    Args:
        path: the downloaded `DTB3.csv`.
        holdout_permission: see `series_from_observations`.

    Returns:
        DailySeries "treasury_bill_3_month_discount_fraction".

    Raises:
        SeriesFormatError: when the header isn't FRED's.
    """
    with open(path, newline="", encoding="utf-8") as csv_file:
        rows = list(csv.reader(csv_file))
    if not rows or rows[0][0] not in FRED_DATE_HEADERS or rows[0][1] != "DTB3":
        raise SeriesFormatError(f"{path}: not a FRED DTB3 download (header {rows[:1]})")
    observations = []
    for row in rows[1:]:
        if row:
            quoted = float_or_none(row[1])
            fraction = None if quoted is None else quoted / 100
            observations.append((datetime.date.fromisoformat(row[0]), fraction))
    return series_from_observations(
        "treasury_bill_3_month_discount_fraction",
        "fraction (discount basis)",
        "FRED DTB3 (Federal Reserve H.15)",
        observations,
        holdout_permission,
    )


def daily_risk_free_log_return(discount_rate_fraction):
    """Continuously compounded return per calendar day of holding a 3-month bill.

    Maths (`docs/maths.md` §3.1): a 91-day bill quoted at discount rate d costs
    P = 1 − d · 91/360 per dollar of face value, so holding it to maturity earns
    r = −ln(P) / 91 per calendar day.

    Args:
        discount_rate_fraction: the DTB3 quote as a fraction (0.05 for 5 %).

    Returns:
        Log return per calendar day (a fraction).

    Example:
        >>> round(daily_risk_free_log_return(0.05) * 365, 5)
        0.05102
    """
    price_per_dollar_of_face = (
        1 - discount_rate_fraction * TREASURY_BILL_DAYS / DISCOUNT_BASIS_YEAR_DAYS
    )
    return -math.log(price_per_dollar_of_face) / TREASURY_BILL_DAYS


def eia_rows_to_series(rows, workbook_date_mode, name, unit, source_key):
    """Turn the rows of an EIA history spreadsheet's "Data 1" sheet into observations.

    Args:
        rows: each row's cell values; row 1 holds ("Sourcekey", key), row 2 the headers,
            data starts at row 3 with (Excel serial date, value).
        workbook_date_mode: the workbook's date system (0 = 1900-based, 1 = 1904-based).
        name: code name of the series.
        unit: unit of the values.
        source_key: the EIA series key the sheet must carry, e.g. "RNGWHHD".

    Returns:
        A list of (date, value) pairs.

    Raises:
        SeriesFormatError: when the source key or header row differs.
    """
    if len(rows) < EIA_FIRST_DATA_ROW or rows[1][:2] != ["Sourcekey", source_key]:
        raise SeriesFormatError(f"{name}: expected source key {source_key}, got {rows[1:2]}")
    if rows[2][0] != "Date":
        raise SeriesFormatError(f"{name}: expected a Date header, got {rows[2]}")
    observations = []
    for row in rows[EIA_FIRST_DATA_ROW:]:
        if row[0] in ("", None):
            continue
        day = xlrd.xldate_as_datetime(row[0], workbook_date_mode).date()
        observations.append((day, float_or_none(row[1])))
    return observations


def read_eia_daily_spot(path, source_key, holdout_permission=None):
    """Read an EIA daily spot-price history spreadsheet (`.xls`).

    Args:
        path: the downloaded file, e.g. `RNGWHHDd.xls`.
        source_key: "RNGWHHD" (Henry Hub gas, $/MMBtu) or "RWTC" (WTI oil, $/barrel).
        holdout_permission: see `series_from_observations`.

    Returns:
        DailySeries "henry_hub_usd_per_mmbtu" or "wti_usd_per_barrel".
    """
    name, unit = {
        "RNGWHHD": ("henry_hub_usd_per_mmbtu", "$/MMBtu"),
        "RWTC": ("wti_usd_per_barrel", "$/barrel"),
    }[source_key]
    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_name(EIA_DATA_SHEET_NAME)
    rows = [sheet.row_values(row_index) for row_index in range(sheet.nrows)]
    observations = eia_rows_to_series(rows, workbook.datemode, name, unit, source_key)
    return series_from_observations(
        name, unit, f"EIA {source_key}", observations, holdout_permission
    )


def read_epu(path, holdout_permission=None):
    """Read the daily US Economic Policy Uncertainty CSV (Baker, Bloom & Davis).

    Args:
        path: the downloaded `All_Daily_Policy_Data.csv`.
        holdout_permission: see `series_from_observations`.

    Returns:
        DailySeries "epu_index" (index points).

    Raises:
        SeriesFormatError: when the header differs from day, month, year, daily_policy_index.
    """
    with open(path, newline="", encoding="utf-8") as csv_file:
        rows = list(csv.reader(csv_file))
    if not rows or rows[0] != ["day", "month", "year", "daily_policy_index"]:
        raise SeriesFormatError(f"{path}: unexpected EPU header {rows[:1]}")
    observations = [
        (datetime.date(int(row[2]), int(row[1]), int(row[0])), float_or_none(row[3]))
        for row in rows[1:]
        if row
    ]
    return series_from_observations(
        "epu_index", "index points", "policyuncertainty.com", observations, holdout_permission
    )


def gpr_rows_to_observations(rows):
    """Turn the GPR sheet's rows into observations per kept column.

    Args:
        rows: the sheet's cell values; row 0 is the header with "DAY" (yyyymmdd text) and
            the GPR columns.

    Returns:
        A mapping from series name to a list of (date, value) pairs.

    Raises:
        SeriesFormatError: when a kept column is missing.

    Example:
        >>> rows = [
        ...     ["DAY", "GPRD", "GPRD_THREAT", "GPRD_ACT"],
        ...     ["20260301", 274.0, 300.0, 250.0],
        ... ]
        >>> gpr_rows_to_observations(rows)["gpr_index"]
        [(datetime.date(2026, 3, 1), 274.0)]
    """
    header = rows[0]
    missing = [column for column in ["DAY", *GPR_SERIES_NAME_BY_COLUMN] if column not in header]
    if missing:
        raise SeriesFormatError(f"GPR file lacks columns {missing}")
    day_index = header.index("DAY")
    observations_by_name = {name: [] for name in GPR_SERIES_NAME_BY_COLUMN.values()}
    for row in rows[1:]:
        day_text = str(row[day_index]).strip()
        if not day_text:
            continue
        day = datetime.datetime.strptime(day_text, "%Y%m%d").date()
        for column, name in GPR_SERIES_NAME_BY_COLUMN.items():
            observations_by_name[name].append((day, float_or_none(row[header.index(column)])))
    return observations_by_name


def read_gpr(path, holdout_permission=None):
    """Read the daily Geopolitical Risk spreadsheet (Caldara & Iacoviello; reporting only).

    Args:
        path: the downloaded `data_gpr_daily_recent.xls`.
        holdout_permission: see `series_from_observations`.

    Returns:
        A mapping from series name ("gpr_index", "gpr_threat_index", "gpr_act_index") to
        DailySeries in index points (100 = the 1985–2019 average).
    """
    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    rows = [sheet.row_values(row_index) for row_index in range(sheet.nrows)]
    return {
        name: series_from_observations(
            name, "index points", "matteoiacoviello.com GPR", observations, holdout_permission
        )
        for name, observations in gpr_rows_to_observations(rows).items()
    }
