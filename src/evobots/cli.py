"""Command line.

- `python -m evobots.cli capital [config] [--starting-capital …]`: the capital settings.
- `python -m evobots.cli data build --stage A [--raw …] [--store …] [--workers N]`: the hub
  price store from the MISO files on disk, checked against the recorded statistics (M1).
- `evobots serve [--port 8765] [--no-browser] [--demo]`: the local app in the browser.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from evobots.capital_summary import capital_summary
from evobots.config import load_capital
from evobots.config.capital import MINIMUM_MPD_USD_PER_MWH, VIRTUAL_EXPOSURE_WINDOW_DAYS

# Full-sample 1-in-100-day full-size loss, 2019-01-01 → 2025-09-21, worse direction (always-INC),
# USD (capital_sizing.md §4; reproduced in round 21). CALIBRATION ONLY: it contains every storm
# of the sample, so simulation code must never use it; tests/test_sizing.py enforces that.
CALIBRATION_ONLY_FULL_SAMPLE_P99_USD = 27_897
# Worst 20-day full-size loss over the same sample (always-INC, ending in Winter Storm Elliott),
# USD (capital_sizing.md §5; reproduced in round 22). CALIBRATION ONLY, as above.
CALIBRATION_ONLY_FULL_SAMPLE_WORST_20_DAY_LOSS_USD = 484_372


def calibration_capital_summary(settings, cleared_share_fraction=0.72):
    """capital_summary at the full-sample calibration losses (for display, never simulation).

    Example:
        >>> from evobots.config.capital import CapitalSettings
        >>> round(calibration_capital_summary(CapitalSettings())["full_size_capital_usd"])
        1394850
    """
    return capital_summary(
        settings,
        CALIBRATION_ONLY_FULL_SAMPLE_P99_USD,
        CALIBRATION_ONLY_FULL_SAMPLE_WORST_20_DAY_LOSS_USD,
        cleared_share_fraction,
    )


def capital_report_lines(settings):
    """Plain-English lines describing a CapitalSettings, for the `capital` command."""
    summary = calibration_capital_summary(settings)
    caps = settings.hub_caps_mw()
    full_size_mwh = summary["full_size_mwh_per_day"]
    lines = [
        f"Starting capital: ${settings.starting_capital_usd:,.0f}",
        f"Daily risk budget: {settings.daily_risk_budget_fraction:.1%} of equity on a 1-in-100 day",
        "Per-hub caps (MW): " + ", ".join(f"{hub} {cap:g}" for hub, cap in caps.items()),
        f"Full size: {sum(caps.values()):g} MW x 24 h = {full_size_mwh:g} MWh per day",
        f"Full size is reached at ${summary['full_size_capital_usd']:,.0f} (full-sample p99, "
        "calibration only; point-in-time it varies, capital_sizing.md §4b)",
        f"MISO collateral at full size: {full_size_mwh:g} MWh x ${MINIMUM_MPD_USD_PER_MWH:g} MPD x "
        f"{VIRTUAL_EXPOSURE_WINDOW_DAYS} days = ${summary['collateral_at_full_size_usd']:,.0f}",
        "Virtual MWh Limit the pledged credit supports: "
        f"{summary['virtual_mwh_limit_mwh_per_day']:,.0f} MWh per day",
    ]
    if summary["ruin_floor_usd"] is None:
        lines.append("Death: out of money (no capital floor set)")
    else:
        lines.append(
            f"Capital floor: ${summary['ruin_floor_usd']:,.0f}; "
            f"headroom {summary['headroom_fraction']:.1%}"
        )
    lines += [f"Warning: {message}" for message in summary["warnings"]]
    return lines


def main(argv=None):
    """Entry point."""
    parser = argparse.ArgumentParser(prog="evobots")
    commands = parser.add_subparsers(dest="command", required=True)
    capital = commands.add_parser("capital", help="show the capital settings and what they imply")
    capital.add_argument("config", nargs="?", help="TOML file with a [capital] table")
    capital.add_argument("--starting-capital", type=float, dest="starting_capital_usd")
    capital.add_argument("--daily-risk-budget", type=float, dest="daily_risk_budget_fraction")
    capital.add_argument("--credit-share", type=float, dest="credit_share_fraction")
    capital.add_argument("--max-mw-per-hub-hour", type=float, dest="max_mw_per_hub_hour")
    capital.add_argument("--ruin-floor-fraction", type=float, dest="ruin_floor_fraction")
    capital.add_argument("--ruin-floor-usd", type=float, dest="ruin_floor_usd")
    data = commands.add_parser("data", help="build the data store (offline)")
    data_commands = data.add_subparsers(dest="data_command", required=True)
    build = data_commands.add_parser("build", help="build and check a stage's store")
    build.add_argument("--stage", choices=["A", "D", "C"], default="A")
    build.add_argument("--raw", type=Path, default=Path("data/raw/miso"))
    build.add_argument("--store", type=Path, default=Path("data/store"))
    build.add_argument("--workers", type=int, default=4)
    serve = commands.add_parser("serve", help="open the app in the browser (localhost only)")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--demo", action="store_true", help="use synthetic demo data")
    run = commands.add_parser("run", help="run a MAP-Elites search (checkpoints, then exits)")
    run.add_argument("--run-id", help="R<n> (default: the next free number)")
    run.add_argument("--evaluations", type=int, default=20_000, help="budget, in traders scored")
    run.add_argument("--hours", type=float, help="stop after this many hours (resume later)")
    run.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--selection-pressure", type=float, default=0.5)
    run.add_argument("--window-years", type=int, default=5)
    run.add_argument("--no-founders", action="store_true", help="the no-founder control run")
    run.add_argument("--demo", action="store_true", help="synthetic demo data")
    run.add_argument("--runs", type=Path, default=Path("runs"))
    resume = commands.add_parser("resume", help="continue a run from its last checkpoint")
    resume.add_argument("directory", type=Path)
    resume.add_argument("--hours", type=float)
    resume.add_argument("--demo", action="store_true")
    life = commands.add_parser("life", help="run Life mode, the market-time ecology")
    life.add_argument("--seed", type=int, default=1)
    life.add_argument("--initial-random", type=int, default=60)
    life.add_argument("--save", type=Path, help="write a JSON summary for the app")
    life.add_argument("--demo", action="store_true")
    refine = commands.add_parser("refine", help="a new run seeded with an elite (§11.5)")
    refine.add_argument("directory", type=Path, help="the parent run")
    refine.add_argument("trader")
    refine.add_argument("--run-id")
    refine.add_argument("--evaluations", type=int, default=5000)
    refine.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    refine.add_argument("--demo", action="store_true")
    report = commands.add_parser("report", help="write a run's report card (JSON and HTML)")
    report.add_argument("directory", type=Path)
    report.add_argument(
        "--trader", help="an elite's id (default: the best bot, else the nearest candidate)"
    )
    report.add_argument("--demo", action="store_true")
    sealed = commands.add_parser(
        "final-test", help="the sealed 12-month test, once per run (logged)"
    )
    sealed.add_argument("directory", type=Path)
    sealed.add_argument("--trader", help="an elite's id (default: the best bot)")
    sealed.add_argument(
        "--yes", action="store_true", help="confirm: this spends the run's hold-out"
    )
    sealed.add_argument("--opened-by", default="final-test")
    arguments = parser.parse_args(argv)
    if arguments.command == "report":
        return write_report(arguments)
    if arguments.command == "final-test":
        return run_final_test(arguments)
    if arguments.command == "run":
        return run_search(arguments)
    if arguments.command == "resume":
        return resume_search(arguments)
    if arguments.command == "life":
        return run_life_mode(arguments)
    if arguments.command == "refine":
        return run_refine(arguments)
    if arguments.command == "serve":
        return run_serve(arguments)
    if arguments.command == "data":
        return run_data_build(arguments)
    overrides = {
        name: getattr(arguments, name)
        for name in (
            "starting_capital_usd",
            "daily_risk_budget_fraction",
            "credit_share_fraction",
            "max_mw_per_hub_hour",
            "ruin_floor_fraction",
            "ruin_floor_usd",
        )
    }
    try:
        settings = load_capital(arguments.config, overrides)
    except ValueError as error:
        parser.error(str(error))
    print("\n".join(capital_report_lines(settings)))


def run_serve(arguments):
    """`serve`: start the app on localhost and open the browser."""
    import threading
    import webbrowser

    import uvicorn

    from evobots.app import server
    from evobots.service import Service

    print("Loading data …")
    server.service_holder["service"] = Service(is_synthetic=arguments.demo)
    server.app_settings["is_demo"] = arguments.demo
    address = f"http://127.0.0.1:{arguments.port}/"
    print(f"evobots is running at {address} (close this window or press Ctrl+C to stop)")
    if not arguments.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(address)).start()
    uvicorn.run(server.app, host="127.0.0.1", port=arguments.port, log_level="warning")
    return 0


def evaluator_for(is_demo):
    """The MISO evaluator from the data built here, or the synthetic one (with a notice)."""
    from evobots.qd.evaluation import Evaluator

    evaluator = None if is_demo else Evaluator.from_store()
    if evaluator is None:
        print("Using synthetic demo data (no MISO hub table built on this machine).")
        evaluator = Evaluator.synthetic()
    return evaluator


def next_run_id(runs_directory):
    """R<n> with n one more than the highest existing run."""
    numbers = [
        int(path.name[1:]) for path in Path(runs_directory).glob("R*") if path.name[1:].isdigit()
    ]
    return f"R{max(numbers, default=0) + 1}"


def print_progress(run):
    """One status line per batch."""
    best = max((elite.evaluation.fitness for elite in run.archive.values()), default=float("nan"))
    print(
        f"{run.evaluations_done:,}/{run.settings.evaluations:,} traders, window "
        f"{run.window_index + 1}/{len(run.windows)}, {len(run.archive)} elites, best F {best:+.3f}",
        flush=True,
    )


def run_search(arguments):
    """`run`: a MAP-Elites search; checkpoints every 10 minutes and at the end."""
    from evobots.qd.run import Run, SearchSettings

    run_id = arguments.run_id or next_run_id(arguments.runs)
    settings = SearchSettings(
        run_id=run_id,
        seed=arguments.seed,
        evaluations=arguments.evaluations,
        workers=arguments.workers,
        selection_pressure=arguments.selection_pressure,
        window_years=arguments.window_years,
        is_using_founders=not arguments.no_founders,
    )
    run = Run(settings, evaluator_for(arguments.demo), arguments.runs / run_id)
    deadline = None if arguments.hours is None else arguments.hours * 3600
    run.run_until_done(
        deadline_seconds=deadline,
        progress=print_progress,
        should_stop=stop_requested(run.directory),
    )
    print(f"Saved {arguments.runs / run_id}; deployable decision: {run.current_bot()['decision']}")
    return 0


def resume_search(arguments):
    """`resume`: continue a run from its checkpoint."""
    from evobots.qd.run import Run

    run = Run.resume(arguments.directory, evaluator_for(arguments.demo))
    deadline = None if arguments.hours is None else arguments.hours * 3600
    run.run_until_done(
        deadline_seconds=deadline,
        progress=print_progress,
        should_stop=stop_requested(run.directory),
    )
    print(f"Saved {arguments.directory}; deployable decision: {run.current_bot()['decision']}")
    return 0


def stop_requested(directory):
    """A callable that is True once runs/<id>/stop.request exists (the app's Stop)."""
    return lambda: (Path(directory) / "stop.request").exists()


def run_refine(arguments):
    """`refine`: a new run seeded with an elite of an earlier run and mutants of it (§11.5)."""
    from evobots.assess.final_test import run_ids_with_opened_holdout
    from evobots.bots.trader import genome_to_json
    from evobots.qd.run import Run, SearchSettings

    evaluator = evaluator_for(arguments.demo)
    parent = Run.resume(arguments.directory, evaluator)
    elite = next(
        (item for item in parent.archive.values() if item.trader_id == arguments.trader), None
    )
    genome = elite.genome if elite is not None else parent.regenerate(arguments.trader)
    is_holdout_used = (
        parent.settings.is_holdout_used or parent.settings.run_id in run_ids_with_opened_holdout()
    )
    run_id = arguments.run_id or next_run_id(arguments.directory.parent)
    settings = SearchSettings(
        run_id=run_id,
        evaluations=arguments.evaluations,
        workers=arguments.workers,
        seed_genomes=((arguments.trader, genome_to_json(genome)),),
        parent_trader_ids=(arguments.trader,),
        prior_trials=parent.lineage.distinct_behaviours() + parent.settings.prior_trials,
        is_holdout_used=is_holdout_used,
    )
    run = Run(settings, evaluator, arguments.directory.parent / run_id)
    run.lineage.attach(arguments.directory / "lineage.sqlite")
    run.run_until_done(progress=print_progress, should_stop=stop_requested(run.directory))
    label = " (hold-out already used)" if is_holdout_used else ""
    print(f"Saved {run.directory}{label}; deployable decision: {run.current_bot()['decision']}")
    return 0


def run_life_mode(arguments):
    """`life`: simulate the ecology and print (and optionally save) its summary."""
    from evobots.qd.life import LifeSettings, run_life

    result = run_life(
        evaluator_for(arguments.demo),
        LifeSettings(seed=arguments.seed, initial_random=arguments.initial_random),
    )
    if arguments.save:
        by_id = {trader.trader_id: trader for trader in result.traders}
        roots = {}
        for trader in result.traders:
            root = trader
            while root.parent_id is not None:
                root = by_id[root.parent_id]
            entry = roots.setdefault(
                root.trader_id, [f"{root.trader_id} {root.name} ({root.origin})", 0, 1]
            )
            if trader is not root:
                entry[1] += 1
            entry[2] = max(entry[2], trader.generation)
        summary = {
            "traders": len(result.traders),
            "deepest_generation": result.deepest_generation(),
            "days": [day.isoformat() for day in result.days],
            "population_by_day": result.population_by_day.tolist(),
            "births": int(result.births_by_day.sum()),
            "deaths": int(result.deaths_by_day.sum()),
            "families": sorted(roots.values(), key=lambda entry: -entry[1]),
        }
        arguments.save.parent.mkdir(parents=True, exist_ok=True)
        arguments.save.write_text(json.dumps(summary), encoding="utf-8")
    print(
        f"{len(result.traders)} traders lived; deepest lineage {result.deepest_generation()} "
        f"generations; {int(result.population_by_day[-1])} alive on {result.days[-1]}"
    )
    return 0


def write_report(arguments):
    """`report`: the report card of a run's best bot (or a named elite) as JSON and HTML."""
    import json

    from evobots.assess.report_card import ReportContext, report_card
    from evobots.assess.report_html import report_html
    from evobots.qd.run import Run

    run = Run.resume(arguments.directory, evaluator_for(arguments.demo))
    elite = None
    if arguments.trader:
        elite = next(
            (item for item in run.archive.values() if item.trader_id == arguments.trader), None
        )
    else:
        elite = run.choose_best() or run.nearest_candidate()
    if elite is None:
        print("No elite to report on.")
        return 1
    final_path = arguments.directory / "final_test.json"
    final = json.loads(final_path.read_text()) if final_path.exists() else None
    card = report_card(ReportContext.from_run(run, final), elite)
    stem = arguments.directory / f"report_{elite.trader_id}"
    stem.with_suffix(".json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    stem.with_suffix(".html").write_text(report_html(card), encoding="utf-8")
    print(card["what_happened"])
    print(f"Wrote {stem}.json and {stem}.html")
    return 0


def run_final_test(arguments):
    """`final-test`: open the sealed year once for the run's chosen trader."""
    if not arguments.yes:
        print(
            "The sealed test can be used once per run and every opening is logged. "
            "Run again with --yes to spend it."
        )
        return 1
    from evobots.assess.final_test import final_test
    from evobots.features.inputs import load_feature_inputs
    from evobots.qd.evaluation import Evaluator

    evaluator = Evaluator.from_store()
    if evaluator is None:
        print("The sealed test needs the MISO data built on this machine.")
        return 1
    result = final_test(
        arguments.directory, evaluator, load_feature_inputs(), arguments.trader, arguments.opened_by
    )
    print(json.dumps(result, indent=2))
    return 0


def run_data_build(arguments):
    """`data build`: build the store for a stage and print the checks; 1 if any fails."""
    if arguments.stage != "A":
        print(f"Stage {arguments.stage} is built at M8; only stage A exists so far.")
        return 1
    from evobots.data.build import build_stage_a

    lines, is_passing = build_stage_a(arguments.raw, arguments.store, arguments.workers)
    print("\n".join(lines))
    return 0 if is_passing else 1


if __name__ == "__main__":
    sys.exit(main())
