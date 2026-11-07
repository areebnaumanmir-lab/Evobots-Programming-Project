"""Settle any trading decisions on history: clearing, sizing, credit, fees, equity, death.

The simulator takes a **decision matrix** from any source (an evolved trader, the O2
optimizer, a baseline), not only from a bot (`docs/design_spec.md` §20.10). For each operating
day, hour and location a decision has a side (+1 DEC, −1 INC, 0 none), a limit price and a
full-size MW. The rules (`docs/design_spec.md` §6, §10.1, §13; `docs/market_rules.md` §3–4):

1. **Clearing** (all-or-nothing, obs. 99.5 %): a DEC clears when DA ≤ limit, an INC when
   DA ≥ limit; an hour without both prices doesn't trade.
2. **Position scale:** scale = min(1, budget × equity / L), where L is the trader's own
   trailing 1-in-100-day full-size loss (two-sided: max of the loss and gain 99th
   percentiles, as `evobots.sizing`), from days D−6−364 … D−6 with a 90-day warm-up (no
   estimate → no trades). Decisions that are already sized (O2) skip the scale.
3. **Daily limits:** submitted MWh (cleared or not) may not exceed the trader's own daily
   cap (its risk slot) nor its Virtual MWh Limit, credit share × equity ÷ (MPD × 2 days)
   (Attachment L §IV.A; `market_rules.md` §4.2). Bids are cut proportionally, never refused.
4. **Rounding:** each bid is rounded down to MISO's 0.1 MW step; below 0.1 MW is no bid.
5. **P&L:** cleared MW × side × (RT − DA), minus fees (`evobots.simulate.fees`).
6. **Pause:** after a day losing more than the trader's pause threshold (a share of the
   equity it started the day with), it sits out its pause days (risk slot, §9.2).
7. **Death (L0, the default career):** when equity can no longer cover the collateral of the
   smallest bid, 0.1 MW × MPD × 2 days ($2.40 at the $12 floor), the trader stops for good.

Two implementations give the same numbers: `settle_reference` (plain NumPy, readable) and a
Numba kernel used by `settle` (`docs/design_spec.md` §14.3: "a readable reference plus a fast
version, with an agreement test"). Without Numba (the website's Pyodide), `settle` uses the
reference.

Example:
    >>> import numpy as np
    >>> from evobots.simulate.market import synthetic_hub_market
    >>> market = synthetic_hub_market(days=500, seed=1)
    >>> decisions = constant_decisions(market, side=-1, full_size_mw=5.0)
    >>> result = settle(decisions, market, 200, 500, AccountRules())
    >>> result.is_alive, round(result.net_direction, 2)
    (True, -1.0)
"""

import dataclasses
import math

import numpy as np

from evobots.config.capital import (
    MINIMUM_BID_MW,
    MINIMUM_MPD_USD_PER_MWH,
    VIRTUAL_EXPOSURE_WINDOW_DAYS,
)
from evobots.simulate.fees import CostTable

try:
    import numba
except ImportError:  # Pyodide (the website) has no Numba
    numba = None

HOURS_PER_DAY = 24
NEWEST_VISIBLE_LAG_DAYS = 6
TRAILING_WINDOW_DAYS = 365
WARM_UP_DAYS = 90
LOSS_PERCENTILE = 99.0
# History before the window that the sizing estimate may use: a full trailing year plus the
# visibility lag (and a margin), all public before the window opens.
SIZING_HISTORY_DAYS = TRAILING_WINDOW_DAYS + NEWEST_VISIBLE_LAG_DAYS + 30
# Bids are rounded down to this step; a tiny epsilon keeps 0.3 × 10 from becoming 2.999….
BID_STEP_MW = MINIMUM_BID_MW
ROUNDING_EPSILON = 1e-9
DEATH_CAUSE_OUT_OF_MONEY = "out of money"


