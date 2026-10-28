"""Settle a trader on history: bids, clearing, P&L, sizing, equity and death.

For each operating day, hour and hub the genome gives a side, a limit price and a size
(`evobots.bots.genome`). The rules (`CLAUDE.md` §6.1, §10, §13):
- **Clearing:** a DEC clears when DA ≤ its limit, an INC when DA ≥ its limit.
- **P&L per cleared MW:** DEC earns RT − DA, INC earns DA − RT, minus costs.
- **Costs** ($/MWh cleared): admin fee $0.09 (Schedules 17 + 24, search-quoted, estimate)
  plus RSG $0.11 (the market monitor's 2024 real-time average, estimate), times a cost
  multiplier (2 = the doubled-cost stress test). Labelled estimates until the Rates
  Factors file arrives (round 28).
- **Sizing:** the trader bids `scale × size_fraction × hub cap`, where
  scale = min(1, budget × equity / its own trailing 1-in-100-day full-size loss), using
  losses visible at the decision (days D−6 and earlier, 365 days, 90-day warm-up).
- **Death:** out of money, when equity can no longer cover MISO's collateral for the
  smallest bid (0.1 MW × $12 MPD × 2 days = $2.40; §10.1).
- **Fitness:** F = ln(W_T / W_0) − r_f × years − 0.01 × rule count (§10.2), with r_f the
  mean 3-month T-bill yield over the window (FRED DTB3) when available, else 0.

Example:
    >>> from evobots.bots.genome import FOUNDERS
    >>> from evobots.simulate.market import synthetic_hub_market, point_in_time_features
    >>> market = synthetic_hub_market(days=800, seed=2)
    >>> features = point_in_time_features(market)
    >>> result = evaluate(FOUNDERS["always_inc"], market, features, 400, 800)
    >>> result.is_alive, round(result.net_direction, 2)
    (True, -1.0)
"""

import dataclasses
import math

import numpy as np

from evobots.config.capital import MINIMUM_MPD_USD_PER_MWH, CapitalSettings

ADMIN_FEE_USD_PER_MWH = 0.09  # Schedules 17 + 24, October 2026 (search quotes; estimate)
RSG_USD_PER_MWH = 0.11  # 2024 real-time RSG average, IMM report (estimate)
SMALLEST_BID_MW = 0.1
EXPOSURE_WINDOW_DAYS = 2
OUT_OF_MONEY_EQUITY_USD = SMALLEST_BID_MW * MINIMUM_MPD_USD_PER_MWH * EXPOSURE_WINDOW_DAYS
NEWEST_VISIBLE_LAG_DAYS = 6
TRAILING_WINDOW_DAYS = 365
WARM_UP_DAYS = 90
# When a trader has no visible losses yet, its loss estimate is at least this much, so a
# trader that never lost can't size itself infinitely (assumption, preview).
MINIMUM_LOSS_ESTIMATE_USD = 1_000.0
PARSIMONY_PER_RULE = 0.01
HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365.25


@dataclasses.dataclass(frozen=True)
class EvaluationResult:
    """One trader's career over one window.

    Attributes:
        fitness: F (log-growth minus risk-free minus parsimony).
        final_equity_usd: equity at the end, USD.
        is_alive: False when it ran out of money.
        death_index: day index (in the window) of death, or None.
        equity_usd: end-of-day equity for each day of the window.
        daily_pnl_usd: P&L for each day of the window, USD.
        net_direction: (DEC MWh − INC MWh) / cleared MWh, −1 … +1 (0 when no trades).
        selectivity: share of hub-hours with a bid.
        cleared_mwh: total cleared MWh.
        max_drawdown_fraction: largest fall from a peak, as a share of the peak.
    """

    fitness: float
    final_equity_usd: float
    is_alive: bool
    death_index: int | None
    equity_usd: np.ndarray
    daily_pnl_usd: np.ndarray
    net_direction: float
    selectivity: float
    cleared_mwh: float
    max_drawdown_fraction: float


def bid_arrays(genome, features, start, end):
    """Side (+1 DEC, −1 INC, 0 none) and limit price for days start … end−1.

    Args:
        genome: a Genome.
        features: {name: array (days, 24, hubs)} from `point_in_time_features`.
        start: first day index.
        end: one past the last day index.

    Returns:
        (side, limit price $/MWh) arrays of shape (end − start, 24, hubs).
    """
    window = {name: values[start:end] for name, values in features.items()}
    shape = window["da_last"].shape
    is_bid = np.ones(shape, dtype=bool)
    for condition in genome.conditions:
        values = window[condition.feature]
        with np.errstate(invalid="ignore"):
            is_bid &= (
                values > condition.threshold if condition.is_above else values < condition.threshold
            )
    hour = window["hour"]
    is_bid &= (hour >= genome.first_hour) & (hour <= genome.last_hour)
    score = np.full(shape, genome.score_bias_usd_per_mwh)
    for feature, weight in genome.score_terms:
        score = score + weight * window[feature]
    with np.errstate(invalid="ignore"):
        side = np.where(score > genome.dec_threshold_usd_per_mwh, 1, 0) - np.where(
            score < -genome.inc_threshold_usd_per_mwh, 1, 0
        )
    side = np.where(is_bid & ~np.isnan(score) & ~np.isnan(window["da_last"]), side, 0)
    limit = window["da_last"] + side * genome.price_offset_usd_per_mwh
    return side.astype(np.int8), limit


