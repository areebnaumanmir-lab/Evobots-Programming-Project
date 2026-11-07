"""The career model: when a trader stops, and its fitness (`docs/design_spec.md` §10).

The simulator (`evobots.simulate.settlement`) already applies the default death, **L0 out
of money**. Every other layer is optional and off by default. Each one freezes the account
from its first trigger, and the path before that day is unchanged, so the layers are
applied here to a settled path:

- L0 out of money: can't post collateral for the smallest bid (in the simulator); on
- L1 capital floor: equity ≤ the floor (relative share of starting capital, or absolute USD); off
- L2 loss limit: equity falls more than a share below its running peak; off
- L3 quitting: monthly hazard h = logistic(β·x), a probability, not a stop (`hazard.py`); off
- L4 edge gone: Page's CUSUM on monthly excess returns signals (`sequential.py`); off
- L5 peers: not modelled: traders are price-takers and don't interact (§6.2)

**Fitness** (§10.2): F = E[ln(W_τ/W_0) − r_f·τ] − μ·size, where τ is when the career ends
(the end of the window, a hard stop, or a quit drawn from the L3 hazard), r_f the
risk-free log return per year (FRED DTB3 over the same days) and μ = 0.002 per tree node.
With L3 on, the expectation is taken over the quitting month, so F stays deterministic:
E = Σ_m S_{m−1}·h_m·g_m + S_M·g_M, with g_m the excess log growth to month m and S the
survival probability.

Example:
    >>> import numpy as np
    >>> path = np.array([1.0e6, 0.9e6, 0.6e6, 0.7e6])
    >>> first_stop(path, 1.0e6, CareerSettings(drawdown_limit_fraction=0.3))
    (2, 'loss limit')
    >>> first_stop(path, 1.0e6, CareerSettings(ruin_floor_fraction=2 / 3))
    (2, 'capital floor')
"""

import dataclasses
import math

import numpy as np

from evobots.career.hazard import QuitHazard, monthly_covariates, survival_curve
from evobots.career.sequential import cusum_signal_month

# Parsimony: fitness lost per tree node (45 nodes at most → 0.09).
PARSIMONY_PER_NODE = 0.002
DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = DAYS_PER_YEAR / 12
# MISO's minimum capitalization for a non-FTR trader (Attachment L §III.C), USD.
MISO_MINIMUM_CAPITALIZATION_USD = 500_000.0
# Assumed fixed yearly costs of a one-person trading company (§10.1, labelled assumption).
FIXED_COSTS_USD_PER_YEAR = 50_000.0


@dataclasses.dataclass(frozen=True)
class CareerSettings:
    """Which layers are on, with their parameters (all off = L0 only, the default).

    Attributes:
        name: preset name.
        ruin_floor_fraction: L1 relative floor (share of starting capital), or None.
        ruin_floor_usd: L1 absolute floor, or None.
        drawdown_limit_fraction: L2 loss limit from the running peak, or None.
        quit_hazard: L3 QuitHazard, or None.
        is_edge_check_on: L4 CUSUM retirement.
        cusum_threshold: L4 decision interval h (standardised units).
        cusum_reference: L4 reference value k (standardised units).
        fixed_costs_usd_per_year: fixed costs the edge must beat in L4 (assumption).
        investor_withdrawal_hazard_per_month: hedge-fund attrition (preset only), or None.
    """

    name: str = "individual"
    ruin_floor_fraction: float | None = None
    ruin_floor_usd: float | None = None
    drawdown_limit_fraction: float | None = None
    quit_hazard: QuitHazard | None = None
    is_edge_check_on: bool = False
    cusum_threshold: float = 5.0
    cusum_reference: float = 0.5
    fixed_costs_usd_per_year: float = FIXED_COSTS_USD_PER_YEAR
    investor_withdrawal_hazard_per_month: float | None = None

    def floor_usd(self, starting_capital_usd):
        """The effective L1 floor (the higher of relative and absolute), or None."""
        floors = []
        if self.ruin_floor_fraction is not None:
            floors.append(self.ruin_floor_fraction * starting_capital_usd)
        if self.ruin_floor_usd is not None:
            floors.append(self.ruin_floor_usd)
        return max(floors) if floors else None


# Hedge-fund attrition: 14.4 %/year for managed futures (Getmansky, Lo & Mei 2004) as a
# monthly hazard, doubled after two losing years (assumption).
HEDGE_FUND_MONTHLY_HAZARD = 1 - (1 - 0.144) ** (1 / 12)
PRESETS = {
    "individual": CareerSettings(),
    "miso_eligible": CareerSettings(
        name="miso_eligible", ruin_floor_usd=MISO_MINIMUM_CAPITALIZATION_USD
    ),
    "two_thirds_floor": CareerSettings(name="two_thirds_floor", ruin_floor_fraction=2 / 3),
    "prop_trader": CareerSettings(
        name="prop_trader", drawdown_limit_fraction=0.10, ruin_floor_fraction=0.5
    ),
    "hedge_fund": CareerSettings(
        name="hedge_fund",
        drawdown_limit_fraction=0.25,
        investor_withdrawal_hazard_per_month=HEDGE_FUND_MONTHLY_HAZARD,
    ),
}


def first_stop(equity_usd, starting_capital_usd, settings):
    """(index of the first day a hard layer triggers, cause) or (None, None)."""
    floor = settings.floor_usd(starting_capital_usd)
    peak = starting_capital_usd
    for index, equity in enumerate(equity_usd):
        if floor is not None and equity <= floor:
            return index, "capital floor"
        peak = max(peak, equity)
        if settings.drawdown_limit_fraction is not None and equity < peak * (
            1 - settings.drawdown_limit_fraction
        ):
            return index, "loss limit"
    return None, None


