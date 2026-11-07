"""O1: scenarios for the hub spread s = DA − RT, from visible data only (§20.4).

A scenario is one possible day: a (24, hubs) matrix of DA − RT spreads (and, for the battery
study, DA and RT levels). Every generator is fitted on days whose final RT price was public at
the decision (operating day D's decision sees spreads up to D − 6) and is seeded.

1. **Stationary block bootstrap** of whole historical days (model-free baseline): the block
   length comes from Politis–White on the daily mean spread.
2. **Regime switching:** a two-state hidden Markov chain (calm, stress) with Student-t
   emissions (4 degrees of freedom) on the daily mean spread, fitted by EM (the t emission
   as a scale mixture of normals). A scenario draws tomorrow's regime from the filtered
   state, a daily mean from that regime, and the hour-and-hub pattern from a historical day
   of the same regime.
3. **Mean-reverting jumps** for price levels (the battery study): the daily mean DA price as
   an Ornstein–Uhlenbeck process plus compound-Poisson jumps, fitted by least squares on
   the visible history, with each hour's average shape added. Levels, not logs, because MISO
   prices go negative.
4. **Analogue days:** the K visible days most similar to tomorrow by the visible features
   (forecast high, gas price, month), their spread matrices as scenarios.

**Validation** (`validation_table`): simulated against real spreads on the mean, standard
deviation, 1st and 99th percentiles, excess kurtosis, lag-1 autocorrelation of the daily mean,
cross-hub correlation and the share of spike days, plus the CRPS and pinball loss of each
generator's forecast of the next visible day's mean spread (rolling origin).

Example:
    >>> import numpy as np
    >>> from evobots.simulate.market import synthetic_hub_market
    >>> market = synthetic_hub_market(days=600, seed=2)
    >>> spreads = market.day_ahead - market.real_time
    >>> scenarios = bootstrap_scenarios(spreads, decision_index=500, count=20, seed=1)
    >>> scenarios.shape
    (20, 24, 8)
"""

import dataclasses
import math

import numpy as np
from scipy import stats

from evobots.assess.statistics import politis_white_block_length

VISIBLE_LAG_DAYS = 6
STUDENT_DEGREES_OF_FREEDOM = 4.0
EM_ITERATIONS = 60
HISTORY_DAYS = 730
SPIKE_THRESHOLD_USD_PER_MWH = 50.0


def visible_history(spreads, decision_index, history_days=HISTORY_DAYS):
    """Spread days usable for operating day `decision_index`: up to D − 6, complete ones only."""
    end = max(0, decision_index - VISIBLE_LAG_DAYS + 1)
    start = max(0, end - history_days)
    window = spreads[start:end]
    complete = ~np.isnan(window).any(axis=(1, 2))
    return window[complete]


def bootstrap_scenarios(spreads, decision_index, count, seed=0):
    """Stationary block bootstrap: count days drawn as the continuation of random blocks."""
    history = visible_history(spreads, decision_index)
    if len(history) == 0:
        return np.zeros((count, *spreads.shape[1:]))
    generator = np.random.Generator(np.random.PCG64(seed))
    block = politis_white_block_length(history.mean(axis=(1, 2)))
    restart = 1 / max(block, 1.0)
    picks = []
    position = int(generator.integers(len(history)))
    for _ in range(count):
        position = (
            int(generator.integers(len(history)))
            if generator.random() < restart
            else (position + 1) % len(history)
        )
        picks.append(position)
    return history[np.array(picks)]


@dataclasses.dataclass(frozen=True)
class RegimeModel:
    """A fitted two-state Student-t hidden Markov model of the daily mean spread."""

    means: np.ndarray  # (2,)
    scales: np.ndarray  # (2,)
    transition: np.ndarray  # (2, 2), rows sum to 1
    last_filtered: np.ndarray  # (2,) P(state | data) on the last visible day
    states: np.ndarray  # most likely state of each visible day (for pattern sampling)

    def stress_state(self):
        """Index of the high-scale state."""
        return int(np.argmax(self.scales))


def student_density(values, mean, scale, degrees=STUDENT_DEGREES_OF_FREEDOM):
    """Student-t density with location and scale."""
    return stats.t.pdf((values - mean) / scale, degrees) / scale


