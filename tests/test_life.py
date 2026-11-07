"""M6b: Life mode, the market-time ecology (`docs/design_spec.md` §11.3)."""

import numpy as np

from evobots.qd.evaluation import Evaluator
from evobots.qd.life import LifeSettings, run_life


def test_life_mode_is_deterministic_and_keeps_family_trees():
    evaluator = Evaluator.synthetic(days=1600, seed=3)
    # k = 1.3 so that the demo market's INC traders reproduce within 4.4 years.
    settings = LifeSettings(seed=4, initial_random=12, max_population=40, reproduction_multiple=1.3)
    first = run_life(evaluator, settings)
    second = run_life(evaluator, settings)
    assert [trader.trader_id for trader in first.traders] == [
        trader.trader_id for trader in second.traders
    ]
    assert np.array_equal(first.total_equity_by_day, second.total_equity_by_day)
    children = [trader for trader in first.traders if trader.parent_id is not None]
    assert children
    by_id = {trader.trader_id: trader for trader in first.traders}
    for child in children:
        parent = by_id[child.parent_id]
        assert child.generation == parent.generation + 1
        assert child.birth_index > parent.birth_index
        assert child.trader_id in parent.children
    assert first.population_by_day.max() <= 40
    assert first.births_by_day.sum() == len(first.traders)
