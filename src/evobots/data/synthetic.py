"""Synthetic hub prices for tests: known truth, so search and statistics can be checked.

M4's planted-signal test needs data where the right answer is known: a rule the GP must
recover, and pure noise where it must find nothing (`docs/design_spec.md` §16, M4). This module makes
day × hour × hub arrays of DA and RT prices plus one synthetic weather input, seeded
(NumPy PCG64), so every call with the same arguments returns identical arrays.

**Models for the spread s = DA − RT** (DA itself is a mean-reverting daily level plus a
fixed daily shape; RT = DA − s):
- `"noise"`: s is Student-t noise with constant scale: nothing to find.
- `"garch"`: s has GARCH(1,1) volatility, so calm and wild days cluster (as in MISO).
- `"regime"`: a two-state Markov chain switches the scale between calm and stress.

**Planted rule** (optional): on hub-hours where the synthetic forecast high exceeds a
threshold and the hour ending is 14–19, RT is raised by `planted_premium_usd_per_mwh`, so a
DEC bid there earns that much on average. Everything else is unchanged.

Example:
    >>> market = synthetic_market(days=30, hubs=2, model="noise", seed=1)
    >>> market.day_ahead.shape
    (30, 24, 2)
    >>> bool((synthetic_market(days=30, hubs=2, model="noise", seed=1).real_time
    ...       == market.real_time).all())
    True
"""

import dataclasses

import numpy as np

HOURS_PER_DAY = 24
# Daily DA shape: higher in the afternoon, $/MWh above the daily level (illustrative).
DAILY_SHAPE_USD_PER_MWH = 8.0 * np.sin(np.linspace(-np.pi / 2, 3 * np.pi / 2, HOURS_PER_DAY))
# Mean-reverting DA level: long-run mean, daily reversion share, daily shock scale ($/MWh).
LEVEL_MEAN_USD_PER_MWH = 30.0
LEVEL_REVERSION_FRACTION = 0.1
LEVEL_SHOCK_USD_PER_MWH = 3.0
# Spread noise: Student-t degrees of freedom (heavy tails) and base scale ($/MWh).
SPREAD_DEGREES_OF_FREEDOM = 3
SPREAD_SCALE_USD_PER_MWH = 5.0
# GARCH(1,1) on the daily scale: ω, α, β with α + β < 1 (persistent, stationary).
GARCH_OMEGA = 0.05
GARCH_ALPHA = 0.10
GARCH_BETA = 0.85
# Regime switching: stress multiplies the scale; daily switch probabilities.
STRESS_SCALE_MULTIPLE = 4.0
CALM_TO_STRESS_PROBABILITY = 0.02
STRESS_TO_CALM_PROBABILITY = 0.10
# Synthetic forecast high: seasonal mean ± amplitude (°F) plus daily noise.
FORECAST_MEAN_DEGF = 60.0
FORECAST_AMPLITUDE_DEGF = 25.0
FORECAST_NOISE_DEGF = 6.0
# The planted rule's hours (hour ending 14–19, inclusive) and default threshold.
PLANTED_FIRST_HOUR_ENDING = 14
PLANTED_LAST_HOUR_ENDING = 19
PLANTED_THRESHOLD_DEGF = 85.0
MODELS = ("noise", "garch", "regime")


@dataclasses.dataclass(frozen=True)
class SyntheticMarket:
    """Synthetic prices and one input, all shaped [day, hour, hub] or [day, hub].

    Attributes:
        day_ahead: DA prices, $/MWh, shape (days, 24, hubs).
        real_time: RT prices, $/MWh, same shape.
        forecast_high_degf: synthetic forecast high for each day and hub, °F, (days, hubs).
        daily_scale_usd_per_mwh: the spread scale used each day, $/MWh, shape (days,).
        is_planted: True where the planted premium was added, shape (days, 24, hubs).
    """

    day_ahead: np.ndarray
    real_time: np.ndarray
    forecast_high_degf: np.ndarray
    daily_scale_usd_per_mwh: np.ndarray
    is_planted: np.ndarray


