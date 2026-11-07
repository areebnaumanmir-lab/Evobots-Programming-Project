"""The ORFE track (design spec §20): each model against a hand solution, brute force or a fact."""

import itertools
import math

import numpy as np
import pytest

from evobots.orfe import battery, optimizer, portfolio, risk, scenarios, search_or
from evobots.simulate.market import synthetic_hub_market


# ----- O1 -----
def test_scenarios_see_nothing_after_the_newest_visible_day():
    market = synthetic_hub_market(days=400, seed=2)
    spreads = market.day_ahead - market.real_time
    changed = spreads.copy()
    changed[395:] += 1000.0  # days ≥ D − 5 for D = 400 are invisible
    for function in (scenarios.bootstrap_scenarios, scenarios.regime_scenarios):
        first = function(spreads, 400, 10, seed=3)
        second = function(changed, 400, 10, seed=3)
        assert np.array_equal(first, second)


def test_regime_model_recovers_two_scales():
    generator = np.random.Generator(np.random.PCG64(4))
    states = np.zeros(3000, dtype=int)
    for day in range(1, 3000):
        states[day] = (
            states[day - 1]
            if generator.random() > (0.02 if states[day - 1] == 0 else 0.1)
            else 1 - states[day - 1]
        )
    values = np.where(states == 0, 1.0, 1.0) + np.where(
        states == 0, 2.0, 15.0
    ) * generator.standard_t(4, 3000)
    model = scenarios.fit_regime_model(values)
    assert model.scales[0] == pytest.approx(2.0, rel=0.25)
    assert model.scales[1] == pytest.approx(15.0, rel=0.3)


def test_crps_of_a_point_ensemble_is_the_absolute_error():
    assert scenarios.crps_of_ensemble(np.array([3.0, 3.0]), 5.0) == pytest.approx(2.0)


# ----- O2 -----
def brute_force_objective(gains, quantity, fee, risk_aversion, alpha):
    profits = (gains * quantity).sum(axis=(1, 2)) - fee * np.abs(quantity).sum()
    losses = -profits
    cvar = min(
        threshold + np.maximum(losses - threshold, 0).sum() / ((1 - alpha) * len(losses))
        for threshold in np.concatenate([losses, [0.0]])
    )
    return profits.mean() - risk_aversion * cvar


@pytest.mark.parametrize("risk_aversion", [0.0, 0.1, 0.5])
def test_mean_cvar_lp_matches_brute_force(risk_aversion):
    generator = np.random.Generator(np.random.PCG64(3))
    gains = generator.normal([[1.0], [-0.8]], 3, size=(6, 2, 1))
    caps = np.array([2.0])
    dec, inc = optimizer.solve_mean_cvar(gains, caps, 0.1, risk_aversion, 0.8)
    solution = (dec - inc).reshape(2, 1)
    grid = np.linspace(-2, 2, 81)
    best = max(
        brute_force_objective(gains, np.array(point).reshape(2, 1), 0.1, risk_aversion, 0.8)
        for point in itertools.product(grid, grid)
    )
    assert brute_force_objective(gains, solution, 0.1, risk_aversion, 0.8) == pytest.approx(
        best, abs=1e-6
    )


def test_dpds_budget_allocation_matches_brute_force():
    generator = np.random.Generator(np.random.PCG64(5))
    values = generator.normal(size=(4, 6))
    values[:, 0] = 0.0
    chosen = optimizer.allocate_budget(values)
    best = max(
        (sum(values[option, index] for option, index in enumerate(combination)), combination)
        for combination in itertools.product(range(6), repeat=4)
        if sum(combination) <= 5
    )
    assert sum(values[option, index] for option, index in enumerate(chosen)) == pytest.approx(
        best[0]
    )
    assert chosen.sum() <= 5


