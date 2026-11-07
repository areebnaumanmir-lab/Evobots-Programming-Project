"""M3: fees, settlement, the fast kernel against the reference, and the calibration numbers.

Done-when (design spec §16, M3): the baselines reproduce `capital_sizing.md` §4 and §7b. The
offline tests prove the simulator equals `evobots.sizing` (which the calibration tests pin to
those numbers); the real-data test reproduces them directly when the hub table is built.
"""

import datetime
import math
from pathlib import Path

import numpy as np
import pytest

from evobots.config.capital import CapitalSettings
from evobots.simulate.fees import CostTable, hourly_fees_usd
from evobots.simulate.market import synthetic_hub_market
from evobots.simulate.settlement import (
    AccountRules,
    Decisions,
    constant_decisions,
    numba,
    round_down_to_step,
    settle,
    settle_reference,
)
from evobots.sizing import simulate_benchmark_equity, trailing_p99_series
from evobots.storms import fitness_with_and_without_storms

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NO_COSTS = AccountRules(cost_multiple=0.0, is_rounding=False)


def hub_caps(market):
    caps = CapitalSettings().hub_caps_mw()
    return np.array([caps[hub] for hub in market.hubs])


def random_decisions(market, seed):
    generator = np.random.Generator(np.random.PCG64(seed))
    shape = market.day_ahead.shape
    side = generator.choice(np.array([-1, 0, 1], dtype=np.int8), size=shape, p=[0.3, 0.4, 0.3])
    limit = market.day_ahead + generator.normal(0, 8, size=shape)
    power = generator.uniform(0, 5, size=shape)
    return Decisions(0, side, limit, power)


def test_rounding_to_the_bid_step():
    assert round_down_to_step(np.array([0.3, 0.29, 4.99, 0.05])).tolist() == pytest.approx(
        [0.3, 0.2, 4.9, 0.0]
    )


def test_fee_netting_matches_the_rules():
    rates = CostTable.estimates().rates_for_day(datetime.date(2024, 1, 1))
    # DEC 3 MW and INC 3 MW at two hubs: admin on 6, DA RSG on 3, DDC on max(−0, 0) = 0.
    assert hourly_fees_usd([3.0, -3.0], rates) == pytest.approx(0.0902 * 6 + 0.05 * 3)
    # Before RSG on virtuals (2008-11) only the admin fee applies.
    early = CostTable.estimates().rates_for_day(datetime.date(2006, 1, 1))
    assert hourly_fees_usd([-4.0], early) == pytest.approx(0.0902 * 4)


