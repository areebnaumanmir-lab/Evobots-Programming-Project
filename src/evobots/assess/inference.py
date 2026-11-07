"""O7: inference on strategy performance beyond the deflated Sharpe (`docs/design_spec.md` §20.11).

All tests compare strategies' daily P&L (or excess returns) d_{k,t} against the benchmark "do
nothing" (d = 0), with stationary-bootstrap resampling (Politis & Romano 1994) so serial
dependence is kept:

- **White's Reality Check** (White 2000): H₀ "no strategy beats the benchmark". Statistic
  V = max_k √T·mean(d_k); its bootstrap distribution recentres each strategy at its mean.
- **Hansen's SPA test** (Hansen 2005): studentised, and strategies that are clearly worse than
  the benchmark don't inflate the p-value (recentring at max(mean, −threshold)).
- **Romano–Wolf step-down** (Romano & Wolf 2005): which strategies beat the benchmark, with
  family-wise error control; adjusted p-values for each.
- **Model confidence set** (Hansen, Lunde & Nason 2011): the set of strategies not
  significantly worse than the best, by sequential elimination with the T_max statistic.
- **Bootstrap confidence interval** of any statistic (e.g. a trader's fitness F).
- **Power:** the smallest annualised Sharpe ratio a test at 5 % detects with 80 % power over
  T years: SR_min ≈ (z₀.₉₅ + z₀.₈₀)/√T, deflated for N trials by the expected maximum.

Example:
    >>> import numpy as np
    >>> generator = np.random.Generator(np.random.PCG64(1))
    >>> noise = generator.normal(0, 1, size=(500, 5))
    >>> reality_check_significance(noise, draws=200, seed=2) > 0.05
    True
    >>> round(minimum_detectable_sharpe(years=20.5), 3)
    0.549
"""

import math

import numpy as np
from scipy import stats

from evobots.assess.statistics import (
    expected_maximum_sharpe,
    politis_white_block_length,
    stationary_bootstrap_indices,
)

DEFAULT_DRAWS = 1000


def bootstrap_index_sets(day_count, block_length, draws, seed):
    """Stationary-bootstrap index arrays (one per draw), shared across strategies."""
    generator = np.random.Generator(np.random.PCG64(seed))
    return [stationary_bootstrap_indices(day_count, block_length, generator) for _ in range(draws)]


def common_block_length(matrix):
    """Mean block length: the median Politis–White length over the strategies."""
    return float(
        np.median(
            [politis_white_block_length(matrix[:, column]) for column in range(matrix.shape[1])]
        )
    )


def reality_check_significance(performance, draws=DEFAULT_DRAWS, seed=0):
    """White's Reality Check p-value for "some strategy beats the benchmark (0)".

    Args:
        performance: (days, strategies) daily P&L relative to the benchmark.
        draws: bootstrap resamples.
        seed: the resampling seed.
    """
    matrix = np.asarray(performance, dtype=float)
    count = matrix.shape[0]
    means = matrix.mean(axis=0)
    statistic = math.sqrt(count) * means.max()
    indices = bootstrap_index_sets(count, common_block_length(matrix), draws, seed)
    exceed = 0
    for sample in indices:
        resampled = matrix[sample].mean(axis=0) - means
        if math.sqrt(count) * resampled.max() >= statistic:
            exceed += 1
    return exceed / draws


def spa_significance(performance, draws=DEFAULT_DRAWS, seed=0):
    """Hansen's SPA (consistent version) p-value for "some strategy beats the benchmark"."""
    matrix = np.asarray(performance, dtype=float)
    count = matrix.shape[0]
    means = matrix.mean(axis=0)
    indices = bootstrap_index_sets(count, common_block_length(matrix), draws, seed)
    bootstrap_means = np.array([matrix[sample].mean(axis=0) for sample in indices])
    deviations = np.sqrt(count) * bootstrap_means.std(axis=0, ddof=1)
    deviations = np.where(deviations > 0, deviations, 1.0)
    statistic = max(0.0, float(np.max(math.sqrt(count) * means / deviations)))
    threshold = deviations / math.sqrt(count) * math.sqrt(2 * math.log(math.log(count)))
    centre = np.where(means >= -threshold, means, 0.0)
    exceed = 0
    for resampled in bootstrap_means:
        value = np.max(math.sqrt(count) * (resampled - means + centre) / deviations)
        if max(0.0, value) >= statistic:
            exceed += 1
    return exceed / draws


