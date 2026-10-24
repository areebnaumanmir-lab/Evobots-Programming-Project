"""Recompute Claude Science's calibration numbers from the archive downloaded in round 20.

Usage:
    uv run python tools/check_against_claude_science.py

Reads data/store/hub_prices.csv.gz (tools/build_miso_hub_prices.py) and compares, for
2019-01-01 → 2025-09-21 (the calibration sample; it stops before the sealed hold-out):
  1. every column of docs/data/hub_price_stats.csv (Claude Science, round 14);
  2. the full-size benchmark P&L of docs/capital_sizing.md §4 (always-INC / always-DEC at
     the per-hub caps: 5 MW, 4 MW at MS.HUB).

Also checks the point-in-time trailing p99 of capital_sizing.md §4b and redraws its figure
(the original was stored inside Claude Science and did not travel) as
docs/data/figures/point_in_time_full_size_threshold.svg.

Writes docs/data/claude_science_check.csv (one row per compared number) and prints a summary.
Quantiles use NumPy's default (linear interpolation); Claude Science's method is not recorded,
so small differences in tail quantiles are expected.
"""

import csv
import gzip
from collections import defaultdict
from pathlib import Path

import numpy as np

HUB_PRICES_PATH = Path("data/store/hub_prices.csv.gz")
REFERENCE_STATS_PATH = Path("docs/data/hub_price_stats.csv")
OUTPUT_PATH = Path("docs/data/claude_science_check.csv")
FIRST_DAY = "2019-01-01"
LAST_DAY = "2025-09-21"
# Per-hub liquidity caps in MW (capital_sizing.md §3): 5 MW, and 4 MW at MS.HUB.
CAP_MW_BY_HUB = {"MS.HUB": 4.0}
DEFAULT_CAP_MW = 5.0

# Claude Science's benchmark numbers, capital_sizing.md §4 (USD per day at full size).
REFERENCE_BENCHMARK = {
    "always_inc_mean_day_usd": 474.0,
    "always_inc_p99_daily_loss_usd": 27897.0,
    "always_inc_p999_daily_loss_usd": 118855.0,
    "always_inc_worst_day_usd": 492173.0,
    "always_inc_worst_5_days_usd": 503873.0,
    "always_inc_worst_20_days_usd": 484372.0,
    "always_dec_mean_day_usd": -474.0,
    "always_dec_p99_daily_loss_usd": 19351.0,
    "always_dec_p999_daily_loss_usd": 69479.0,
    "always_dec_worst_day_usd": 176554.0,
    "always_dec_worst_5_days_usd": 380617.0,
    "always_dec_worst_20_days_usd": 373652.0,
}


def load_hub_series():
    """{hub: (da_prices, rt_prices)} for hours where both exist, plus daily INC P&L."""
    da_by_hub = defaultdict(list)
    rt_by_hub = defaultdict(list)
    inc_pnl_by_day = defaultdict(float)
    with gzip.open(HUB_PRICES_PATH, "rt", encoding="utf-8") as hub_file:
        for row in csv.DictReader(hub_file):
            if not FIRST_DAY <= row["date"] <= LAST_DAY:
                continue
            if not (row["da_lmp"] and row["rt_lmp"]):
                continue
            da_price = float(row["da_lmp"])
            rt_price = float(row["rt_lmp"])
            da_by_hub[row["hub"]].append(da_price)
            rt_by_hub[row["hub"]].append(rt_price)
            cap_mw = CAP_MW_BY_HUB.get(row["hub"], DEFAULT_CAP_MW)
            inc_pnl_by_day[row["date"]] += cap_mw * (da_price - rt_price)
    series = {
        hub: (np.array(da_by_hub[hub]), np.array(rt_by_hub[hub])) for hub in sorted(da_by_hub)
    }
    daily_inc_pnl = np.array([inc_pnl_by_day[day] for day in sorted(inc_pnl_by_day)])
    return series, daily_inc_pnl, sorted(inc_pnl_by_day)


