"""Write docs/data/benchmark_full_size_daily_pnl.csv: the full-size always-INC P&L per day.

Usage:
    uv run python tools/build_benchmark_fixture.py

Period 2015-03-01 → 2025-09-21 (the calibration periods of capital_sizing.md; it stops before
the sealed hold-out). One small derived series, committed so that the capital tests run
offline without the git-ignored price store. Always-DEC is its negative.
"""

import csv
from pathlib import Path

from evobots.calibration import full_size_benchmark_daily_pnl

FIXTURE_PATH = Path("docs/data/benchmark_full_size_daily_pnl.csv")
FIRST_DAY = "2015-03-01"
LAST_DAY = "2025-09-21"


def main():
    days, pnl = full_size_benchmark_daily_pnl(FIRST_DAY, LAST_DAY)
    with FIXTURE_PATH.open("w", encoding="utf-8", newline="") as fixture_file:
        writer = csv.writer(fixture_file, lineterminator="\n")
        writer.writerow(["date", "always_inc_usd"])
        for day, value in zip(days, pnl):
            writer.writerow([day, f"{value:.4f}"])
    print(f"{len(days)} days, {days[0]} → {days[-1]}, written to {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
