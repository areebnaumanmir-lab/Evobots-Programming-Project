"""A MAP-Elites run: search, rolling windows, checkpoints, resume, lineage, best bot (§11).

**Loop** (`docs/design_spec.md` §11): seed the archive with founders (about 10 %) and PTC2
random traders; then, batch after batch, draw parents by rank-weighted selection
(P(i) = (1 − p)/n + p · rank weight, pressure p = 0.5; §11.2), vary them with the
bandit-chosen operator (§9.6), skip neutral children (same behaviour id as the parent; up to
5 retries), score the children on the current 5-year window, and keep the best surviving
trader in each cell.

**Windows** (round 20): 5 years, stepped by 1 year through the history as the run goes on.
When the window moves, every elite is re-evaluated on the new window and the cells are
re-decided before any child is compared with them. Each elite is also scored on the next
unseen year (walk-forward) at checkpoints.

**Determinism:** every random draw comes from the run's PCG64 generator, and each child's
variation from its own seed (stored in its birth record), so a resumed run is byte-identical
to an uninterrupted one and any trader can be regenerated from its parents. Evaluations run in
parallel but are applied in birth order, so the number of workers doesn't change the result.

**Best bot** (§11.4): the highest walk-forward fitness among elites that pass the quick gates
(G1, G2, G4, G6), ties to the smaller program; otherwise "do nothing", naming the nearest
candidate and the gate it failed. Written to `runs/<id>/deployable/current_bot.json` after
every checkpoint.

Example:
    >>> from evobots.qd.evaluation import Evaluator
    >>> settings = SearchSettings(run_id="R1", evaluations=60, batch_size=20, seed=1)
    >>> run = Run(settings, Evaluator.synthetic(days=1500, seed=3))
    >>> run.run_until_done()
    >>> run.evaluations_done, len(run.archive) > 0
    (60, True)
"""

import concurrent.futures
import dataclasses
import datetime
import hashlib
import json
import multiprocessing
import os
import pickle
import time
from pathlib import Path

import numpy as np

from evobots.bots.founders import FOUNDERS
from evobots.bots.random_trees import ConstantRanges
from evobots.bots.source import trader_source
from evobots.bots.trader import describe, genome_from_json, genome_id, genome_to_json, trader_name
from evobots.bots.variation import OperatorBandit, random_genome, vary
from evobots.qd.archive import Elite, cell_of, ranked
from evobots.qd.gates import quick_gates
from evobots.qd.lineage import BirthRecord, LineageStore

DAYS_PER_YEAR = 365.25
FORWARD_DAYS = 365
NEUTRAL_RETRIES = 5
RESERVOIR_SIZE = 64
GATED_ELITES = 10
CHECKPOINT_FILE_NAME = "checkpoint.pickle"
WORKER_EVALUATOR = {}


@dataclasses.dataclass(frozen=True)
class SearchSettings:
    """What a run searches with (every value a user choice, §13.1).

    Attributes:
        run_id: "R<n>"; trader ids are "<run_id>-<birth>".
        seed: the run's seed.
        evaluations: budget, in traders scored.
        batch_size: children per batch.
        window_years: training window length (5, round 20).
        window_step_years: how far the window moves (1).
        evaluations_per_window: budget before the window moves (None: budget ÷ windows).
        selection_pressure: p in [0, 1].
        initial_population: traders in the first batch (founders + PTC2 random).
        is_using_founders: include the seven founders (the no-founder control sets False).
        workers: evaluation processes (1 = in this process).
        checkpoint_seconds: time between checkpoints.
        seed_genomes: ((label, genome JSON), …) for a Refine run; empty for a fresh run.
        parent_trader_ids: the Refine run's parents in earlier runs (lineage across runs).
        prior_trials: distinct behaviours already searched by parent runs (G2 counts them).
        is_holdout_used: the refined lineage's sealed test was already opened (§11.5).
        first_day: first operating day the windows may use (None = the first in the store).
        last_day: last operating day (None = the last; never past 2025-09-21).
        stage: the location set: "A" trading hubs, "D" yearly cluster representatives (§7.10).
    """

    run_id: str = "R1"
    seed: int = 1
    evaluations: int = 2000
    batch_size: int = 50
    window_years: int = 5
    window_step_years: int = 1
    evaluations_per_window: int | None = None
    selection_pressure: float = 0.5
    initial_population: int = 70
    is_using_founders: bool = True
    workers: int = 1
    checkpoint_seconds: float = 600.0
    seed_genomes: tuple = ()
    parent_trader_ids: tuple = ()
    prior_trials: int = 0
    is_holdout_used: bool = False
    first_day: datetime.date | None = None
    last_day: datetime.date | None = None
    stage: str = "A"