@pytest.mark.skipif(numba is None, reason="needs Numba")
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_fast_kernel_agrees_with_reference(seed):
    market = synthetic_hub_market(days=900, seed=seed)
    decisions = random_decisions(market, seed)
    rules = AccountRules(
        starting_capital_usd=400_000,
        max_mwh_per_day=300.0,
        pause_loss_fraction=0.01,
        pause_days=3,
    )
    fast = settle(decisions, market, 450, 900, rules)
    reference = settle_reference(decisions, market, 450, 900, rules)
    np.testing.assert_allclose(fast.equity_usd, reference.equity_usd, rtol=1e-9)
    np.testing.assert_allclose(fast.fees_usd, reference.fees_usd, rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(fast.position_scale, reference.position_scale, rtol=1e-9)
    assert fast.death_index == reference.death_index
    assert fast.bid_location_hours == reference.bid_location_hours


def test_simulator_equals_the_calibrated_sizing_module():
    """Always-INC at the caps, no costs, unrounded: equity = evobots.sizing's benchmark path."""
    market = synthetic_hub_market(days=800, seed=7)
    caps = hub_caps(market)
    decisions = constant_decisions(market, -1, caps)
    result = settle(decisions, market, 0, 800, NO_COSTS, history_start=0)
    full_size = np.nansum((market.day_ahead - market.real_time) * caps, axis=(1, 2))
    np.testing.assert_allclose(result.full_size_daily_pnl_usd, full_size, rtol=1e-12)
    _, expected_pnl = simulate_benchmark_equity(
        full_size, 1_500_000, 0.02, trailing_p99_series(full_size)
    )
    np.testing.assert_allclose(result.daily_pnl_usd, expected_pnl, rtol=1e-9, atol=1e-6)


def test_credit_limit_cuts_bids_instead_of_refusing_them():
    market = synthetic_hub_market(days=400, seed=3)
    decisions = constant_decisions(market, -1, 5.0)
    # $10,000 at 25 % credit: limit 2,500 ÷ (12 × 2) ≈ 104 MWh/day, below 960 at full size.
    rules = AccountRules(starting_capital_usd=10_000, is_scaled=False, cost_multiple=0)
    result = settle(decisions, market, 200, 210, rules)
    assert result.submitted_mwh[0] <= 2_500 / 24 + 1e-9
    # 104 MWh over 192 bids is 0.54 MW each, rounded down to 0.5 MW: 96 MWh.
    assert result.submitted_mwh[0] == pytest.approx(96.0)


def test_out_of_money_death_freezes_the_account():
    market = synthetic_hub_market(days=400, seed=5)
    # A small account at full size, no sizing and (for this test) no credit limit: DEC
    # loses the demo market's planted DA premium every day until the money runs out.
    rules = AccountRules(starting_capital_usd=3_000.0, is_scaled=False, credit_share_fraction=1e9)
    result = settle(constant_decisions(market, 1, 5.0), market, 100, 400, rules)
    assert not result.is_alive
    assert result.death_cause == "out of money"
    after = result.death_index + 1
    assert (result.position_scale[after:] == 0).all()
    assert (result.daily_pnl_usd[after:] == 0).all()


def test_doubled_costs_cost_more():
    market = synthetic_hub_market(days=600, seed=2)
    decisions = constant_decisions(market, -1, 5.0)
    single = settle(decisions, market, 300, 600, AccountRules())
    doubled = settle(decisions, market, 300, 600, AccountRules(cost_multiple=2.0))
    assert doubled.fees_usd.sum() > 1.9 * single.fees_usd.sum() > 0


@pytest.mark.skipif(
    not (REPOSITORY_ROOT / "data/store/hub_prices.csv.gz").exists(),
    reason="needs the MISO hub table built on this machine",
)
def test_real_benchmarks_reproduce_capital_sizing(monkeypatch):
    """capital_sizing.md §4 (full-size tails) and §7b (storm fitness at $1.5M)."""
    from evobots.simulate.market import read_miso_hub_market

    monkeypatch.chdir(REPOSITORY_ROOT)
    market = read_miso_hub_market()
    start = market.day_index(datetime.date(2019, 1, 1))
    end = len(market.days)
    caps = hub_caps(market)
    for side, worst_loss, worst_day, fitness in (
        (-1, 492_173, "2022-12-23", 0.540),
        (1, 176_554, "2021-02-18", -0.411),
    ):
        decisions = constant_decisions(market, side, caps)
        result = settle(decisions, market, start, end, NO_COSTS, history_start=start)
        full = result.full_size_daily_pnl_usd
        assert round(-full.min()) == worst_loss
        assert result.days[int(np.argmin(full))].isoformat() == worst_day
        storms = fitness_with_and_without_storms(
            result.daily_pnl_usd,
            [day.isoformat() for day in result.days],
            1_500_000,
            ruin_floor_usd=1_000_000,
        )
        assert storms["fitness_all_days"] == pytest.approx(fitness, abs=5e-4)
    # Mean full-size day of always-INC: +$474 (§4).
    inc = settle(
        constant_decisions(market, -1, caps), market, start, end, NO_COSTS, history_start=start
    )
    assert round(inc.full_size_daily_pnl_usd.mean()) == 474
    assert math.isclose(np.percentile(-inc.full_size_daily_pnl_usd, 99), 27_897, abs_tol=1)
