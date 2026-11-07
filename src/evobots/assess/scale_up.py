"""G5 at Stage C: the trader re-scored on every location (`docs/design_spec.md` §12, M8).

A trader evolved on the hubs (Stage A) or on cluster representatives (Stage D) chooses
locations by their properties (type, hub area, congestion share, spread statistics), never by
name, so it can be run unchanged on every priced location. This asks whether its edge
survives when it can bid wherever its rule fires, with the same capital, sizing, credit
limit and daily cap rules.

The whole period at every location doesn't fit in memory (≈ 2,500 locations × 7,500 days ×
24 hours per array), so the re-score covers one period, normally the unseen year, with
`WARM_UP_DAYS` before it for the features, the hub-area codes and the sizing history.

Result (JSON-ready): the period, the number of locations, and for each stage the log growth,
whether it stayed alive, the drawdown, cleared MWh, fees and the number of locations it
traded.
"""

import datetime

import numpy as np

from evobots.simulate.settlement import SIZING_HISTORY_DAYS

# The hub-area code needs 365 visible days; sizing needs SIZING_HISTORY_DAYS.
WARM_UP_DAYS = max(SIZING_HISTORY_DAYS, 372) + 30


def evaluation_row(evaluation, locations_traded):
    """The numbers G5 reports for one stage."""
    return {
        "log_growth": float(evaluation.log_growth),
        "is_alive": bool(evaluation.is_alive),
        "max_drawdown_fraction": float(evaluation.max_drawdown_fraction),
        "cleared_mwh": float(evaluation.cleared_mwh),
        "fees_usd": float(evaluation.fees_usd),
        "locations_traded": int(locations_traded),
    }


def locations_traded(evaluator, genome, start, end):
    """How many columns the trader bids on, where priced, at least once in days start … end−1."""
    decisions = evaluator.decisions(genome, start, end)
    offset = decisions.side.shape[0] - (end - start)
    market = evaluator.market
    is_priced = ~np.isnan(market.day_ahead[start:end]) & ~np.isnan(market.real_time[start:end])
    return int(np.any((decisions.side[offset:] != 0) & is_priced, axis=(0, 1)).sum())


def every_location_rescore(genome, evaluator, first_day, last_day, every_location_evaluator=None):
    """Score a genome on every location for first_day … last_day, beside its own stage.

    Args:
        genome: the trader.
        evaluator: the run's evaluator (Stage A or D).
        first_day: first day of the period (datetime.date), normally the unseen year.
        last_day: its last day.
        every_location_evaluator: an evaluator over every location covering the period and
            WARM_UP_DAYS before it (None: built from the store on this machine).

    Returns:
        A dict, or None when the Stage C store isn't built here.
    """
    if every_location_evaluator is None:
        from evobots.qd.evaluation import Evaluator

        every_location_evaluator = Evaluator.from_store(
            capital=evaluator.capital,
            career=evaluator.career,
            stage="C",
            first_day=first_day - datetime.timedelta(days=WARM_UP_DAYS),
            last_day=last_day,
        )
        if every_location_evaluator is None:
            return None
    start_every = every_location_evaluator.index_of(first_day)
    end_every = every_location_evaluator.index_of(last_day + datetime.timedelta(days=1))
    start_own = evaluator.index_of(first_day)
    end_own = evaluator.index_of(last_day + datetime.timedelta(days=1))
    every_location = every_location_evaluator.evaluate(genome, start_every, end_every)
    own = evaluator.evaluate(genome, start_own, end_own)
    return {
        "period": [first_day.isoformat(), last_day.isoformat()],
        "locations": len(every_location_evaluator.store.locations),
        "own_stage_locations": len(evaluator.store.locations),
        "stage_c": evaluation_row(
            every_location,
            locations_traded(every_location_evaluator, genome, start_every, end_every),
        ),
        "own_stage": evaluation_row(own, locations_traded(evaluator, genome, start_own, end_own)),
    }
