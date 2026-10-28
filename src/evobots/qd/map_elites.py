"""MAP-Elites over traders, with a walk-forward test year and quick gates (preview).

The search keeps the best surviving trader in each cell of a 2-D map (`CLAUDE.md` §11):
- **net direction**, (DEC MWh − INC MWh) / cleared MWh, −1 … +1, in 10 columns;
- **selectivity**, the share of hub-hours bid, on a log scale 0.1 % … 100 %, in 8 rows.

Each child is a mutation (85 %) or slot-wise crossover (15 %) of parents drawn with
rank-weighted selection: P(i) = (1 − p)/n + p × rank weight, pressure p = 0.5 by default
(§11.2). Children are scored on the training window (the `training_years` before the test
year); dead traders are discarded (natural selection). At the end every elite is scored on
the **test year** (2024-09-22 → 2025-09-21, unseen during search) at estimated and at
doubled costs.

**Best bot** (§11.4): the highest test-year fitness among elites that survive both windows
and keep positive test fitness with doubled costs; ties go to the smaller rule set. If none
passes, the answer is "do nothing", with the nearest candidate named.

The sealed hold-out (2025-09-22 → 2026-09-21) is never touched: the market arrays end on
2025-09-21.

Example:
    >>> from evobots.simulate.market import synthetic_hub_market, point_in_time_features
    >>> market = synthetic_hub_market(days=1500, seed=3)
    >>> settings = RunSettings(training_years=2, evaluations=40, seed=1)
    >>> result = run_evolution(market, point_in_time_features(market), settings)
    >>> result.evaluations, len(result.elites) > 0
    (40, True)
"""

import dataclasses
import datetime

import numpy as np

from evobots.bots.genome import FOUNDERS, crossover, mutate, random_genome
from evobots.config.capital import CapitalSettings
from evobots.simulate.engine import evaluate

DIRECTION_BINS = 10
SELECTIVITY_BINS = 8
SELECTIVITY_LOG_RANGE = (-3.0, 0.0)
TEST_YEAR_DAYS = 365
INITIAL_RANDOM_TRADERS = 30
REFINE_INITIAL_MUTANTS = 30
BATCH_SIZE = 20
CROSSOVER_SHARE = 0.15


@dataclasses.dataclass(frozen=True)
class RunSettings:
    """What a run searches with. Every field is a user choice (§13.1).

    Attributes:
        training_years: years of history before the test year used to score children.
        evaluations: number of traders scored (the search budget).
        seed: random seed; equal settings and seed give an identical run.
        selection_pressure: p in [0, 1]; 0 = uniform parents (plain MAP-Elites).
        starting_capital_usd: equity each trader starts with.
        daily_risk_budget_fraction: share of equity a 1-in-100 day may cost.
        max_mw_per_hub_hour: absolute cap per hub-hour, MW.
        cost_multiple: 1 = estimated costs; 2 = doubled.
        is_using_founders: start from the hand-written founders as well as random traders.
    """

    training_years: int = 5
    evaluations: int = 600
    seed: int = 1
    selection_pressure: float = 0.5
    starting_capital_usd: float = 1_500_000.0
    daily_risk_budget_fraction: float = 0.02
    max_mw_per_hub_hour: float = 5.0
    cost_multiple: float = 1.0
    is_using_founders: bool = True

    def capital_settings(self):
        """The CapitalSettings these choices imply (validated there)."""
        return CapitalSettings(
            starting_capital_usd=self.starting_capital_usd,
            daily_risk_budget_fraction=self.daily_risk_budget_fraction,
            max_mw_per_hub_hour=self.max_mw_per_hub_hour,
        )


@dataclasses.dataclass
class Trader:
    """One evaluated trader and its birth record (§9.4).

    Attributes:
        trader_id: run number and birth number, e.g. "R2-118".
        genome: its Genome.
        parent_ids: ids of its parents (empty for founders and random traders).
        origin: "founder:<name>", "random", "seed", or the operator that made it.
        training: its EvaluationResult on the training window.
        test: its EvaluationResult on the test year (elites only, after the search).
        test_doubled_costs: the same at doubled costs.
    """

    trader_id: str
    genome: object
    parent_ids: tuple
    origin: str
    training: object
    test: object = None
    test_doubled_costs: object = None

    def cell(self):
        """The (direction column, selectivity row) of the map this trader belongs in."""
        direction = self.training.net_direction
        column = min(DIRECTION_BINS - 1, int((direction + 1) / 2 * DIRECTION_BINS))
        low, high = SELECTIVITY_LOG_RANGE
        log_share = np.log10(max(self.training.selectivity, 10**low))
        row = min(SELECTIVITY_BINS - 1, int((log_share - low) / (high - low) * SELECTIVITY_BINS))
        return column, row

    def passes_gates(self):
        """Survives both windows and stays profitable on the test year at doubled costs."""
        return (
            self.training.is_alive
            and self.test is not None
            and self.test.is_alive
            and self.test.fitness > 0
            and self.test_doubled_costs.fitness > 0
        )


@dataclasses.dataclass
class RunResult:
    """What a run found.

    Attributes:
        elites: the archive's traders, best training fitness first.
        best: the best bot (§11.4), or None for "do nothing".
        nearest_candidate: when best is None, the elite with the highest test fitness.
        evaluations: traders scored.
        training_days: (first, last) dates of the training window.
        test_days: (first, last) dates of the test year.
        operator_successes: {operator: (children that entered the archive, children tried)}.
    """

    elites: list
    best: Trader | None
    nearest_candidate: Trader | None
    evaluations: int
    training_days: tuple
    test_days: tuple
    operator_successes: dict


