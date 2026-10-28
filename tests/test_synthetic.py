"""Tests for the synthetic market (`evobots.data.synthetic`): seeding, models, planted rule."""

import numpy as np
import pytest

from evobots.data import synthetic


def test_same_seed_same_arrays_different_seed_different():
    first = synthetic.synthetic_market(days=50, hubs=3, model="garch", seed=7)
    again = synthetic.synthetic_market(days=50, hubs=3, model="garch", seed=7)
    other = synthetic.synthetic_market(days=50, hubs=3, model="garch", seed=8)
    assert np.array_equal(first.real_time, again.real_time)
    assert not np.array_equal(first.real_time, other.real_time)


def test_unknown_model_is_an_error():
    with pytest.raises(ValueError):
        synthetic.synthetic_market(days=5, hubs=1, model="neural")


def test_noise_has_no_planted_signal():
    market = synthetic.synthetic_market(days=2000, hubs=2, model="noise", seed=3)
    assert not market.is_planted.any()
    spread = market.day_ahead - market.real_time
    # Mean spread ≈ 0: standard error of the mean of 96,000 t(3) draws at scale 5 is ≈ 0.03.
    assert abs(spread.mean()) < 0.15


def test_planted_rule_raises_real_time_only_where_it_holds():
    plain = synthetic.synthetic_market(days=3000, hubs=2, model="noise", seed=11)
    planted = synthetic.synthetic_market(
        days=3000, hubs=2, model="noise", seed=11, planted_premium_usd_per_mwh=10.0
    )
    difference = planted.real_time - plain.real_time
    assert np.allclose(difference[planted.is_planted], 10.0)
    assert np.allclose(difference[~planted.is_planted], 0.0)
    # The rule holds only on hot days' afternoons, a small but non-empty share.
    assert 0.001 < planted.is_planted.mean() < 0.1
    hours_with_rule = np.where(planted.is_planted.any(axis=(0, 2)))[0] + 1
    assert hours_with_rule.min() >= 14 and hours_with_rule.max() <= 19


def test_garch_volatility_clusters():
    scale = synthetic.synthetic_market(
        days=5000, hubs=1, model="garch", seed=5
    ).daily_scale_usd_per_mwh
    variance = scale**2
    lag_one_correlation = np.corrcoef(variance[:-1], variance[1:])[0, 1]
    assert lag_one_correlation > 0.8


def test_regime_has_two_scales_and_mostly_calm():
    scale = synthetic.synthetic_market(
        days=5000, hubs=1, model="regime", seed=5
    ).daily_scale_usd_per_mwh
    levels = sorted(set(scale.round(6)))
    assert levels == [5.0, 20.0]
    # Stationary stress share = p(calm→stress) / (p(calm→stress) + p(stress→calm)) = 1/6.
    assert abs((scale == 20.0).mean() - 1 / 6) < 0.05