@dataclasses.dataclass(frozen=True)
class AccountRules:
    """How a trader's account is run. Defaults are the project defaults (§13).

    Attributes:
        starting_capital_usd: equity on the first day of the window.
        daily_risk_budget_fraction: share of equity a 1-in-100 full-size day may cost.
        credit_share_fraction: share of equity pledged as MISO collateral.
        mpd_usd_per_mwh: MISO's MPD (the $12 floor, labelled estimate, round 28).
        exposure_window_days: VMEW (2 days).
        max_mwh_per_day: the trader's own daily cap on submitted MWh (risk slot).
        pause_loss_fraction: a day losing more than this share of the day's starting equity
            starts a pause (inf = never).
        pause_days: days sat out after such a day.
        is_scaled: apply the position scale (False for decisions already in final MW).
        is_rounding: round each bid down to 0.1 MW (False only to reproduce unrounded
            calibration benchmarks).
        cost_multiple: 1 for estimated costs, 2 for the G4 stress test, 0 for none.
    """

    starting_capital_usd: float = 1_500_000.0
    daily_risk_budget_fraction: float = 0.02
    credit_share_fraction: float = 0.25
    mpd_usd_per_mwh: float = MINIMUM_MPD_USD_PER_MWH
    exposure_window_days: float = VIRTUAL_EXPOSURE_WINDOW_DAYS
    max_mwh_per_day: float = math.inf
    pause_loss_fraction: float = math.inf
    pause_days: int = 0
    is_scaled: bool = True
    is_rounding: bool = True
    cost_multiple: float = 1.0

    def out_of_money_equity_usd(self):
        """Equity at or below which the trader can't post the smallest bid's collateral."""
        return MINIMUM_BID_MW * self.mpd_usd_per_mwh * self.exposure_window_days


@dataclasses.dataclass(frozen=True)
class Decisions:
    """Decisions for days first_day_index … first_day_index + len − 1 of a market.

    Attributes:
        first_day_index: market day index of the first row.
        side: int8 array (days, 24, locations): +1 DEC, −1 INC, 0 no bid.
        limit_usd_per_mwh: float array, same shape; ignored where side is 0.
        full_size_mw: float array, same shape: MW bid at position scale 1.
    """

    first_day_index: int
    side: np.ndarray
    limit_usd_per_mwh: np.ndarray
    full_size_mw: np.ndarray

    def day_count(self):
        """Number of days covered."""
        return self.side.shape[0]


@dataclasses.dataclass(frozen=True)
class SettlementResult:
    """One account's life over a window (all arrays one value per window day).

    Attributes:
        days: the window's operating days.
        daily_pnl_usd: P&L after fees.
        equity_usd: end-of-day equity.
        fees_usd: fees paid.
        position_scale: the scale used (0 before the warm-up ends, when paused or dead).
        cleared_dec_mwh, cleared_inc_mwh: cleared MWh by side.
        submitted_mwh: MWh bid (cleared or not).
        full_size_daily_pnl_usd: P&L each day would have made at scale 1 (sizing input).
        death_index: window day index of death, or None.
        death_cause: "out of money" or None.
        bid_location_hours: location-hours with a bid in the window.
        priced_location_hours: location-hours with both prices in the window.
        starting_capital_usd: equity at the start.
    """

    days: tuple
    daily_pnl_usd: np.ndarray
    equity_usd: np.ndarray
    fees_usd: np.ndarray
    position_scale: np.ndarray
    cleared_dec_mwh: np.ndarray
    cleared_inc_mwh: np.ndarray
    submitted_mwh: np.ndarray
    full_size_daily_pnl_usd: np.ndarray
    death_index: int | None
    death_cause: str | None
    bid_location_hours: int
    priced_location_hours: int
    starting_capital_usd: float

    @property
    def is_alive(self):
        """True when the trader never died in the window."""
        return self.death_index is None

    @property
    def final_equity_usd(self):
        """Equity at the end of the window."""
        return float(self.equity_usd[-1]) if len(self.equity_usd) else self.starting_capital_usd

    @property
    def cleared_mwh(self):
        """Total cleared MWh."""
        return float(self.cleared_dec_mwh.sum() + self.cleared_inc_mwh.sum())

    @property
    def net_direction(self):
        """(DEC MWh − INC MWh) ÷ cleared MWh, −1 … +1; 0 with no trades (map axis 1)."""
        total = self.cleared_mwh
        if total == 0:
            return 0.0
        return float((self.cleared_dec_mwh.sum() - self.cleared_inc_mwh.sum()) / total)

    @property
    def selectivity(self):
        """Share of priced location-hours with a bid (map axis 2)."""
        if self.priced_location_hours == 0:
            return 0.0
        return self.bid_location_hours / self.priced_location_hours

    def max_drawdown_fraction(self):
        """Largest fall from a running peak, as a share of the peak."""
        if not len(self.equity_usd):
            return 0.0
        path = np.concatenate([[self.starting_capital_usd], self.equity_usd])
        peaks = np.maximum.accumulate(path)
        return float(np.max(1 - path / peaks))

    def log_growth(self):
        """ln(final equity ÷ starting capital); equity is floored at $1 (death)."""
        return math.log(max(self.final_equity_usd, 1.0) / self.starting_capital_usd)