def romano_wolf_step_down(performance, draws=DEFAULT_DRAWS, seed=0):
    """Romano–Wolf adjusted p-values of "strategy k beats the benchmark", one per strategy."""
    matrix = np.asarray(performance, dtype=float)
    count, strategies = matrix.shape
    means = matrix.mean(axis=0)
    deviations = matrix.std(axis=0, ddof=1) / math.sqrt(count)
    deviations = np.where(deviations > 0, deviations, 1.0)
    statistics = means / deviations
    indices = bootstrap_index_sets(count, common_block_length(matrix), draws, seed)
    centred = np.array([(matrix[sample].mean(axis=0) - means) / deviations for sample in indices])
    order = np.argsort(-statistics)
    adjusted = np.empty(strategies)
    running = 0.0
    for position, strategy in enumerate(order):
        remaining = order[position:]
        maxima = centred[:, remaining].max(axis=1)
        significance = float((maxima >= statistics[strategy]).mean())
        running = max(running, significance)
        adjusted[strategy] = running
    return adjusted


def model_confidence_set(losses, alpha=0.10, draws=DEFAULT_DRAWS, seed=0):
    """Indices of the model confidence set (Hansen, Lunde & Nason 2011), T_max elimination.

    Args:
        losses: (days, models) daily losses (e.g. −P&L); smaller is better.
        alpha: size; the set contains the best model with probability ≥ 1 − alpha.
        draws: bootstrap resamples.
        seed: the resampling seed.

    Returns:
        (sorted indices kept, {eliminated index: p-value at elimination}).
    """
    matrix = np.asarray(losses, dtype=float)
    count = matrix.shape[0]
    alive = list(range(matrix.shape[1]))
    indices = bootstrap_index_sets(count, common_block_length(matrix), draws, seed)
    eliminated = {}
    running = 0.0
    while len(alive) > 1:
        subset = matrix[:, alive]
        relative = subset - subset.mean(axis=1, keepdims=True)
        means = relative.mean(axis=0)
        bootstrap_means = np.array([relative[sample].mean(axis=0) for sample in indices])
        deviations = bootstrap_means.std(axis=0, ddof=1)
        deviations = np.where(deviations > 0, deviations, 1e-12)
        statistics = means / deviations
        statistic = statistics.max()
        bootstrap_statistics = ((bootstrap_means - means) / deviations).max(axis=1)
        significance = max(running, float((bootstrap_statistics >= statistic).mean()))
        if significance >= alpha:
            break
        worst = alive[int(np.argmax(statistics))]
        eliminated[worst] = significance
        running = significance
        alive.remove(worst)
    return sorted(alive), eliminated


def bootstrap_interval(values, statistic, level=0.90, draws=DEFAULT_DRAWS, seed=0):
    """Percentile interval of statistic(values resampled by the stationary bootstrap)."""
    series = np.asarray(values, dtype=float)
    block = politis_white_block_length(series)
    generator = np.random.Generator(np.random.PCG64(seed))
    estimates = np.array(
        [
            statistic(series[stationary_bootstrap_indices(len(series), block, generator)])
            for _ in range(draws)
        ]
    )
    tail = (1 - level) / 2
    return float(np.quantile(estimates, tail)), float(np.quantile(estimates, 1 - tail))


def minimum_detectable_sharpe(years, trials=1, significance=0.05, power=0.80):
    """Smallest annualised Sharpe ratio detectable over `years` (one-sided), deflated for trials.

    With one trial: (z_{1−α} + z_{power}) / √years. With N trials the luck benchmark
    E[max of N] / √years is added (the deflated Sharpe's SR₀ in annual units).
    """
    detect = (stats.norm.ppf(1 - significance) + stats.norm.ppf(power)) / math.sqrt(years)
    return float(detect + expected_maximum_sharpe(1.0, trials) / math.sqrt(years))
