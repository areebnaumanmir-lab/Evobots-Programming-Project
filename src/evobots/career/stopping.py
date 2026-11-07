"""O6: quitting as optimal stopping for a Bayesian trader (`docs/design_spec.md` §20.9).

A trader does not know its edge μ (mean monthly excess log return). Its prior is
N(m₀, s₀²); monthly results are x ~ N(μ, σ²), so after n months the posterior is
N(m_n, s_n²) with s_n² = 1 / (1/s₀² + n/σ²). Each month it may stop (value 0, the outside
option: T-bills minus fixed costs, already netted into x) or trade one more month (expected
reward m_n). Over a horizon of N months:

    V_N(m) = 0,  V_n(m) = max(0, m + E[V_{n+1}(m')]),  m' ~ N(m, s_n² − s_{n+1}²)

(the posterior mean moves by the variance it loses). The rule is a threshold b_n: stop when
m_n < b_n. Solved by backward induction on a grid of posterior means.

Example:
    >>> thresholds = stopping_thresholds(0.0, 0.02, 0.05, horizon_months=24)
    >>> bool(thresholds[0] < 0 < thresholds[-1] + 1e-9)
    True
"""

import math

import numpy as np

GRID_POINTS = 801
GRID_HALF_WIDTH_STANDARD_DEVIATIONS = 6.0
QUADRATURE_POINTS = 41


def posterior_variances(prior_variance, noise_variance, horizon_months):
    """s_n² for n = 0 … horizon."""
    months = np.arange(horizon_months + 1)
    return 1.0 / (1.0 / prior_variance + months / noise_variance)


def stopping_thresholds(
    prior_mean, prior_standard_deviation, noise_standard_deviation, horizon_months=60
):
    """The posterior-mean threshold b_n below which the trader stops, n = 0 … horizon − 1."""
    variances = posterior_variances(
        prior_standard_deviation**2, noise_standard_deviation**2, horizon_months
    )
    half_width = GRID_HALF_WIDTH_STANDARD_DEVIATIONS * prior_standard_deviation
    grid = np.linspace(prior_mean - half_width, prior_mean + half_width, GRID_POINTS)
    nodes, weights = np.polynomial.hermite_e.hermegauss(QUADRATURE_POINTS)
    weights = weights / weights.sum()
    value_next = np.zeros(GRID_POINTS)
    thresholds = np.empty(horizon_months)
    for month in range(horizon_months - 1, -1, -1):
        step = math.sqrt(max(variances[month] - variances[month + 1], 0.0))
        expected_next = np.zeros(GRID_POINTS)
        for node, weight in zip(nodes, weights):
            expected_next += weight * np.interp(grid + step * node, grid, value_next)
        continuing = grid + expected_next
        value = np.maximum(0.0, continuing)
        stopping = continuing <= 0
        thresholds[month] = grid[np.flatnonzero(~stopping)[0]] if (~stopping).any() else math.inf
        value_next = value
    return thresholds


def stopping_month(
    monthly_excess, prior_mean, prior_standard_deviation, noise_standard_deviation, thresholds
):
    """The month a Bayesian trader with these thresholds stops on an observed path, or None."""
    precision = 1.0 / prior_standard_deviation**2
    weighted_sum = prior_mean * precision
    noise_precision = 1.0 / noise_standard_deviation**2
    for month in range(min(len(monthly_excess), len(thresholds))):
        posterior_mean = weighted_sum / precision
        if posterior_mean < thresholds[month]:
            return month
        precision += noise_precision
        weighted_sum += monthly_excess[month] * noise_precision
    return None
