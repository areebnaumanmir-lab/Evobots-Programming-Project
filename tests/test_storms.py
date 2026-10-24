"""Storm sensitivity reproduces capital_sizing.md §7b exactly (round 21)."""

import math
from pathlib import Path

import pytest

from evobots.calibration import read_benchmark_fixture
from evobots.sizing import simulate_benchmark_equity
from evobots.storms import compounded_fitness, fitness_with_and_without_storms

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DAYS, PNL = read_benchmark_fixture(REPOSITORY_ROOT / "docs/data/benchmark_full_size_daily_pnl.csv")
START = DAYS.index("2019-01-01")
SAMPLE_DAYS, SAMPLE_PNL = DAYS[START:], PNL[START:]


def benchmark_result(direction):
    _, daily_pnl = simulate_benchmark_equity(direction * SAMPLE_PNL, 1_500_000, 0.02)
    return fitness_with_and_without_storms(
        daily_pnl, SAMPLE_DAYS, 1_500_000, ruin_floor_usd=1_000_000
    )


def test_always_inc_at_1_5m():
    result = benchmark_result(1)
    assert result["fitness_all_days"] == pytest.approx(0.540, abs=5e-4)
    assert result["fitness_without_storms"] == pytest.approx(0.684, abs=5e-4)
    assert result["contribution_by_storm"]["Uri"] == pytest.approx(0.069, abs=5e-4)
    assert result["contribution_by_storm"]["Elliott"] == pytest.approx(-0.212, abs=5e-4)
    assert result["ruined_on"] is None


def test_always_dec_at_1_5m_is_ruined_on_2022_01_21():
    result = benchmark_result(-1)
    assert result["fitness_all_days"] == pytest.approx(-0.411, abs=5e-4)
    assert result["ruined_on"] == "2022-01-21"


def test_hand_example_storm_day_losing_a_tenth():
    fitness, _ = compounded_fitness([-0.1, 0.0], ["2021-02-15", "2021-03-01"], 100.0, set())
    assert fitness == pytest.approx(math.log(0.9))
    flat, _ = compounded_fitness([-0.1, 0.0], ["2021-02-15", "2021-03-01"], 100.0, {"2021-02-15"})
    assert flat == 0.0


def test_input_series_is_not_modified():
    daily_pnl = SAMPLE_PNL[:400].copy() * 0.01
    before = daily_pnl.copy()
    fitness_with_and_without_storms(daily_pnl, SAMPLE_DAYS[:400], 1_500_000)
    assert (daily_pnl == before).all()


def test_custom_windows():
    result = fitness_with_and_without_storms(
        [1000.0, -5000.0, 2000.0],
        ["2020-01-01", "2020-01-02", "2020-01-03"],
        100_000.0,
        storm_windows={"test": ("2020-01-02", "2020-01-02")},
    )
    assert set(result["contribution_by_storm"]) == {"test"}
    assert result["contribution_by_storm"]["test"] < 0
