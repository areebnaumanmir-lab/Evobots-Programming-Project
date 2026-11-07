"""O2: bidders built by optimization instead of evolution (`docs/design_spec.md` §20.5).

**SAA mean-CVaR bidder.** For operating day D, take K scenarios of the hub-hour gains
g_k = RT − DA from visible data (O1). Choose DEC quantities q⁺ ≥ 0 and INC quantities q⁻ ≥ 0
(MW) for every hub-hour to

    maximise   (1/K) Σ_k π_k − λ · CVaR_α(−π)
    π_k = Σ_{h,n} (q⁺ − q⁻) · g_{k,h,n} − f · (q⁺ + q⁻)
    CVaR_α(−π) = min_ζ ζ + 1/((1 − α)K) Σ_k max(0, −π_k − ζ)       (Rockafellar & Uryasev 2000)
    0 ≤ q⁺, q⁻ ≤ cap_n,   Σ (q⁺ + q⁻) ≤ the daily MWh limit

a linear program, solved with HiGHS (`scipy.optimize.linprog`). Its decisions are settled
through the same simulator as every trader: clearing, fees, sizing rule, career.

**Bid curves** (optional): offer each hub-hour at a grid of limit offsets δ_j from yesterday's
DA. Whether a block clears in scenario k is a known 0/1 number (the scenario's DA change
against its own previous day), so the problem stays linear and the bidder chooses its own
clearing rate.

**Perfect-foresight bound:** the same LP with the realised day as its only scenario — an
upper bound, never a strategy, and labelled so.

**DPDS** (Baltaoglu, Tong & Zhao 2018, arXiv 1802.03010, §III): options k = (hub, hour,
side). A bid is translated so that it clears when x′ ≥ λ′ and pays π′ − λ′ (DEC:
x′ = x − l, λ′ = DA − l, π′ = RT − l; INC: x′ = u − x, λ′ = u − DA, π′ = u − RT). Each
day the empirical average payoff r̄_k(x′) of every option over the visible history is a step
function; the budget B (Σ x′ ≤ B) is spread across options by dynamic programming on the grid
{0, B/α, …, B}. The risk-averse variant subtracts ρ times the sample variance (their eq. 5).
Deviations, stated: the grid has α = min(t − 1, 50) points (the paper uses t − 1), the
history is the last 365 visible days, and when DEC and INC are both chosen for one
hub-hour the larger expected payoff is kept (our decisions allow one side per hub-hour).

Example:
    >>> import numpy as np
    >>> gains = np.array([[[2.0]], [[1.0]], [[-1.0]]])  # three scenarios, 1 hour, 1 hub
    >>> dec, inc = solve_mean_cvar(gains, np.array([5.0]), fee_usd_per_mwh=0.1, risk_aversion=0.0)
    >>> float(dec[0, 0]), float(inc[0, 0])
    (5.0, 0.0)
"""

import numpy as np
from scipy import optimize, sparse

from evobots.orfe.scenarios import VISIBLE_LAG_DAYS
from evobots.simulate.settlement import Decisions

HOURS_PER_DAY = 24
DEFAULT_FEE_USD_PER_MWH = 0.20
DPDS_GRID_POINTS = 50
DPDS_HISTORY_DAYS = 365
# B / (K × (u − l)) in the paper's NYISO setting: $250,000 / (2 × 11 × 24 × $1,000) ≈ 0.47.
DPDS_BUDGET_SHARE = 0.47


