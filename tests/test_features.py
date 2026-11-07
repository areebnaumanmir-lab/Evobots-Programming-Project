"""M2: the feature catalogue, calendar, store and the look-ahead test (design spec §8, §16 M2).

The look-ahead test corrupts every observation that was not yet public at a decision time
(by the publication rules of `evobots.data.visible`) and checks that no feature at that
decision changes. It runs on synthetic data, so it needs no downloads.
"""

import dataclasses
import datetime
from pathlib import Path

import numpy as np
import pytest

from evobots.data.sources.series import DailySeries
from evobots.data.visible import add_business_days
from evobots.features.calendar import is_nerc_holiday, nerc_holidays
from evobots.features.catalogue import FEATURE_BY_NAME, FEATURE_NAMES, FEATURES
from evobots.features.inputs import FeatureInputs, cloud_fraction, synthetic_feature_inputs
from evobots.features.store import build_feature_store
from evobots.simulate.market import synthetic_hub_market
from evobots.units import USD_PER_MWH

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_catalogue_has_the_25_features_of_the_spec():
    assert len(FEATURES) == 25
    assert FEATURE_NAMES[:7] == (
        "spread_mean_7d",
        "spread_mean_28d",
        "spread_std_28d",
        "spread_pos_frac_28d",
        "spread_spike_frac_28d",
        "da_last",
        "congestion_share_28d",
    )
    assert len({feature.display_name for feature in FEATURES}) == 25
    assert FEATURE_BY_NAME["da_last"].unit == USD_PER_MWH
    assert {feature.name for feature in FEATURES if feature.is_hindsight_check} == {
        "gas_price",
        "gas_chg_5d",
        "gas_vol_20d",
        "epu",
    }


def test_nerc_holidays_and_the_sunday_rule():
    assert nerc_holidays(2024) == (
        datetime.date(2024, 1, 1),
        datetime.date(2024, 5, 27),
        datetime.date(2024, 7, 4),
        datetime.date(2024, 9, 2),
        datetime.date(2024, 11, 28),
        datetime.date(2024, 12, 25),
    )
    # 2021-07-04 was a Sunday: Sunday and Monday flagged. 2021-12-25 was a Saturday: no move.
    assert is_nerc_holiday(datetime.date(2021, 7, 4))
    assert is_nerc_holiday(datetime.date(2021, 7, 5))
    assert is_nerc_holiday(datetime.date(2021, 12, 25))
    assert not is_nerc_holiday(datetime.date(2021, 12, 27))
    assert not is_nerc_holiday(datetime.date(2021, 12, 24))


def test_cloud_codes_become_fractions():
    assert cloud_fraction("CL CL") == 0.0
    assert cloud_fraction("OV B2") == pytest.approx((1.0 + 0.875) / 2)
    assert cloud_fraction("MM MM") is None


def corrupted_after_decision(market, inputs, operating_day, generator):
    """Market and inputs with every observation not public at D's decision replaced."""
    decision_day = operating_day - datetime.timedelta(days=1)
    days = np.array(market.days)
    day_ahead = market.day_ahead.copy()
    real_time = market.real_time.copy()
    congestion = market.day_ahead_congestion.copy()
    is_day_ahead_future = days >= operating_day  # DA of t is public 16:30 on t−1
    is_real_time_future = np.array(
        [day + datetime.timedelta(days=5) > decision_day for day in days]
    )
    noise = lambda shape: 1000 * generator.standard_normal(shape)  # noqa: E731
    day_ahead[is_day_ahead_future] = noise(day_ahead[is_day_ahead_future].shape)
    congestion[is_day_ahead_future] = noise(congestion[is_day_ahead_future].shape)
    real_time[is_real_time_future] = noise(real_time[is_real_time_future].shape)
    forecasts = {
        key: (tuple(generator.normal(size=4)) if key[0] > decision_day else value)
        for key, value in inputs.forecasts.items()
    }
    capacity = {
        key: ((9e9, 9e9) if (key[0], key[1]) > (decision_day.year, decision_day.month) else value)
        for key, value in inputs.capacity.items()
    }

    def corrupt_series(series, is_public):
        values = tuple(
            value if is_public(day) else 1e6 + index
            for index, (day, value) in enumerate(zip(series.days, series.values))
        )
        return dataclasses.replace(series, values=values)

    gas = corrupt_series(inputs.gas, lambda day: add_business_days(day, 1) <= decision_day)
    epu = corrupt_series(inputs.epu, lambda day: day + datetime.timedelta(days=2) <= decision_day)
    corrupted_market = dataclasses.replace(
        market, day_ahead=day_ahead, real_time=real_time, day_ahead_congestion=congestion
    )
    return corrupted_market, FeatureInputs(forecasts, capacity, gas, epu, "corrupted")