def hub_statistics(da_prices, rt_prices):
    """The columns of hub_price_stats.csv for one hub."""
    spread = da_prices - rt_prices
    absolute_spread = np.abs(spread)
    centred = spread - spread.mean()
    excess_kurtosis = (centred**4).mean() / (centred**2).mean() ** 2 - 3
    return {
        "hours": len(spread),
        "DA_median": np.median(da_prices),
        "DA_p99": np.percentile(da_prices, 99),
        "DA_max": da_prices.max(),
        "RT_median": np.median(rt_prices),
        "RT_p1": np.percentile(rt_prices, 1),
        "RT_p99": np.percentile(rt_prices, 99),
        "RT_p99_9": np.percentile(rt_prices, 99.9),
        "RT_max": rt_prices.max(),
        "RT_min": rt_prices.min(),
        "RT_share_above_500": (rt_prices > 500).mean(),
        "RT_share_below_0": (rt_prices < 0).mean(),
        "spread_mean": spread.mean(),
        "spread_median": np.median(spread),
        "spread_std": spread.std(ddof=1),
        "spread_p1": np.percentile(spread, 1),
        "spread_p99": np.percentile(spread, 99),
        "abs_spread_median": np.median(absolute_spread),
        "abs_spread_p95": np.percentile(absolute_spread, 95),
        "abs_spread_p99": np.percentile(absolute_spread, 99),
        "abs_spread_max": absolute_spread.max(),
        "spread_excess_kurtosis": excess_kurtosis,
    }


def worst_rolling_loss(daily_pnl, window_days):
    """Largest loss (positive number) over any run of window_days consecutive days."""
    rolling_sums = np.convolve(daily_pnl, np.ones(window_days), mode="valid")
    return -rolling_sums.min()


def benchmark_statistics(daily_inc_pnl, days):
    results = {}
    for name, daily_pnl in (("always_inc", daily_inc_pnl), ("always_dec", -daily_inc_pnl)):
        daily_loss = -daily_pnl
        results[f"{name}_mean_day_usd"] = daily_pnl.mean()
        results[f"{name}_p99_daily_loss_usd"] = np.percentile(daily_loss, 99)
        results[f"{name}_p999_daily_loss_usd"] = np.percentile(daily_loss, 99.9)
        results[f"{name}_worst_day_usd"] = daily_loss.max()
        results[f"{name}_worst_day_date"] = days[int(daily_loss.argmax())]
        results[f"{name}_worst_5_days_usd"] = worst_rolling_loss(daily_pnl, 5)
        results[f"{name}_worst_20_days_usd"] = worst_rolling_loss(daily_pnl, 20)
    return results


# --- Point-in-time trailing p99 (capital_sizing.md §4b), checked in round 21 -------------

# Visibility and window rules of sizing.py (capital_sizing.md §4b).
NEWEST_VISIBLE_LAG_DAYS = 6
TRAILING_WINDOW_DAYS = 365
WARM_UP_DAYS = 90
DAILY_RISK_BUDGET = 0.02
# Rows of the §4b table: operating day → trailing p99 in USD (Claude Science).
REFERENCE_TRAILING_P99 = {
    "2021-02-13": 12261.0,
    "2021-02-18": 12261.0,
    "2021-02-25": 18777.0,
    "2021-03-20": 24859.0,
    "2022-02-26": 16787.0,
    "2022-12-23": 31519.0,
    "2022-12-31": 39723.0,
    "2023-12-31": 19885.0,
}


def trailing_p99_by_day(daily_inc_pnl, days):
    """{operating day: trailing p99 loss (worse of INC/DEC) or None during warm-up}."""
    day_index = {day: index for index, day in enumerate(days)}
    results = {}
    for day in days:
        newest_visible = day_index[day] - NEWEST_VISIBLE_LAG_DAYS
        if newest_visible < 0:
            results[day] = None
            continue
        first_visible = max(0, newest_visible - TRAILING_WINDOW_DAYS + 1)
        window = daily_inc_pnl[first_visible : newest_visible + 1]
        if len(window) < WARM_UP_DAYS:
            results[day] = None
            continue
        results[day] = max(np.percentile(-window, 99), np.percentile(window, 99))
    return results