def solve_mean_cvar(
    gains,
    caps_mw,
    fee_usd_per_mwh=DEFAULT_FEE_USD_PER_MWH,
    risk_aversion=0.0,
    alpha=0.95,
    daily_limit_mwh=None,
):
    """The mean-CVaR LP above. gains: (K, 24, hubs) RT − DA per scenario.

    Returns:
        (dec_mw, inc_mw), each (24, hubs).
    """
    scenario_count, hours, hubs = gains.shape
    size = hours * hubs
    flat = gains.reshape(scenario_count, size)
    mean_gain = flat.mean(axis=0)
    # Variables: q⁺ (size), q⁻ (size), ζ (1), u (K).
    objective = np.concatenate(
        [
            -mean_gain + fee_usd_per_mwh,
            mean_gain + fee_usd_per_mwh,
            [risk_aversion],
            np.full(scenario_count, risk_aversion / ((1 - alpha) * scenario_count)),
        ]
    )
    rows = []
    bounds_upper = []
    if risk_aversion > 0:
        # −π_k − ζ − u_k ≤ 0  ⇔  −g_k·q⁺ + g_k·q⁻ + f(q⁺ + q⁻) − ζ − u_k ≤ 0
        cvar_block = sparse.hstack(
            [
                sparse.csr_matrix(-flat + fee_usd_per_mwh),
                sparse.csr_matrix(flat + fee_usd_per_mwh),
                sparse.csr_matrix(-np.ones((scenario_count, 1))),
                -sparse.identity(scenario_count, format="csr"),
            ]
        )
        rows.append(cvar_block)
        bounds_upper.append(np.zeros(scenario_count))
    if daily_limit_mwh is not None:
        rows.append(
            sparse.csr_matrix(
                np.concatenate([np.ones(2 * size), np.zeros(1 + scenario_count)])[None, :]
            )
        )
        bounds_upper.append([daily_limit_mwh])
    caps = np.tile(np.asarray(caps_mw, dtype=float), hours)
    bounds = [(0, cap) for cap in caps] * 2 + [(None, None)] + [(0, None)] * scenario_count
    result = optimize.linprog(
        objective,
        A_ub=sparse.vstack(rows) if rows else None,
        b_ub=np.concatenate(bounds_upper) if rows else None,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(f"LP failed: {result.message}")
    solution = result.x
    dec = solution[:size].reshape(hours, hubs)
    inc = solution[size : 2 * size].reshape(hours, hubs)
    # Buying and selling the same hub-hour only pays fees; net it (the LP never prefers both).
    net = dec - inc
    return np.maximum(net, 0.0), np.maximum(-net, 0.0)


def daily_decisions_from_quantities(dec_mw, inc_mw, day_ahead_last):
    """One day's Decisions arrays from quantities (limit ±∞: price-taking, always clears)."""
    side = np.where(dec_mw > 1e-9, 1, np.where(inc_mw > 1e-9, -1, 0)).astype(np.int8)
    limit = np.where(side > 0, np.inf, np.where(side < 0, -np.inf, 0.0))
    power = np.where(side > 0, dec_mw, inc_mw)
    return side, limit, power


def optimizer_decisions(
    market,
    start,
    end,
    scenario_function,
    caps_mw,
    risk_aversion=0.0,
    alpha=0.95,
    scenario_count=50,
    fee_usd_per_mwh=DEFAULT_FEE_USD_PER_MWH,
    daily_limit_mwh=None,
):
    """Mean-CVaR decisions for market days start … end−1.

    Args:
        market: the HubMarket.
        start: first market day index.
        end: one past the last.
        scenario_function: callable(decision_index, count, seed) → (K, 24, hubs) DA − RT
            scenarios from visible data (O1).
        caps_mw: each hub's MW cap.
        risk_aversion: λ.
        alpha: the CVaR level.
        scenario_count: K.
        fee_usd_per_mwh: cost per cleared MWh in the objective.
        daily_limit_mwh: optional limit on Σ(q⁺ + q⁻).
    """
    shape = (end - start, HOURS_PER_DAY, len(market.hubs))
    side = np.zeros(shape, dtype=np.int8)
    limit = np.zeros(shape)
    power = np.zeros(shape)
    for offset, index in enumerate(range(start, end)):
        spreads = scenario_function(index, scenario_count, index)
        gains = -np.nan_to_num(spreads)  # RT − DA
        dec, inc = solve_mean_cvar(
            gains, caps_mw, fee_usd_per_mwh, risk_aversion, alpha, daily_limit_mwh
        )
        side[offset], limit[offset], power[offset] = daily_decisions_from_quantities(dec, inc, None)
    return Decisions(start, side, limit, power)


def perfect_foresight_decisions(
    market, start, end, caps_mw, fee_usd_per_mwh=DEFAULT_FEE_USD_PER_MWH
):
    """Upper bound, never a strategy: the LP solved on the realised day."""
    gains_all = np.nan_to_num(market.real_time - market.day_ahead)
    shape = (end - start, HOURS_PER_DAY, len(market.hubs))
    side = np.zeros(shape, dtype=np.int8)
    limit = np.zeros(shape)
    power = np.zeros(shape)
    for offset, index in enumerate(range(start, end)):
        dec, inc = solve_mean_cvar(gains_all[index][None], caps_mw, fee_usd_per_mwh)
        side[offset], limit[offset], power[offset] = daily_decisions_from_quantities(dec, inc, None)
    return Decisions(start, side, limit, power)


# ----- DPDS -----


def option_payoff_steps(translated_prices, payoffs, grid):
    """r̄(x′) on a grid: mean over history of payoff · 1{x′ ≥ λ′} (and its mean square).

    Args:
        translated_prices: (t, options) λ′.
        payoffs: (t, options) π′ − λ′.
        grid: (G,) bid levels x′.

    Returns:
        (mean (options, G), mean of squares (options, G)).
    """
    cleared = translated_prices[:, :, None] <= grid[None, None, :]
    mean = (payoffs[:, :, None] * cleared).mean(axis=0)
    square = ((payoffs**2)[:, :, None] * cleared).mean(axis=0)
    return mean, square


def allocate_budget(values):
    """DP over options: choose a grid index per option, Σ indices ≤ G − 1, maximising Σ values.

    Args:
        values: (options, G) reward of each option at grid index j (bid j·B/(G − 1)).

    Returns:
        chosen grid index per option.
    """
    options, grid_size = values.shape
    best = np.zeros(grid_size)  # best[b]: best total with budget index b over options so far
    choices = np.zeros((options, grid_size), dtype=int)
    budgets = np.arange(grid_size)
    for option in range(options):
        # candidate[b, j] = values[option, j] + best[b − j] for j ≤ b
        spent = budgets[:, None] - budgets[None, :]
        candidate = np.where(
            spent >= 0, values[option][None, :] + best[np.clip(spent, 0, None)], -np.inf
        )
        choices[option] = np.argmax(candidate, axis=1)
        best = candidate[budgets, choices[option]]
    chosen = np.zeros(options, dtype=int)
    budget = grid_size - 1
    for option in range(options - 1, -1, -1):
        chosen[option] = choices[option, budget]
        budget -= chosen[option]
    return chosen


def dpds_decisions(
    market,
    start,
    end,
    caps_mw,
    lower_price=None,
    upper_price=None,
    risk_penalty=0.0,
    grid_points=DPDS_GRID_POINTS,
):
    """DPDS bids for market days start … end−1 (see the module docstring)."""
    hubs = len(market.hubs)
    shape = (end - start, HOURS_PER_DAY, hubs)
    side = np.zeros(shape, dtype=np.int8)
    limit = np.zeros(shape)
    power = np.zeros(shape)
    for offset, index in enumerate(range(start, end)):
        newest = index - VISIBLE_LAG_DAYS
        first = max(0, newest - DPDS_HISTORY_DAYS + 1)
        if newest - first < 30:
            continue
        day_ahead = market.day_ahead[first : newest + 1].reshape(newest + 1 - first, -1)
        real_time = market.real_time[first : newest + 1].reshape(newest + 1 - first, -1)
        complete = ~np.isnan(day_ahead).any(axis=1) & ~np.isnan(real_time).any(axis=1)
        day_ahead, real_time = day_ahead[complete], real_time[complete]
        if len(day_ahead) < 30:
            continue
        low = np.nanmin(day_ahead) - 10 if lower_price is None else lower_price
        high = np.nanmax(day_ahead) + 10 if upper_price is None else upper_price
        options = day_ahead.shape[1]
        translated = np.concatenate([day_ahead - low, high - day_ahead], axis=1)
        payoffs = np.concatenate([real_time - day_ahead, day_ahead - real_time], axis=1)
        budget = DPDS_BUDGET_SHARE * 2 * options * (high - low)
        size = min(grid_points, len(day_ahead) - 1)
        grid = np.linspace(0.0, budget, size + 1)
        mean, square = option_payoff_steps(translated, payoffs, grid)
        count = len(day_ahead)
        values = mean - risk_penalty * count / (count - 1) * (square - mean**2)
        values[:, 0] = 0.0  # x′ = 0 is not bidding
        chosen = allocate_budget(values)
        bid_levels = grid[chosen]
        expected = values[np.arange(len(chosen)), chosen]
        dec_level, inc_level = bid_levels[:options], bid_levels[options:]
        dec_value, inc_value = expected[:options], expected[options:]
        is_dec = (dec_level > 0) & (dec_value > 0) & ((inc_level == 0) | (dec_value >= inc_value))
        is_inc = (inc_level > 0) & (inc_value > 0) & ~is_dec
        day_side = np.where(is_dec, 1, np.where(is_inc, -1, 0)).reshape(HOURS_PER_DAY, hubs)
        day_limit = np.where(
            is_dec, dec_level + low, np.where(is_inc, high - inc_level, 0.0)
        ).reshape(HOURS_PER_DAY, hubs)
        side[offset] = day_side
        limit[offset] = day_limit
        power[offset] = np.where(day_side != 0, caps_mw[None, :], 0.0)
    return Decisions(start, side, limit, power)
