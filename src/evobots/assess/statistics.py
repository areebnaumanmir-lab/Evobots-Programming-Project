"""Statistics behind the deployment gates (`docs/design_spec.md` §12.2, §20.11).

- **Sharpe ratio** of daily P&L returns, annualised with √365 (power trades every day).
- **Probabilistic and deflated Sharpe ratio** (Bailey & López de Prado 2014): the probability
  that the true Sharpe ratio exceeds a benchmark SR₀, allowing for skewness γ₃ and kurtosis γ₄:
  PSR = Φ((ŜR − SR₀)·√(T − 1) / √(1 − γ₃·ŜR + (γ₄ − 1)/4·ŜR²)). The deflated version sets
  SR₀ to the expected maximum Sharpe ratio of N independent trials with no skill:
  SR₀ = √V·((1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))), γ = 0.5772 (Euler–Mascheroni).
- **Effective number of trials:** the participation ratio of the eigenvalues of the
  correlation matrix of the candidates' daily P&L, (Σλ)²/Σλ² (1 for identical streams, n for
  independent ones). A documented choice (§12.2 says "cluster or PCA").
- **MinBTL** (Bailey, Borwein, López de Prado & Zhu 2014): the years of data needed so that
  N trials can't produce an annualised Sharpe ratio of SR by luck: ≈ (E[max of N] / SR)².
- **Stationary bootstrap** (Politis & Romano 1994), mean block length by the automatic rule of
  Politis & White (2004, corrected by Patton, Politis & White 2009).
- **Probability of backtest overfitting** by CSCV (Bailey, Borwein, López de Prado & Zhu 2017).

Example:
    >>> round(float(expected_maximum_sharpe(1.0, 100)), 3)
    2.531
    >>> round(float(minimum_backtest_length_years(1.0, 45)), 1)
    5.0
"""

import itertools
import math

import numpy as np
from scipy import stats

EULER_MASCHERONI = 0.5772156649015329
DAYS_PER_YEAR = 365.0


def sharpe_ratio(daily_returns, periods_per_year=DAYS_PER_YEAR):
    """Annualised Sharpe ratio of daily returns (mean ÷ sample standard deviation × √365)."""
    returns = np.asarray(daily_returns, dtype=float)
    deviation = returns.std(ddof=1) if len(returns) > 1 else 0.0
    if deviation == 0:
        return 0.0
    return float(returns.mean() / deviation * math.sqrt(periods_per_year))


def expected_maximum_sharpe(standard_deviation, trial_count):
    """E[max Sharpe ratio] of N unskilled trials whose estimates have this standard deviation."""
    if trial_count <= 1:
        return 0.0
    normal = stats.norm.ppf
    return standard_deviation * (
        (1 - EULER_MASCHERONI) * normal(1 - 1 / trial_count)
        + EULER_MASCHERONI * normal(1 - 1 / (trial_count * math.e))
    )


def probabilistic_sharpe_ratio(daily_returns, benchmark_sharpe_per_period):
    """P(true per-period Sharpe > benchmark), allowing for skewness and kurtosis."""
    returns = np.asarray(daily_returns, dtype=float)
    count = len(returns)
    deviation = returns.std(ddof=1)
    if count < 3 or deviation == 0:
        return 0.0
    estimate = returns.mean() / deviation
    skewness = float(stats.skew(returns))
    kurtosis = float(stats.kurtosis(returns, fisher=False))
    denominator = 1 - skewness * estimate + (kurtosis - 1) / 4 * estimate**2
    if denominator <= 0:
        return 0.0
    return float(
        stats.norm.cdf(
            (estimate - benchmark_sharpe_per_period) * math.sqrt(count - 1) / math.sqrt(denominator)
        )
    )


def deflated_sharpe_ratio(daily_returns, trial_sharpe_variance_per_period, effective_trials):
    """The deflated Sharpe ratio: PSR against the expected best of the effective trials."""
    benchmark = expected_maximum_sharpe(
        math.sqrt(max(trial_sharpe_variance_per_period, 0.0)), effective_trials
    )
    return probabilistic_sharpe_ratio(daily_returns, benchmark)


