"""Run the ORFE modules on the real hub data and write docs/data/orfe/<section>.json.

Sections (run one or several; each is slow in its own way):
- scenarios: O1 validation table (rolling origin, 2018 → 2025);
- risk: O5 VaR/ES estimators and backtests on the full-size always-INC benchmark;
- battery: O4 policies at ILLINOIS.HUB, bound ratios by year, storm days, sensitivity;
- leaderboard: O2 optimizer and DPDS against baselines and the evolved elite, last unseen year;
- portfolio: O3 models over the run's elites, walk-forward;
- impact: O9 price-impact regression on a sample of cleared-bids days;
- search: O8 MAP-Elites vs NSGA-II at equal budget, successive halving, OCBA.

The outputs are summary statistics (no price series). They are MISO-derived, so they are
listed in `evobots.service.MISO_DERIVED_FILES`.

Run: `uv run python tools/build_orfe_results.py --sections scenarios risk --run runs/R101`
"""

import argparse
import datetime
import json
import time
from pathlib import Path

import numpy as np

OUTPUT_DIRECTORY = Path("docs/data/orfe")


def write(name, data):
    """Write one section's JSON."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIRECTORY / f"{name}.json").write_text(
        json.dumps(data, indent=2, default=float) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT_DIRECTORY / name}.json")


def scenarios_section(evaluator):
    from evobots.orfe.scenarios import validation_table

    market = evaluator.market
    start = market.day_index(datetime.date(2018, 1, 1))
    spreads = (market.day_ahead - market.real_time)[start:]
    store = evaluator.store
    features = np.column_stack(
        [
            np.nanmean(store.full("temp_max_fcst")[start:, 0, :], axis=1),
            store.full("gas_price")[start:, 0, 0],
            np.array([day.month for day in store.days[start:]], dtype=float),
        ]
    )
    tests = np.arange(1500, len(spreads), 7)
    table = validation_table(spreads, features, tests, count=40)
    return {
        "test_days": len(tests),
        "first_test_day": store.days[start + tests[0]].isoformat(),
        "last_test_day": store.days[start + tests[-1]].isoformat(),
        "table": table,
    }


def risk_section(evaluator):
    from evobots.calibration import read_benchmark_fixture
    from evobots.orfe.risk import backtest_table

    days, pnl = read_benchmark_fixture(Path("docs/data/benchmark_full_size_daily_pnl.csv"))
    periods = {
        "2015-06 → 2018": ("2015-06-01", "2018-12-31"),
        "2019 → 2021": ("2019-01-01", "2021-12-31"),
        "2022 → 2025-09": ("2022-01-01", "2025-09-21"),
    }
    return {
        "series": "always-INC at full size, 8 hubs (docs/data/benchmark_full_size_daily_pnl.csv)",
        "rows": backtest_table(pnl, days, periods),
    }


def battery_section(evaluator):
    from evobots.orfe import battery as model
    from evobots.orfe.scenarios import fit_jump_model, jump_price_paths

    market = evaluator.market
    hub = market.hubs.index("ILLINOIS.HUB")
    prices = market.day_ahead[:, :, hub]
    first = market.day_index(datetime.date(2015, 3, 1))
    unit = model.Battery()
    results = {}
    value_function = None
    thresholds = evolved = None
    per_day = []
    for index in range(first, len(market.days)):
        day = market.days[index]
        today = prices[index]
        yesterday = prices[index - 1]
        if np.isnan(today).any() or np.isnan(yesterday).any():
            continue
        if value_function is None or day.day == 1:
            history = prices[index - 365 : index - 1]
            history = history[~np.isnan(history).any(axis=1)]
            jump = fit_jump_model(history.mean(axis=1), history)
            samples = jump_price_paths(jump, history[-1].mean(), 1, 200, seed=index)[:, 0, :]
            value_function = model.dp_value_function(samples, unit, grid_points=21)
            if day.month == 1 or thresholds is None:
                thresholds = model.tune_thresholds(history[-120:], unit)
                evolved = model.evolve_threshold_policy(
                    history[-120:], unit, generations=15, population=12, seed=index
                )
        perfect = model.schedule_lp(today, unit).revenue_usd
        intrinsic = model.apply_schedule_to_prices(model.schedule_lp(yesterday, unit), today, unit)
        dynamic = model.dp_policy_day(today, unit, *value_function).revenue_usd
        threshold = model.threshold_policy_day(today, unit, *thresholds).revenue_usd
        evolved_revenue = model.threshold_policy_day(today, unit, *evolved).revenue_usd
        per_day.append((day.isoformat(), perfect, intrinsic, dynamic, threshold, evolved_revenue))
    names = (
        "perfect_foresight",
        "rolling_intrinsic",
        "stochastic_dp",
        "threshold_tuned",
        "threshold_evolved",
    )
    by_year = {}
    for row in per_day:
        year = row[0][:4]
        totals = by_year.setdefault(year, np.zeros(5))
        totals += np.array(row[1:])
    results["revenue_by_year_usd"] = {
        year: dict(zip(names, map(float, totals))) for year, totals in by_year.items()
    }
    totals = np.sum([row[1:] for row in per_day], axis=0)
    results["total_usd"] = dict(zip(names, map(float, totals)))
    results["bound_ratio"] = {
        name: float(totals[position] / totals[0]) for position, name in enumerate(names)
    }
    storm_days = {
        row[0]: dict(zip(names, row[1:]))
        for row in per_day
        if row[0] in ("2021-02-15", "2021-02-16", "2021-02-17", "2022-12-23", "2022-12-24")
    }
    results["storm_days_usd"] = storm_days
    sensitivity = {}
    sample = [
        prices[index]
        for index in range(first, len(market.days), 15)
        if not np.isnan(prices[index]).any()
    ]
    for efficiency in (0.70, 0.82, 0.90):
        for wear in (0.0, 2.0, 5.0):
            variant = model.Battery(round_trip_efficiency=efficiency, degradation_usd_per_mwh=wear)
            sensitivity[f"efficiency {efficiency:.2f}, wear ${wear:.0f}/MWh"] = float(
                np.mean([model.schedule_lp(day, variant).revenue_usd for day in sample])
            )
    results["perfect_foresight_daily_mean_by_parameters_usd"] = sensitivity
    results["battery"] = {
        "power_mw": unit.power_mw,
        "energy_mwh": unit.energy_mwh,
        "round_trip_efficiency": unit.round_trip_efficiency,
        "degradation_usd_per_mwh": unit.degradation_usd_per_mwh,
        "hub": "ILLINOIS.HUB",
        "days": len(per_day),
    }
    return results


def elite_genome(run_directory):
    """The run's reported trader (report JSON) or None."""
    from evobots.bots.trader import genome_from_data

    reports = sorted(Path(run_directory).glob("report_*.json"))
    if not reports:
        return None, None
    card = json.loads(reports[-1].read_text())
    from evobots.qd.lineage import LineageStore

    store = LineageStore(Path(run_directory) / "lineage.sqlite")
    record = store.record(card["identity"]["trader_id"])
    genome_json = store.genome_json(record.genome_id)
    from evobots.bots.trader import genome_from_json

    del genome_from_data
    return card["identity"]["trader_id"], genome_from_json(genome_json)


