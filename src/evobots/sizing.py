"""Point-in-time position sizing: the trailing 1-in-100-day loss and the position scale.

Rules (capital_sizing.md §4–4b; decisions log rounds 14–15):
  * bids for operating day D are placed on D−1, and final real-time prices post about five
    days late, so the newest operating day with known P&L is D−6 (NEWEST_VISIBLE_LAG_DAYS);
  * the window is the 365 most recent visible days, expanding from a 90-day warm-up; with
    fewer than 90 visible days the estimate is None and the bot does not trade;
  * the p99 is taken on the worse of the two benchmark directions (always-INC, always-DEC).

Day series here are numpy arrays indexed by consecutive calendar days with no gaps (the hub
archive has none, docs/data_coverage.md). Index i is operating day i.

Reproduced exactly in round 21 against docs/data/trailing_p99_daily_loss.csv and
docs/data/trailing_breach_rate_by_year_2015_2025.csv (tests/test_sizing.py).
"""

import numpy as np

# Final RT for day D posts about D+5, so on decision day D−1 the newest known day is D−6.
NEWEST_VISIBLE_LAG_DAYS = 6
# Trailing window length, days (capital_sizing.md §4b).
TRAILING_WINDOW_DAYS = 365
# Fewer visible days than this: no estimate, no trading.
WARM_UP_DAYS = 90
# The quantile the sizing rule targets: the 1-in-100 day.
LOSS_PERCENTILE = 99.0


def trailing_p99_daily_loss(full_size_daily_pnl_usd, operating_day_index):
    """1-in-100-day loss visible when bidding for one operating day, worse direction, USD.

    Args:
        full_size_daily_pnl_usd: daily P&L of the always-INC benchmark at full size, USD
            (always-DEC is its negative), one value per consecutive calendar day.
        operating_day_index: index of operating day D in that array.

    Returns:
        max(p99 of INC losses, p99 of DEC losses) over the visible window, or None during
        the warm-up.

    Maths: docs/maths.md §1.4. Decision: decisions log round 15.

    Example:
        >>> pnl = np.arange(200.0) - 100.0
        >>> trailing_p99_daily_loss(pnl, 50) is None
        True
        >>> round(trailing_p99_daily_loss(pnl, 199), 2)
        98.07
    """
    newest_visible_index = operating_day_index - NEWEST_VISIBLE_LAG_DAYS
    if newest_visible_index < 0:
        return None
    first_visible_index = max(0, newest_visible_index - TRAILING_WINDOW_DAYS + 1)
    window = np.asarray(full_size_daily_pnl_usd[first_visible_index : newest_visible_index + 1])
    if len(window) < WARM_UP_DAYS:
        return None
    return float(
        max(np.percentile(-window, LOSS_PERCENTILE), np.percentile(window, LOSS_PERCENTILE))
    )


def trailing_p99_series(full_size_daily_pnl_usd):
    """trailing_p99_daily_loss for every operating day; None during the warm-up."""
    return [
        trailing_p99_daily_loss(full_size_daily_pnl_usd, index)
        for index in range(len(full_size_daily_pnl_usd))
    ]


def position_scale(equity_usd, p99_daily_loss_usd, daily_risk_budget_fraction):
    """Share of full size to bid: min(1, budget × equity / p99 loss); 0 with no estimate.

    Args:
        equity_usd: equity at the end of the previous day, USD.
        p99_daily_loss_usd: the trailing 1-in-100-day full-size loss, USD, or None.
        daily_risk_budget_fraction: share of equity a 1-in-100 day may cost.

    Returns:
        A fraction in [0, 1].

    Maths: docs/maths.md §1.1.

    Example:
        >>> position_scale(1_500_000, 27_897, 0.02)
        1.0
        >>> round(position_scale(250_000, 27_897, 0.02), 3)
        0.179
        >>> position_scale(1_500_000, None, 0.02)
        0.0
    """
    if p99_daily_loss_usd is None or equity_usd <= 0:
        return 0.0
    return min(1.0, daily_risk_budget_fraction * equity_usd / p99_daily_loss_usd)


def simulate_benchmark_equity(
    full_size_daily_pnl_usd, starting_capital_usd, daily_risk_budget_fraction, p99_series=None
):
    """Equity path of a benchmark sized point-in-time from its trailing p99.

    Args:
        full_size_daily_pnl_usd: the benchmark's daily P&L at full size, USD.
        starting_capital_usd: starting equity, USD.
        daily_risk_budget_fraction: the sizing rule's budget.
        p99_series: trailing p99 per day (computed if None). Pass the always-INC series'
            estimates for both directions: the estimate is two-sided already.

    Returns:
        (equity_before_day, daily_pnl): numpy arrays; equity_before_day[i] is the equity the
        day-i bids were sized on, daily_pnl[i] the scaled P&L of day i.
    """
    if p99_series is None:
        p99_series = trailing_p99_series(full_size_daily_pnl_usd)
    equity_usd = float(starting_capital_usd)
    equity_before_day = np.empty(len(full_size_daily_pnl_usd))
    daily_pnl = np.empty(len(full_size_daily_pnl_usd))
    for index, full_size_pnl in enumerate(full_size_daily_pnl_usd):
        equity_before_day[index] = equity_usd
        scale = position_scale(equity_usd, p99_series[index], daily_risk_budget_fraction)
        daily_pnl[index] = scale * full_size_pnl
        equity_usd += daily_pnl[index]
    return equity_before_day, daily_pnl


def worst_rolling_loss_fraction(daily_pnl, equity_before_day, window_days=20):
    """Largest loss over any run of window_days days, as a share of equity at the run's start.

    Returns:
        (fraction, index of the run's last day).

    Maths: docs/maths.md §1.5.
    """
    losses = -np.convolve(daily_pnl, np.ones(window_days), mode="valid")
    fractions = losses / equity_before_day[: len(losses)]
    worst_start = int(np.argmax(fractions))
    return float(fractions[worst_start]), worst_start + window_days - 1