def effective_trial_count(daily_pnl_matrix):
    """Participation ratio (Σλ)²/Σλ² of the correlation matrix of candidates' daily P&L.

    Args:
        daily_pnl_matrix: (days, candidates).
    """
    matrix = np.asarray(daily_pnl_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        return 0.0
    varying = matrix[:, matrix.std(axis=0) > 0]
    if varying.shape[1] <= 1:
        return float(varying.shape[1])
    eigenvalues = np.clip(np.linalg.eigvalsh(np.corrcoef(varying, rowvar=False)), 0, None)
    return float(eigenvalues.sum() ** 2 / (eigenvalues**2).sum())


def minimum_backtest_length_years(annual_sharpe, trial_count):
    """Years of data below which N trials can produce this Sharpe ratio by luck (MinBTL)."""
    return float((expected_maximum_sharpe(1.0, trial_count) / annual_sharpe) ** 2)


def politis_white_block_length(values):
    """Optimal mean block length of the stationary bootstrap (Politis & White 2004, PPW 2009)."""
    series = np.asarray(values, dtype=float)
    count = len(series)
    if count < 10:
        return 1.0
    centered = series - series.mean()
    variance = centered @ centered / count
    if variance == 0:
        return 1.0
    max_lag = min(int(math.ceil(math.sqrt(count))) + 5, count - 1)
    autocorrelation = np.array(
        [centered[: count - lag] @ centered[lag:] / count / variance for lag in range(max_lag + 1)]
    )
    # Smallest m such that the next K_N = max(5, log10 n) autocorrelations are insignificant.
    band = 2 * math.sqrt(math.log10(count) / count)
    run_length = max(5, int(math.ceil(math.log10(count))))
    chosen = max_lag // 2
    for lag in range(1, max_lag - run_length + 1):
        if np.all(np.abs(autocorrelation[lag : lag + run_length]) < band):
            chosen = lag
            break
    window = min(2 * max(chosen, 1), max_lag)
    lags = np.arange(-window, window + 1)
    flat_top = np.where(
        np.abs(lags) / window <= 0.5, 1.0, np.clip(2 * (1 - np.abs(lags) / window), 0, 1)
    )
    covariance = variance * autocorrelation[np.abs(lags)]
    spectral_sum = float(np.sum(flat_top * covariance))
    weighted_sum = float(np.sum(flat_top * np.abs(lags) * covariance))
    if spectral_sum <= 0:
        return 1.0
    block = (2 * weighted_sum**2 / spectral_sum**2) ** (1 / 3) * count ** (1 / 3)
    return float(min(max(block, 1.0), count / 2))


def stationary_bootstrap_indices(count, mean_block_length, generator):
    """One stationary-bootstrap resample of indices 0 … count−1 (blocks wrap around)."""
    restart = 1.0 / max(mean_block_length, 1.0)
    indices = np.empty(count, dtype=int)
    position = int(generator.integers(count))
    starts = generator.random(count) < restart
    jumps = generator.integers(count, size=count)
    for step in range(count):
        if step > 0:
            position = int(jumps[step]) if starts[step] else (position + 1) % count
        indices[step] = position
    return indices


def probability_of_backtest_overfitting(performance_matrix, partitions=8):
    """PBO by combinatorially symmetric cross-validation.

    Args:
        performance_matrix: (days, candidates) daily P&L (or returns).
        partitions: S, an even number of blocks; every half of them is a training set.

    Returns:
        (pbo, logits): the share of splits where the in-sample best ranks in the bottom half
        out of sample, and each split's logit of its out-of-sample relative rank.
    """
    matrix = np.asarray(performance_matrix, dtype=float)
    blocks = np.array_split(np.arange(matrix.shape[0]), partitions)
    logits = []
    for chosen in itertools.combinations(range(partitions), partitions // 2):
        train = np.concatenate([blocks[index] for index in chosen])
        test = np.concatenate([blocks[index] for index in range(partitions) if index not in chosen])
        train_score = matrix[train].mean(axis=0) / (matrix[train].std(axis=0, ddof=1) + 1e-12)
        test_score = matrix[test].mean(axis=0) / (matrix[test].std(axis=0, ddof=1) + 1e-12)
        best = int(np.argmax(train_score))
        relative_rank = (stats.rankdata(test_score)[best]) / (matrix.shape[1] + 1)
        logits.append(math.log(relative_rank / (1 - relative_rank)))
    logits = np.array(logits)
    return float((logits <= 0).mean()), logits
