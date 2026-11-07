"""L4 and O6: detecting that an edge has gone (`docs/design_spec.md` §10.1, §20.9).

**Page's CUSUM** on standardised monthly excess returns z_m (return minus the hurdle,
divided by its standard deviation): S_0 = 0, S_m = max(0, S_{m−1} + k − z_m); signal when
S_m > h. The reference value k is half the shift (in standard deviations) worth detecting;
the decision interval h sets how often a trader whose edge is intact is retired by mistake.

**Average run length (ARL)**, simulated and by Siegmund's approximation (Siegmund 1985,
*Sequential Analysis*) for z ~ N(μ, 1): with Δ = k − μ, the mean of the increments k − z,
and b = h + 1.166:
    ARL(Δ) ≈ (exp(−2Δb) + 2Δb − 1) / (2Δ²),  and b² for Δ = 0.

**Shiryaev–Roberts** (Roberts 1966): R_m = (1 + R_{m−1}) · Λ_m with the likelihood ratio
Λ_m = exp(−δ·z_m + δ²/2) of "edge gone" (z ~ N(0, 1)) against "edge intact"
(z ~ N(δ, 1)); signal when R_m > A.

**Bayesian online change-point detection** (Adams & MacKay 2007, arXiv 0710.3742), Gaussian
observations with known variance and a normal prior on each segment's mean: the posterior
over the current run length, updated each month; the probability that a change happened
within the last few months is the signal.

Example:
    >>> import numpy as np
    >>> cusum_signal_month(np.array([0.5, 0.4, -2.0, -2.0, -2.0, -2.0]), 0.5, 4.0)
    3
    >>> round(siegmund_average_run_length(0.5, 0.5, 4.0), 1)  # Δ = 0
    26.7
"""

import math

import numpy as np

SIEGMUND_CORRECTION = 1.166


def cusum_path(standardised_excess, reference, threshold=None):
    """CUSUM statistic S_m for each month (no reset after a signal)."""
    statistic = 0.0
    path = np.empty(len(standardised_excess))
    for month, value in enumerate(standardised_excess):
        statistic = max(0.0, statistic + reference - value)
        path[month] = statistic
    return path


def cusum_signal_month(excess_returns, reference, threshold, scale=None):
    """First month whose CUSUM exceeds the threshold, or None.

    Args:
        excess_returns: monthly returns minus the hurdle (fractions).
        reference: k, in standard deviations.
        threshold: h, in standard deviations.
        scale: the returns' standard deviation; estimated from the first 12 months (or all
            months if fewer) when None.
    """
    excess_returns = np.asarray(excess_returns, dtype=float)
    if len(excess_returns) == 0:
        return None
    if scale is None:
        sample = excess_returns[:12] if len(excess_returns) >= 12 else excess_returns
        scale = float(np.std(sample, ddof=1)) if len(sample) > 1 else 0.0
    if not scale > 0:
        scale = max(abs(float(excess_returns.mean())), 1e-6)
    path = cusum_path(excess_returns / scale, reference)
    signals = np.flatnonzero(path > threshold)
    return int(signals[0]) if len(signals) else None


def siegmund_average_run_length(mean, reference, threshold):
    """Siegmund's approximation of the CUSUM's ARL when z ~ N(mean, 1)."""
    drift = reference - mean  # mean of the increments k − z
    boundary = threshold + SIEGMUND_CORRECTION
    if abs(drift) < 1e-9:
        return boundary**2
    return (math.exp(-2 * drift * boundary) + 2 * drift * boundary - 1) / (2 * drift**2)


def simulated_average_run_length(mean, reference, threshold, runs=4000, seed=0, max_months=100_000):
    """Monte Carlo ARL (mean months to the first signal) when z ~ N(mean, 1)."""
    generator = np.random.Generator(np.random.PCG64(seed))
    lengths = np.empty(runs)
    for run in range(runs):
        statistic = 0.0
        for month in range(1, max_months + 1):
            statistic = max(0.0, statistic + reference - (mean + generator.standard_normal()))
            if statistic > threshold:
                break
        lengths[run] = month
    return float(lengths.mean()), float(lengths.std(ddof=1) / math.sqrt(runs))


def threshold_for_average_run_length(target_months, edge_mean, reference):
    """The h giving a Siegmund ARL of target_months when the edge is intact (z ~ N(edge, 1))."""
    low, high = 0.0, 50.0
    for _ in range(100):
        middle = (low + high) / 2
        if siegmund_average_run_length(edge_mean, reference, middle) < target_months:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def shiryaev_roberts_signal_month(standardised_excess, shift, threshold):
    """First month the Shiryaev–Roberts statistic exceeds the threshold, or None.

    Pre-change z ~ N(shift, 1) (the edge), post-change z ~ N(0, 1) (edge gone); the
    likelihood ratio of one month is exp(−shift·z + shift²/2).
    """
    statistic = 0.0
    for month, value in enumerate(standardised_excess):
        ratio = math.exp(-shift * value + shift**2 / 2)
        statistic = (1 + statistic) * ratio
        if statistic > threshold:
            return month
    return None


def bocpd_change_probabilities(
    observations, hazard_rate, noise_variance, prior_mean, prior_variance
):
    """Posterior run-length distributions (Adams & MacKay 2007), Gaussian, known variance.

    Args:
        observations: the monthly values.
        hazard_rate: constant probability per month that a change happens.
        noise_variance: variance of an observation around its segment's mean.
        prior_mean: the normal prior's mean for a new segment's mean.
        prior_variance: the normal prior's variance.

    Returns:
        A (months + 1, months + 1) array: row t is P(run length = r | x_1..x_t).
    """
    count = len(observations)
    run_length = np.zeros((count + 1, count + 1))
    run_length[0, 0] = 1.0
    means = np.array([prior_mean])
    variances = np.array([prior_variance])
    for time, value in enumerate(observations, start=1):
        predictive_variance = variances + noise_variance
        predictive = np.exp(-((value - means) ** 2) / (2 * predictive_variance)) / np.sqrt(
            2 * math.pi * predictive_variance
        )
        previous = run_length[time - 1, :time]
        growth = previous * predictive * (1 - hazard_rate)
        change = float(np.sum(previous * predictive * hazard_rate))
        run_length[time, 1 : time + 1] = growth
        run_length[time, 0] = change
        run_length[time, : time + 1] /= run_length[time, : time + 1].sum()
        posterior_variance = 1 / (1 / variances + 1 / noise_variance)
        posterior_mean = posterior_variance * (means / variances + value / noise_variance)
        means = np.concatenate([[prior_mean], posterior_mean])
        variances = np.concatenate([[prior_variance], posterior_variance])
    return run_length


def recent_change_probability(run_length, within_months=3):
    """For each month, P(the current run is shorter than within_months)."""
    return run_length[1:, :within_months].sum(axis=1)


def average_run_length_table(edge_means, references, target_months=120):
    """Rows (edge mean, k, h for the target ARL, Siegmund ARL when the edge is gone).

    For each edge size and reference value, h is set so that a trader whose edge is intact is
    retired by mistake once per `target_months` on average; the detection delay is the ARL
    once the edge has gone (z ~ N(0, 1)).
    """
    rows = []
    for edge in edge_means:
        for reference in references:
            threshold = threshold_for_average_run_length(target_months, edge, reference)
            delay = siegmund_average_run_length(0.0, reference, threshold)
            rows.append((edge, reference, threshold, delay))
    return rows
