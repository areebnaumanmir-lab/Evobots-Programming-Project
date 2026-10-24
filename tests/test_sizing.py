"""Point-in-time sizing reproduces capital_sizing.md §4 and §4b exactly (round 21)."""

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from evobots.calibration import read_benchmark_fixture
from evobots.sizing import (
    position_scale,
    simulate_benchmark_equity,
    trailing_p99_daily_loss,
    trailing_p99_series,
    worst_rolling_loss_fraction,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DAYS, FIXTURE_PNL = read_benchmark_fixture(
    REPOSITORY_ROOT / "docs/data/benchmark_full_size_daily_pnl.csv"
)
# The 2019 cold-start sample of capital_sizing.md §4–4b.
SAMPLE_START = FIXTURE_DAYS.index("2019-01-01")
SAMPLE_DAYS = FIXTURE_DAYS[SAMPLE_START:]
SAMPLE_PNL = FIXTURE_PNL[SAMPLE_START:]
SAMPLE_P99 = trailing_p99_series(SAMPLE_PNL)


def test_fixture_is_gapless_and_stops_before_the_hold_out():
    assert FIXTURE_DAYS[0] == "2015-03-01"
    assert FIXTURE_DAYS[-1] == "2025-09-21"
    assert len(FIXTURE_DAYS) == 3858


def test_full_sample_benchmark_numbers():
    # capital_sizing.md §4, 2019-01-01 → 2025-09-21.
    assert SAMPLE_PNL.mean() == pytest.approx(474.4, abs=0.1)
    assert np.percentile(-SAMPLE_PNL, 99) == pytest.approx(27_897, abs=1)
    assert np.percentile(SAMPLE_PNL, 99) == pytest.approx(19_351, abs=1)
    assert -SAMPLE_PNL.min() == pytest.approx(492_173, abs=1)
    assert SAMPLE_DAYS[int(SAMPLE_PNL.argmin())] == "2022-12-23"
    assert SAMPLE_PNL.max() == pytest.approx(176_554, abs=1)
    assert SAMPLE_DAYS[int(SAMPLE_PNL.argmax())] == "2021-02-18"


def test_warm_up_ends_on_2019_04_06():
    first_estimate = next(index for index, value in enumerate(SAMPLE_P99) if value is not None)
    assert SAMPLE_DAYS[first_estimate] == "2019-04-06"


def test_trailing_p99_equals_claude_science_on_every_day():
    with (REPOSITORY_ROOT / "docs/data/trailing_p99_daily_loss.csv").open(
        encoding="utf-8"
    ) as table:
        reference_rows = list(csv.DictReader(table))
    assert [row["date"] for row in reference_rows] == SAMPLE_DAYS
    for row, value in zip(reference_rows, SAMPLE_P99):
        if row["p99_daily_loss_trailing"] == "":
            assert value is None
        else:
            assert round(value) == pytest.approx(float(row["p99_daily_loss_trailing"]), abs=1)


@pytest.mark.parametrize(
    ("day", "p99_usd"),
    [
        ("2021-02-13", 12_261),
        ("2021-02-18", 12_261),
        ("2021-02-25", 18_777),
        ("2021-03-20", 24_859),
        ("2022-02-26", 16_787),
        ("2022-12-23", 31_519),
        ("2022-12-31", 39_723),
        ("2023-12-31", 19_885),
    ],
)
def test_section_4b_table(day, p99_usd):
    assert SAMPLE_P99[SAMPLE_DAYS.index(day)] == pytest.approx(p99_usd, abs=1)


def test_breach_rate_by_year_2015_2025():
    p99_series = trailing_p99_series(FIXTURE_PNL)
    counts = defaultdict(lambda: [0, 0])
    for day, pnl, p99 in zip(FIXTURE_DAYS, FIXTURE_PNL, p99_series):
        if p99 is not None:
            counts[day[:4]][0] += abs(pnl) > p99
            counts[day[:4]][1] += 1
    path = REPOSITORY_ROOT / "docs/data/trailing_breach_rate_by_year_2015_2025.csv"
    with path.open(encoding="utf-8") as table:
        for row in csv.DictReader(table):
            breaches, days = counts[row["date"]]
            assert days == int(row["days"])
            assert 100 * breaches / days == pytest.approx(float(row["breach_rate_pct"]), abs=0.005)


def test_look_ahead_changing_d_minus_5_onwards_changes_nothing():
    operating_day = SAMPLE_DAYS.index("2022-12-23")
    changed = SAMPLE_PNL.copy()
    changed[operating_day - 5 :] = 1e9
    assert trailing_p99_daily_loss(changed, operating_day) == SAMPLE_P99[operating_day]


def test_d_minus_6_is_visible():
    operating_day = SAMPLE_DAYS.index("2022-12-23")
    changed = SAMPLE_PNL.copy()
    changed[operating_day - 6] = -1e9
    assert trailing_p99_daily_loss(changed, operating_day) != SAMPLE_P99[operating_day]


def test_position_scale_rules():
    assert position_scale(1_500_000, 27_897, 0.02) == 1.0
    assert position_scale(250_000, 27_897, 0.02) == pytest.approx(0.1792, abs=1e-4)
    assert position_scale(1_500_000, None, 0.02) == 0.0
    assert position_scale(0, 27_897, 0.02) == 0.0


@pytest.mark.parametrize(
    ("capital_usd", "worst_fraction"),
    [
        (1_050_000, 0.3452),
        (1_400_000, 0.2641),
        (1_500_000, 0.2457),
        (2_000_000, 0.1842),
        (3_000_000, 0.1234),
    ],
)
def test_worst_20_day_loss_point_in_time(capital_usd, worst_fraction):
    # capital_sizing.md §5–6b; docs/data/headroom_trailing.csv. Worse of INC and DEC.
    worst = 0.0
    for direction in (1, -1):
        equity, pnl = simulate_benchmark_equity(
            direction * SAMPLE_PNL, capital_usd, 0.02, SAMPLE_P99
        )
        worst = max(worst, worst_rolling_loss_fraction(pnl, equity)[0])
    assert worst == pytest.approx(worst_fraction, abs=5e-5)


def test_calibration_constant_lives_only_in_the_cli():
    source_root = REPOSITORY_ROOT / "src/evobots"
    users = [
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*.py")
        if "CALIBRATION_ONLY_" in path.read_text(encoding="utf-8")
    ]
    assert users == ["cli.py"]