def daily_spread_scale(model, days, generator):
    """The spread scale for each day under one model, $/MWh."""
    if model == "noise":
        return np.full(days, SPREAD_SCALE_USD_PER_MWH)
    if model == "garch":
        variance = np.empty(days)
        variance[0] = GARCH_OMEGA / (1 - GARCH_ALPHA - GARCH_BETA)
        for day in range(1, days):
            shock = generator.standard_normal()
            variance[day] = GARCH_OMEGA + (GARCH_ALPHA * shock**2 + GARCH_BETA) * variance[day - 1]
        return SPREAD_SCALE_USD_PER_MWH * np.sqrt(variance / variance[0])
    if model == "regime":
        is_stress = np.zeros(days, dtype=bool)
        for day in range(1, days):
            switch_probability = (
                STRESS_TO_CALM_PROBABILITY if is_stress[day - 1] else CALM_TO_STRESS_PROBABILITY
            )
            is_stress[day] = is_stress[day - 1] ^ (generator.random() < switch_probability)
        return SPREAD_SCALE_USD_PER_MWH * np.where(is_stress, STRESS_SCALE_MULTIPLE, 1.0)
    raise ValueError(f"model must be one of {MODELS}, not {model!r}")


def synthetic_market(
    days,
    hubs,
    model="noise",
    seed=0,
    planted_premium_usd_per_mwh=0.0,
    planted_threshold_degf=PLANTED_THRESHOLD_DEGF,
):
    """Generate synthetic DA/RT prices and a forecast input.

    Args:
        days: number of days.
        hubs: number of hubs.
        model: "noise", "garch" or "regime" (module docstring).
        seed: the PCG64 seed; equal arguments give identical arrays.
        planted_premium_usd_per_mwh: RT − DA added where the planted rule holds (0 = none).
        planted_threshold_degf: the forecast high above which the rule holds.

    Returns:
        A SyntheticMarket.
    """
    generator = np.random.Generator(np.random.PCG64(seed))
    level = np.empty((days, hubs))
    level[0] = LEVEL_MEAN_USD_PER_MWH
    for day in range(1, days):
        level[day] = (
            level[day - 1]
            + LEVEL_REVERSION_FRACTION * (LEVEL_MEAN_USD_PER_MWH - level[day - 1])
            + LEVEL_SHOCK_USD_PER_MWH * generator.standard_normal(hubs)
        )
    day_ahead = level[:, None, :] + DAILY_SHAPE_USD_PER_MWH[None, :, None]
    scale = daily_spread_scale(model, days, generator)
    spread = scale[:, None, None] * generator.standard_t(
        SPREAD_DEGREES_OF_FREEDOM, size=(days, HOURS_PER_DAY, hubs)
    )
    season = np.sin(2 * np.pi * np.arange(days) / 365.25 - np.pi / 2)
    forecast_high = (
        FORECAST_MEAN_DEGF
        + FORECAST_AMPLITUDE_DEGF * season[:, None]
        + FORECAST_NOISE_DEGF * generator.standard_normal((days, hubs))
    )
    hour_ending = np.arange(1, HOURS_PER_DAY + 1)
    is_planted_hour = (hour_ending >= PLANTED_FIRST_HOUR_ENDING) & (
        hour_ending <= PLANTED_LAST_HOUR_ENDING
    )
    is_planted = (
        (forecast_high[:, None, :] > planted_threshold_degf)
        & is_planted_hour[None, :, None]
        & (planted_premium_usd_per_mwh != 0)
    )
    real_time = day_ahead - spread + planted_premium_usd_per_mwh * is_planted
    return SyntheticMarket(
        day_ahead=day_ahead,
        real_time=real_time,
        forecast_high_degf=forecast_high,
        daily_scale_usd_per_mwh=scale,
        is_planted=is_planted,
    )