def leaderboard_section(evaluator, run_directory):
    from evobots.orfe.leaderboard import Strategy, baseline_strategies, genome_strategy, leaderboard
    from evobots.orfe.optimizer import (
        dpds_decisions,
        optimizer_decisions,
        perfect_foresight_decisions,
    )
    from evobots.orfe.scenarios import fit_regime_model, regime_scenarios, visible_history
    from evobots.qd.lineage import LineageStore
    from evobots.simulate.settlement import SIZING_HISTORY_DAYS

    market = evaluator.market
    caps = evaluator.caps_mw
    start = market.day_index(datetime.date(2024, 3, 28))
    end = market.day_index(datetime.date(2025, 3, 28))
    spreads = market.day_ahead - market.real_time
    models = {}

    def scenario_function(index, count, seed):
        month = (market.days[index].year, market.days[index].month)
        if month not in models:
            models[month] = fit_regime_model(
                np.nanmean(visible_history(spreads, index), axis=(1, 2))
            )
        return regime_scenarios(spreads, index, count, seed, models[month])

    def with_history(function):
        def decisions(first, last):
            history = max(0, first - SIZING_HISTORY_DAYS)
            return function(history, last)

        return decisions

    strategies = baseline_strategies(evaluator)
    trader_id, genome = elite_genome(run_directory)
    if genome is not None:
        trials = LineageStore(Path(run_directory) / "lineage.sqlite").distinct_behaviours()
        strategies.append(
            genome_strategy(evaluator, f"evolved elite {trader_id}", genome, "evolved", trials)
        )
    for risk_aversion in (0.0, 1.0):
        strategies.append(
            Strategy(
                f"mean-CVaR optimizer λ={risk_aversion:g}",
                "optimizer",
                2,
                with_history(
                    lambda first, last, risk_aversion=risk_aversion: optimizer_decisions(
                        market,
                        first,
                        last,
                        scenario_function,
                        caps,
                        risk_aversion=risk_aversion,
                        scenario_count=30,
                    )
                ),
            )
        )
    for penalty in (0.0, 0.002):
        strategies.append(
            Strategy(
                f"DPDS ρ={penalty:g} (arXiv 1802.03010)",
                "online",
                2,
                with_history(
                    lambda first, last, penalty=penalty: dpds_decisions(
                        market, first, last, caps, risk_penalty=penalty
                    )
                ),
            )
        )
    strategies.append(
        Strategy(
            "perfect foresight (upper bound, not a strategy)",
            "bound",
            1,
            with_history(
                lambda first, last: perfect_foresight_decisions(market, first, last, caps)
            ),
            is_bound=True,
        )
    )
    rows, kept = leaderboard(evaluator, strategies, start, end)
    return {
        "period": [market.days[start].isoformat(), market.days[end - 1].isoformat()],
        "rows": rows,
        "model_confidence_set": kept,
    }


