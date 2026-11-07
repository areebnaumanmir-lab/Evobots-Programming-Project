"""`evobots data build --stage A`: the hub price store, checked against the recorded numbers.

Stage A is the trading hubs that exist each day (`docs/design_spec.md` §7.10). The build reads the raw
MISO files already on disk (offline; MISO data is built locally and never redistributed,
round 25), one operating day at a time through the era reader, for the evolution period
2005-04-01 → 2025-09-21 only. It writes `hub_prices.csv.gz` (write-then-rename) and then
checks itself:
- the per-hub price and spread statistics against `docs/data/hub_price_stats.csv`
  (2019-01-01 → 2025-09-21; Claude Science, reproduced in round 21);
- when the cleared-bids files are present, the hub liquidity statistics against
  `docs/data/hub_volume_stats.csv` (the 15th of each month 2023-01 → 2025-09; round 26).

When the weather forecasts are on disk it also writes `hub_forecasts.csv.gz`
(`evobots.data.forecasts`) and checks that no stored issue is later than its decision time.

Example:
    >>> import numpy as np
    >>> day_ahead = np.array([30.0, 40.0, 35.0, 32.0, 38.0])
    >>> real_time = np.array([25.0, 45.0, 35.0, 30.0, 40.0])
    >>> statistics = hub_price_statistics(day_ahead, real_time)
    >>> statistics["spread_mean"], statistics["hours"]
    (0.0, 5)
    >>> values_agree(0.4313, 0.431), values_agree(0.4320, 0.431)
    (True, False)
"""

import csv
import datetime
import gzip
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from evobots.data.forecasts import FORECAST_TABLE_FILE_NAME, NWS_RAW_DIRECTORY, build_forecast_table
from evobots.data.periods import EVOLUTION_LAST_DAY, MARKET_FIRST_DAY
from evobots.data.sources.miso_cleared_bids import hub_volume_statistics, read_day_volumes
from evobots.data.sources.miso_eras import read_day

RAW_DIRECTORY = Path("data/raw/miso")
STORE_DIRECTORY = Path("data/store")
HUB_PRICES_FILE_NAME = "hub_prices.csv.gz"
PRICE_STATISTICS_REFERENCE_PATH = Path("docs/data/hub_price_stats.csv")
VOLUME_STATISTICS_REFERENCE_PATH = Path("docs/data/hub_volume_stats.csv")
# The window of hub_price_stats.csv (capital_sizing.md §1).
PRICE_STATISTICS_FIRST_DAY = datetime.date(2019, 1, 1)
PRICE_STATISTICS_LAST_DAY = EVOLUTION_LAST_DAY
# The cleared-bids sample of hub_volume_stats.csv: the 15th of each month (round 26).
VOLUME_SAMPLE_FIRST_MONTH = (2023, 1)
VOLUME_SAMPLE_LAST_MONTH = (2025, 9)
VOLUME_SAMPLE_DAY_OF_MONTH = 15
HOURS_PER_DAY = 24
MARKETS = ("da", "rt")
VALUE_TYPES = ("LMP", "MCC", "MLC")
HUB_PRICE_COLUMNS = ("da_lmp", "rt_lmp", "da_mcc", "rt_mcc", "da_mlc", "rt_mlc")
# Volume statistics: the store's names → the reference file's column names.
VOLUME_REFERENCE_COLUMN_BY_NAME = {
    "observable_hub_hours": "observable_hub_hours",
    "observable_share": "observable_share",
    "total_mw_p10": "total_MW_p10",
    "total_mw_median": "total_MW_median",
    "total_mw_p90": "total_MW_p90",
    "dec_mw_median": "DEC_MW_median",
    "inc_mw_median": "INC_MW_median",
    "participants_median": "participants_median",
}


