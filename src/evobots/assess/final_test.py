"""G8: the sealed 12-month test, once per finished run (`docs/design_spec.md` §7.2, §12.4).

`final_test(run_directory, evaluator)` is the only path that opens the hold-out
(2025-09-22 → 2026-09-21). It:
1. picks the run's chosen trader (the best bot, or a trader named explicitly);
2. refuses if this run's sealed test was already opened (the access log says so);
3. logs the opening (`evobots.data.holdout.open_holdout`) **before** reading anything;
4. reads the hold-out's MISO prices, forecasts, gas and EPU with that permission;
5. appends them to the evolution data, rebuilds the features point-in-time, and scores the
   trader on the hold-out days with the same account, costs and career as the run;
6. writes `runs/<id>/final_test.json`.

Once opened, the lineage's sealed test is spent: a Refine run of this trader is labelled
"hold-out already used" (§11.5), and only forward data (2026-09-22 onward) stays clean.

Run: `evobots final-test runs/R12 [--trader R12-184213]` (needs the hold-out files built on
this machine; tests use a temporary fake hold-out).
"""

import dataclasses
import datetime
import json
from pathlib import Path

import numpy as np

from evobots.data import holdout
from evobots.data.forecasts import forecast_rows_for_decision_day
from evobots.data.periods import HOLDOUT_FIRST_DAY, HOLDOUT_LAST_DAY
from evobots.data.sources.eia860m import read_units
from evobots.data.sources.miso_eras import read_day
from evobots.data.sources.series import read_eia_daily_spot, read_epu
from evobots.features.inputs import (
    FeatureInputs,
    capacity_table_from_units,
    cloud_fraction,
    newest_file,
)
from evobots.features.store import build_feature_store
from evobots.qd.run import Run
from evobots.simulate.market import HubMarket

HOURS_PER_DAY = 24
RESULT_FILE_NAME = "final_test.json"


class FinalTestRefusedError(RuntimeError):
    """The sealed test can't be run (already opened for this run, or nothing to test)."""


def run_ids_with_opened_holdout(log_path=holdout.ACCESS_LOG_PATH):
    """Runs whose sealed test was opened (a Refine run of their traders is "hold-out used")."""
    return {opening["run_id"] for opening in holdout.holdout_openings(log_path)}


def holdout_days():
    """Every hold-out operating day."""
    count = (HOLDOUT_LAST_DAY - HOLDOUT_FIRST_DAY).days + 1
    return [HOLDOUT_FIRST_DAY + datetime.timedelta(days=offset) for offset in range(count)]


def holdout_market(market, raw_directory, permission):
    """The evolution market extended by the hold-out year read with permission."""
    days = holdout_days()
    hub_index = {hub: index for index, hub in enumerate(market.hubs)}
    shape = (len(days), HOURS_PER_DAY, len(market.hubs))
    arrays = {name: np.full(shape, np.nan) for name in ("da", "rt", "da_mcc")}
    for day_index, day in enumerate(days):
        for kind in ("da", "rt"):
            prices = read_day(raw_directory, day, kind, holdout_permission=permission)
            if prices is None:
                continue
            for hub in prices.trading_hubs():
                if hub not in hub_index:
                    continue
                for value_type, target in (
                    (("LMP"), kind),
                    ("MCC", "da_mcc" if kind == "da" else None),
                ):
                    hours = prices.hours_by_location_and_value.get((hub, value_type))
                    if hours is None or target is None:
                        continue
                    for hour, value in enumerate(hours[:HOURS_PER_DAY]):
                        if value is not None:
                            arrays[target][day_index, hour, hub_index[hub]] = value
    congestion = (
        market.day_ahead_congestion
        if market.day_ahead_congestion is not None
        else np.full_like(market.day_ahead, np.nan)
    )
    return HubMarket(
        days=tuple(market.days) + tuple(days),
        hubs=market.hubs,
        day_ahead=np.concatenate([market.day_ahead, arrays["da"]]),
        real_time=np.concatenate([market.real_time, arrays["rt"]]),
        source=market.source + " + sealed hold-out",
        day_ahead_congestion=np.concatenate([congestion, arrays["da_mcc"]]),
        location_types=market.location_types,
    )