def constant_decisions(market, side, full_size_mw, limit_usd_per_mwh=None, first_day_index=0):
    """The same bid at every location and hour (baselines; limit ±∞ = always clears)."""
    shape = (len(market.days) - first_day_index, HOURS_PER_DAY, len(market.hubs))
    if limit_usd_per_mwh is None:
        limit_usd_per_mwh = math.inf if side > 0 else -math.inf
    return Decisions(
        first_day_index=first_day_index,
        side=np.full(shape, side, dtype=np.int8),
        limit_usd_per_mwh=np.full(shape, limit_usd_per_mwh, dtype=float),
        full_size_mw=np.broadcast_to(np.asarray(full_size_mw, dtype=float), shape).copy(),
    )


def round_down_to_step(power_mw):
    """Round MW down to the 0.1 MW bid step (works on arrays)."""
    return np.floor(power_mw / BID_STEP_MW + ROUNDING_EPSILON) * BID_STEP_MW


@dataclasses.dataclass(frozen=True)
class PreparedDays:
    """Day-by-day inputs of the settlement loop, prepared once per trader and window."""

    signed_gain: np.ndarray  # (days, 24, L): side × (RT − DA) where cleared, else 0
    net_sign: np.ndarray  # (days, 24, L): side where cleared, else 0 (for fees)
    is_bid: np.ndarray  # (days, 24, L): side ≠ 0 and priced
    full_size_mw: np.ndarray  # (days, 24, L): unrounded MW at scale 1 where bid, else 0
    admin: np.ndarray  # (days,)
    da_rsg: np.ndarray  # (days,)
    ddc: np.ndarray  # (days, 24)
    priced_count: int


def prepare_days(decisions, market, first, end, rules, cost_table):
    """Clearing, signed gains and rates for market days first … end−1."""
    rows = slice(first - decisions.first_day_index, end - decisions.first_day_index)
    if rows.start < 0 or rows.stop > decisions.day_count():
        raise ValueError("decisions don't cover the days to settle (sizing history included)")
    side = decisions.side[rows].astype(float)
    limit = decisions.limit_usd_per_mwh[rows]
    day_ahead = market.day_ahead[first:end]
    real_time = market.real_time[first:end]
    is_priced = ~np.isnan(day_ahead) & ~np.isnan(real_time)
    with np.errstate(invalid="ignore"):
        is_cleared = is_priced & (
            ((side > 0) & (day_ahead <= limit)) | ((side < 0) & (day_ahead >= limit))
        )
    is_bid = is_priced & (side != 0)
    gain = np.where(is_cleared, real_time - day_ahead, 0.0)
    admin, da_rsg, ddc = cost_table.daily_arrays(market.days[first:end], rules.cost_multiple)
    return PreparedDays(
        signed_gain=side * gain,
        net_sign=np.where(is_cleared, side, 0.0),
        is_bid=is_bid,
        full_size_mw=np.where(is_bid, np.nan_to_num(decisions.full_size_mw[rows]), 0.0),
        admin=admin,
        da_rsg=da_rsg,
        ddc=ddc,
        priced_count=int(is_priced.sum()),
    )


def day_outcome(prepared, day, power_mw):
    """(P&L before fees, fees, DEC MWh, INC MWh) of one day at given MW (reference form)."""
    net = prepared.net_sign[day] * power_mw  # (24, L): + DEC, − INC, 0 where not cleared
    gross = float((prepared.signed_gain[day] * power_mw).sum())
    admin = prepared.admin[day] * np.abs(net).sum()
    da_rsg = prepared.da_rsg[day] * np.maximum(net, 0.0).sum()
    rt_rsg = float((prepared.ddc[day] * np.maximum(-net.sum(axis=1), 0.0)).sum())
    dec = float(np.maximum(net, 0.0).sum())
    inc = float(np.maximum(-net, 0.0).sum())
    return gross, float(admin + da_rsg + rt_rsg), dec, inc


