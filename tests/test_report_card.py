"""M7: the report card and the sealed final test (G8), on synthetic data and a fake hold-out.

The real hold-out is never opened by tests: the final test here reads a temporary folder of
fake MISO files and writes to a temporary access log, so the committed log stays "Sealed".
"""

import datetime
import json

import numpy as np
import pytest

from evobots.assess.final_test import FinalTestRefusedError, final_test, holdout_days
from evobots.assess.report_card import ReportContext, report_card
from evobots.assess.report_html import report_html
from evobots.data.holdout import ACCESS_LOG_PATH, holdout_status
from evobots.features.inputs import synthetic_feature_inputs
from evobots.qd.evaluation import Evaluator
from evobots.qd.run import Run, SearchSettings
from evobots.simulate.market import synthetic_hub_market

GATES = [f"G{number}" for number in range(1, 9)]


@pytest.fixture(scope="module")
def finished_run(tmp_path_factory):
    market = synthetic_hub_market(days=1800, seed=3)
    inputs = synthetic_feature_inputs(market.days, market.hubs, seed=4)
    evaluator = Evaluator.synthetic(market=market, inputs=inputs)
    directory = tmp_path_factory.mktemp("runs") / "R9"
    run = Run(
        SearchSettings(run_id="R9", evaluations=240, batch_size=60, seed=2, window_years=2),
        evaluator,
        directory,
    )
    run.run_until_done()
    return run, evaluator, inputs, directory


def test_report_card_covers_every_gate_and_is_json(finished_run):
    run, *_ = finished_run
    elite = run.best or next(iter(run.archive.values()))
    card = report_card(ReportContext.from_run(run), elite, bootstrap_paths=100)
    assert [name.split()[0] for name in card["gates"]] == GATES
    assert {entry["status"] for entry in card["gates"].values()} <= {"pass", "fail", "not run"}
    assert card["gates"]["G8 hold-out"]["status"] == "not run"
    assert card["what_happened"].startswith(card["identity"]["name"])
    text = json.dumps(card)
    assert json.loads(text)["identity"]["trader_id"] == elite.trader_id
    page = report_html(card)
    assert page.startswith("<!doctype html>")
    assert "http://" not in page and "https://" not in page


def write_fake_holdout_day(folder, day, generator):
    header = "Node,Type,Value," + ",".join(f"HE {hour}" for hour in range(1, 25))
    for kind in ("da_expost_lmp", "rt_lmp_final"):
        rows = ["Fake market file", day.strftime("%m/%d/%Y"), "", header]
        for hub in (
            "ARKANSAS.HUB",
            "ILLINOIS.HUB",
            "INDIANA.HUB",
            "LOUISIANA.HUB",
            "MICHIGAN.HUB",
            "MINN.HUB",
            "MS.HUB",
            "TEXAS.HUB",
        ):
            values = 30 + 5 * generator.standard_normal(24)
            rows.append(f"{hub},Hub,LMP," + ",".join(f"{value:.2f}" for value in values))
            if kind.startswith("da"):
                rows.append(f"{hub},Hub,MCC," + ",".join("0.50" for _ in range(24)))
        (folder / f"{day:%Y%m%d}_{kind}.csv").write_text("\n".join(rows) + "\n")


def test_final_test_runs_once_and_is_logged(finished_run, tmp_path):
    run, evaluator, inputs, directory = finished_run
    raw = tmp_path / "holdout" / "raw" / "miso"
    raw.mkdir(parents=True)
    generator = np.random.Generator(np.random.PCG64(1))
    for day in holdout_days()[:60]:
        write_fake_holdout_day(raw, day, generator)
    log_path = tmp_path / "access.jsonl"
    trader = run.best.trader_id if run.best else next(iter(run.archive.values())).trader_id
    result = final_test(
        directory,
        evaluator,
        inputs,
        trader_id=trader,
        opened_by="test",
        log_path=log_path,
        holdout_root=tmp_path / "holdout",
        series_root=tmp_path / "no_series",
    )
    assert result["trader_id"] == trader
    assert result["days"] == ["2025-09-22", "2026-09-21"]
    assert holdout_status(log_path).startswith("Opened on ")
    assert json.loads((directory / "final_test.json").read_text())["trader_id"] == trader
    with pytest.raises(FinalTestRefusedError):
        final_test(
            directory,
            evaluator,
            inputs,
            trader_id=trader,
            log_path=log_path,
            holdout_root=tmp_path / "holdout",
        )
    # The committed access log is untouched.
    assert (
        holdout_status(ACCESS_LOG_PATH) in {"Sealed: never opened"} or not ACCESS_LOG_PATH.exists()
    )
    assert datetime.date(2025, 9, 22) == holdout_days()[0]