def hub_rows_for_day(arguments):
    """Hub price rows for one operating day: [(day, hour, hub, {column: value})].

    Args:
        arguments: (raw_directory, day) as one tuple, for multiprocessing.

    Returns:
        A list of rows; a market whose file is missing contributes nothing (never filled).
    """
    raw_directory, day = arguments
    values_by_hour_and_hub = {}
    for market in MARKETS:
        prices = read_day(raw_directory, day, market)
        if prices is None:
            continue
        for hub in prices.trading_hubs():
            for value_type in VALUE_TYPES:
                hours = prices.hours_by_location_and_value.get((hub, value_type))
                if hours is None:
                    continue
                for hour_index, value in enumerate(hours):
                    column = f"{market}_{value_type.lower()}"
                    values_by_hour_and_hub.setdefault((hour_index + 1, hub), {})[column] = value
    return [
        (day, hour, hub, values) for (hour, hub), values in sorted(values_by_hour_and_hub.items())
    ]


def days_between(first_day, last_day):
    """Every date from first_day to last_day inclusive."""
    return [
        first_day + datetime.timedelta(days=offset)
        for offset in range((last_day - first_day).days + 1)
    ]


def build_hub_prices(
    raw_directory=RAW_DIRECTORY,
    output_path=STORE_DIRECTORY / HUB_PRICES_FILE_NAME,
    first_day=MARKET_FIRST_DAY,
    last_day=EVOLUTION_LAST_DAY,
    worker_count=4,
):
    """Write the hub price table for a range of operating days, write-then-rename.

    Args:
        raw_directory: the downloaded MISO files.
        output_path: the gzip CSV to write: date, hour_ending_est, hub, then
            HUB_PRICE_COLUMNS in $/MWh (empty = not published).
        first_day: first operating day.
        last_day: last operating day; must not be in the hold-out (the reader refuses).
        worker_count: parallel processes.

    Returns:
        The number of rows written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_name(output_path.name + ".part")
    tasks = [(Path(raw_directory), day) for day in days_between(first_day, last_day)]
    row_count = 0
    with (
        Pool(worker_count) as pool,
        gzip.open(partial_path, "wt", encoding="utf-8", newline="") as output_file,
    ):
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(["date", "hour_ending_est", "hub", *HUB_PRICE_COLUMNS])
        for rows in pool.imap(hub_rows_for_day, tasks, chunksize=8):
            for day, hour, hub, values in rows:
                writer.writerow(
                    [day.isoformat(), hour, hub]
                    + [
                        "" if values.get(column) is None else f"{values[column]:g}"
                        for column in HUB_PRICE_COLUMNS
                    ]
                )
                row_count += 1
    partial_path.replace(output_path)
    return row_count


def read_hub_spreads(path, first_day, last_day):
    """DA and RT prices per hub for hours where both exist, from the hub price table.

    Returns:
        {hub: (DA prices array, RT prices array)} in $/MWh.
    """
    day_ahead_by_hub, real_time_by_hub = {}, {}
    first_text, last_text = first_day.isoformat(), last_day.isoformat()
    with gzip.open(path, "rt", encoding="utf-8") as hub_file:
        for row in csv.DictReader(hub_file):
            if not first_text <= row["date"] <= last_text:
                continue
            if row["da_lmp"] and row["rt_lmp"]:
                day_ahead_by_hub.setdefault(row["hub"], []).append(float(row["da_lmp"]))
                real_time_by_hub.setdefault(row["hub"], []).append(float(row["rt_lmp"]))
    return {
        hub: (np.array(day_ahead_by_hub[hub]), np.array(real_time_by_hub[hub]))
        for hub in sorted(day_ahead_by_hub)
    }


def hub_price_statistics(day_ahead_prices, real_time_prices):
    """The columns of docs/data/hub_price_stats.csv for one hub ($/MWh unless a share).

    Maths: spread s = DA − RT; spread_std uses ddof = 1; percentiles interpolate linearly
    (NumPy's default). Excess kurtosis is the bias-corrected sample estimate
    G2 = ((n + 1) g2 + 6)(n − 1) / ((n − 2)(n − 3)), where g2 = m4 / m2² − 3 uses central
    moments (pandas' `kurt`); it reproduces all eight recorded values to the third decimal,
    while g2 alone is about 0.01 % lower (round 28). Together these reproduce every value of
    the recorded file.
    """
    spread = day_ahead_prices - real_time_prices
    absolute_spread = np.abs(spread)
    centred = spread - spread.mean()
    count = len(spread)
    moment_excess_kurtosis = (centred**4).mean() / (centred**2).mean() ** 2 - 3
    sample_excess_kurtosis = (
        ((count + 1) * moment_excess_kurtosis + 6) * (count - 1) / ((count - 2) * (count - 3))
    )
    return {
        "hours": len(spread),
        "DA_median": float(np.median(day_ahead_prices)),
        "DA_p99": float(np.percentile(day_ahead_prices, 99)),
        "DA_max": float(day_ahead_prices.max()),
        "RT_median": float(np.median(real_time_prices)),
        "RT_p1": float(np.percentile(real_time_prices, 1)),
        "RT_p99": float(np.percentile(real_time_prices, 99)),
        "RT_p99_9": float(np.percentile(real_time_prices, 99.9)),
        "RT_max": float(real_time_prices.max()),
        "RT_min": float(real_time_prices.min()),
        "RT_share_above_500": float((real_time_prices > 500).mean()),
        "RT_share_below_0": float((real_time_prices < 0).mean()),
        "spread_mean": float(spread.mean()),
        "spread_median": float(np.median(spread)),
        "spread_std": float(spread.std(ddof=1)),
        "spread_p1": float(np.percentile(spread, 1)),
        "spread_p99": float(np.percentile(spread, 99)),
        "abs_spread_median": float(np.median(absolute_spread)),
        "abs_spread_p95": float(np.percentile(absolute_spread, 95)),
        "abs_spread_p99": float(np.percentile(absolute_spread, 99)),
        "abs_spread_max": float(absolute_spread.max()),
        "spread_excess_kurtosis": float(sample_excess_kurtosis),
    }


def values_agree(computed, recorded_text):
    """True when a computed value rounds to a recorded one at the recorded precision.

    Args:
        computed: the value computed here.
        recorded_text: the recorded value, as text or number (e.g. "0.431").
    """
    recorded = str(recorded_text)
    decimals = len(recorded.split(".")[1]) if "." in recorded else 0
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    return abs(computed - float(recorded)) <= tolerance


def compare_with_reference(computed_by_hub, reference_path, column_by_name=None):
    """Compare computed statistics with a recorded CSV, value by value.

    Args:
        computed_by_hub: {hub: {statistic name: value}}.
        reference_path: a CSV with a `hub` column and one column per statistic.
        column_by_name: optional mapping from computed names to reference column names.

    Returns:
        (agreeing count, list of "hub statistic: computed vs recorded" disagreements).
    """
    agreeing, disagreements = 0, []
    with open(reference_path, encoding="utf-8") as reference_file:
        for row in csv.DictReader(reference_file):
            computed = computed_by_hub.get(row["hub"])
            for name, column in (
                column_by_name or {key: key for key in row if key != "hub"}
            ).items():
                if computed is None or name not in computed:
                    disagreements.append(f"{row['hub']} {column}: missing vs {row[column]}")
                elif values_agree(computed[name], row[column]):
                    agreeing += 1
                else:
                    disagreements.append(
                        f"{row['hub']} {column}: {computed[name]:.6g} vs {row[column]}"
                    )
    return agreeing, disagreements


def volume_sample_days():
    """The 15th of each month 2023-01 → 2025-09: the cleared-bids sample (round 26)."""
    year, month = VOLUME_SAMPLE_FIRST_MONTH
    days = []
    while (year, month) <= VOLUME_SAMPLE_LAST_MONTH:
        days.append(datetime.date(year, month, VOLUME_SAMPLE_DAY_OF_MONTH))
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    return days


def hub_volume_statistics_from_raw(raw_directory=RAW_DIRECTORY):
    """Hub liquidity statistics on the sample days, or None when a file is missing."""
    volumes = []
    sample_days = volume_sample_days()
    for day in sample_days:
        bids_path = Path(raw_directory) / f"{day:%Y%m%d}_bids_cb.zip"
        exante_path = Path(raw_directory) / f"{day:%Y%m%d}_da_exante_lmp.csv"
        if not (bids_path.exists() and exante_path.exists()):
            return None
        volumes.extend(read_day_volumes(bids_path, exante_path, day))
    return hub_volume_statistics(volumes, len(sample_days) * HOURS_PER_DAY)


def forecast_issues_after_decision_time(path):
    """Rows of the forecast table whose issue time is after their decision time (should be 0)."""
    from evobots.data.visible import decision_time

    late = 0
    with gzip.open(path, "rt", encoding="utf-8") as table:
        for row in csv.DictReader(table):
            if not row["issued_at_utc"]:
                continue
            operating_day = datetime.date.fromisoformat(row["decision_day"]) + datetime.timedelta(
                days=1
            )
            issued = datetime.datetime.fromisoformat(row["issued_at_utc"])
            late += issued > decision_time(operating_day)
    return late


def build_stage_a(
    raw_directory=RAW_DIRECTORY,
    store_directory=STORE_DIRECTORY,
    worker_count=4,
    nws_directory=NWS_RAW_DIRECTORY,
):
    """Build the Stage A store and check it; return report lines and whether every check passed.

    Returns:
        (list of report lines, True when every check passed).
    """
    output_path = Path(store_directory) / HUB_PRICES_FILE_NAME
    row_count = build_hub_prices(raw_directory, output_path, worker_count=worker_count)
    lines = [f"Wrote {output_path}: {row_count:,} day-hour-hub rows, 2005-04-01 → 2025-09-21"]
    spreads = read_hub_spreads(output_path, PRICE_STATISTICS_FIRST_DAY, PRICE_STATISTICS_LAST_DAY)
    computed = {hub: hub_price_statistics(*prices) for hub, prices in spreads.items()}
    agreeing, disagreements = compare_with_reference(computed, PRICE_STATISTICS_REFERENCE_PATH)
    lines.append(f"hub_price_stats.csv: {agreeing} values agree, {len(disagreements)} differ")
    lines += [f"  differs: {text}" for text in disagreements]
    is_passing = not disagreements
    volumes = hub_volume_statistics_from_raw(raw_directory)
    if volumes is None:
        lines.append("hub_volume_stats.csv: not checked (cleared-bids sample files missing)")
    else:
        agreeing, disagreements = compare_with_reference(
            volumes, VOLUME_STATISTICS_REFERENCE_PATH, VOLUME_REFERENCE_COLUMN_BY_NAME
        )
        lines.append(f"hub_volume_stats.csv: {agreeing} values agree, {len(disagreements)} differ")
        lines += [f"  differs: {text}" for text in disagreements]
        is_passing = is_passing and not disagreements
    if Path(nws_directory).exists():
        forecast_path = Path(store_directory) / FORECAST_TABLE_FILE_NAME
        count_by_status = build_forecast_table(nws_directory, forecast_path)
        summary = ", ".join(
            f"{status} {count:,}" for status, count in sorted(count_by_status.items())
        )
        lines.append(f"Wrote {forecast_path}: {summary}")
        late = forecast_issues_after_decision_time(forecast_path)
        lines.append(f"forecast issues after their decision time: {late}")
        is_passing = is_passing and late == 0
    else:
        lines.append("hub_forecasts.csv.gz: not built (no weather forecasts on disk)")
    return lines, is_passing
