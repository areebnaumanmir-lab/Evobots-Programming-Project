"""The methods leaderboard: every strategy class under one protocol (§20.11).

Same evaluation days, costs (and doubled costs), point-in-time data, sizing rule, career
model and gates for everything; trial counts tracked per strategy class, so the deflated
Sharpe ratio is fair to each; and a model confidence set across the classes (Hansen, Lunde &
Nason 2011) on their daily losses.

A strategy is a name, a class, its trial count and a function giving its `Decisions` for
market days start … end−1 (with the sizing history before start). Baselines, evolved elites,
the optimization bidders (O2), DPDS and the portfolio of elites (O3) all fit that shape.

Example:
    >>> from evobots.qd.evaluation import Evaluator
    >>> evaluator = Evaluator.synthetic(days=900, seed=3)
    >>> rows, kept = leaderboard(evaluator, baseline_strategies(evaluator), 500, 900)
    >>> names = {"always INC", "always DEC", "do nothing", "1 MW INC at one hub", "persistence"}
    >>> rows[0]["strategy"] in names
    True
"""

import dataclasses

import numpy as np

from evobots.assess.inference import model_confidence_set
from evobots.assess.statistics import deflated_sharpe_ratio, sharpe_ratio
from evobots.bots.founders import FOUNDERS
from evobots.career.model import apply_career
from evobots.qd.gates import MANDATE_DRAWDOWN_FRACTION, bootstrap_survival, null_sharpe_variance
from evobots.simulate.settlement import SIZING_HISTORY_DAYS, Decisions, settle


@dataclasses.dataclass(frozen=True)
class Strategy:
    """One leaderboard entry.

    Attributes:
        name: shown on the board.
        strategy_class: "baseline", "evolved", "optimizer", "online", "portfolio".
        trials: how many variants of this class were tried before choosing this one.
        decisions: callable(start, end) → Decisions covering start − history … end − 1.
        is_bound: an upper bound, never a strategy (perfect foresight).
    """

    name: str
    strategy_class: str
    trials: int
    decisions: object
    is_bound: bool = False


def genome_strategy(evaluator, name, genome, strategy_class="baseline", trials=1):
    """A strategy from a trader genome."""
    return Strategy(
        name, strategy_class, trials, lambda start, end: evaluator.decisions(genome, start, end)
    )


def baseline_strategies(evaluator):
    """Do nothing, 1 MW INC at one hub, always INC, always DEC, persistence (§12.1)."""

    def nothing(start, end):
        history = max(0, start - SIZING_HISTORY_DAYS)
        shape = (end - history, 24, len(evaluator.store.locations))
        return Decisions(history, np.zeros(shape, dtype=np.int8), np.zeros(shape), np.zeros(shape))

    def one_hub(start, end):
        decisions = evaluator.decisions(FOUNDERS["always_inc"], start, end)
        power = np.zeros_like(decisions.full_size_mw)
        power[:, :, 0] = np.where(decisions.side[:, :, 0] != 0, 1.0, 0.0)
        return dataclasses.replace(
            decisions,
            full_size_mw=power,
            side=np.where(power > 0, decisions.side, 0).astype(np.int8),
        )

    return [
        Strategy("do nothing", "baseline", 1, nothing),
        Strategy("1 MW INC at one hub", "baseline", 1, one_hub),
        genome_strategy(evaluator, "always INC", FOUNDERS["always_inc"]),
        genome_strategy(evaluator, "always DEC", FOUNDERS["always_dec"]),
        genome_strategy(evaluator, "persistence", FOUNDERS["persistence"]),
    ]


def score_strategy(evaluator, strategy, start, end, cost_multiple=1.0):
    """Settle and apply the career model; returns (CareerOutcome, SettlementResult)."""
    decisions = strategy.decisions(start, end)
    rules = dataclasses.replace(
        evaluator.account_rules(FOUNDERS["always_inc"], cost_multiple), max_mwh_per_day=np.inf
    )
    result = settle(decisions, evaluator.market, start, end, rules, evaluator.cost_table)
    risk_free = None if evaluator.risk_free_daily is None else evaluator.risk_free_daily[start:end]
    return apply_career(result, evaluator.career, 0, risk_free), result


def leaderboard(evaluator, strategies, start, end):
    """Rows (best first) and the model confidence set of strategy names."""
    capital = evaluator.capital.starting_capital_usd
    rows, losses = [], []
    for strategy in strategies:
        outcome, result = score_strategy(evaluator, strategy, start, end)
        doubled, _ = score_strategy(evaluator, strategy, start, end, cost_multiple=2.0)
        before = np.concatenate([[capital], outcome.equity_usd[:-1]])
        returns = np.where(before > 0, outcome.daily_pnl_usd / before, 0.0)
        peaks = np.maximum.accumulate(np.concatenate([[capital], outcome.equity_usd]))[1:]
        drawdown = float(np.max(1 - outcome.equity_usd / peaks)) if len(peaks) else 0.0
        traded = np.any(outcome.daily_pnl_usd != 0)
        rows.append(
            {
                "strategy": strategy.name,
                "class": strategy.strategy_class,
                "trials": strategy.trials,
                "is_bound": strategy.is_bound,
                "log_growth": outcome.log_growth,
                "fitness": outcome.fitness,
                "log_growth_doubled_costs": doubled.log_growth,
                "annual_sharpe": sharpe_ratio(returns) if traded else 0.0,
                "deflated_sharpe": deflated_sharpe_ratio(
                    returns, null_sharpe_variance(len(returns)), max(strategy.trials, 1)
                )
                if traded
                else 0.0,
                "max_drawdown_fraction": drawdown,
                "is_alive": outcome.stop_index is None,
                "survival_share": bootstrap_survival(returns, capital, paths=200)
                if traded
                else 1.0,
                "cleared_mwh": result.cleared_mwh,
                "within_mandate": drawdown < MANDATE_DRAWDOWN_FRACTION,
            }
        )
        losses.append(-outcome.daily_pnl_usd)
    candidates = [index for index, row in enumerate(rows) if not row["is_bound"]]
    kept, _ = model_confidence_set(
        np.column_stack([losses[index] for index in candidates]), alpha=0.10, draws=300
    )
    kept_names = [rows[candidates[index]]["strategy"] for index in kept]
    for row in rows:
        row["in_model_confidence_set"] = row["strategy"] in kept_names
    rows.sort(key=lambda row: -row["fitness"])
    return rows, kept_names
