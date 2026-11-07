"""M5 and O6: career layers, fitness, the quit hazard fit, sequential tests, stopping, survival.

Each statistical method is tested on simulated data with a known answer (design spec §20.9).
"""

import math

import numpy as np
import pytest
from scipy import optimize, stats

from evobots.career.hazard import TARGET_SURVIVAL, fit_quit_hazard, monthly_covariates
from evobots.career.model import PARSIMONY_PER_NODE, PRESETS, CareerSettings, apply_career
from evobots.career.sequential import (
    bocpd_change_probabilities,
    cusum_signal_month,
    recent_change_probability,
    shiryaev_roberts_signal_month,
    siegmund_average_run_length,
    simulated_average_run_length,
)
from evobots.career.stopping import stopping_thresholds
from evobots.career.survival import cox_proportional_hazards, kaplan_meier, schoenfeld_test
from evobots.simulate.market import synthetic_hub_market
from evobots.simulate.settlement import AccountRules, constant_decisions, settle


@pytest.fixture(scope="module")
def losing_result():
    """Always-DEC on the demo market loses the planted DA premium: a losing career."""
    market = synthetic_hub_market(days=1600, seed=3)
    return settle(constant_decisions(market, 1, 5.0), market, 500, 1600, AccountRules())


def test_default_career_is_out_of_money_only(losing_result):
    outcome = apply_career(losing_result, PRESETS["individual"], node_count=3)
    assert outcome.stop_cause == losing_result.death_cause
    expected = math.log(max(losing_result.final_equity_usd, 1) / 1_500_000) - PARSIMONY_PER_NODE * 3
    assert outcome.fitness == pytest.approx(expected)
    assert (outcome.survival_by_month == 1).all()


def test_floor_and_loss_limit_freeze_the_account(losing_result):
    outcome = apply_career(losing_result, CareerSettings(ruin_floor_fraction=0.99))
    assert outcome.stop_cause == "capital floor"
    frozen = outcome.equity_usd[outcome.stop_index :]
    assert (frozen == frozen[0]).all()
    assert outcome.equity_usd[outcome.stop_index] <= 0.99 * 1_500_000
    limited = apply_career(losing_result, CareerSettings(drawdown_limit_fraction=0.005))
    assert limited.stop_cause == "loss limit"


def test_edge_check_retires_a_steady_loser(losing_result):
    outcome = apply_career(
        losing_result, CareerSettings(is_edge_check_on=True, cusum_threshold=3.0)
    )
    assert outcome.stop_cause in {"edge gone", "out of money"}
    assert outcome.stop_index is not None


def test_fitness_is_deterministic_with_the_quit_hazard(losing_result):
    from evobots.career.hazard import QuitHazard

    settings = CareerSettings(quit_hazard=QuitHazard((-3.0, -1.0, -1.0, 1.0, -0.3)))
    first = apply_career(losing_result, settings).fitness
    second = apply_career(losing_result, settings).fitness
    assert first == second
    assert apply_career(losing_result, settings).survival_by_month[-1] < 1


def losing_population(count, seed):
    generator = np.random.Generator(np.random.PCG64(seed))
    paths = []
    for _ in range(count):
        drift = generator.uniform(-0.03, -0.002)
        returns = generator.normal(drift, 0.06, 48)
        equity = 1e6 * np.exp(np.cumsum(returns))
        paths.append(monthly_covariates(equity, 1e6, np.arange(48)))
    return paths


def test_quit_hazard_reproduces_the_survival_targets():
    fit = fit_quit_hazard(losing_population(200, seed=4), bootstrap_draws=20)
    for months, target in TARGET_SURVIVAL.items():
        assert fit.fitted_survival[months] == pytest.approx(target, abs=0.025)
    assert all(error >= 0 for error in fit.standard_errors)


@pytest.mark.parametrize("mean", [0.0, 0.5, 1.0])
def test_siegmund_approximation_matches_simulation(mean):
    simulated, standard_error = simulated_average_run_length(mean, 0.5, 4.0, runs=3000, seed=1)
    approximated = siegmund_average_run_length(mean, 0.5, 4.0)
    assert abs(simulated - approximated) / simulated < 0.06