def fit_regime_model(daily_means, iterations=EM_ITERATIONS):
    """EM for a two-state hidden Markov model with Student-t emissions (fixed degrees)."""
    values = np.asarray(daily_means, dtype=float)
    count = len(values)
    deviation = values.std() or 1.0
    means = np.array([values.mean(), values.mean()])
    scales = np.array([0.5 * deviation, 2.0 * deviation])
    transition = np.array([[0.95, 0.05], [0.10, 0.90]])
    start = np.array([0.5, 0.5])
    degrees = STUDENT_DEGREES_OF_FREEDOM
    for _ in range(iterations):
        densities = (
            np.column_stack(
                [student_density(values, means[state], scales[state]) for state in range(2)]
            )
            + 1e-300
        )
        forward = np.zeros((count, 2))
        norms = np.zeros(count)
        forward[0] = start * densities[0]
        norms[0] = forward[0].sum()
        forward[0] /= norms[0]
        for day in range(1, count):
            forward[day] = (forward[day - 1] @ transition) * densities[day]
            norms[day] = forward[day].sum()
            forward[day] /= norms[day]
        backward = np.ones((count, 2))
        for day in range(count - 2, -1, -1):
            backward[day] = transition @ (densities[day + 1] * backward[day + 1])
            backward[day] /= backward[day].sum()
        posterior = forward * backward
        posterior /= posterior.sum(axis=1, keepdims=True)
        pair = np.zeros((2, 2))
        for day in range(count - 1):
            joint = (
                forward[day][:, None]
                * transition
                * (densities[day + 1] * backward[day + 1])[None, :]
            )
            pair += joint / joint.sum()
        transition = pair / pair.sum(axis=1, keepdims=True)
        start = posterior[0]
        for state in range(2):
            residual = (values - means[state]) / scales[state]
            weight = posterior[:, state] * (degrees + 1) / (degrees + residual**2)
            means[state] = (weight * values).sum() / weight.sum()
            scales[state] = math.sqrt(
                (weight * (values - means[state]) ** 2).sum() / posterior[:, state].sum()
            )
            scales[state] = max(scales[state], 1e-6)
    order = np.argsort(scales)
    return RegimeModel(
        means=means[order],
        scales=scales[order],
        transition=transition[np.ix_(order, order)],
        last_filtered=forward[-1][order],
        states=np.argsort(order)[np.argmax(posterior, axis=1)],
    )


def regime_scenarios(spreads, decision_index, count, seed=0, model=None):
    """Regime-switching scenarios (see the module docstring)."""
    history = visible_history(spreads, decision_index)
    if len(history) < 30:
        return bootstrap_scenarios(spreads, decision_index, count, seed)
    daily_means = history.mean(axis=(1, 2))
    model = model or fit_regime_model(daily_means)
    generator = np.random.Generator(np.random.PCG64(seed))
    # The decision is VISIBLE_LAG_DAYS after the last visible day: step the chain forward.
    probabilities = model.last_filtered @ np.linalg.matrix_power(model.transition, VISIBLE_LAG_DAYS)
    scenarios = np.empty((count, *history.shape[1:]))
    for draw in range(count):
        state = int(generator.random() < probabilities[1])
        mean = model.means[state] + model.scales[state] * generator.standard_t(
            STUDENT_DEGREES_OF_FREEDOM
        )
        same = np.flatnonzero(model.states == state)
        pattern_day = (
            history[same[int(generator.integers(len(same)))]]
            if len(same)
            else history[int(generator.integers(len(history)))]
        )
        scenarios[draw] = pattern_day - pattern_day.mean() + mean
    return scenarios


@dataclasses.dataclass(frozen=True)
class JumpModel:
    """Daily mean DA price: OU with compound-Poisson jumps, plus an hourly shape."""

    long_run_mean: float
    reversion: float
    volatility: float
    jump_probability: float
    jump_mean: float
    jump_scale: float
    hourly_shape: np.ndarray


def fit_jump_model(daily_mean_prices, hourly_prices, jump_threshold_deviations=3.0):
    """Least-squares OU fit; changes beyond the threshold count as jumps."""
    values = np.asarray(daily_mean_prices, dtype=float)
    previous, current = values[:-1], values[1:]
    slope, intercept = np.polyfit(previous, current, 1)
    reversion = float(np.clip(1 - slope, 1e-3, 1.0))
    long_run = float(intercept / reversion)
    residuals = current - (intercept + slope * previous)
    deviation = residuals.std() or 1.0
    is_jump = np.abs(residuals) > jump_threshold_deviations * deviation
    calm = residuals[~is_jump]
    jumps = residuals[is_jump]
    return JumpModel(
        long_run_mean=long_run,
        reversion=reversion,
        volatility=float(calm.std() if len(calm) > 1 else deviation),
        jump_probability=float(is_jump.mean()),
        jump_mean=float(jumps.mean()) if len(jumps) else 0.0,
        jump_scale=float(jumps.std()) if len(jumps) > 1 else deviation,
        hourly_shape=np.nanmean(
            hourly_prices - np.nanmean(hourly_prices, axis=1, keepdims=True), axis=0
        ),
    )


