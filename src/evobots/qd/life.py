"""Life mode: a market-time ecology of traders (`docs/design_spec.md` §11.3, M6b).

A population lives through the history day by day. Each trader trades every day it is alive
(sized, capped and charged as in the simulator) and dies when out of money. When its equity
reaches k × the starting capital (k = 2), it hands one starting capital to a mutated child,
which trades from the next day. A child's whole career is therefore out of sample relative to
its creation. With a population cap, a birth at the cap crowds out the poorest living trader.

Because traders are price-takers and don't interact, each trader's account between two of its
own events is an ordinary settlement; the ecology is simulated event by event (births at the
first day a trader's equity reaches k × capital), so it is exact and deterministic.

This is the literal natural selection of §1.1 and a realism check, not the search engine:
a trader that doubles every 2–5 years gets about 4–10 generations in 20 years.

Example:
    >>> from evobots.qd.evaluation import Evaluator
    >>> evaluator = Evaluator.synthetic(days=1200, seed=3)
    >>> result = run_life(evaluator, LifeSettings(initial_random=6, seed=2))
    >>> bool(result.population_by_day[0] >= 6)
    True
"""

import dataclasses
import heapq

import numpy as np

from evobots.bots.founders import FOUNDERS
from evobots.bots.random_trees import ConstantRanges
from evobots.bots.trader import trader_name
from evobots.bots.variation import INITIAL_OPERATOR_WEIGHTS, random_genome, vary
from evobots.simulate.settlement import settle

CROWDED_OUT = "crowded out (population cap)"


@dataclasses.dataclass(frozen=True)
class LifeSettings:
    """Life-mode choices.

    Attributes:
        seed: the ecology's seed.
        initial_random: PTC2 random traders alive on the first day (plus founders).
        is_using_founders: the seven founders are also alive on the first day.
        reproduction_multiple: k; a trader reproduces when equity reaches k × capital.
        max_population: living traders at most (a birth at the cap crowds out the poorest).
        first_index: first store day (None = the first; the warm-up of 90 days applies).
        end_index: one past the last store day (None = the last).
    """

    seed: int = 1
    initial_random: int = 60
    is_using_founders: bool = True
    reproduction_multiple: float = 2.0
    max_population: int = 300
    first_index: int | None = None
    end_index: int | None = None


@dataclasses.dataclass
class LifeTrader:
    """One trader's life."""

    trader_id: str
    name: str
    genome: object
    parent_id: str | None
    generation: int
    birth_index: int
    origin: str
    death_index: int | None = None
    death_cause: str | None = None
    children: list = dataclasses.field(default_factory=list)
    equity_by_index: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class LifeResult:
    """The ecology's history.

    Attributes:
        traders: every LifeTrader, in birth order.
        days: the store days simulated.
        population_by_day: living traders each day.
        births_by_day, deaths_by_day: counts each day.
        total_equity_by_day: summed equity of the living (USD).
    """

    traders: list
    days: tuple
    population_by_day: np.ndarray
    births_by_day: np.ndarray
    deaths_by_day: np.ndarray
    total_equity_by_day: np.ndarray

    def deepest_generation(self):
        """The most generations any lineage reached."""
        return max(trader.generation for trader in self.traders)


def run_life(evaluator, settings):
    """Simulate the ecology (see the module docstring)."""
    generator = np.random.Generator(np.random.PCG64(settings.seed))
    ranges = ConstantRanges.from_summary(evaluator.constant_summary())
    capital = evaluator.capital.starting_capital_usd
    first = settings.first_index or 0
    end = settings.end_index or len(evaluator.store.days)
    traders = []
    events = []  # (day index, birth order, trader index, segment equity)
    operators = list(INITIAL_OPERATOR_WEIGHTS)
    weights = np.array([INITIAL_OPERATOR_WEIGHTS[name] for name in operators])

    def born(genome, parent, origin, day_index):
        trader_id = f"L{settings.seed}-{len(traders) + 1}"
        generation = 1 if parent is None else parent.generation + 1
        trader = LifeTrader(
            trader_id,
            trader_name(trader_id),
            genome,
            None if parent is None else parent.trader_id,
            generation,
            day_index,
            origin,
        )
        traders.append(trader)
        if parent is not None:
            parent.children.append(trader_id)
        heapq.heappush(events, (day_index, len(traders) - 1, capital))
        return trader

    if settings.is_using_founders:
        for name, genome in FOUNDERS.items():
            born(genome, None, f"founder:{name}", first)
    for _ in range(settings.initial_random):
        born(random_genome(generator, ranges), None, "random", first)

    def living_on(day_index):
        return [
            trader
            for trader in traders
            if trader.birth_index <= day_index
            and (trader.death_index is None or trader.death_index >= day_index)
        ]

    while events:
        day_index, position, equity = heapq.heappop(events)
        trader = traders[position]
        if trader.death_index is not None or day_index >= end:
            continue
        decisions = evaluator.decisions(trader.genome, day_index, end)
        rules = dataclasses.replace(
            evaluator.account_rules(trader.genome), starting_capital_usd=equity
        )
        result = settle(decisions, evaluator.market, day_index, end, rules, evaluator.cost_table)
        path = result.equity_usd
        death = result.death_index
        target = settings.reproduction_multiple * capital
        reached = np.flatnonzero(path >= target)
        reproduction = int(reached[0]) if len(reached) else None
        if death is not None and (reproduction is None or death <= reproduction):
            for offset in range(death + 1):
                trader.equity_by_index[day_index + offset] = float(path[offset])
            trader.death_index = day_index + death
            trader.death_cause = result.death_cause
            continue
        if reproduction is None:
            for offset, value in enumerate(path):
                trader.equity_by_index[day_index + offset] = float(value)
            continue
        for offset in range(reproduction + 1):
            trader.equity_by_index[day_index + offset] = float(path[offset])
        birth_day = day_index + reproduction + 1
        if birth_day >= end:
            continue
        crowded = living_on(birth_day)
        if len(crowded) >= settings.max_population:
            poorest = min(
                (other for other in crowded if other is not trader),
                key=lambda other: (
                    other.equity_by_index.get(birth_day - 1, capital),
                    other.trader_id,
                ),
            )
            poorest.death_index = birth_day - 1
            poorest.death_cause = CROWDED_OUT
            for key in [index for index in poorest.equity_by_index if index > birth_day - 1]:
                del poorest.equity_by_index[key]
        operator = operators[int(generator.choice(len(operators), p=weights / weights.sum()))]
        child_seed = int(generator.integers(2**63))
        child, _ = vary(
            trader.genome, np.random.Generator(np.random.PCG64(child_seed)), ranges, operator
        )
        born(child, trader, f"child ({operator})", birth_day)
        heapq.heappush(events, (birth_day, position, float(path[reproduction]) - capital))
    day_count = end - first
    population = np.zeros(day_count, dtype=int)
    births = np.zeros(day_count, dtype=int)
    deaths = np.zeros(day_count, dtype=int)
    total = np.zeros(day_count)
    for trader in traders:
        births[trader.birth_index - first] += 1
        if trader.death_index is not None and trader.death_index < end:
            deaths[trader.death_index - first] += 1
        for index, value in trader.equity_by_index.items():
            if first <= index < end:
                population[index - first] += 1
                total[index - first] += value
    return LifeResult(
        traders, tuple(evaluator.store.days[first:end]), population, births, deaths, total
    )