def portfolio_section(evaluator, run_directory):
    from evobots.orfe import portfolio as model
    from evobots.qd.run import Run

    run = Run.resume(run_directory, evaluator)
    elites = list(run.archive.values())
    start = evaluator.index_of(datetime.date(2015, 3, 28))
    end = run.window()[2]
    capital = evaluator.capital.starting_capital_usd
    streams = []
    for elite in elites:
        evaluation = evaluator.evaluate(elite.genome, start, end)
        streams.append(evaluation.daily_returns(capital))
    returns = np.column_stack(streams)
    models = {
        "mean-CVaR λ=1": lambda history: model.mean_cvar_weights(history, 1.0),
        "mean-variance γ=10": lambda history: model.mean_variance_weights(history, 10.0),
        "growth-optimal (half Kelly)": lambda history: model.growth_optimal_weights(history, 0.5),
        "risk parity": model.risk_parity_weights,
        "equal weight": lambda history: np.full(history.shape[1], 1 / history.shape[1]),
        "best single elite (trailing)": lambda history: np.eye(history.shape[1])[
            int(np.argmax(history.mean(axis=0)))
        ],
    }
    results = {}
    for name, function in models.items():
        out_of_sample, weights = model.walk_forward(
            returns, function, refit_days=91, training_days=730
        )
        growth = float(np.log1p(out_of_sample).sum())
        deviation = out_of_sample.std(ddof=1)
        results[name] = {
            "out_of_sample_log_growth": growth,
            "annual_sharpe": float(out_of_sample.mean() / deviation * np.sqrt(365))
            if deviation > 0
            else 0.0,
            "worst_day_fraction": float(out_of_sample.min()),
            "average_holdings": float(np.mean([np.sum(weight > 1e-3) for weight in weights])),
        }
    frontier = model.frontier(returns[-730:])
    return {
        "elites": len(elites),
        "days": [evaluator.day(start).isoformat(), evaluator.day(end - 1).isoformat()],
        "walk_forward": results,
        "frontier_last_two_years": frontier,
        "note": (
            "The elites were evolved through these years, so the walk-forward is out of sample "
            "for the weights, not for the elites."
        ),
    }


def impact_section(evaluator):
    from evobots.orfe.price_impact import (
        cleared_bid_days,
        impact_regression,
        implied_spread_change,
        observations_from_raw,
    )

    market = evaluator.market
    raw = Path("data/raw/miso")
    days = cleared_bid_days(raw)[::5]
    hub_prices = {}
    for day in days:
        index = market.day_index(day)
        for hub_index, hub in enumerate(market.hubs):
            for hour in range(24):
                hub_prices[(day, hour + 1, hub)] = (
                    float(market.day_ahead[index, hour, hub_index]),
                    float(market.real_time[index, hour, hub_index]),
                )
    spread, net, groups, day_numbers = observations_from_raw(raw, hub_prices, days)
    keep = ~np.isnan(spread)
    estimate = impact_regression(spread[keep], net[keep], groups[keep], day_numbers[keep])
    estimate["implied_spread_change_for_5_mw_usd_per_mwh"] = implied_spread_change(
        estimate["coefficient"], 5.0
    )
    estimate["sample"] = f"every 5th day with cleared-bids files, {days[0]} → {days[-1]}"
    estimate["caveats"] = [
        "endogeneity: traders bid more DEC when they expect RT above DA; an association, "
        "not causation",
        "selection: observable hub-hours only",
    ]
    return estimate


