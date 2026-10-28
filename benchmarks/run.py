"""Time the hot code paths and append the results to benchmarks/results.csv (CLAUDE.md §14.3).

Usage:
    python benchmarks/run.py [--milestone M0] [--repeats 5]

Each benchmark runs --repeats times; the best time is recorded (the least disturbed by other
work on the machine). One row per benchmark: date, milestone, commit, machine, benchmark,
items, best seconds, items per second. Run it at the end of every milestone; compare rows
for the same benchmark across milestones, and profile before optimising anything.

Benchmarks so far (M0, the capital slice):
    trailing_p99_series      the point-in-time 1-in-100-day loss on every day of the fixture
    simulate_benchmark_equity  one sized equity path over the fixture
    capital_summary          one summary of a set of capital settings
The §14.3 targets (≥ 100,000 trader-years per hour, page loads) apply from M3 and M1.5.
"""

import argparse
import csv
import datetime
import os
import platform
import subprocess
import time
from pathlib import Path

from evobots.calibration import read_benchmark_fixture
from evobots.cli import calibration_capital_summary
from evobots.config.capital import CapitalSettings
from evobots.sizing import simulate_benchmark_equity, trailing_p99_series

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = REPOSITORY_ROOT / "benchmarks/results.csv"
FIXTURE_PATH = REPOSITORY_ROOT / "docs/data/benchmark_full_size_daily_pnl.csv"
RESULT_COLUMNS = [
    "date",
    "milestone",
    "commit",
    "machine",
    "benchmark",
    "items",
    "item_unit",
    "best_seconds",
    "items_per_second",
]


def best_seconds(function, repeats):
    """Shortest wall-clock time of `repeats` calls to function()."""
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        times.append(time.perf_counter() - start)
    return min(times)


def current_commit():
    """Short hash of HEAD, with '+' when the working tree has changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPOSITORY_ROOT,
        ).stdout.strip()
        is_dirty = (
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                capture_output=True,
                text=True,
                check=True,
                cwd=REPOSITORY_ROOT,
            ).stdout.strip()
            != ""
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return commit + ("+" if is_dirty else "")


def machine_description():
    """Operating system, processor count and Python version, in one short string."""
    return f"{platform.system()} {os.cpu_count()} cores Python {platform.python_version()}"


def benchmark_rows(milestone, repeats):
    """Run every benchmark; return one result row each."""
    _, daily_pnl_usd = read_benchmark_fixture(FIXTURE_PATH)
    day_count = len(daily_pnl_usd)
    p99_series = trailing_p99_series(daily_pnl_usd)
    settings = CapitalSettings()
    cases = [
        ("trailing_p99_series", day_count, "days", lambda: trailing_p99_series(daily_pnl_usd)),
        (
            "simulate_benchmark_equity",
            day_count,
            "days",
            lambda: simulate_benchmark_equity(daily_pnl_usd, 1_500_000, 0.02, p99_series),
        ),
        ("capital_summary", 1, "summaries", lambda: calibration_capital_summary(settings)),
    ]
    common = {
        "date": datetime.date.today().isoformat(),
        "milestone": milestone,
        "commit": current_commit(),
        "machine": machine_description(),
    }
    rows = []
    for name, items, item_unit, function in cases:
        seconds = best_seconds(function, repeats)
        rows.append(
            {
                **common,
                "benchmark": name,
                "items": items,
                "item_unit": item_unit,
                "best_seconds": f"{seconds:.6f}",
                "items_per_second": f"{items / seconds:.1f}",
            }
        )
    return rows


def main():
    """Run the benchmarks, append them to results.csv and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--milestone", default="M0")
    parser.add_argument("--repeats", type=int, default=5)
    arguments = parser.parse_args()
    rows = benchmark_rows(arguments.milestone, arguments.repeats)
    is_new_file = not RESULTS_PATH.exists()
    with RESULTS_PATH.open("a", newline="", encoding="utf-8") as results_file:
        writer = csv.DictWriter(results_file, fieldnames=RESULT_COLUMNS)
        if is_new_file:
            writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(
            f"{row['benchmark']:28} {row['best_seconds']:>10} s  "
            f"{row['items_per_second']:>14} {row['item_unit']}/s"
        )


if __name__ == "__main__":
    main()