def windows(market, training_years):
    """(train start, train end, test start, test end) day indices; test = the last year."""
    end = len(market.days)
    test_start = end - TEST_YEAR_DAYS
    train_start = max(0, test_start - int(round(training_years * 365.25)))
    return train_start, test_start, test_start, end


def parent_index(ranked_count, pressure, generator):
    """Draw an elite by rank: P(i) = (1 − p)/n + p × (n − i) / Σ ranks (i = 0 is best)."""
    weights = np.arange(ranked_count, 0, -1, dtype=float)
    probabilities = (1 - pressure) / ranked_count + pressure * weights / weights.sum()
    return int(generator.choice(ranked_count, p=probabilities / probabilities.sum()))


def run_evolution(
    market,
    features,
    settings,
    run_number=1,
    seed_genomes=None,
    progress=None,
    should_stop=None,
):
    """Run MAP-Elites, then score elites on the test year and choose the best bot.

    Args:
        market: a HubMarket.
        features: its point-in-time features.
        settings: RunSettings.
        run_number: used in trader ids ("R<run>-<birth>").
        seed_genomes: {label: Genome} to start from (a Refine run); None for a fresh run.
        progress: optional callable(evaluations done, budget, best training fitness).
        should_stop: optional callable returning True to stop early.

    Returns:
        A RunResult.
    """
    generator = np.random.Generator(np.random.PCG64(settings.seed))
    capital = settings.capital_settings()
    train_start, train_end, test_start, test_end = windows(market, settings.training_years)
    archive = {}
    birth = 0
    operator_successes = {}

    def score(genome, parent_ids, origin, operator=None):
        nonlocal birth
        birth += 1
        result = evaluate(
            genome, market, features, train_start, train_end, capital, settings.cost_multiple
        )
        trader = Trader(f"R{run_number}-{birth}", genome, parent_ids, origin, result)
        is_entering = False
        if result.is_alive:
            cell = trader.cell()
            incumbent = archive.get(cell)
            if incumbent is None or result.fitness > incumbent.training.fitness:
                archive[cell] = trader
                is_entering = True
        if operator is not None:
            entered, tried = operator_successes.get(operator, (0, 0))
            operator_successes[operator] = (entered + is_entering, tried + 1)
        if progress is not None:
            best = max(
                (trader.training.fitness for trader in archive.values()), default=float("nan")
            )
            progress(birth, settings.evaluations, best)

    starting = []
    if seed_genomes:
        for label, genome in seed_genomes.items():
            starting.append((genome, (), f"seed:{label}"))
        seeds = list(seed_genomes.values())
        for _ in range(REFINE_INITIAL_MUTANTS):
            child, operator = mutate(seeds[generator.integers(len(seeds))], generator)
            starting.append((child, (), f"seed mutant ({operator})"))
    else:
        if settings.is_using_founders:
            starting += [(genome, (), f"founder:{name}") for name, genome in FOUNDERS.items()]
        starting += [
            (random_genome(generator), (), "random") for _ in range(INITIAL_RANDOM_TRADERS)
        ]
    for genome, parent_ids, origin in starting[: settings.evaluations]:
        score(genome, parent_ids, origin)
    while birth < settings.evaluations and not (should_stop and should_stop()):
        ranked = sorted(archive.values(), key=lambda trader: -trader.training.fitness)
        if not ranked:
            score(random_genome(generator), (), "random")
            continue
        for _ in range(min(BATCH_SIZE, settings.evaluations - birth)):
            first = ranked[parent_index(len(ranked), settings.selection_pressure, generator)]
            if len(ranked) > 1 and generator.random() < CROSSOVER_SHARE:
                second = ranked[parent_index(len(ranked), settings.selection_pressure, generator)]
                child = crossover(first.genome, second.genome, generator)
                score(child, (first.trader_id, second.trader_id), "crossover", "crossover")
            else:
                child, operator = mutate(first.genome, generator)
                score(child, (first.trader_id,), f"mutation ({operator})", operator)
    elites = sorted(archive.values(), key=lambda trader: -trader.training.fitness)
    for trader in elites:
        trader.test = evaluate(
            trader.genome, market, features, test_start, test_end, capital, settings.cost_multiple
        )
        trader.test_doubled_costs = evaluate(
            trader.genome,
            market,
            features,
            test_start,
            test_end,
            capital,
            2 * settings.cost_multiple,
        )
    passing = [trader for trader in elites if trader.passes_gates()]
    best = (
        min(passing, key=lambda trader: (-trader.test.fitness, trader.genome.size()))
        if passing
        else None
    )
    nearest = None
    if best is None and elites:
        nearest = max(elites, key=lambda trader: trader.test.fitness)
    day = market.days
    return RunResult(
        elites=elites,
        best=best,
        nearest_candidate=nearest,
        evaluations=birth,
        training_days=(day[train_start], day[train_end - 1]),
        test_days=(day[test_start], day[test_end - 1]),
        operator_successes=operator_successes,
    )


def first_failed_gate(trader):
    """Plain-English name of the first gate a trader fails, or None."""
    if not trader.training.is_alive:
        return "ran out of money in training"
    if not trader.test.is_alive:
        return "ran out of money in the test year"
    if trader.test.fitness <= 0:
        return "lost money (after costs) in the test year"
    if trader.test_doubled_costs.fitness <= 0:
        return "not profitable in the test year with doubled costs"
    return None


def describe_window(days):
    """'2020-09-22 → 2024-09-21'."""
    first, last = days
    return f"{first.isoformat()} → {last.isoformat()}" if isinstance(first, datetime.date) else ""