def test_cusum_and_shiryaev_roberts_detect_a_lost_edge():
    """Over 300 simulated careers: few false alarms while the edge lasts, quick detection after.

    Edge intact: z ~ N(1, 1) for 60 months, then z ~ N(0, 1). With k = 0.5 and h = 4 the
    CUSUM's in-control ARL is about 338 months (so about 16 % false alarms in 60 months) and its
    detection delay about 8.3 months (Siegmund).
    """
    generator = np.random.Generator(np.random.PCG64(8))
    false_alarms = {"cusum": 0, "roberts": 0}
    delays = {"cusum": [], "roberts": []}
    for _ in range(300):
        path = np.concatenate([generator.normal(1.0, 1.0, 60), generator.normal(0.0, 1.0, 60)])
        signals = {
            "cusum": cusum_signal_month(path, reference=0.5, threshold=4.0, scale=1.0),
            "roberts": shiryaev_roberts_signal_month(path, shift=1.0, threshold=300.0),
        }
        for name, month in signals.items():
            if month is not None and month < 60:
                false_alarms[name] += 1
            elif month is not None:
                delays[name].append(month - 60 + 1)
    assert false_alarms["cusum"] / 300 < 0.25
    assert false_alarms["roberts"] / 300 < 0.25
    assert 5 <= np.mean(delays["cusum"]) <= 12
    assert 4 <= np.mean(delays["roberts"]) <= 14


def test_bocpd_puts_the_change_where_it_happened():
    generator = np.random.Generator(np.random.PCG64(2))
    path = np.concatenate([generator.normal(2.0, 0.5, 40), generator.normal(-1.0, 0.5, 40)])
    run_length = bocpd_change_probabilities(path, 1 / 50, 0.25, 0.0, 4.0)
    recent = recent_change_probability(run_length, within_months=3)
    assert int(np.argmax(recent[35:50])) + 35 in range(40, 43)
    assert recent[3:38].max() < 0.5  # the first months are trivially "recent"


def test_stopping_threshold_against_a_two_month_hand_solution():
    """Two months left: continue iff m + E[max(0, m')] > 0, m' ~ N(m, v)."""
    prior, noise = 0.03, 0.05
    thresholds = stopping_thresholds(0.0, prior, noise, horizon_months=2)
    variances = 1 / (1 / prior**2 + np.arange(3) / noise**2)
    step = math.sqrt(variances[0] - variances[1])

    def continuing_value(mean):
        standardised = mean / step
        return mean + mean * stats.norm.cdf(standardised) + step * stats.norm.pdf(standardised)

    exact = optimize.brentq(continuing_value, -1.0, 0.0)
    grid_step = 12 * prior / 800
    assert abs(thresholds[0] - exact) <= grid_step * 1.001
    assert abs(thresholds[1]) <= grid_step * 1.001  # one month left: stop iff m < 0


def test_kaplan_meier_and_greenwood_by_hand():
    times, survival, variance = kaplan_meier([2, 3, 3, 5, 6, 6], [1, 1, 0, 1, 0, 1])
    assert times.tolist() == [2.0, 3.0, 5.0, 6.0]
    # At t = 6 two are at risk (one dies, one is censored): S falls by half, not to zero.
    np.testing.assert_allclose(
        survival, [5 / 6, 5 / 6 * 4 / 5, 5 / 6 * 4 / 5 * 2 / 3, 5 / 6 * 4 / 5 * 2 / 3 / 2]
    )
    assert variance[0] == pytest.approx((5 / 6) ** 2 * (1 / (6 * 5)))


def test_cox_recovers_a_known_coefficient():
    generator = np.random.Generator(np.random.PCG64(6))
    count = 800
    covariate = generator.normal(size=count)
    true_beta = 0.7
    durations = generator.exponential(1 / np.exp(true_beta * covariate))
    censor = generator.exponential(2.0, size=count)
    events = (durations <= censor).astype(int)
    observed = np.minimum(durations, censor)
    beta, standard_errors, _ = cox_proportional_hazards(observed, events, covariate)
    assert abs(beta[0] - true_beta) < 3 * standard_errors[0]
    ((_, significance),) = schoenfeld_test(observed, events, covariate, beta)
    assert significance > 0.01