def windows_for(store_days, settings):
    """[(train start, train end, forward end), …] day indices of the rolling windows."""
    first = 0
    if settings.first_day is not None:
        first = next(
            (index for index, day in enumerate(store_days) if day >= settings.first_day), 0
        )
    last = len(store_days)
    if settings.last_day is not None:
        last = sum(1 for day in store_days if day <= settings.last_day)
    length = int(round(settings.window_years * DAYS_PER_YEAR))
    step = int(round(settings.window_step_years * DAYS_PER_YEAR))
    windows = []
    start = first
    while start + length + FORWARD_DAYS <= last:
        windows.append((start, start + length, start + length + FORWARD_DAYS))
        start += step
    if not windows:
        train_end = max(first + 1, last - FORWARD_DAYS)
        windows.append((first, train_end, last))
    return windows


def parent_position(count, pressure, generator):
    """Rank-weighted draw: P(i) = (1 − p)/n + p·(n − i)/Σ ranks, i = 0 the best."""
    weights = np.arange(count, 0, -1, dtype=float)
    probabilities = (1 - pressure) / count + pressure * weights / weights.sum()
    return int(generator.choice(count, p=probabilities / probabilities.sum()))


def evaluate_in_worker(genome_json, start, end, cost_multiple):
    """Worker-side evaluation (the evaluator is set before the pool forks)."""
    return WORKER_EVALUATOR["evaluator"].evaluate(
        genome_from_json(genome_json), start, end, cost_multiple
    )