def full_size_pnl_reference(prepared, is_rounding):
    """Daily P&L at scale 1 (after fees), the sizing rule's input."""
    power = round_down_to_step(prepared.full_size_mw) if is_rounding else prepared.full_size_mw
    pnl = np.empty(prepared.signed_gain.shape[0])
    for day in range(len(pnl)):
        gross, fees, _, _ = day_outcome(prepared, day, power[day])
        pnl[day] = gross - fees
    return pnl


def trailing_loss_estimates_reference(full_size_pnl, first_window_index):
    """Two-sided 1-in-100-day full-size loss for each window day (NaN = no estimate yet).

    For series index i the window is i−6−364 … i−6 (clipped at 0), needing ≥ 90 days.
    """
    estimates = np.full(len(full_size_pnl) - first_window_index, np.nan)
    for position, index in enumerate(range(first_window_index, len(full_size_pnl))):
        newest = index - NEWEST_VISIBLE_LAG_DAYS
        if newest < 0:
            continue
        window = full_size_pnl[max(0, newest - TRAILING_WINDOW_DAYS + 1) : newest + 1]
        if len(window) < WARM_UP_DAYS:
            continue
        estimates[position] = max(
            np.percentile(-window, LOSS_PERCENTILE), np.percentile(window, LOSS_PERCENTILE)
        )
    return estimates


def scale_for_day(rules, equity, estimate, full_size_submitted_mwh):
    """The position scale after the sizing rule, the daily cap and the credit limit."""
    if rules.is_scaled:
        if np.isnan(estimate):
            return 0.0
        scale = (
            1.0 if estimate <= 0 else min(1.0, rules.daily_risk_budget_fraction * equity / estimate)
        )
    else:
        scale = 1.0
    submitted = scale * full_size_submitted_mwh
    if submitted > 0:
        credit_limit = (
            rules.credit_share_fraction
            * max(equity, 0.0)
            / (rules.mpd_usd_per_mwh * rules.exposure_window_days)
        )
        scale *= min(1.0, rules.max_mwh_per_day / submitted, credit_limit / submitted)
    return scale


def settle_reference(decisions, market, start, end, rules, cost_table=None, history_start=None):
    """Settle decisions over market days start … end−1 (plain NumPy; see the module docstring).

    Args:
        decisions: Decisions covering history_start … end−1.
        market: a HubMarket.
        start: first window day index (equity = starting capital before it).
        end: one past the last window day.
        rules: AccountRules.
        cost_table: CostTable (labelled estimates by default).
        history_start: first day whose full-size P&L may feed the sizing estimate; default
            max(decisions.first_day_index, start − SIZING_HISTORY_DAYS).

    Returns:
        SettlementResult.
    """
    cost_table = cost_table or CostTable.estimates()
    if history_start is None:
        history_start = max(decisions.first_day_index, start - SIZING_HISTORY_DAYS)
    prepared = prepare_days(decisions, market, history_start, end, rules, cost_table)
    full_pnl = full_size_pnl_reference(prepared, rules.is_rounding)
    offset = start - history_start
    estimates = trailing_loss_estimates_reference(full_pnl, offset)
    day_count = end - start
    outputs = {
        name: np.zeros(day_count)
        for name in ("pnl", "equity", "fees", "scale", "dec", "inc", "submitted")
    }
    equity = rules.starting_capital_usd
    death_index = None
    pause_remaining = 0
    for position in range(day_count):
        day = offset + position
        scale = 0.0
        if death_index is None and pause_remaining == 0:
            full_submitted = float(prepared.full_size_mw[day].sum())
            scale = scale_for_day(rules, equity, estimates[position], full_submitted)
        elif pause_remaining > 0:
            pause_remaining -= 1
        power = scale * prepared.full_size_mw[day]
        if rules.is_rounding:
            power = round_down_to_step(power)
        gross, fees, dec, inc = day_outcome(prepared, day, power)
        pnl = gross - fees
        starting_equity = equity
        equity += pnl
        outputs["pnl"][position] = pnl
        outputs["equity"][position] = equity
        outputs["fees"][position] = fees
        outputs["scale"][position] = scale
        outputs["dec"][position] = dec
        outputs["inc"][position] = inc
        outputs["submitted"][position] = float(power.sum())
        if death_index is None and equity <= rules.out_of_money_equity_usd():
            death_index = position
        elif pnl < -rules.pause_loss_fraction * starting_equity and rules.pause_days > 0:
            pause_remaining = rules.pause_days
    return result_from_outputs(
        outputs, market, start, end, prepared, offset, full_pnl, death_index, rules
    )


