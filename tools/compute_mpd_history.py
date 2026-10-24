"""Compute MISO's virtual-transaction MPD for every assessment year from the downloaded archive.

Usage:
    python tools/compute_mpd_history.py [--workers 4]

Attachment L defines the MPD as "the greater of the highest differential between the Day-Ahead
and Real-Time Locational Marginal Prices at the 50th percentile over the previous twelve (12)
months, assessed during the month of April and implemented May 1 … or the Minimum MPD Value"
($12.00/MWh; docs/market_rules.md §4.1). MISO's 2023 credit task team describes it as "the
median difference (P(50)) between DA & RT LMP's across all nodes".

The reading tested here (round 27): for each hour ending 1–24, the median of |DA − RT| over all
nodes and all days of the twelve months April (Y−1) → March (Y); the MPD for May Y → April Y+1
is the highest of those 24 medians. Checks against MISO's published values are printed:
$13.33 for the first MPD (May 2006), $4.89 for 2021, and the historic medians of the yearly
MPDs ($12.05 since the start, $10.23 over 10 years, $8.00 over 5 years).

Result (round 27): this reading is NOT MISO's method. It gives $4.87 for 2021 (published
$4.89) but $18.54 for 2006 (published $13.33) and $3.59 for 2016, below 2021's value although
MISO called 2021's "the lowest level since shortly after MISO's Virtual Market began"
(docs/rounds/round27_verification.md §4). The output is kept as a record of the test, not as
an MPD history.

Reads data/raw/miso/ only (assessment windows end in March 2025 at the latest, before the
sealed hold-out). Writes docs/data/mpd_history.csv.
"""

import argparse
import csv
import datetime
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from evobots.data.sources.miso_eras import read_day  # noqa: E402

RAW_DIRECTORY = Path("data/raw/miso")
OUTPUT_PATH = Path("docs/data/mpd_history.csv")
FIRST_ASSESSMENT_YEAR = 2006
LAST_ASSESSMENT_YEAR = 2025
MINIMUM_MPD_USD_PER_MWH = 12.0
# The $12 floor arrived with Attachment L v56.0.0, effective 2024-06-03 (docs/market_rules.md
# §4.1), so it applies from the 2024 assessment on.
FIRST_YEAR_WITH_FLOOR = 2024
# MISO's published values (docs/market_rules.md §4.1; 2023 credit task-team slides 9–11).
PUBLISHED_MPD_USD_PER_MWH = {2006: 13.33, 2021: 4.89}


def absolute_differences_by_hour(day_text):
    """24 arrays of |DA − RT| over all nodes for one day (empty when a file is missing)."""
    day = datetime.date.fromisoformat(day_text)
    day_ahead = read_day(RAW_DIRECTORY, day, "da")
    real_time = read_day(RAW_DIRECTORY, day, "rt")
    by_hour = [[] for _ in range(24)]
    if day_ahead is None or real_time is None:
        return [np.zeros(0, dtype=np.float32) for _ in range(24)]
    for key, day_ahead_hours in day_ahead.hours_by_location_and_value.items():
        if key[1] != "LMP":
            continue
        real_time_hours = real_time.hours_by_location_and_value.get(key)
        if real_time_hours is None:
            continue
        for hour_index, (day_ahead_price, real_time_price) in enumerate(
            zip(day_ahead_hours, real_time_hours)
        ):
            if day_ahead_price is not None and real_time_price is not None:
                by_hour[hour_index].append(abs(day_ahead_price - real_time_price))
    return [np.array(values, dtype=np.float32) for values in by_hour]


def assessment_window(year):
    """The twelve months April (year − 1) → March (year), as inclusive dates."""
    return datetime.date(year - 1, 4, 1), datetime.date(year, 3, 31)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()
    rows = []
    with Pool(arguments.workers) as pool:
        for year in range(FIRST_ASSESSMENT_YEAR, LAST_ASSESSMENT_YEAR + 1):
            first_day, last_day = assessment_window(year)
            days = [
                (first_day + datetime.timedelta(days=offset)).isoformat()
                for offset in range((last_day - first_day).days + 1)
            ]
            daily = pool.map(absolute_differences_by_hour, days, chunksize=8)
            medians = [
                float(np.median(np.concatenate([day[hour] for day in daily]))) for hour in range(24)
            ]
            highest = max(medians)
            row = {
                "assessment_year": year,
                "window_first_day": first_day.isoformat(),
                "window_last_day": last_day.isoformat(),
                "days_with_both_markets": sum(1 for day in daily if len(day[0])),
                "calculated_mpd_usd_per_mwh": round(highest, 2),
                "hour_ending_of_maximum": medians.index(highest) + 1,
                "with_floor_usd_per_mwh": round(
                    max(highest, MINIMUM_MPD_USD_PER_MWH)
                    if year >= FIRST_YEAR_WITH_FLOOR
                    else highest,
                    2,
                ),
                "published_mpd_usd_per_mwh": PUBLISHED_MPD_USD_PER_MWH.get(year, ""),
            }
            rows.append(row)
            print(row, flush=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    calculated = np.array([row["calculated_mpd_usd_per_mwh"] for row in rows])
    years = np.array([row["assessment_year"] for row in rows])
    for label, mask in [
        ("all years to 2021", years <= 2021),
        ("10 years 2012-2021", (years >= 2012) & (years <= 2021)),
        ("5 years 2017-2021", (years >= 2017) & (years <= 2021)),
    ]:
        print(f"median of yearly MPDs, {label}: {np.median(calculated[mask]):.2f}")
    print("published: since start 12.05, last 10 years 10.23, last 5 years 8.00")


if __name__ == "__main__":
    main()