def full_size_results(genome, market, features, caps_mw, start, end, cost_multiple):
    """Full-size daily P&L and cleared MWh by side, before sizing.

    Returns:
        (daily P&L USD, daily DEC MWh, daily INC MWh, bid hub-hours, all hub-hours).
    """
    side, limit = bid_arrays(genome, features, start, end)
    day_ahead = market.day_ahead[start:end]
    real_time = market.real_time[start:end]
    is_priced = ~np.isnan(day_ahead) & ~np.isnan(real_time)
    with np.errstate(invalid="ignore"):
        is_cleared = is_priced & (
            ((side == 1) & (day_ahead <= limit)) | ((side == -1) & (day_ahead >= limit))
        )
    megawatts = genome.size_fraction * caps_mw[None, None, :]
    cost = (ADMIN_FEE_USD_PER_MWH + RSG_USD_PER_MWH) * cost_multiple
    spread_gain = np.where(is_cleared, side * (real_time - day_ahead), 0.0)
    hourly_pnl = np.where(is_cleared, megawatts * (spread_gain - cost), 0.0)
    dec_mwh = np.where(is_cleared & (side == 1), megawatts, 0.0).sum(axis=(1, 2))
    inc_mwh = np.where(is_cleared & (side == -1), megawatts, 0.0).sum(axis=(1, 2))
    return (
        np.nan_to_num(hourly_pnl).sum(axis=(1, 2)),
        dec_mwh,
        inc_mwh,
        int((side != 0).sum()),
        int(is_priced.sum()),
    )


def trailing_loss_estimates(full_size_pnl, first_index):
    """Visible 1-in-100-day full-size loss for each day from first_index on (None in warm-up).

    For day index i the window is days max(0, i − 6 − 364) … i − 6 (§13), floored at
    MINIMUM_LOSS_ESTIMATE_USD. Full windows are computed together (vectorised).
    """
    losses = -np.asarray(full_size_pnl, dtype=float)
    estimates = [None] * (len(losses) - first_index)
    full_windows = np.lib.stride_tricks.sliding_window_view(losses, TRAILING_WINDOW_DAYS)
    full_percentiles = np.percentile(full_windows, 99, axis=1) if len(full_windows) else []
    for position, index in enumerate(range(first_index, len(losses))):
        newest = index - NEWEST_VISIBLE_LAG_DAYS
        oldest = newest - TRAILING_WINDOW_DAYS + 1
        if oldest >= 0:
            estimate = float(full_percentiles[oldest])
        elif newest + 1 >= WARM_UP_DAYS:
            estimate = float(np.percentile(losses[: newest + 1], 99))
        else:
            continue
        estimates[position] = max(estimate, MINIMUM_LOSS_ESTIMATE_USD)
    return estimates


def evaluate(
    genome,
    market,
    features,
    start,
    end,
    settings=None,
    cost_multiple=1.0,
    risk_free_annual_fraction=0.0,
):
    """Run one trader's career over days start … end−1 and score it.

    Sizing history reaches back up to 400 days before `start` (all visible before the
    window opens), so the trader can trade from the first day of its window.

    Args:
        genome: a Genome.
        market: a HubMarket.
        features: its point-in-time features.
        start: first day index of the window.
        end: one past the last day index.
        settings: CapitalSettings (defaults when None).
        cost_multiple: 1 for estimated costs, 2 for the doubled-cost stress test.
        risk_free_annual_fraction: r_f, e.g. 0.04.

    Returns:
        An EvaluationResult.
    """
    settings = settings or CapitalSettings()
    caps_by_hub = settings.hub_caps_mw()
    caps_mw = np.array([caps_by_hub.get(hub, 0.0) for hub in market.hubs])
    history_start = max(0, start - TRAILING_WINDOW_DAYS - NEWEST_VISIBLE_LAG_DAYS - 30)
    full_pnl, dec_mwh, inc_mwh, bid_count, priced_count = full_size_results(
        genome, market, features, caps_mw, history_start, end, cost_multiple
    )
    offset = start - history_start
    estimates = trailing_loss_estimates(full_pnl, offset)
    starting_equity = settings.starting_capital_usd
    equity = starting_equity
    equity_path, pnl_path = [], []
    death_index = None
    window_dec = window_inc = 0.0
    for day, estimate in enumerate(estimates):
        scale = 0.0
        if death_index is None and estimate is not None:
            scale = min(1.0, settings.daily_risk_budget_fraction * equity / estimate)
        pnl = scale * full_pnl[offset + day]
        equity += pnl
        window_dec += scale * dec_mwh[offset + day]
        window_inc += scale * inc_mwh[offset + day]
        if death_index is None and equity <= OUT_OF_MONEY_EQUITY_USD:
            death_index = day
        equity_path.append(equity)
        pnl_path.append(pnl)
    equity_array = np.array(equity_path)
    years = len(estimates) / DAYS_PER_YEAR
    log_growth = math.log(max(equity, 1.0) / starting_equity)
    fitness = log_growth - risk_free_annual_fraction * years - PARSIMONY_PER_RULE * genome.size()
    cleared = window_dec + window_inc
    peaks = np.maximum.accumulate(np.concatenate([[starting_equity], equity_array]))[1:]
    drawdown = float(np.max(1 - equity_array / peaks)) if len(equity_array) else 0.0
    window_share = (end - start) / max(1, end - history_start)
    return (
        EvaluationResult(
            fitness=fitness,
            final_equity_usd=float(equity),
            is_alive=death_index is None,
            death_index=death_index,
            equity_usd=equity_array,
            daily_pnl_usd=np.array(pnl_path),
            net_direction=float((window_dec - window_inc) / cleared) if cleared else 0.0,
            selectivity=bid_count / priced_count * 1.0 if priced_count else 0.0,
            cleared_mwh=float(cleared),
            max_drawdown_fraction=drawdown,
        )
        if window_share > 0
        else None
    )