def result_from_outputs(
    outputs, market, start, end, prepared, offset, full_pnl, death_index, rules
):
    """Pack the loop's outputs into a SettlementResult."""
    is_bid_window = prepared.is_bid[offset:]
    priced_window = prepared.priced_count if offset == 0 else None
    if priced_window is None:
        day_ahead = market.day_ahead[start:end]
        real_time = market.real_time[start:end]
        priced_window = int((~np.isnan(day_ahead) & ~np.isnan(real_time)).sum())
    return SettlementResult(
        days=tuple(market.days[start:end]),
        daily_pnl_usd=outputs["pnl"],
        equity_usd=outputs["equity"],
        fees_usd=outputs["fees"],
        position_scale=outputs["scale"],
        cleared_dec_mwh=outputs["dec"],
        cleared_inc_mwh=outputs["inc"],
        submitted_mwh=outputs["submitted"],
        full_size_daily_pnl_usd=full_pnl[offset:],
        death_index=death_index,
        death_cause=DEATH_CAUSE_OUT_OF_MONEY if death_index is not None else None,
        bid_location_hours=int(is_bid_window.sum()),
        priced_location_hours=priced_window,
        starting_capital_usd=rules.starting_capital_usd,
    )


# ----- the fast version (Numba) -----

if numba is not None:

    @numba.njit(cache=True)
    def full_size_pnl_kernel(signed_gain, net_sign, full_size_mw, admin, da_rsg, ddc, is_rounding):
        """Daily full-size P&L after fees (same arithmetic as the reference)."""
        day_count, hour_count, location_count = signed_gain.shape
        pnl = np.zeros(day_count)
        for day in range(day_count):
            total = 0.0
            fees = 0.0
            for hour in range(hour_count):
                net_hour = 0.0
                for location in range(location_count):
                    power = full_size_mw[day, hour, location]
                    if is_rounding:
                        power = np.floor(power / 0.1 + 1e-9) * 0.1
                    total += signed_gain[day, hour, location] * power
                    net = net_sign[day, hour, location] * power
                    net_hour += net
                    fees += admin[day] * abs(net) + da_rsg[day] * max(net, 0.0)
                fees += ddc[day, hour] * max(-net_hour, 0.0)
            pnl[day] = total - fees
        return pnl

    @numba.njit(cache=True)
    def percentile_of_sorted(values, count, quantile):
        """np.percentile's linear interpolation on the first `count` sorted values."""
        position = quantile / 100.0 * (count - 1)
        lower = int(np.floor(position))
        upper = min(lower + 1, count - 1)
        fraction = position - lower
        return values[lower] + (values[upper] - values[lower]) * fraction

    @numba.njit(cache=True)
    def trailing_estimates_kernel(full_pnl, first_window_index):
        """Two-sided trailing p99 loss per window day, keeping a sorted window."""
        length = full_pnl.shape[0]
        estimates = np.full(length - first_window_index, np.nan)
        window = np.empty(365)
        count = 0
        added_until = -1  # series index of the newest value in the window
        for index in range(first_window_index, length):
            newest = index - 6
            if newest < 0:
                continue
            while added_until < newest:
                added_until += 1
                value = full_pnl[added_until]
                if count == 365:
                    # Remove the value leaving the window (series index added_until − 365).
                    leaving = full_pnl[added_until - 365]
                    position = np.searchsorted(window[:count], leaving)
                    for shift in range(position, count - 1):
                        window[shift] = window[shift + 1]
                    count -= 1
                position = np.searchsorted(window[:count], value)
                for shift in range(count, position, -1):
                    window[shift] = window[shift - 1]
                window[position] = value
                count += 1
            if count < 90:
                continue
            high = percentile_of_sorted(window, count, 99.0)
            low = percentile_of_sorted(window, count, 1.0)
            estimates[index - first_window_index] = max(-low, high)
        return estimates

    @numba.njit(cache=True)
    def settle_kernel(
        signed_gain,
        net_sign,
        full_size_mw,
        admin,
        da_rsg,
        ddc,
        estimates,
        offset,
        starting_capital,
        budget,
        credit_share,
        mpd,
        exposure_days,
        max_mwh_per_day,
        pause_loss_fraction,
        pause_days,
        is_scaled,
        is_rounding,
        out_of_money,
    ):
        """The day loop of `settle_reference`, element by element."""
        day_count = estimates.shape[0]
        hour_count = signed_gain.shape[1]
        location_count = signed_gain.shape[2]
        outputs = np.zeros((7, day_count))
        equity = starting_capital
        death_index = -1
        pause_remaining = 0
        for position in range(day_count):
            day = offset + position
            scale = 0.0
            if death_index < 0 and pause_remaining == 0:
                full_submitted = 0.0
                for hour in range(hour_count):
                    for location in range(location_count):
                        full_submitted += full_size_mw[day, hour, location]
                estimate = estimates[position]
                if is_scaled:
                    if np.isnan(estimate):
                        scale = 0.0
                    elif estimate <= 0:
                        scale = 1.0
                    else:
                        scale = min(1.0, budget * equity / estimate)
                else:
                    scale = 1.0
                submitted = scale * full_submitted
                if submitted > 0:
                    credit_limit = credit_share * max(equity, 0.0) / (mpd * exposure_days)
                    scale *= min(1.0, max_mwh_per_day / submitted, credit_limit / submitted)
            elif pause_remaining > 0:
                pause_remaining -= 1
            gross = 0.0
            fees = 0.0
            dec = 0.0
            inc = 0.0
            submitted_power = 0.0
            for hour in range(hour_count):
                net_hour = 0.0
                for location in range(location_count):
                    power = scale * full_size_mw[day, hour, location]
                    if is_rounding:
                        power = np.floor(power / 0.1 + 1e-9) * 0.1
                    submitted_power += power
                    gross += signed_gain[day, hour, location] * power
                    net = net_sign[day, hour, location] * power
                    net_hour += net
                    fees += admin[day] * abs(net) + da_rsg[day] * max(net, 0.0)
                    dec += max(net, 0.0)
                    inc += max(-net, 0.0)
                fees += ddc[day, hour] * max(-net_hour, 0.0)
            pnl = gross - fees
            starting_equity = equity
            equity += pnl
            outputs[0, position] = pnl
            outputs[1, position] = equity
            outputs[2, position] = fees
            outputs[3, position] = scale
            outputs[4, position] = dec
            outputs[5, position] = inc
            outputs[6, position] = submitted_power
            if death_index < 0 and equity <= out_of_money:
                death_index = position
            elif pnl < -pause_loss_fraction * starting_equity and pause_days > 0:
                pause_remaining = pause_days
        return outputs, death_index