def check_trailing_estimator():
    _, daily_inc_pnl, days = load_hub_series()
    trailing = trailing_p99_by_day(daily_inc_pnl, days)
    rows = []
    for day, reference_value in REFERENCE_TRAILING_P99.items():
        rows.append(
            {
                "group": "capital_sizing_section_4b",
                "item": f"trailing p99 {day}",
                "claude_science": reference_value,
                "round_21": round(float(trailing[day]), 1),
                "difference": round(float(trailing[day]) - reference_value, 1),
            }
        )
    values = [value for value in trailing.values() if value is not None]
    first_trading_day = next(day for day in days if trailing[day] is not None)
    breaches_by_year = defaultdict(lambda: [0, 0])
    for index, day in enumerate(days):
        if trailing[day] is None:
            continue
        is_breach = abs(daily_inc_pnl[index]) > trailing[day]
        breaches_by_year[day[:4]][0] += is_breach
        breaches_by_year[day[:4]][1] += 1
    total_breaches = sum(count for count, _ in breaches_by_year.values())
    total_days = sum(days_counted for _, days_counted in breaches_by_year.values())
    print(f"first day with a trailing estimate: {first_trading_day}")
    print(
        f"trailing p99 range ${min(values):,.0f} – ${max(values):,.0f}, "
        f"median ${np.median(values):,.0f}; C_full median ${np.median(values) / DAILY_RISK_BUDGET:,.0f}"
    )
    print(
        f"breach rate {100 * total_breaches / total_days:.2f} % of {total_days} days; by year:",
        {
            year: round(100 * count / days_counted, 1)
            for year, (count, days_counted) in sorted(breaches_by_year.items())
        },
    )
    for row in rows:
        print(f"{row['item']:<26} {row['claude_science']:>10,.0f} {row['round_21']:>10,.0f}")
    return rows, trailing, days


FIGURE_PATH = Path("docs/data/figures/point_in_time_full_size_threshold.svg")
FIGURE_WIDTH = 960
FIGURE_HEIGHT = 300
FIGURE_MARGIN_LEFT = 56
FIGURE_MARGIN_BOTTOM = 28
STORM_MARKERS = {"2021-02-15": "Uri", "2022-12-23": "Elliott"}


