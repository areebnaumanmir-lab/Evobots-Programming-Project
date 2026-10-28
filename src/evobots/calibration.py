"""Calibration helpers: the full-size benchmark P&L behind the capital defaults.

Calibration only: these functions use whole-sample data and are never called by simulation or
evolution code (CLAUDE.md §18). They rebuild the numbers of docs/capital_sizing.md from the hub
table written by tools/build_miso_hub_prices.py.
"""

import csv
import gzip
from collections import defaultdict
from pathlib import Path

import numpy as np

from evobots.config.capital import CapitalSettings
from evobots.data.periods import HOLDOUT_FIRST_DAY, HOLDOUT_LAST_DAY

DEFAULT_HUB_PRICES_PATH = Path("data/store/hub_prices.csv.gz")


def full_size_benchmark_daily_pnl(
    first_day, last_day, settings=None, hub_prices_path=DEFAULT_HUB_PRICES_PATH
):
    """Daily P&L of always-INC at every hub's cap in every hour, USD (always-DEC is −1×).

    Args:
        first_day: first ISO date, inclusive.
        last_day: last ISO date, inclusive. The range may not touch the hold-out.
        settings: CapitalSettings for the per-hub caps; default CapitalSettings().
        hub_prices_path: the hub table.

    Returns:
        (days, pnl): ISO dates and a numpy array, USD. A hub counts on the hours it has both
        prices; hubs outside the settings (e.g. CINERGY, FE) are ignored.

    Maths: docs/maths.md §1.2 (P&L of INC = q × (DA − RT)).
    """
    if not (last_day < HOLDOUT_FIRST_DAY.isoformat() or first_day > HOLDOUT_LAST_DAY.isoformat()):
        raise ValueError("calibration ranges may not touch the sealed hold-out (CLAUDE.md §7.2)")
    caps = (settings or CapitalSettings()).hub_caps_mw()
    pnl_by_day = defaultdict(float)
    with gzip.open(hub_prices_path, "rt", encoding="utf-8") as hub_file:
        for row in csv.DictReader(hub_file):
            if not first_day <= row["date"] <= last_day or row["hub"] not in caps:
                continue
            if row["da_lmp"] and row["rt_lmp"]:
                spread = float(row["da_lmp"]) - float(row["rt_lmp"])
                pnl_by_day[row["date"]] += caps[row["hub"]] * spread
    days = sorted(pnl_by_day)
    return days, np.array([pnl_by_day[day] for day in days])


def read_benchmark_fixture(path):
    """Read docs/data/benchmark_full_size_daily_pnl.csv → (days, always-INC P&L array)."""
    with Path(path).open(encoding="utf-8") as fixture_file:
        rows = list(csv.DictReader(fixture_file))
    return [row["date"] for row in rows], np.array([float(row["always_inc_usd"]) for row in rows])


DAYS_PER_YEAR = 365


def fixed_cost_usd_per_cleared_mwh(
    fixed_cost_usd_per_year, position_scale_fraction, full_size_mwh_per_day, cleared_share_fraction
):
    """Fixed yearly cost spread over the cleared MWh of a year, USD/MWh.

    cleared MWh per year = scale × full-size MWh/day × 365 × cleared share
    (capital_sizing.md §5; the round-15 correction).

    Maths: docs/maths.md §1.7.

    Example:
        >>> round(fixed_cost_usd_per_cleared_mwh(50_000, 1.0, 936, 1.0), 3)
        0.146
    """
    cleared_mwh_per_year = (
        position_scale_fraction * full_size_mwh_per_day * DAYS_PER_YEAR * cleared_share_fraction
    )
    return fixed_cost_usd_per_year / cleared_mwh_per_year


def capital_floor_for_fixed_costs(
    fixed_cost_usd_per_year,
    p99_daily_loss_usd,
    daily_risk_budget_fraction,
    full_size_mwh_per_day,
    cleared_share_fraction,
    target_usd_per_mwh=1.0,
):
    """Smallest capital at which fixed costs fall to target_usd_per_mwh, USD (inf if never).

    C_min = F × p99 / (budget × target × full-size MWh/day × 365 × share); infinite when even
    full size can't reach the target.

    Maths: docs/maths.md §1.7.
    """
    full_size_cost = fixed_cost_usd_per_cleared_mwh(
        fixed_cost_usd_per_year, 1.0, full_size_mwh_per_day, cleared_share_fraction
    )
    if full_size_cost > target_usd_per_mwh:
        return float("inf")
    return (
        fixed_cost_usd_per_year
        * p99_daily_loss_usd
        / (
            daily_risk_budget_fraction
            * target_usd_per_mwh
            * full_size_mwh_per_day
            * DAYS_PER_YEAR
            * cleared_share_fraction
        )
    )
