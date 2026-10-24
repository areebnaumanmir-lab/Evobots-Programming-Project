"""The calibration tables of capital_sizing.md §5–6 are reproduced row by row (round 21)."""

import csv
from pathlib import Path

import numpy as np
import pytest

from evobots.calibration import (
    capital_floor_for_fixed_costs,
    fixed_cost_usd_per_cleared_mwh,
    read_benchmark_fixture,
)
from evobots.config.capital import CapitalSettings
from evobots.sizing import (
    position_scale,
    simulate_benchmark_equity,
    trailing_p99_series,
    worst_rolling_loss_fraction,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DAYS, PNL = read_benchmark_fixture(REPOSITORY_ROOT / "docs/data/benchmark_full_size_daily_pnl.csv")
SAMPLE_PNL = PNL[DAYS.index("2019-01-01") :]
SAMPLE_P99 = trailing_p99_series(SAMPLE_PNL)
FULL_SAMPLE_P99_USD = 27_897
FIXED_COST_USD_PER_YEAR = 50_000
FULL_SIZE_MWH_PER_DAY = CapitalSettings().full_size_mwh_per_day()
ABSOLUTE_FLOOR_USD = 1_000_000


def read_table(name):
    with (REPOSITORY_ROOT / "docs/data" / name).open(encoding="utf-8") as table:
        return list(csv.DictReader(table))


def worst_20_day_full_size_loss_usd():
    return max(
        -np.convolve(direction * SAMPLE_PNL, np.ones(20), mode="valid").min()
        for direction in (1, -1)
    )


@pytest.mark.parametrize("row", read_table("capital_sweep.csv"), ids=lambda row: row["capital"])
def test_capital_sweep(row):
    capital = float(row["capital"])
    scale = position_scale(capital, FULL_SAMPLE_P99_USD, 0.02)
    assert scale == pytest.approx(float(row["position_scale"]), abs=5e-4)
    for share in ("1.0", "0.721", "0.25"):
        cost = fixed_cost_usd_per_cleared_mwh(
            FIXED_COST_USD_PER_YEAR, scale, FULL_SIZE_MWH_PER_DAY, float(share)
        )
        assert cost == pytest.approx(float(row[f"fixed_cost_per_MWh_share_{share}"]), abs=5e-4)
    # Constant scale from starting capital; worst 20 days at full size is always-INC's.
    worst_percent = 100 * scale * worst_20_day_full_size_loss_usd() / capital
    assert worst_percent == pytest.approx(float(row["worst_20d_loss_pct_fullsample"]), abs=5e-4)


@pytest.mark.parametrize(
    "row", read_table("fixed_cost_capital_floor.csv"), ids=lambda row: row["case"]
)
def test_fixed_cost_capital_floor(row):
    # The printed share is rounded (0.721); the MWh column carries the measured share.
    share = int(row["cleared_MWh_per_year_full_size"]) / (FULL_SIZE_MWH_PER_DAY * 365)
    assert share == pytest.approx(float(row["cleared_share"]), abs=5e-4)
    cost = fixed_cost_usd_per_cleared_mwh(
        FIXED_COST_USD_PER_YEAR, 1.0, FULL_SIZE_MWH_PER_DAY, share
    )
    assert cost == pytest.approx(float(row["fixed_cost_per_MWh_at_full_size"]), abs=5e-4)
    p99_values = [value for value in SAMPLE_P99 if value is not None]
    for column, p99 in (
        ("C_min_full_sample_p99", FULL_SAMPLE_P99_USD),
        ("C_min_trailing_median_p99", float(np.median(p99_values))),
        ("C_min_trailing_max_p99", max(p99_values)),
    ):
        floor = capital_floor_for_fixed_costs(
            FIXED_COST_USD_PER_YEAR, p99, 0.02, FULL_SIZE_MWH_PER_DAY, share
        )
        assert floor == pytest.approx(float(row[column]), rel=1e-5)


@pytest.mark.parametrize("row", read_table("headroom_trailing.csv"), ids=lambda row: row["capital"])
def test_headroom_trailing(row):
    capital = float(row["capital"])
    headroom = 1 - ABSOLUTE_FLOOR_USD / capital
    assert headroom == pytest.approx(float(row["headroom_frac"]), abs=5e-5)
    constant_p99 = [FULL_SAMPLE_P99_USD] * len(SAMPLE_PNL)
    worst_by_sizing = {}
    for name, p99_series in (("trailing", SAMPLE_P99), ("fullsample", constant_p99)):
        worst_by_sizing[name] = max(
            worst_rolling_loss_fraction(
                *reversed(
                    simulate_benchmark_equity(direction * SAMPLE_PNL, capital, 0.02, p99_series)
                )
            )[0]
            for direction in (1, -1)
        )
    assert worst_by_sizing["trailing"] == pytest.approx(
        float(row["worst20_frac_trailing"]), abs=5e-5
    )
    assert worst_by_sizing["fullsample"] == pytest.approx(
        float(row["worst20_frac_fullsample"]), abs=5e-5
    )
    assert (headroom > worst_by_sizing["trailing"]) == (row["survives_trailing"] == "True")
    assert (headroom > worst_by_sizing["fullsample"]) == (row["survives_fullsample"] == "True")
