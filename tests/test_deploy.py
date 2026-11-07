"""M9: export-bot (the equivalence-checked file) and paper trading on forward days."""

import dataclasses
import datetime

import numpy as np
import pytest

from evobots.bots.founders import FOUNDERS
from evobots.bots.source import genome_from_source
from evobots.bots.trader import genome_id
from evobots.data.periods import FORWARD_FIRST_DAY, HOLDOUT_FIRST_DAY, HOLDOUT_LAST_DAY
from evobots.deploy.export import export_bot
from evobots.deploy.paper import paper_trade, read_paper_result, write_paper_result
from evobots.deploy.vintages import save_vintages
from evobots.features.inputs import synthetic_feature_inputs
from evobots.features.store import build_feature_store
from evobots.qd.evaluation import Evaluator
from evobots.simulate.market import synthetic_hub_market


def test_export_bot_writes_an_equivalent_file_that_parses_back(tmp_path):
    evaluator = Evaluator.synthetic(days=400, seed=3)
    genome = FOUNDERS["heat_dec"]
    path = tmp_path / "bot_R1-5.py"
    result = export_bot(genome, {"trader_id": "R1-5", "run_id": "R1"}, evaluator, path, 20)
    assert result["mismatches"] == 0 and result["rows_checked"] == 20 * 24 * 8
    assert genome_id(genome_from_source(path.read_text())) == genome_id(genome)


def forward_evaluator(newest_day=datetime.date(2026, 10, 20), seed=4):
    """A synthetic market to the day after newest_day, with the sealed year blank and RT for
    the last 5 days not yet final."""
    last_day = newest_day + datetime.timedelta(days=1)
    market = synthetic_hub_market(days=2000, seed=seed, last_day=last_day)
    days = np.array(market.days, dtype="datetime64[D]")
    sealed = (days >= np.datetime64(HOLDOUT_FIRST_DAY)) & (days <= np.datetime64(HOLDOUT_LAST_DAY))
    day_ahead, real_time = market.day_ahead.copy(), market.real_time.copy()
    day_ahead[sealed] = real_time[sealed] = np.nan
    day_ahead[-1] = real_time[-1] = np.nan  # the next operating day
    real_time[-6:] = np.nan
    market = dataclasses.replace(market, day_ahead=day_ahead, real_time=real_time)
    inputs = synthetic_feature_inputs(market.days, market.hubs, seed=seed + 1)
    return Evaluator(market, build_feature_store(market, inputs)), newest_day


def test_paper_ledger_settles_forward_days_and_lists_the_next_bids(tmp_path):
    evaluator, newest = forward_evaluator()
    result = paper_trade(FOUNDERS["always_inc"], evaluator, newest, "test")
    days = [row[0] for row in result.ledger]
    assert days[0] == FORWARD_FIRST_DAY.isoformat() and days[-1] == newest.isoformat()
    statuses = [row[1] for row in result.ledger]
    assert statuses[-5:] == ["waiting for RT"] * 5 and statuses[-6] == "settled"
    assert result.next_day == newest + datetime.timedelta(days=1)
    assert result.next_bids and all(bid["side"] == "INC" for bid in result.next_bids)
    # sizing has an estimate from the observed days before the sealed year (0 would mean none)
    assert result.next_bids[0]["position_scale"] > 0
    write_paper_result(result, tmp_path)
    summary, ledger, bids = read_paper_result(tmp_path)
    assert summary["settled_days"] == statuses.count("settled") and len(bids) == len(
        result.next_bids
    )


def test_doing_nothing_keeps_the_capital():
    evaluator, newest = forward_evaluator()
    result = paper_trade(None, evaluator, newest, "do nothing")
    assert result.summary["pnl_usd"] == 0 and result.next_bids == []


def test_vintages_need_the_contact_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lines = save_vintages(tmp_path / "vintages", opener=pytest.fail)
    assert "contact_email" in lines[0]