def jump_price_paths(model, start_level, days, count, seed=0):
    """Count paths of hourly prices (count, days, 24) from the jump model."""
    generator = np.random.Generator(np.random.PCG64(seed))
    levels = np.empty((count, days))
    level = np.full(count, float(start_level))
    for day in range(days):
        jump = (generator.random(count) < model.jump_probability) * generator.normal(
            model.jump_mean, model.jump_scale, count
        )
        level = (
            level
            + model.reversion * (model.long_run_mean - level)
            + model.volatility * generator.standard_normal(count)
            + jump
        )
        levels[:, day] = level
    return levels[:, :, None] + model.hourly_shape[None, None, :]


def analogue_scenarios(spreads, features_by_day, decision_index, count):
    """The `count` visible days nearest to tomorrow in standardised visible features.

    Args:
        spreads: (days, 24, hubs) DA − RT.
        features_by_day: (days, f) visible features per operating day (NaN allowed).
        decision_index: the operating day.
        count: K.
    """
    end = max(0, decision_index - VISIBLE_LAG_DAYS + 1)
    candidates = np.arange(max(0, end - HISTORY_DAYS), end)
    candidates = candidates[~np.isnan(spreads[candidates]).any(axis=(1, 2))]
    if len(candidates) == 0:
        return np.zeros((count, *spreads.shape[1:]))
    target = features_by_day[decision_index]
    pool = features_by_day[candidates]
    scale = np.nanstd(pool, axis=0)
    scale = np.where(scale > 0, scale, 1.0)
    distance = np.nansum(((pool - target) / scale) ** 2, axis=1)
    nearest = candidates[np.argsort(distance, kind="stable")[:count]]
    return spreads[nearest]


def crps_of_ensemble(ensemble, observation):
    """Continuous ranked probability score of an ensemble forecast (lower is better)."""
    ensemble = np.asarray(ensemble, dtype=float)
    first = np.mean(np.abs(ensemble - observation))
    second = np.mean(np.abs(ensemble[:, None] - ensemble[None, :])) / 2
    return float(first - second)


def pinball_loss(ensemble, observation, quantiles=(0.1, 0.5, 0.9)):
    """Mean pinball loss of the ensemble's quantiles."""
    losses = []
    for level in quantiles:
        forecast = np.quantile(ensemble, level)
        difference = observation - forecast
        losses.append(max(level * difference, (level - 1) * difference))
    return float(np.mean(losses))


def summary_statistics(days_matrix):
    """The moments the validation compares, for (days, 24, hubs) spreads."""
    flat = days_matrix.reshape(len(days_matrix), -1)
    values = flat.ravel()
    daily = flat.mean(axis=1)
    hub_daily = days_matrix.mean(axis=1)
    correlation = np.corrcoef(hub_daily, rowvar=False)
    off_diagonal = correlation[~np.eye(len(correlation), dtype=bool)]
    return {
        "mean": float(values.mean()),
        "standard_deviation": float(values.std()),
        "p1": float(np.percentile(values, 1)),
        "p99": float(np.percentile(values, 99)),
        "excess_kurtosis": float(stats.kurtosis(values)),
        "daily_mean_autocorrelation": float(np.corrcoef(daily[:-1], daily[1:])[0, 1])
        if len(daily) > 2
        else float("nan"),
        "cross_hub_correlation": float(np.nanmean(off_diagonal))
        if off_diagonal.size
        else float("nan"),
        "spike_day_share": float((np.abs(flat) > SPIKE_THRESHOLD_USD_PER_MWH).any(axis=1).mean()),
    }


def validation_table(spreads, features_by_day, test_indices, count=50, seed=0):
    """Rolling-origin validation of each generator against the realised days.

    Returns {generator: {"crps": …, "pinball": …, **summary statistics of its draws}} and
    {"real": summary statistics of the realised test days}.
    """
    generators = {
        "bootstrap": lambda index, draw_seed: bootstrap_scenarios(spreads, index, count, draw_seed),
        "regime": lambda index, draw_seed: regime_scenarios(spreads, index, count, draw_seed),
        "analogue": lambda index, draw_seed: analogue_scenarios(
            spreads, features_by_day, index, count
        ),
    }
    table = {}
    realised = spreads[test_indices]
    for name, generate in generators.items():
        crps, pinball, draws = [], [], []
        for offset, index in enumerate(test_indices):
            scenarios = generate(index, seed + offset)
            observation = float(np.nanmean(spreads[index]))
            ensemble = scenarios.mean(axis=(1, 2))
            crps.append(crps_of_ensemble(ensemble, observation))
            pinball.append(pinball_loss(ensemble, observation))
            draws.append(scenarios[0])
        table[name] = {
            "crps": float(np.mean(crps)),
            "pinball": float(np.mean(pinball)),
            **summary_statistics(np.array(draws)),
        }
    table["real"] = summary_statistics(realised[~np.isnan(realised).any(axis=(1, 2))])
    return table