def holdout_inputs(inputs, nws_directory, series_root, permission):
    """The evolution inputs extended by hold-out forecasts, capacity, gas and EPU."""
    forecasts = dict(inputs.forecasts)
    for day in holdout_days():
        decision_day = day - datetime.timedelta(days=1)
        for row in forecast_rows_for_decision_day(
            nws_directory, decision_day, holdout_permission=permission
        ):
            if row["status"] != "ok":
                continue

            def number(column, row=row):
                return float(row[column]) if row[column] not in ("", None) else None

            key = (decision_day, row["hub"], datetime.date.fromisoformat(row["target_day"]))
            forecasts[key] = (
                number("max_temp_degf"),
                number("min_temp_degf"),
                number("mean_wind_mph"),
                cloud_fraction(row["cloud_codes"]),
            )
    capacity = dict(inputs.capacity)
    workbook = newest_file(Path(series_root) / "eia_860m", "*.xlsx")
    if workbook is not None:
        capacity.update(
            capacity_table_from_units(
                read_units(workbook), last_month=(HOLDOUT_LAST_DAY.year, HOLDOUT_LAST_DAY.month)
            )
        )
    gas_path = newest_file(Path(series_root) / "eia_henry_hub", "*.xls")
    epu_path = newest_file(Path(series_root) / "epu", "*.csv")
    gas = (
        read_eia_daily_spot(gas_path, "RNGWHHD", holdout_permission=permission)
        if gas_path
        else inputs.gas
    )
    epu = read_epu(epu_path, holdout_permission=permission) if epu_path else inputs.epu
    return FeatureInputs(forecasts, capacity, gas, epu, inputs.description + " + sealed hold-out")


def final_test(
    run_directory,
    evaluator,
    inputs,
    trader_id=None,
    opened_by="final-test",
    log_path=holdout.ACCESS_LOG_PATH,
    holdout_root=holdout.HOLDOUT_DIRECTORY,
    series_root=Path("data/raw/series"),
):
    """Run the sealed test once for a run's chosen trader (see the module docstring).

    Args:
        run_directory: runs/<id> with a checkpoint.
        evaluator: the run's Evaluator (evolution data).
        inputs: the FeatureInputs the evaluator's store was built from.
        trader_id: test this elite instead of the best bot.
        opened_by: who asked (logged).
        log_path: the access log (tests use a temporary one).
        holdout_root: the hold-out folder (tests use a fake one).
        series_root: where the downloaded daily series are.

    Returns:
        The result dict (also written to runs/<id>/final_test.json).
    """
    run_directory = Path(run_directory)
    run = Run.resume(run_directory, evaluator)
    run_id = run.settings.run_id
    if any(opening["run_id"] == run_id for opening in holdout.holdout_openings(log_path)):
        raise FinalTestRefusedError(
            f"the sealed test of {run_id} was already opened; it is used once per run"
        )
    if trader_id is None:
        best = run.choose_best()
        if best is None:
            raise FinalTestRefusedError(
                "the run's decision is 'do nothing': name a trader to test it anyway"
            )
        elite = best
    else:
        elite = next(
            (candidate for candidate in run.archive.values() if candidate.trader_id == trader_id),
            None,
        )
        if elite is None:
            raise FinalTestRefusedError(f"{trader_id} is not an elite of {run_id}")
    permission = holdout.open_holdout(run_id, elite.trader_id, opened_by, log_path)
    raw = Path(holdout_root) / "raw"
    market = holdout_market(evaluator.market, raw / "miso", permission)
    store = build_feature_store(
        market, holdout_inputs(inputs, raw / "nws", series_root, permission)
    )
    sealed_evaluator = dataclasses.replace(evaluator, market=market, store=store)
    sealed_evaluator.cache = type(evaluator.cache)()
    first = len(evaluator.market.days)
    result = sealed_evaluator.evaluate(elite.genome, first, len(market.days))
    doubled = sealed_evaluator.evaluate(elite.genome, first, len(market.days), cost_multiple=2.0)
    summary = {
        "run_id": run_id,
        "trader_id": elite.trader_id,
        "opened_by": opened_by,
        "opened_at_utc": permission.opened_at_utc.isoformat(),
        "days": [HOLDOUT_FIRST_DAY.isoformat(), HOLDOUT_LAST_DAY.isoformat()],
        "log_growth": result.log_growth,
        "fitness": result.fitness,
        "final_equity_usd": result.final_equity_usd,
        "max_drawdown_fraction": result.max_drawdown_fraction,
        "is_alive": result.is_alive,
        "stop_cause": result.stop_cause,
        "log_growth_doubled_costs": doubled.log_growth,
        "walk_forward_fitness_before": None if elite.forward is None else elite.forward.fitness,
    }
    (run_directory / RESULT_FILE_NAME).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    run.close()
    return summary
