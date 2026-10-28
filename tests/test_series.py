"""Tests for the daily-series readers (`evobots.data.sources.series`).

Small hand-made files check the parsing rules and the hold-out cut. When the real
downloads exist in data/raw/series/ (they are git-ignored), the facts recorded in
`CLAUDE.md` §7.5–7.7 and `docs/rounds/round27_verification.md` are checked against them.
"""

import datetime
import math
from pathlib import Path

import pytest

from evobots.data.sources import series

SERIES_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "raw" / "series"


def newest_download(source, pattern):
    """The newest downloaded file of one source, or skip the test when there is none."""
    paths = sorted((SERIES_DIRECTORY / source).glob(pattern))
    if not paths:
        pytest.skip(f"no {source} download in data/raw/series (run tools/fetch_series.py)")
    return paths[-1]


def test_fred_csv_blank_days_absent_and_holdout_cut(tmp_path):
    path = tmp_path / "DTB3.csv"
    path.write_text(
        "observation_date,DTB3\n2025-09-18,3.90\n2025-09-19,\n2025-09-22,3.85\n",
        encoding="utf-8",
    )
    result = series.read_fred_dtb3(path)
    assert result.days == (datetime.date(2025, 9, 18),)
    assert result.values == (pytest.approx(0.039),)
    with_permission = series.read_fred_dtb3(path, holdout_permission=object())
    assert with_permission.days[-1] == datetime.date(2025, 9, 22)


def test_fred_rejects_other_series(tmp_path):
    path = tmp_path / "other.csv"
    path.write_text("observation_date,DGS10\n2020-01-02,1.88\n", encoding="utf-8")
    with pytest.raises(series.SeriesFormatError):
        series.read_fred_dtb3(path)


def test_daily_risk_free_log_return_worked_example():
    # docs/maths.md §3.1: d = 5 % gives P = 1 − 0.05 × 91/360 = 0.987361.
    price = 1 - 0.05 * 91 / 360
    assert price == pytest.approx(0.987361, abs=1e-6)
    assert series.daily_risk_free_log_return(0.05) == pytest.approx(-math.log(price) / 91)
    assert series.daily_risk_free_log_return(0.05) * 365 == pytest.approx(0.051018, abs=1e-6)
    assert series.daily_risk_free_log_return(0.0) == 0.0


def test_epu_csv_and_header_check(tmp_path):
    path = tmp_path / "epu.csv"
    path.write_text(
        "day,month,year,daily_policy_index\n9,3,2020,500.5\n10,3,2020,525.0\n",
        encoding="utf-8",
    )
    result = series.read_epu(path)
    assert result.value_by_day() == {
        datetime.date(2020, 3, 9): 500.5,
        datetime.date(2020, 3, 10): 525.0,
    }
    path.write_text("date,epu\n2020-03-09,500\n", encoding="utf-8")
    with pytest.raises(series.SeriesFormatError):
        series.read_epu(path)


def test_eia_rows_dates_and_source_key():
    rows = [
        ["Back to Contents", "Data 1: Henry Hub"],
        ["Sourcekey", "RNGWHHD"],
        ["Date", "Henry Hub Natural Gas Spot Price (Dollars per Million Btu)"],
        [35437.0, 3.82],
        [35438.0, ""],
    ]
    observations = series.eia_rows_to_series(rows, 0, "henry_hub", "$/MMBtu", "RNGWHHD")
    assert observations == [(datetime.date(1997, 1, 7), 3.82), (datetime.date(1997, 1, 8), None)]
    with pytest.raises(series.SeriesFormatError):
        series.eia_rows_to_series(rows, 0, "wti", "$/barrel", "RWTC")


def test_gpr_rows_missing_column():
    with pytest.raises(series.SeriesFormatError):
        series.gpr_rows_to_observations([["DAY", "GPRD"], ["20200101", 90.0]])


def test_duplicate_dates_rejected():
    day = datetime.date(2020, 1, 2)
    with pytest.raises(series.SeriesFormatError):
        series.series_from_observations("x", "percent", "test", [(day, 1.0), (day, 2.0)])


def test_real_dtb3_trading_days():
    # Round 27: 5,123 trading days in 2005-04-01 → 2025-09-21.
    result = series.read_fred_dtb3(newest_download("fred_dtb3", "*.csv"))
    evolution_days = [day for day in result.days if day >= datetime.date(2005, 4, 1)]
    assert len(evolution_days) == 5123
    assert result.days[-1] <= datetime.date(2025, 9, 21)


def test_real_henry_hub_coverage():
    # CLAUDE.md §7.5: daily from January 1997.
    result = series.read_eia_daily_spot(newest_download("eia_henry_hub", "*.xls"), "RNGWHHD")
    assert result.days[0] == datetime.date(1997, 1, 7)
    assert result.days[-1] <= datetime.date(2025, 9, 21)
    assert all(value > 0 for value in result.values)


def test_real_epu_covid_period():
    # CLAUDE.md §7.6 (corrected round 28): mean 513 over 2020-03-09 → 04-30, above every
    # 2015–19 day except 2016-06-25 (586.6, the day after the Brexit vote).
    result = series.read_epu(newest_download("epu", "*.csv")).value_by_day()
    covid = [
        value
        for day, value in result.items()
        if datetime.date(2020, 3, 9) <= day <= datetime.date(2020, 4, 30)
    ]
    baseline = {
        day: value
        for day, value in result.items()
        if datetime.date(2015, 1, 1) <= day <= datetime.date(2019, 12, 31)
    }
    covid_mean = sum(covid) / len(covid)
    assert covid_mean == pytest.approx(512.6, abs=0.1)
    above = [day for day, value in baseline.items() if value > covid_mean]
    assert above == [datetime.date(2016, 6, 25)]


def test_real_gpr_russia_ukraine_period():
    # CLAUDE.md §7.7: mean GPR 318 over 2022-02-24 → 03-31.
    result = series.read_gpr(newest_download("gpr", "*.xls"))["gpr_index"].value_by_day()
    values = [
        value
        for day, value in result.items()
        if datetime.date(2022, 2, 24) <= day <= datetime.date(2022, 3, 31)
    ]
    assert round(sum(values) / len(values)) == 318
