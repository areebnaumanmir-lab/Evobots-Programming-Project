"""O5: estimating the 1-in-100-day loss and expected shortfall, and backtesting them (§20.8).

The sizing rule uses the trailing empirical 99th-percentile loss, which was exceeded on 2.2 %
of days instead of 1 % (§13). Here it is treated as a risk-model problem: several point-in-time
estimators of VaR₉₉ and ES₉₉ of tomorrow's loss, each using only losses up to D − 6, and the
standard backtests of their breaches.

**Estimators** (window: the trailing 365 visible days):
- empirical quantile (the current rule);
- EVT peaks-over-threshold: a generalised Pareto tail fitted above the 90th percentile of
  losses (`scipy.stats.genpareto`, location fixed at the threshold);
- GARCH(1,1)-filtered historical simulation: losses standardised by a fitted GARCH volatility,
  the empirical quantile rescaled by tomorrow's forecast volatility;
- Cornish–Fisher: the normal quantile adjusted for sample skewness and kurtosis;
- regime-conditional: O1's two-state model's stress or calm scale, by the filtered state.

**Backtests:**
- Kupiec's proportion-of-failures likelihood ratio (χ²₁);
- Christoffersen's independence and conditional-coverage tests (χ²₁, χ²₂);
- Acerbi & Székely's Z₂ test of expected shortfall: Z₂ = Σ L_t·1{L_t > VaR_t} / (T·(1 − p)·ES_t)
  − 1, with a p-value by simulation under the estimated tail.

Example:
    >>> import numpy as np
    >>> breaches = np.array([0] * 98 + [1, 1])
    >>> round(kupiec_significance(breaches, 0.01), 3)
    0.376
"""

import math

import numpy as np
from scipy import optimize, stats

LEVEL = 0.99
TRAILING_DAYS = 365
LAG_DAYS = 6
MINIMUM_DAYS = 90
EVT_THRESHOLD_QUANTILE = 0.90


def empirical_var_es(losses, level=LEVEL):
    """(VaR, ES) as the empirical quantile and the mean beyond it."""
    var = float(np.percentile(losses, 100 * level))
    tail = losses[losses >= var]
    return var, float(tail.mean()) if len(tail) else var


def evt_var_es(losses, level=LEVEL, threshold_quantile=EVT_THRESHOLD_QUANTILE):
    """Peaks over threshold with a generalised Pareto tail (falls back to empirical)."""
    threshold = float(np.quantile(losses, threshold_quantile))
    excesses = losses[losses > threshold] - threshold
    if len(excesses) < 10:
        return empirical_var_es(losses, level)
    shape, _, scale = stats.genpareto.fit(excesses, floc=0.0)
    exceed_share = len(excesses) / len(losses)
    tail_probability = (1 - level) / exceed_share
    if abs(shape) < 1e-6:
        var = threshold + scale * math.log(1 / tail_probability)
    else:
        var = threshold + scale / shape * (tail_probability ** (-shape) - 1)
    es = (var + scale - shape * threshold) / (1 - shape) if shape < 1 else float("inf")
    return float(var), float(es)


def fit_garch(values):
    """GARCH(1,1) by maximum likelihood (normal): returns (ω, α, β, conditional variances)."""
    values = np.asarray(values, dtype=float)
    variance = values.var()

    def variances(parameters):
        omega, alpha, beta = parameters
        series = np.empty(len(values))
        series[0] = variance
        for index in range(1, len(values)):
            series[index] = omega + alpha * values[index - 1] ** 2 + beta * series[index - 1]
        return series

    def negative_likelihood(parameters):
        omega, alpha, beta = parameters
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.999:
            return 1e12
        series = variances(parameters)
        return 0.5 * np.sum(np.log(series) + values**2 / series)

    start = np.array([0.1 * variance, 0.1, 0.8])
    result = optimize.minimize(
        negative_likelihood,
        start,
        method="Nelder-Mead",
        options={"maxiter": 600, "xatol": 1e-8, "fatol": 1e-8},
    )
    omega, alpha, beta = result.x
    return omega, alpha, beta, variances(result.x)


def garch_var_es(losses, level=LEVEL):
    """Filtered historical simulation with a GARCH(1,1) volatility."""
    centred = losses - losses.mean()
    omega, alpha, beta, series = fit_garch(centred)
    deviation = np.sqrt(series)
    standardised = centred / deviation
    forecast = math.sqrt(omega + alpha * centred[-1] ** 2 + beta * series[-1])
    standardised_var, standardised_es = empirical_var_es(standardised, level)
    return float(losses.mean() + forecast * standardised_var), float(
        losses.mean() + forecast * standardised_es
    )


def cornish_fisher_var_es(losses, level=LEVEL):
    """Cornish–Fisher adjusted quantile (ES by the empirical tail beyond it)."""
    normal_quantile = stats.norm.ppf(level)
    skewness = stats.skew(losses)
    kurtosis = stats.kurtosis(losses)
    adjusted = (
        normal_quantile
        + (normal_quantile**2 - 1) * skewness / 6
        + (normal_quantile**3 - 3 * normal_quantile) * kurtosis / 24
        - (2 * normal_quantile**3 - 5 * normal_quantile) * skewness**2 / 36
    )
    var = float(losses.mean() + losses.std(ddof=1) * adjusted)
    tail = losses[losses >= var]
    return var, float(tail.mean()) if len(tail) else var


ESTIMATORS = {
    "empirical": empirical_var_es,
    "evt_pot": evt_var_es,
    "garch_fhs": garch_var_es,
    "cornish_fisher": cornish_fisher_var_es,
}


