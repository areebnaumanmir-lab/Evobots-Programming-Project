"""M6 (and M4's planted-signal test): MAP-Elites runs, resume, lineage, the best bot.

- A resumed run is byte-identical to an uninterrupted one (`docs/design_spec.md` §11.1).
- The number of worker processes doesn't change the result.
- Every trader regenerates exactly from its birth record.
- The search recovers a planted rule and finds nothing in pure noise (§16, M4).
"""

import json

import pytest

from evobots.bots.trader import genome_id, trader_decisions
from evobots.features.inputs import synthetic_feature_inputs
from evobots.qd.evaluation import Evaluator
from evobots.qd.run import Run, SearchSettings
from evobots.simulate.market import planted_hub_market

SMALL = dict(
    evaluations=360,
    batch_size=40,
    initial_population=40,
    window_years=1,
    evaluations_per_window=150,
)


@pytest.fixture(scope="module")
def evaluator():
    return Evaluator.synthetic(days=1500, seed=3)


def test_resume_is_byte_identical(evaluator, tmp_path):
    straight = Run(SearchSettings(run_id="R1", seed=4, **SMALL), evaluator, tmp_path / "straight")
    straight.run_until_done()
    interrupted = Run(
        SearchSettings(run_id="R1", seed=4, **SMALL), evaluator, tmp_path / "interrupted"
    )
    interrupted.run_until_done(max_batches=3)
    assert interrupted.evaluations_done < 360
    resumed = Run.resume(tmp_path / "interrupted", evaluator)
    resumed.run_until_done()
    assert resumed.window_index == straight.window_index >= 1
    assert resumed.state_digest() == straight.state_digest()


def test_worker_count_does_not_change_the_run(evaluator):
    one = Run(SearchSettings(run_id="R2", seed=5, workers=1, **SMALL), evaluator)
    one.run_until_done()
    two = Run(SearchSettings(run_id="R2", seed=5, workers=2, **SMALL), evaluator)
    two.run_until_done()
    assert one.state_digest() == two.state_digest()


def test_every_trader_regenerates_from_its_birth_record(evaluator):
    run = Run(SearchSettings(run_id="R3", seed=6, **SMALL), evaluator)
    run.run_until_done()
    for birth in range(1, run.evaluations_done + 1):
        record = run.lineage.record(f"R3-{birth}")
        assert genome_id(run.regenerate(record.trader_id)) == record.genome_id
    elite = next(iter(run.archive.values()))
    assert set(run.lineage.ancestors(elite.trader_id)) >= set(elite.record.parent_ids)


def test_deployable_file_is_written(evaluator, tmp_path):
    run = Run(SearchSettings(run_id="R4", seed=7, **SMALL), evaluator, tmp_path / "R4")
    run.run_until_done()
    current = json.loads((tmp_path / "R4/deployable/current_bot.json").read_text())
    assert current["decision"] in {"trade", "do nothing"}
    if current["decision"] == "trade":
        assert (tmp_path / f"R4/deployable/trader_{current['trader_id']}.py").exists()
    else:
        assert current["failed_gate"]


def planted_evaluator(premium, seed):
    market, forecast_high, is_planted = planted_hub_market(
        days=2600, seed=seed, planted_premium_usd_per_mwh=premium
    )
    inputs = synthetic_feature_inputs(
        market.days, market.hubs, seed=seed, forecast_high_degf=forecast_high
    )
    return Evaluator.synthetic(market=market, inputs=inputs), is_planted


PLANTED_SEARCH = dict(evaluations=2400, batch_size=100, initial_population=100, window_years=5)


@pytest.mark.slow
def test_search_recovers_a_planted_rule():
    evaluator, is_planted = planted_evaluator(premium=6.0, seed=21)
    run = Run(SearchSettings(run_id="P1", seed=1, **PLANTED_SEARCH), evaluator)
    run.run_until_done()
    current = run.current_bot()
    assert current["decision"] == "trade", current
    best = run.best
    _, end, forward_end = run.window()
    decisions = trader_decisions(best.genome, evaluator.store, end, forward_end, evaluator.caps_mw)
    dec_bids = decisions.side == 1
    planted = is_planted[end:forward_end]
    precision = (dec_bids & planted).sum() / max(dec_bids.sum(), 1)
    recall = (dec_bids & planted).sum() / planted.sum()
    base_rate = planted.mean()
    # The best bot bids DEC on (nearly) every planted hub-hour, and its DEC bids are far more
    # concentrated there than chance (round 37: 19 % vs a 2.5 % base rate, recall 100 %).
    assert base_rate < 0.1
    assert recall > 0.8
    assert precision > 4 * base_rate
    used = set(best.genome.features())
    assert used & {"temp_max_fcst", "cdd_fcst", "temp_min_fcst", "hdd_fcst"}
    assert "hour" in used
    assert best.forward.log_growth > 0


@pytest.mark.slow
def test_search_finds_nothing_in_pure_noise():
    evaluator, _ = planted_evaluator(premium=0.0, seed=22)
    run = Run(SearchSettings(run_id="P2", seed=1, **PLANTED_SEARCH), evaluator)
    run.run_until_done()
    assert run.current_bot()["decision"] == "do nothing"