@dataclasses.dataclass(frozen=True)
class CareerOutcome:
    """A trader's career over one window.

    Attributes:
        settings_name: the preset.
        equity_usd: equity per day, frozen from the stop on.
        daily_pnl_usd: P&L per day (zero after the stop).
        stop_index: day index of the stop (death or a layer), or None.
        stop_cause: "out of money", "capital floor", "loss limit", "edge gone", or None.
        survival_by_month: L3 survival probabilities (ones when L3 is off).
        fitness: F (see the module docstring).
        log_growth: ln(W_T/W_0) of the frozen path.
        risk_free_log_return: Σ r_f over the window.
    """

    settings_name: str
    equity_usd: np.ndarray
    daily_pnl_usd: np.ndarray
    stop_index: int | None
    stop_cause: str | None
    survival_by_month: np.ndarray
    fitness: float
    log_growth: float
    risk_free_log_return: float


def monthly_index_ends(day_count):
    """Day indices ending each 30.44-day month of a window (the last may be partial)."""
    ends = list(range(int(DAYS_PER_MONTH) - 1, day_count, int(round(DAYS_PER_MONTH))))
    if not ends or ends[-1] != day_count - 1:
        ends.append(day_count - 1)
    return np.array(ends)


def apply_career(result, settings, node_count=0, risk_free_daily_log_return=None):
    """Apply the career layers to a SettlementResult and compute the fitness.

    Args:
        result: a SettlementResult (L0 already applied).
        settings: CareerSettings.
        node_count: the trader's tree size (parsimony).
        risk_free_daily_log_return: per-day risk-free log returns aligned to the window,
            or None for zero.

    Returns:
        CareerOutcome.
    """
    start = result.starting_capital_usd
    equity = result.equity_usd.copy()
    pnl = result.daily_pnl_usd.copy()
    day_count = len(equity)
    stop_index, stop_cause = (result.death_index, result.death_cause)
    layer_index, layer_cause = first_stop(equity, start, settings)
    if layer_index is not None and (stop_index is None or layer_index < stop_index):
        stop_index, stop_cause = layer_index, layer_cause
    month_ends = monthly_index_ends(day_count) if day_count else np.array([], dtype=int)
    if settings.is_edge_check_on and day_count:
        monthly_equity = np.concatenate([[start], equity[month_ends]])
        monthly_returns = np.diff(np.log(np.maximum(monthly_equity, 1.0)))
        risk_free_monthly = 0.0
        if risk_free_daily_log_return is not None and len(risk_free_daily_log_return):
            risk_free_monthly = float(np.mean(risk_free_daily_log_return)) * DAYS_PER_MONTH
        hurdle = risk_free_monthly + settings.fixed_costs_usd_per_year / 12 / start
        month = cusum_signal_month(
            monthly_returns - hurdle, settings.cusum_reference, settings.cusum_threshold
        )
        if month is not None:
            index = int(month_ends[month])
            if stop_index is None or index < stop_index:
                stop_index, stop_cause = index, "edge gone"
    if stop_index is not None and stop_index + 1 < day_count:
        equity[stop_index + 1 :] = equity[stop_index]
        pnl[stop_index + 1 :] = 0.0
    risk_free = (
        np.zeros(day_count)
        if risk_free_daily_log_return is None
        else np.asarray(risk_free_daily_log_return, dtype=float)
    )
    cumulative_risk_free = np.cumsum(risk_free)
    excess_growth = np.log(np.maximum(equity, 1.0) / start) - cumulative_risk_free
    if stop_index is not None:
        # After a stop the money earns nothing in the account; its excess return is frozen.
        excess_growth[stop_index + 1 :] = excess_growth[stop_index]
    hazards = []
    if settings.quit_hazard is not None and day_count:
        hazards.append(
            settings.quit_hazard.monthly_hazards(monthly_covariates(equity, start, month_ends))
        )
    if settings.investor_withdrawal_hazard_per_month is not None and day_count:
        hazards.append(
            withdrawal_hazards(
                equity, start, month_ends, settings.investor_withdrawal_hazard_per_month
            )
        )
    if hazards and day_count:
        combined = 1 - np.prod([1 - hazard for hazard in hazards], axis=0)
        survival = survival_curve(combined)
        quit_probability = np.concatenate([[1.0], survival[:-1]]) * combined
        monthly_growth = excess_growth[month_ends]
        expected = float(
            np.sum(quit_probability * monthly_growth) + survival[-1] * monthly_growth[-1]
        )
    else:
        survival = np.ones(len(month_ends))
        expected = float(excess_growth[-1]) if day_count else 0.0
    fitness = expected - PARSIMONY_PER_NODE * node_count
    return CareerOutcome(
        settings_name=settings.name,
        equity_usd=equity,
        daily_pnl_usd=pnl,
        stop_index=stop_index,
        stop_cause=stop_cause,
        survival_by_month=survival,
        fitness=fitness,
        log_growth=float(math.log(max(equity[-1], 1.0) / start)) if day_count else 0.0,
        risk_free_log_return=float(cumulative_risk_free[-1]) if day_count else 0.0,
    )


def withdrawal_hazards(equity, starting_capital_usd, month_ends, base_hazard):
    """Hedge-fund investor withdrawal: base hazard, doubled after two losing years running."""
    yearly = np.concatenate([[starting_capital_usd], equity[month_ends]])
    hazards = np.full(len(month_ends), base_hazard)
    for month in range(24, len(month_ends)):
        first_year = yearly[month - 11] < yearly[month - 23]
        second_year = yearly[month + 1] < yearly[month - 11]
        if first_year and second_year:
            hazards[month] = min(1.0, 2 * base_hazard)
    return hazards
