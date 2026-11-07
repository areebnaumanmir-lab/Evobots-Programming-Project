"""Quick deployment gates run at every checkpoint (`docs/design_spec.md` §11.1, §12.2).

- G1 survival: stationary-bootstrap paths of the training window's daily returns (Politis–White
  block length): at least 95 % of paths stay within the 50 % loss mandate
- G2 skill vs trials: deflated Sharpe ratio ≥ 0.95 on the training window, with the effective number
  of trials
- G4 cost stress: positive log growth on the next unseen year with fees and uplift doubled
- G6 walk-forward: positive log growth on the next unseen year, with drawdown within the 50 %
  mandate

**Effective trials** (G2): the participation ratio of a reservoir sample of the run's evaluated
traders' daily P&L on the current window, scaled from the sample to every distinct behaviour
the run (and, for a Refine run, its parent runs) has evaluated:
N_eff = ratio × distinct behaviours ÷ sample size. A documented choice: it counts how many
independent bets the search has really made.

The full report card (M7) runs every gate with more paths.

Example:
    >>> import numpy as np
    >>> bootstrap_survival(np.full(400, 0.001), 1.0, paths=50, seed=1)
    1.0
"""

import numpy as np

from evobots.assess.statistics import (
    deflated_sharpe_ratio,
    effective_trial_count,
    politis_white_block_length,
    stationary_bootstrap_indices,
)

MANDATE_DRAWDOWN_FRACTION = 0.5
SURVIVAL_SHARE_REQUIRED = 0.95
DEFLATED_SHARPE_REQUIRED = 0.95
QUICK_BOOTSTRAP_PATHS = 200


def bootstrap_survival(daily_returns, starting_capital_usd, paths=QUICK_BOOTSTRAP_PATHS, seed=0):
    """Share of stationary-bootstrap paths that stay within the loss mandate."""
    returns = np.asarray(daily_returns, dtype=float)
    if len(returns) < 10:
        return 0.0
    block = politis_white_block_length(returns)
    generator = np.random.Generator(np.random.PCG64(seed))
    survived = 0
    for _ in range(paths):
        sample = returns[stationary_bootstrap_indices(len(returns), block, generator)]
        path = np.cumprod(1 + sample)
        peaks = np.maximum.accumulate(np.concatenate([[1.0], path]))[1:]
        if np.min(path / peaks) > 1 - MANDATE_DRAWDOWN_FRACTION and path.min() > 0:
            survived += 1
    return survived / paths


def effective_trials(reservoir_pnl, distinct_behaviours):
    """N_eff from a reservoir of daily P&L streams scaled to all distinct behaviours."""
    if not reservoir_pnl:
        return max(1.0, float(distinct_behaviours))
    matrix = np.column_stack(reservoir_pnl)
    ratio = effective_trial_count(matrix)
    return max(1.0, ratio * distinct_behaviours / len(reservoir_pnl))


def null_sharpe_variance(day_count):
    """Sampling variance of a per-day Sharpe estimate when the true Sharpe is zero: 1/(T − 1).

    The deflated Sharpe's benchmark is the best Sharpe that N skill-less trials would show by
    luck. Bailey & López de Prado estimate V[SR] from the trials' own spread, but in a search
    where many traders share a real edge (or its mirror) that spread measures skill, not
    luck, and would deflate a genuine edge away. Under the null every trial's estimate has
    variance about 1/(T − 1), so that is used (a documented choice, round 37).
    """
    return 1.0 / max(day_count - 1, 1)


def quick_gates(elite, starting_capital_usd, reservoir_pnl, distinct_behaviours, seed=0):
    """{gate: (passed, detail)} for G1, G2, G4, G6 (forward evaluations must be filled)."""
    training_returns = elite.evaluation.daily_returns(starting_capital_usd)
    survival = bootstrap_survival(training_returns, starting_capital_usd, seed=seed)
    trials = effective_trials(reservoir_pnl, distinct_behaviours)
    deflated = deflated_sharpe_ratio(
        training_returns, null_sharpe_variance(len(training_returns)), trials
    )
    forward = elite.forward
    doubled = elite.forward_doubled_costs
    return {
        "G1 survival": (
            survival >= SURVIVAL_SHARE_REQUIRED,
            f"{survival:.0%} of {QUICK_BOOTSTRAP_PATHS} bootstrap paths stay within a 50 % loss",
        ),
        "G2 skill vs trials": (
            deflated >= DEFLATED_SHARPE_REQUIRED,
            f"deflated Sharpe {deflated:.2f} against {trials:,.0f} effective trials",
        ),
        "G4 cost stress": (
            doubled is not None and doubled.log_growth > 0,
            "next-year growth with doubled costs "
            + (f"{doubled.log_growth:+.3f}" if doubled is not None else "not scored"),
        ),
        "G6 walk-forward": (
            forward is not None
            and forward.log_growth > 0
            and forward.max_drawdown_fraction < MANDATE_DRAWDOWN_FRACTION,
            "next-year growth "
            + (
                f"{forward.log_growth:+.3f}, drawdown {forward.max_drawdown_fraction:.0%}"
                if forward is not None
                else "not scored"
            ),
        ),
    }
