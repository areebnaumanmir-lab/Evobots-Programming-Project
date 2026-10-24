"""Storm sensitivity: fitness with and without named storm days (reporting only, never selection).

Rule (capital_sizing.md §7b): keep the bot's own daily returns (P&L ÷ previous equity), set the
returns on storm days to zero, and recompound, stopping at the ruin floor if one is given.
F = ln(W_T / W_0) − rf·T. This measures "the same bot, flat on storm days", not "a world
without storms".

Reproduced exactly in round 21: always-INC at $1.5M gives F 0.540 → 0.684 without storms
(Uri +0.069, Elliott −0.212); always-DEC −0.411, ruined 2022-01-21 (tests/test_storms.py).
"""

import math

import numpy as np

# Storm windows (inclusive operating days), chosen in round 16 from the data: every day within
# ±7 days of the event whose worse-direction full-size loss exceeded its full-sample p99.
DEFAULT_STORM_WINDOWS = {
    "Uri": ("2021-02-15", "2021-02-19"),
    "Elliott": ("2022-12-23", "2022-12-25"),
}
DAYS_PER_YEAR = 365.25


def storm_days(days, storm_windows):
    """Set of ISO dates in `days` that fall inside any of the windows."""
    return {
        day
        for day in days
        for first_day, last_day in storm_windows.values()
        if first_day <= day <= last_day
    }


def compounded_fitness(
    daily_returns,
    days,
    starting_capital_usd,
    skipped_days,
    ruin_floor_usd=None,
    risk_free_rate_annual=0.0,
):
    """F = ln(W_T/W_0) − rf·T after recompounding, with skipped days set flat.

    Args:
        daily_returns: P&L ÷ previous equity, per day.
        days: ISO dates matching daily_returns.
        starting_capital_usd: W_0, USD.
        skipped_days: dates whose return is set to zero.
        ruin_floor_usd: stop the first day equity is at or below it; None = no floor.
        risk_free_rate_annual: rf, per year (continuously compounded).

    Returns:
        (fitness, ruined_on): the fitness and the ruin date or None.

    Maths: docs/maths.md §1.6.

    Example:
        >>> round(compounded_fitness([-0.1], ["2021-02-15"], 1.0, set())[0], 4)
        -0.1054
    """
    equity_usd = float(starting_capital_usd)
    ruined_on = None
    days_counted = 0
    for day, daily_return in zip(days, daily_returns):
        days_counted += 1
        equity_usd *= 1.0 + (0.0 if day in skipped_days else daily_return)
        if ruin_floor_usd is not None and equity_usd <= ruin_floor_usd:
            ruined_on = day
            break
    years = days_counted / DAYS_PER_YEAR
    fitness = math.log(equity_usd / starting_capital_usd) - risk_free_rate_annual * years
    return fitness, ruined_on


def fitness_with_and_without_storms(
    daily_pnl_usd,
    days,
    starting_capital_usd,
    storm_windows=None,
    ruin_floor_usd=None,
    risk_free_rate_annual=0.0,
):
    """Fitness with all days, without all storms, and each storm's contribution.

    Args:
        daily_pnl_usd: the bot's daily P&L, USD (not modified).
        days: ISO dates, one per P&L value.
        starting_capital_usd: starting equity, USD.
        storm_windows: {name: (first ISO date, last ISO date)}; default DEFAULT_STORM_WINDOWS.
        ruin_floor_usd: optional floor; None = none.
        risk_free_rate_annual: rf per year.

    Returns:
        dict with "fitness_all_days", "fitness_without_storms", "ruined_on" and
        "contribution_by_storm" ({name: F(all) − F(without that storm)}).
    """
    windows = DEFAULT_STORM_WINDOWS if storm_windows is None else storm_windows
    daily_pnl = np.asarray(daily_pnl_usd, dtype=float)
    equity_before_day = starting_capital_usd + np.concatenate([[0.0], np.cumsum(daily_pnl)[:-1]])
    daily_returns = daily_pnl / equity_before_day
    arguments = (daily_returns, days, starting_capital_usd)
    options = {"ruin_floor_usd": ruin_floor_usd, "risk_free_rate_annual": risk_free_rate_annual}
    fitness_all_days, ruined_on = compounded_fitness(*arguments, set(), **options)
    fitness_without_storms, _ = compounded_fitness(*arguments, storm_days(days, windows), **options)
    contribution_by_storm = {
        name: fitness_all_days
        - compounded_fitness(*arguments, storm_days(days, {name: window}), **options)[0]
        for name, window in windows.items()
    }
    return {
        "fitness_all_days": fitness_all_days,
        "fitness_without_storms": fitness_without_storms,
        "ruined_on": ruined_on,
        "contribution_by_storm": contribution_by_storm,
    }