class Run:
    """One MAP-Elites run (see the module docstring)."""

    def __init__(self, settings, evaluator, directory=None):
        """Start a run; `directory` (runs/<id>) holds lineage, checkpoints and the best bot."""
        self.settings = settings
        self.evaluator = evaluator
        self.directory = Path(directory) if directory else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
        self.lineage = LineageStore(
            self.directory / "lineage.sqlite" if self.directory else ":memory:"
        )
        self.generator = np.random.Generator(np.random.PCG64(settings.seed))
        self.reservoir_generator = np.random.Generator(np.random.PCG64([settings.seed, 1]))
        self.ranges = ConstantRanges.from_summary(evaluator.constant_summary())
        self.windows = windows_for(evaluator.store.days, settings)
        self.window_index = 0
        self.evaluations_done = 0
        self.evaluations_in_window = 0
        self.batches_done = 0
        self.archive = {}
        self.bandit = OperatorBandit()
        self.reservoir = []
        self.reservoir_seen = 0
        self.behaviour_by_trader = {}
        self.generation_by_trader = {}
        self.best = None
        self.started_at = time.time()
        self.last_checkpoint_at = time.time()
        self.pool = None

    # ----- windows -----
    def window(self):
        """(train start, train end, forward end) of the current window."""
        return self.windows[self.window_index]

    def evaluations_per_window(self):
        """Budget spent on each window before it moves."""
        if self.settings.evaluations_per_window:
            return self.settings.evaluations_per_window
        return max(self.settings.batch_size, self.settings.evaluations // len(self.windows))

    def move_window_if_due(self):
        """Advance the window, re-evaluating every elite before any comparison (round 20)."""
        if (
            self.window_index + 1 >= len(self.windows)
            or self.evaluations_in_window < self.evaluations_per_window()
        ):
            return False
        self.window_index += 1
        self.evaluations_in_window = 0
        self.reservoir, self.reservoir_seen = [], 0
        start, end, _ = self.window()
        elites = list(self.archive.values())
        evaluations = self.evaluate_many([elite.genome for elite in elites], start, end)
        self.archive = {}
        for elite, evaluation in zip(elites, evaluations):
            elite.evaluation, elite.forward, elite.forward_doubled_costs, elite.gates = (
                evaluation,
                None,
                None,
                {},
            )
            if evaluation.is_alive:
                self.place(elite)
        return True

    # ----- evaluation -----
    def evaluate_many(self, genomes, start, end, cost_multiple=1.0):
        """Evaluate genomes on a window, in order (parallel when workers > 1)."""
        if self.settings.workers <= 1:
            return [
                self.evaluator.evaluate(genome, start, end, cost_multiple) for genome in genomes
            ]
        if self.pool is None:
            WORKER_EVALUATOR["evaluator"] = self.evaluator
            context = multiprocessing.get_context("fork") if os.name != "nt" else None
            self.pool = concurrent.futures.ProcessPoolExecutor(
                self.settings.workers, mp_context=context
            )
        futures = [
            self.pool.submit(evaluate_in_worker, genome_to_json(genome), start, end, cost_multiple)
            for genome in genomes
        ]
        return [future.result() for future in futures]

    def close(self):
        """Stop the worker pool and close the lineage store."""
        if self.pool is not None:
            self.pool.shutdown()
            self.pool = None
        self.lineage.commit()

    # ----- archive -----
    def place(self, elite):
        """Put an elite in its cell if the cell is empty or it beats the incumbent."""
        cell = elite.cell()
        incumbent = self.archive.get(cell)
        if incumbent is None or (elite.evaluation.fitness, -elite.record.birth) > (
            incumbent.evaluation.fitness,
            -incumbent.record.birth,
        ):
            self.archive[cell] = elite
            return True
        return False

    def remember(self, daily_pnl):
        """Reservoir-sample a daily P&L stream (for G2's effective trials)."""
        self.reservoir_seen += 1
        if len(self.reservoir) < RESERVOIR_SIZE:
            self.reservoir.append(np.asarray(daily_pnl, dtype=float))
        else:
            slot = int(self.reservoir_generator.integers(self.reservoir_seen))
            if slot < RESERVOIR_SIZE:
                self.reservoir[slot] = np.asarray(daily_pnl, dtype=float)

    # ----- children -----
    def starting_children(self):
        """The first batch: founders and PTC2 random traders, or a Refine run's seeds."""
        children = []
        if self.settings.seed_genomes:
            seeds = [(label, genome_from_json(text)) for label, text in self.settings.seed_genomes]
            for label, genome in seeds:
                children.append(
                    (genome, tuple(self.settings.parent_trader_ids), "seed", 0, f"seed:{label}")
                )
            while len(children) < self.settings.initial_population:
                _, genome = seeds[int(self.generator.integers(len(seeds)))]
                operation_seed = int(self.generator.integers(2**63))
                child, _ = vary(
                    genome,
                    np.random.Generator(np.random.PCG64(operation_seed)),
                    self.ranges,
                    "subtree",
                )
                children.append(
                    (
                        child,
                        tuple(self.settings.parent_trader_ids),
                        "subtree",
                        operation_seed,
                        "seed mutant",
                    )
                )
            return children
        if self.settings.is_using_founders:
            children += [
                (genome, (), "founder", 0, f"founder:{name}") for name, genome in FOUNDERS.items()
            ]
        while len(children) < self.settings.initial_population:
            operation_seed = int(self.generator.integers(2**63))
            genome = random_genome(
                np.random.Generator(np.random.PCG64(operation_seed)), self.ranges
            )
            children.append((genome, (), "random", operation_seed, "random"))
        return children

    def bred_children(self, count):
        """Children of the archive: (genome, parent ids, operator, operation seed, origin)."""
        elites = ranked(self.archive.values())
        children = []
        for _ in range(count):
            operator = self.bandit.choose(self.generator)
            parent = elites[
                parent_position(len(elites), self.settings.selection_pressure, self.generator)
            ]
            partner = elites[
                parent_position(len(elites), self.settings.selection_pressure, self.generator)
            ]
            parent_behaviour = self.behaviour_by_trader.get(parent.trader_id)
            for _attempt in range(NEUTRAL_RETRIES + 1):
                operation_seed = int(self.generator.integers(2**63))
                child, used = vary(
                    parent.genome,
                    np.random.Generator(np.random.PCG64(operation_seed)),
                    self.ranges,
                    operator,
                    partner.genome,
                )
                if self.evaluator.behaviour(child) != parent_behaviour:
                    break
            # The partner is a parent when its genes could reach the child: crossover, the
            # constant operators (iso+line-DD) and any fallback to a constant step.
            uses_partner = (
                operator == "crossover" or operator.startswith("constant") or used != operator
            )
            if uses_partner and partner.trader_id != parent.trader_id:
                parents = (parent.trader_id, partner.trader_id)
            else:
                parents = (parent.trader_id,)
            children.append((child, parents, operator, operation_seed, f"mutation ({used})"))
        return children

    def regenerate(self, trader_id):
        """A trader's genome: stored, or replayed from its parents, operator and seed."""
        record = self.lineage.record(trader_id)
        stored = self.lineage.genome_json(record.genome_id)
        if stored is not None:
            return genome_from_json(stored)
        if record.operator == "random":
            return random_genome(
                np.random.Generator(np.random.PCG64(record.operation_seed)), self.ranges
            )
        if record.origin.startswith("founder:"):
            return FOUNDERS[record.origin.split(":", 1)[1]]
        parents = [self.regenerate(parent) for parent in record.parent_ids]
        partner = parents[1] if len(parents) > 1 else parents[0]
        child, _ = vary(
            parents[0],
            np.random.Generator(np.random.PCG64(record.operation_seed)),
            self.ranges,
            record.operator,
            partner,
        )
        return child

    # ----- one batch -----
    def step(self):
        """Breed (or seed), evaluate and archive one batch."""
        size = min(self.settings.batch_size, self.settings.evaluations - self.evaluations_done)
        if size <= 0:
            return
        if self.evaluations_done == 0 or not self.archive:
            children = self.starting_children()[: max(size, self.settings.initial_population)]
            children = children[: self.settings.evaluations - self.evaluations_done]
        else:
            children = self.bred_children(size)
        start, end, _ = self.window()
        evaluations = self.evaluate_many([child for child, *_ in children], start, end)
        for (genome, parents, operator, operation_seed, origin), evaluation in zip(
            children, evaluations
        ):
            self.evaluations_done += 1
            self.evaluations_in_window += 1
            trader_id = f"{self.settings.run_id}-{self.evaluations_done}"
            identity = genome_id(genome)
            behaviour = self.evaluator.behaviour(genome)
            generation = 1 + max(
                (self.generation_by_trader.get(parent, 0) for parent in parents), default=0
            )
            record = BirthRecord(
                trader_id=trader_id,
                genome_id=identity,
                behaviour_id=behaviour,
                name=trader_name(trader_id),
                run_id=self.settings.run_id,
                birth=self.evaluations_done,
                generation=generation,
                parent_ids=tuple(parents),
                operator=operator,
                operation_seed=operation_seed,
                origin=origin,
                window_first_day=self.evaluator.day(start).isoformat(),
                window_last_day=self.evaluator.day(end - 1).isoformat(),
            )
            self.lineage.add(record)
            self.behaviour_by_trader[trader_id] = behaviour
            self.generation_by_trader[trader_id] = generation
            self.remember(evaluation.daily_pnl_usd)
            has_entered = False
            if evaluation.is_alive:
                elite = Elite(record, genome, evaluation)
                has_entered = self.place(elite)
            if has_entered:
                self.store_genome_with_ancestors(trader_id, genome)
            elif origin.startswith(("seed", "founder")):
                # Seeds and founders can't be replayed from parents in this run: keep them.
                self.lineage.store_genome(identity, genome_to_json(genome))
            if operator in self.bandit.quality:
                self.bandit.reward(operator, has_entered)
            death_day = None
            if evaluation.stop_index is not None:
                death_day = self.evaluator.day(start + evaluation.stop_index).isoformat()
            self.lineage.update_result(
                trader_id,
                evaluation.fitness,
                cell_of(evaluation.net_direction, evaluation.selectivity),
                evaluation.is_alive,
                evaluation.stop_cause,
                death_day,
                has_entered,
            )
        self.batches_done += 1
        self.move_window_if_due()

    def store_genome_with_ancestors(self, trader_id, genome):
        """Keep the genome of an archive entrant and of all its ancestors."""
        self.lineage.store_genome(genome_id(genome), genome_to_json(genome))
        for ancestor in self.lineage.ancestors(trader_id):
            record = self.lineage.record(ancestor)
            if record is not None and self.lineage.genome_json(record.genome_id) is None:
                self.lineage.store_genome(
                    record.genome_id, genome_to_json(self.regenerate(ancestor))
                )

    # ----- gates, best bot, checkpoints -----
    def gate_elites(self):
        """Score the top elites on the next unseen year and run the quick gates."""
        _, end, forward_end = self.window()
        top = ranked(self.archive.values())[:GATED_ELITES]
        if forward_end <= end:
            return top
        forward = self.evaluate_many([elite.genome for elite in top], end, forward_end)
        doubled = self.evaluate_many(
            [elite.genome for elite in top], end, forward_end, cost_multiple=2.0
        )
        trials = self.lineage.distinct_behaviours() + self.settings.prior_trials
        for position, (elite, forward_evaluation, doubled_evaluation) in enumerate(
            zip(top, forward, doubled)
        ):
            elite.forward, elite.forward_doubled_costs = forward_evaluation, doubled_evaluation
            elite.gates = quick_gates(
                elite,
                self.evaluator.capital.starting_capital_usd,
                self.reservoir,
                trials,
                seed=position,
            )
        return top

    def choose_best(self):
        """The best bot (§11.4), or None ("do nothing"); sets self.best and returns it."""
        top = self.gate_elites()
        passing = [elite for elite in top if elite.passes_quick_gates()]
        self.best = (
            min(
                passing,
                key=lambda elite: (
                    -elite.forward.fitness,
                    elite.genome.node_count(),
                    elite.record.birth,
                ),
            )
            if passing
            else None
        )
        return self.best

    def nearest_candidate(self):
        """The elite with the highest walk-forward fitness, when nothing passes."""
        scored = [elite for elite in self.archive.values() if elite.forward is not None]
        return (
            max(scored, key=lambda elite: (elite.forward.fitness, -elite.record.birth))
            if scored
            else None
        )

    def current_bot(self):
        """The deployable decision as plain data (`current_bot.json`)."""
        best = self.best
        window = self.window()
        common = {
            "run_id": self.settings.run_id,
            "evaluations": self.evaluations_done,
            "window": [
                self.evaluator.day(window[0]).isoformat(),
                self.evaluator.day(window[1] - 1).isoformat(),
            ],
            "walk_forward_year": [
                self.evaluator.day(window[1]).isoformat(),
                self.evaluator.day(window[2] - 1).isoformat(),
            ]
            if window[2] > window[1]
            else None,
            "is_holdout_used": self.settings.is_holdout_used,
            "data": self.evaluator.store.source,
        }
        if best is None:
            nearest = self.nearest_candidate()
            failed = nearest.first_failed_gate() if nearest else None
            return {
                **common,
                "decision": "do nothing",
                "why": "Do nothing: no trader passes the gates.",
                "nearest_candidate": nearest.trader_id if nearest else None,
                "failed_gate": list(failed) if failed else None,
            }
        return {
            **common,
            "decision": "trade",
            "trader_id": best.trader_id,
            "name": best.record.name,
            "genome": json.loads(genome_to_json(best.genome)),
            "rules": describe(best.genome),
            "walk_forward_fitness": best.forward.fitness,
            "training_fitness": best.evaluation.fitness,
            "gates": {gate: detail for gate, (_, detail) in best.gates.items()},
        }

    def write_deployable(self):
        """Write runs/<id>/deployable/current_bot.json (and the best bot's code)."""
        if not self.directory:
            return
        folder = self.directory / "deployable"
        folder.mkdir(exist_ok=True)
        write_atomically(folder / "current_bot.json", json.dumps(self.current_bot(), indent=2))
        if self.best is not None:
            record = self.best.record
            text = trader_source(
                self.best.genome,
                {
                    "trader_id": record.trader_id,
                    "parent_ids": record.parent_ids,
                    "operator": record.origin,
                    "evaluation": record.birth,
                    "run_id": record.run_id,
                },
            )
            write_atomically(folder / f"trader_{record.trader_id}.py", text)

    def state(self):
        """Everything needed to resume, as plain picklable data."""
        return {
            "settings": self.settings,
            "generator": self.generator.bit_generator.state,
            "reservoir_generator": self.reservoir_generator.bit_generator.state,
            "window_index": self.window_index,
            "evaluations_done": self.evaluations_done,
            "evaluations_in_window": self.evaluations_in_window,
            "batches_done": self.batches_done,
            "archive": {cell: elite for cell, elite in sorted(self.archive.items())},
            "bandit": self.bandit,
            "reservoir": self.reservoir,
            "reservoir_seen": self.reservoir_seen,
            "behaviour_by_trader": self.behaviour_by_trader,
            "generation_by_trader": self.generation_by_trader,
        }

    def checkpoint(self):
        """Save the state and commit the lineage (write-then-rename)."""
        self.lineage.commit()
        if self.directory:
            payload = pickle.dumps(self.state(), protocol=5)
            write_atomically(self.directory / CHECKPOINT_FILE_NAME, payload)
            self.write_status()
        self.last_checkpoint_at = time.time()

    def write_status(self):
        """runs/<id>/status.json for the app (progress and the deployable decision)."""
        status = {
            "run_id": self.settings.run_id,
            "evaluations_done": self.evaluations_done,
            "budget": self.settings.evaluations,
            "batches_done": self.batches_done,
            "window_index": self.window_index,
            "windows": len(self.windows),
            "elites": len(self.archive),
            "deepest_lineage": max(self.generation_by_trader.values(), default=0),
            "best": self.best.trader_id if self.best else None,
            "updated_at_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        }
        write_atomically(self.directory / "status.json", json.dumps(status, indent=2))

    @classmethod
    def resume(cls, directory, evaluator):
        """Continue a run from its last checkpoint."""
        directory = Path(directory)
        state = pickle.loads((directory / CHECKPOINT_FILE_NAME).read_bytes())
        run = cls(state["settings"], evaluator, directory)
        run.generator.bit_generator.state = state["generator"]
        run.reservoir_generator.bit_generator.state = state["reservoir_generator"]
        for name in (
            "window_index",
            "evaluations_done",
            "evaluations_in_window",
            "batches_done",
            "archive",
            "bandit",
            "reservoir",
            "reservoir_seen",
            "behaviour_by_trader",
            "generation_by_trader",
        ):
            setattr(run, name, state[name])
        return run

    def state_digest(self):
        """SHA-256 of the archive, generator states and lineage (for byte-identical checks)."""
        archive = [
            (cell, elite.trader_id, genome_to_json(elite.genome), repr(elite.evaluation.fitness))
            for cell, elite in sorted(self.archive.items())
        ]
        text = repr(
            (
                archive,
                self.generator.bit_generator.state,
                self.evaluations_done,
                self.window_index,
                sorted(self.bandit.quality.items()),
            )
        )
        return hashlib.sha256((text + self.lineage.dump()).encode("utf-8")).hexdigest()

    # ----- driving -----
    def run_until_done(
        self, deadline_seconds=None, should_stop=None, progress=None, max_batches=None
    ):
        """Run batches until the budget, a deadline, a stop request or max_batches."""
        batches = 0
        while self.evaluations_done < self.settings.evaluations:
            if should_stop is not None and should_stop():
                break
            if deadline_seconds is not None and time.time() - self.started_at > deadline_seconds:
                break
            if max_batches is not None and batches >= max_batches:
                break
            self.step()
            batches += 1
            if progress is not None:
                progress(self)
            if (
                self.directory
                and time.time() - self.last_checkpoint_at > self.settings.checkpoint_seconds
            ):
                self.choose_best()
                self.write_deployable()
                self.checkpoint()
        self.choose_best()
        self.write_deployable()
        self.checkpoint()
        self.close()


def write_atomically(path, content):
    """Write text or bytes to a temporary file and rename it over path."""
    path = Path(path)
    partial = path.with_name(path.name + ".part")
    if isinstance(content, bytes):
        partial.write_bytes(content)
    else:
        partial.write_text(content, encoding="utf-8")
    partial.replace(path)