def write_threshold_figure(trailing, days):
    """Ink-only SVG of C_full = trailing p99 / budget over time (capital_sizing.md §4b figure)."""
    points = [(day, trailing[day] / DAILY_RISK_BUDGET) for day in days if trailing[day] is not None]
    values = [value for _, value in points]
    low, high = 0.0, max(values) * 1.05
    plot_width = FIGURE_WIDTH - FIGURE_MARGIN_LEFT
    plot_height = FIGURE_HEIGHT - FIGURE_MARGIN_BOTTOM

    def horizontal_position(index):
        return FIGURE_MARGIN_LEFT + index * plot_width / (len(points) - 1)

    def vertical_position(value):
        return 8 + (high - value) * (plot_height - 16) / (high - low)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {FIGURE_WIDTH} {FIGURE_HEIGHT}" '
        'font-family="-apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-size="12">',
        f'<rect width="{FIGURE_WIDTH}" height="{FIGURE_HEIGHT}" fill="#ffffff"/>',
    ]
    for tick in (0, 500_000, 1_000_000, 1_500_000, 2_000_000):
        tick_position = vertical_position(tick)
        parts.append(
            f'<line x1="{FIGURE_MARGIN_LEFT}" x2="{FIGURE_WIDTH}" y1="{tick_position:.1f}" y2="{tick_position:.1f}" '
            f'stroke="#e4e4e4"/><text x="0" y="{tick_position + 4:.1f}" fill="#5f5f5f">${tick / 1e6:.1f}M</text>'
        )
    full_sample = REFERENCE_BENCHMARK["always_inc_p99_daily_loss_usd"] / DAILY_RISK_BUDGET
    parts.append(
        f'<line x1="{FIGURE_MARGIN_LEFT}" x2="{FIGURE_WIDTH}" y1="{vertical_position(full_sample):.1f}" '
        f'y2="{vertical_position(full_sample):.1f}" stroke="#111111" stroke-dasharray="4 4" stroke-width="0.8"/>'
        f'<text x="{FIGURE_MARGIN_LEFT + 8}" y="{vertical_position(full_sample) - 6:.1f}" fill="#5f5f5f">'
        "full-sample constant $1.39M (calibration only)</text>"
    )
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{horizontal_position(index):.1f},{vertical_position(value):.1f}"
        for index, (_, value) in enumerate(points)
    )
    parts.append(f'<path d="{path}" fill="none" stroke="#111111" stroke-width="1.2"/>')
    point_days = [day for day, _ in points]
    for day, label in STORM_MARKERS.items():
        storm_position = horizontal_position(point_days.index(day))
        parts.append(
            f'<line x1="{storm_position:.1f}" x2="{storm_position:.1f}" y1="8" y2="{plot_height:.1f}" stroke="#a3271f" '
            f'stroke-width="0.8"/><text x="{storm_position + 4:.1f}" y="20" fill="#a3271f">{label}</text>'
        )
    previous_year = None
    for index, day in enumerate(point_days):
        if day[:4] != previous_year:
            parts.append(
                f'<text x="{horizontal_position(index):.1f}" y="{FIGURE_HEIGHT - 6}" fill="#5f5f5f">{day[:4]}</text>'
            )
            previous_year = day[:4]
    parts.append("</svg>")
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIGURE_PATH.write_text("".join(parts) + "\n", encoding="utf-8")


def main():
    series, daily_inc_pnl, days = load_hub_series()
    comparison_rows = []
    with REFERENCE_STATS_PATH.open(encoding="utf-8") as reference_file:
        for reference in csv.DictReader(reference_file):
            hub = reference["hub"]
            measured = hub_statistics(*series[hub])
            for column, measured_value in measured.items():
                reference_value = float(reference[column])
                comparison_rows.append(
                    {
                        "group": "hub_price_stats",
                        "item": f"{hub} {column}",
                        "claude_science": reference_value,
                        "round_21": round(float(measured_value), 4),
                        "difference": round(float(measured_value) - reference_value, 4),
                    }
                )
    measured_benchmark = benchmark_statistics(daily_inc_pnl, days)
    for key, reference_value in REFERENCE_BENCHMARK.items():
        comparison_rows.append(
            {
                "group": "capital_sizing_section_4",
                "item": key,
                "claude_science": reference_value,
                "round_21": round(float(measured_benchmark[key]), 1),
                "difference": round(float(measured_benchmark[key]) - reference_value, 1),
            }
        )
    trailing_rows, trailing, trailing_days = check_trailing_estimator()
    comparison_rows += trailing_rows
    write_threshold_figure(trailing, trailing_days)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["group", "item", "claude_science", "round_21", "difference"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(comparison_rows)
    print(f"days in benchmark: {len(days)}")
    print(
        "worst days:",
        measured_benchmark["always_inc_worst_day_date"],
        measured_benchmark["always_dec_worst_day_date"],
    )
    for row in comparison_rows:
        if row["group"] == "capital_sizing_section_4":
            print(f"{row['item']:<32} {row['claude_science']:>12,.1f} {row['round_21']:>12,.1f}")
    hub_rows = [row for row in comparison_rows if row["group"] == "hub_price_stats"]
    exact = sum(
        abs(row["difference"]) <= max(0.0015, 0.0005 * abs(row["claude_science"]))
        for row in hub_rows
    )
    print(f"hub_price_stats: {exact}/{len(hub_rows)} values agree to rounding")
    for row in hub_rows:
        if abs(row["difference"]) > max(0.0015, 0.0005 * abs(row["claude_science"])):
            print("  differs:", row["item"], row["claude_science"], row["round_21"])


if __name__ == "__main__":
    main()