def test_perfect_foresight_is_an_upper_bound():
    from evobots.simulate.settlement import AccountRules, constant_decisions, settle

    market = synthetic_hub_market(days=120, seed=6)
    caps = np.full(8, 5.0)
    rules = AccountRules(is_scaled=False, cost_multiple=0.0)
    bound = settle(
        optimizer.perfect_foresight_decisions(market, 60, 120, caps, 0.0),
        market,
        60,
        120,
        rules,
        history_start=60,
    )
    always = settle(constant_decisions(market, -1, caps), market, 60, 120, rules, history_start=60)
    assert bound.daily_pnl_usd.sum() >= always.daily_pnl_usd.sum()


# ----- O3 -----
def test_portfolio_models_agree_on_small_cases():
    generator = np.random.Generator(np.random.PCG64(7))
    returns = generator.normal([0.001, 0.0005, 0.0002], [0.01, 0.01, 0.01], size=(500, 3))
    # Risk-neutral mean-CVaR and nearly risk-neutral mean-variance put everything on the best mean.
    cvar = portfolio.mean_cvar_weights(returns, risk_aversion=0.0)
    variance = portfolio.mean_variance_weights(returns, risk_aversion=1e-6)
    best = int(np.argmax(returns.mean(axis=0)))
    assert cvar[best] == pytest.approx(1.0, abs=1e-6)
    assert variance[best] == pytest.approx(1.0, abs=1e-3)
    # Equal variances, independent: risk parity is equal weights.
    np.testing.assert_allclose(
        portfolio.risk_parity_weights(generator.normal(0, 0.01, (5000, 3))), 1 / 3, atol=0.03
    )


def test_growth_optimal_weight_matches_kelly_for_one_asset():
    generator = np.random.Generator(np.random.PCG64(8))
    returns = generator.normal(0.002, 0.04, size=(20_000, 1))
    weight = portfolio.growth_optimal_weights(returns)[0]
    kelly = returns.mean() / returns.var()
    assert weight == pytest.approx(min(kelly, 1.0), rel=0.1)


# ----- O4 -----
def test_battery_lp_matches_a_hand_solved_three_hours():
    prices = np.array([10.0, 50.0, 30.0])
    unit = battery.Battery(
        power_mw=1.0,
        energy_mwh=1.0,
        round_trip_efficiency=1.0,
        degradation_usd_per_mwh=0.0,
        initial_fraction=0.0,
    )
    schedule = battery.schedule_lp(prices, unit)
    # Charge 1 MWh at $10, discharge at $50: $40.
    assert schedule.revenue_usd == pytest.approx(40.0)
    np.testing.assert_allclose(schedule.charge_mw, [1, 0, 0], atol=1e-9)
    np.testing.assert_allclose(schedule.discharge_mw, [0, 1, 0], atol=1e-9)


def test_exclusive_milp_and_lp_differ_only_when_prices_turn_negative():
    unit = battery.Battery(
        power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=0.81, degradation_usd_per_mwh=0.0
    )
    positive = np.array([20.0, 60.0, 15.0, 70.0])
    assert battery.schedule_lp(positive, unit).revenue_usd == pytest.approx(
        battery.schedule_lp(positive, unit, is_exclusive=True).revenue_usd, abs=1e-6
    )
    negative = np.array([-50.0, -40.0, 30.0, 35.0])
    relaxed = battery.schedule_lp(negative, unit)
    exclusive = battery.schedule_lp(negative, unit, is_exclusive=True)
    assert relaxed.revenue_usd >= exclusive.revenue_usd - 1e-6
    assert np.all(np.minimum(exclusive.charge_mw, exclusive.discharge_mw) < 1e-6)


def test_dynamic_program_agrees_with_brute_force_on_a_tiny_grid():
    unit = battery.Battery(
        power_mw=1.0,
        energy_mwh=2.0,
        round_trip_efficiency=1.0,
        degradation_usd_per_mwh=0.0,
        initial_fraction=0.5,
    )
    prices = np.full(24, 30.0)
    prices[2], prices[20] = 5.0, 80.0
    grid, values = battery.dp_value_function(prices[None, :], unit, grid_points=5)
    policy = battery.dp_policy_day(prices, unit, grid, values)
    assert policy.revenue_usd == pytest.approx(
        battery.schedule_lp(prices, unit).revenue_usd, rel=1e-6
    )