def search_section(evaluator):
    from evobots.bots.variation import random_genome, vary
    from evobots.orfe.search_or import (
        hypervolume,
        non_dominated_fronts,
        nsga2,
        ocba_allocation,
        successive_halving,
    )
    from evobots.qd.run import Run, SearchSettings

    budget = 1500
    run = Run(
        SearchSettings(
            run_id="O8",
            evaluations=budget,
            batch_size=100,
            seed=3,
            window_years=5,
            first_day=datetime.date(2014, 3, 28),
            last_day=datetime.date(2020, 3, 27),
            initial_population=100,
        ),
        evaluator,
    )
    run.run_until_done()
    start, end, forward = run.window()

    def objectives(genome):
        evaluation = evaluator.evaluate(genome, start, end)
        losses = -evaluation.daily_returns(evaluator.capital.starting_capital_usd)
        tail = np.sort(losses)[-max(1, len(losses) // 20) :].mean()
        return (evaluation.log_growth, -evaluation.max_drawdown_fraction, -tail)

    generator = np.random.Generator(np.random.PCG64(5))
    population = [random_genome(generator, run.ranges) for _ in range(50)]

    def vary_pair(parent, partner, generator):
        child, _ = vary(
            parent,
            generator,
            run.ranges,
            "subtree" if generator.random() < 0.5 else "crossover",
            partner,
        )
        return child

    nsga_population, nsga_objectives = nsga2(
        population, objectives, vary_pair, generations=budget // 50 - 1, generator=generator
    )
    elite_objectives = [objectives(elite.genome) for elite in run.archive.values()]
    reference = np.array([-1.0, -1.0, -0.2])
    front_nsga = np.array(nsga_objectives)[non_dominated_fronts(nsga_objectives)[0]]
    front_map = np.array(elite_objectives)[non_dominated_fronts(elite_objectives)[0]]

    def forward_best(genomes):
        return max(evaluator.evaluate(genome, end, forward).fitness for genome in genomes)

    halving_candidates = [random_genome(generator, run.ranges) for _ in range(64)]
    timing = {}
    started = time.time()
    survivors, cost = successive_halving(
        halving_candidates,
        lambda genome, years: evaluator.evaluate(genome, end - int(years * 365.25), end).fitness,
        [1, 2.5, 5],
    )
    timing["successive_halving_seconds"] = time.time() - started
    started = time.time()
    full = sorted(
        (
            (evaluator.evaluate(genome, start, end).fitness, position)
            for position, genome in enumerate(halving_candidates)
        ),
        reverse=True,
    )
    timing["full_scoring_seconds"] = time.time() - started
    top = sorted(run.archive.values(), key=lambda elite: -elite.evaluation.fitness)[:6]
    yearly = []
    for elite in top:
        values = [
            evaluator.evaluate(
                elite.genome, start + year * 365, start + (year + 1) * 365
            ).log_growth
            for year in range(5)
        ]
        yearly.append(values)
    yearly = np.array(yearly)
    allocation = ocba_allocation(yearly.mean(axis=1), yearly.std(axis=1, ddof=1), 60)
    return {
        "budget_each": budget,
        "window": [evaluator.day(start).isoformat(), evaluator.day(end - 1).isoformat()],
        "hypervolume": {
            "map_elites": hypervolume(front_map, reference),
            "nsga2": hypervolume(front_nsga, reference),
        },
        "front_size": {"map_elites": int(len(front_map)), "nsga2": int(len(front_nsga))},
        "best_next_year_fitness": {
            "map_elites": forward_best([elite.genome for elite in run.archive.values()]),
            "nsga2": forward_best(nsga_population),
        },
        "map_elites_cells_filled": len(run.archive),
        "successive_halving": {
            "cost_trader_years": cost,
            "full_cost_trader_years": 64 * 5,
            "survivor_full_rank": [
                int(
                    next(
                        rank
                        for rank, (_, position) in enumerate(full)
                        if halving_candidates[position] is genome
                    )
                )
                for genome, _ in survivors
            ],
            **timing,
        },
        "ocba_allocation_of_60_re_evaluations": allocation.tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sections",
        nargs="+",
        default=["scenarios", "risk", "battery", "leaderboard", "portfolio", "impact", "search"],
    )
    parser.add_argument("--run", type=Path, default=Path("runs/R101"))
    arguments = parser.parse_args()
    from evobots.qd.evaluation import Evaluator

    evaluator = Evaluator.from_store()
    if evaluator is None:
        raise SystemExit("needs the MISO hub table")
    for section in arguments.sections:
        started = time.time()
        if section in ("leaderboard", "portfolio"):
            data = globals()[f"{section}_section"](evaluator, arguments.run)
        else:
            data = globals()[f"{section}_section"](evaluator)
        data["computed_on"] = datetime.date.today().isoformat()
        data["seconds"] = time.time() - started
        write(section, data)


if __name__ == "__main__":
    main()