def test_no_feature_sees_data_published_after_the_decision():
    market = synthetic_hub_market(days=700, seed=11)
    inputs = synthetic_feature_inputs(market.days, market.hubs, seed=3)
    clean = build_feature_store(market, inputs)
    generator = np.random.Generator(np.random.PCG64(5))
    for day_index in (40, 200, 452, 699):
        operating_day = market.days[day_index]
        corrupted = build_feature_store(
            *corrupted_after_decision(market, inputs, operating_day, generator)
        )
        for name in FEATURE_NAMES:
            before = clean.window(name, day_index, day_index + 1)
            after = corrupted.window(name, day_index, day_index + 1)
            assert np.array_equal(before, after, equal_nan=True), (name, operating_day)


def test_the_check_would_catch_a_leak():
    """Control: corrupting DA of day D itself must change something (else the test is blind)."""
    market = synthetic_hub_market(days=300, seed=2)
    inputs = synthetic_feature_inputs(market.days, market.hubs, seed=3)
    leaked_day_ahead = market.day_ahead.copy()
    leaked_day_ahead[150] += 500.0  # DA of D−1 for D = index 151 is visible: must show up
    leaked = dataclasses.replace(market, day_ahead=leaked_day_ahead)
    clean = build_feature_store(market, inputs).window("da_last", 151, 152)
    changed = build_feature_store(leaked, inputs).window("da_last", 151, 152)
    assert not np.array_equal(clean, changed)


def test_hub_is_its_own_area_and_area_inputs_reach_it():
    market = synthetic_hub_market(days=120, seed=1)
    inputs = synthetic_feature_inputs(market.days, market.hubs, seed=3)
    store = build_feature_store(market, inputs)
    codes = store.full("loc_region")[5, 0, :]
    assert codes.tolist() == list(range(8))
    day = market.days[10]
    expected_high = inputs.forecasts[(day - datetime.timedelta(days=1), "MINN.HUB", day)][0]
    assert store.full("temp_max_fcst")[10, 3, market.hubs.index("MINN.HUB")] == expected_high


def test_gas_features_follow_the_trading_day_lag():
    days = tuple(
        datetime.date(2024, 1, 1) + datetime.timedelta(days=offset) for offset in range(40)
    )
    trading_days = tuple(day for day in days if day.weekday() < 5)
    gas = DailySeries(
        "henry_hub_usd_per_mmbtu",
        "$/MMBtu",
        "test",
        trading_days,
        tuple(float(position) for position in range(len(trading_days))),
    )
    market = synthetic_hub_market(days=40, seed=1, last_day=days[-1])
    inputs = FeatureInputs({}, {}, gas, None, "test")
    store = build_feature_store(market, inputs)
    # Operating day Tue 2024-01-16: decision Mon 01-15; Fri 01-12 (index 9) is public Mon.
    index = days.index(datetime.date(2024, 1, 16))
    assert store.full("gas_price")[index, 0, 0] == 9.0
    assert store.full("gas_chg_5d")[index, 0, 0] == 5.0


def test_hindsight_copy_blanks_only_the_named_features():
    market = synthetic_hub_market(days=200, seed=1)
    store = build_feature_store(market, synthetic_feature_inputs(market.days, market.hubs, 3))
    blank = store.with_missing(["epu"])
    assert np.isnan(blank.full("epu")).all()
    assert np.array_equal(blank.full("gas_price"), store.full("gas_price"), equal_nan=True)


@pytest.mark.skipif(
    not (REPOSITORY_ROOT / "data/store/hub_prices.csv.gz").exists(),
    reason="needs the MISO hub table built on this machine",
)
def test_real_store_matches_recorded_facts(monkeypatch):
    from evobots.features.inputs import load_feature_inputs
    from evobots.simulate.market import read_miso_hub_market

    monkeypatch.chdir(REPOSITORY_ROOT)
    market = read_miso_hub_market()
    store = build_feature_store(market, load_feature_inputs())
    # EIA-860M MISO wind: about 1.3 GW in 2005-04 (design spec §7.8); the eight areas sum it.
    first = store.days.index(datetime.date(2005, 4, 2))
    assert 1_200 < store.full("wind_cap_region")[first, 0, :].sum() < 1_400
    # Henry Hub peaked at $30.72 on 2026-01-23 (hold-out, never read): the evolution-period
    # maximum is lower; Winter Storm Uri's 2021-02 prices are visible within days.
    assert np.nanmax(store.full("gas_price")) < 30.72
    # Forecasts cover over 99 % of hub-days (round 31).
    assert np.isnan(store.full("temp_max_fcst")).mean() < 0.01