# ----- O5 -----
def test_kupiec_and_estimators_on_normal_losses():
    generator = np.random.Generator(np.random.PCG64(9))
    pnl = generator.normal(0, 1000, 1500)
    var, _ = risk.point_in_time_forecasts(pnl, risk.empirical_var_es)
    known = ~np.isnan(var)
    breaches = (-pnl[known] > var[known]).astype(int)
    assert 0.003 < breaches.mean() < 0.025
    assert risk.kupiec_significance(np.array([0] * 990 + [1] * 10), 0.01) == pytest.approx(1.0)


def test_evt_tail_on_pareto_losses():
    generator = np.random.Generator(np.random.PCG64(10))
    losses = generator.pareto(3.0, 20_000) + 1
    var, es = risk.evt_var_es(losses, 0.99)
    true_var = (0.01) ** (-1 / 3.0)
    assert var == pytest.approx(true_var, rel=0.1)
    assert es > var


# ----- O8 -----
def test_ocba_picks_the_best_more_often_than_equal_allocation():
    generator = np.random.Generator(np.random.PCG64(11))
    true_means = np.array([1.0, 0.8, 0.5, 0.0, -0.5])
    noise = 1.5
    correct = {"ocba": 0, "equal": 0}
    for _ in range(300):
        first = generator.normal(true_means[:, None], noise, size=(5, 5))
        means, deviations = first.mean(axis=1), first.std(axis=1, ddof=1)
        for name, allocation in (
            ("ocba", search_or.ocba_allocation(means, deviations, 100)),
            ("equal", np.full(5, 20)),
        ):
            totals = [
                np.concatenate(
                    [first[index], generator.normal(true_means[index], noise, allocation[index])]
                ).mean()
                for index in range(5)
            ]
            correct[name] += int(np.argmax(totals) == 0)
    assert correct["ocba"] >= correct["equal"]


def test_cma_es_minimises_rosenbrock():
    def rosenbrock(point):
        return float(sum(100 * (point[1:] - point[:-1] ** 2) ** 2 + (1 - point[:-1]) ** 2))

    best, value = search_or.cma_es(rosenbrock, np.zeros(4), 0.5, iterations=400, seed=1)
    assert value < 1e-4
    np.testing.assert_allclose(best, 1.0, atol=0.02)


def test_nsga2_returns_a_spread_non_dominated_front():
    generator = np.random.Generator(np.random.PCG64(12))

    def evaluate(point):
        return (-(point[0] ** 2), -((point[0] - 2) ** 2))

    def vary(parent, partner, generator):
        return np.clip((parent + partner) / 2 + generator.normal(0, 0.3, 1), -1, 3)

    population, objectives = search_or.nsga2(
        [generator.uniform(-1, 3, 1) for _ in range(30)], evaluate, vary, 30, generator
    )
    front = search_or.non_dominated_fronts(objectives)[0]
    points = np.array([population[index][0] for index in front])
    assert (
        len(front) >= 20
        and points.min() < 0.3
        and points.max() > 1.7
        and np.all((points > -0.1) & (points < 2.1))
    )
    assert search_or.hypervolume(np.array(objectives)[front], np.array([-10.0, -10.0])) > 0


def test_successive_halving_counts_cost():
    survivors, cost = search_or.successive_halving(
        list(range(16)), lambda candidate, fidelity: candidate * fidelity, [1, 2, 4]
    )
    assert [candidate for candidate, _ in survivors] == [15, 14, 13, 12]
    assert cost == 16 * 1 + 8 * 2 + 4 * 4
    assert cost < 16 * 4
    assert math.isclose(cost / (16 * 4), 0.75)