def settle(decisions, market, start, end, rules, cost_table=None, history_start=None):
    """Settle decisions over market days start … end−1 (fast; same contract as the reference)."""
    if numba is None:
        return settle_reference(decisions, market, start, end, rules, cost_table, history_start)
    cost_table = cost_table or CostTable.estimates()
    if history_start is None:
        history_start = max(decisions.first_day_index, start - SIZING_HISTORY_DAYS)
    prepared = prepare_days(decisions, market, history_start, end, rules, cost_table)
    full_pnl = full_size_pnl_kernel(
        prepared.signed_gain,
        prepared.net_sign,
        prepared.full_size_mw,
        prepared.admin,
        prepared.da_rsg,
        prepared.ddc,
        rules.is_rounding,
    )
    offset = start - history_start
    estimates = trailing_estimates_kernel(full_pnl, offset)
    packed, death = settle_kernel(
        prepared.signed_gain,
        prepared.net_sign,
        prepared.full_size_mw,
        prepared.admin,
        prepared.da_rsg,
        prepared.ddc,
        estimates,
        offset,
        float(rules.starting_capital_usd),
        float(rules.daily_risk_budget_fraction),
        float(rules.credit_share_fraction),
        float(rules.mpd_usd_per_mwh),
        float(rules.exposure_window_days),
        float(rules.max_mwh_per_day),
        float(rules.pause_loss_fraction),
        int(rules.pause_days),
        bool(rules.is_scaled),
        bool(rules.is_rounding),
        float(rules.out_of_money_equity_usd()),
    )
    names = ("pnl", "equity", "fees", "scale", "dec", "inc", "submitted")
    outputs = {name: packed[index].copy() for index, name in enumerate(names)}
    return result_from_outputs(
        outputs,
        market,
        start,
        end,
        prepared,
        offset,
        full_pnl,
        None if death < 0 else int(death),
        rules,
    )