def point_in_time_forecasts(daily_pnl, estimator, level=LEVEL):
    """(VaR, ES) of each day's loss from losses up to D − 6 (NaN in the warm-up)."""
    losses = -np.asarray(daily_pnl, dtype=float)
    var = np.full(len(losses), np.nan)
    es = np.full(len(losses), np.nan)
    for day in range(len(losses)):
        newest = day - LAG_DAYS
        window = losses[max(0, newest - TRAILING_DAYS + 1) : newest + 1]
        if len(window) < MINIMUM_DAYS:
            continue
        var[day], es[day] = estimator(window, level)
    return var, es


def kupiec_significance(breaches, expected_rate):
    """Kupiec's proportion-of-failures test p-value."""
    breaches = np.asarray(breaches, dtype=int)
    count, failures = len(breaches), int(breaches.sum())
    observed = failures / count
    if failures in (0, count):
        log_ratio = -2 * (
            count * math.log(1 - expected_rate)
            if failures == 0
            else count * math.log(expected_rate)
        )
    else:
        log_ratio = -2 * (
            (count - failures) * math.log(1 - expected_rate)
            + failures * math.log(expected_rate)
            - (count - failures) * math.log(1 - observed)
            - failures * math.log(observed)
        )
    return float(stats.chi2.sf(log_ratio, 1))


def christoffersen_significance(breaches, expected_rate):
    """(independence p-value, conditional-coverage p-value)."""
    breaches = np.asarray(breaches, dtype=int)
    previous, current = breaches[:-1], breaches[1:]
    counts = {
        (before, after): int(((previous == before) & (current == after)).sum())
        for before in (0, 1)
        for after in (0, 1)
    }
    stay = counts[(0, 0)] + counts[(0, 1)]
    leave = counts[(1, 0)] + counts[(1, 1)]
    rate_after_calm = counts[(0, 1)] / stay if stay else 0.0
    rate_after_breach = counts[(1, 1)] / leave if leave else 0.0
    overall = (counts[(0, 1)] + counts[(1, 1)]) / max(stay + leave, 1)

    def log_likelihood(rate, failures, successes):
        total = 0.0
        if failures:
            total += failures * math.log(max(rate, 1e-300))
        if successes:
            total += successes * math.log(max(1 - rate, 1e-300))
        return total

    unrestricted = log_likelihood(rate_after_calm, counts[(0, 1)], counts[(0, 0)]) + log_likelihood(
        rate_after_breach, counts[(1, 1)], counts[(1, 0)]
    )
    restricted = log_likelihood(
        overall, counts[(0, 1)] + counts[(1, 1)], counts[(0, 0)] + counts[(1, 0)]
    )
    independence = max(0.0, -2 * (restricted - unrestricted))
    coverage = -2 * (
        log_likelihood(expected_rate, int(breaches.sum()), len(breaches) - int(breaches.sum()))
        - log_likelihood(breaches.mean(), int(breaches.sum()), len(breaches) - int(breaches.sum()))
    )
    return float(stats.chi2.sf(independence, 1)), float(
        stats.chi2.sf(max(coverage, 0) + independence, 2)
    )


def acerbi_szekely_test(losses, var, es, level=LEVEL, draws=2000, seed=0):
    """Acerbi–Székely Z₂ statistic and its simulated p-value (resampling the forecast tail).

    Under H₀ each day's loss beyond VaR has mean ES; Z₂ near 0, negative when ES is too small.
    """
    losses, var, es = (np.asarray(array, dtype=float) for array in (losses, var, es))
    usable = es > 0  # ES ≤ 0 (a forecast tail of gains) makes the ratio meaningless
    if usable.sum() < 10:
        return float("nan"), float("nan")
    losses, var, es = losses[usable], var[usable], es[usable]
    count = len(losses)
    statistic = float(np.sum(losses * (losses > var) / es) / (count * (1 - level)) - 1)
    generator = np.random.Generator(np.random.PCG64(seed))
    simulated = []
    for _ in range(draws):
        breaches = generator.random(count) < 1 - level
        tail = var + generator.exponential(np.maximum(es - var, 1e-9))
        simulated.append(np.sum(np.where(breaches, tail, 0.0) / es) / (count * (1 - level)) - 1)
    return statistic, float(np.mean(np.array(simulated) <= statistic))


def backtest_table(daily_pnl, days, periods, level=LEVEL):
    """For each estimator and period: breach rate and the three tests' p-values."""
    losses = -np.asarray(daily_pnl, dtype=float)
    rows = []
    for name, estimator in ESTIMATORS.items():
        var, es = point_in_time_forecasts(daily_pnl, estimator, level)
        for label, (first, last) in periods.items():
            selected = np.array([first <= day <= last for day in days]) & ~np.isnan(var)
            if selected.sum() < 50:
                continue
            breaches = (losses[selected] > var[selected]).astype(int)
            independence, coverage = christoffersen_significance(breaches, 1 - level)
            tail_statistic, tail_test_significance = acerbi_szekely_test(
                losses[selected], var[selected], es[selected], level
            )
            rows.append(
                {
                    "estimator": name,
                    "period": label,
                    "days": int(selected.sum()),
                    "breach_rate": float(breaches.mean()),
                    "kupiec": kupiec_significance(breaches, 1 - level),
                    "christoffersen_independence": independence,
                    "christoffersen_coverage": coverage,
                    "acerbi_szekely_test": tail_statistic,
                    "acerbi_szekely_significance": tail_test_significance,
                }
            )
    return rows
