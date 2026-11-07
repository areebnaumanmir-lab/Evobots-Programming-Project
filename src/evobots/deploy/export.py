"""`evobots export-bot`: a trader as one standard-library Python file, checked (§14.6).

The file is the trader's reference form (`evobots.bots.source`). Before it is written out,
the equivalence test runs on `check_days` random days of the run's data: for every
location-hour, the file (reading its inputs through its own CSV parser) must bid exactly what
the engine bids (side, limit price, full-size MW, and MW after a random position scale). Any
mismatch stops the export.

Example:
    >>> from evobots.bots.founders import FOUNDERS
    >>> from evobots.qd.evaluation import Evaluator
    >>> import tempfile
    >>> evaluator = Evaluator.synthetic(days=300, seed=2)
    >>> path = Path(tempfile.mkdtemp()) / "trader_R1-1.py"
    >>> result = export_bot(FOUNDERS["always_inc"], {"trader_id": "R1-1"}, evaluator, path, 5)
    >>> result["days_checked"], result["mismatches"], path.exists()
    (5, 0, True)
"""

import tempfile
import types
from pathlib import Path

import numpy as np

from evobots.bots.source import input_rows, rows_to_csv, trader_source
from evobots.bots.trader import trader_decisions
from evobots.simulate.settlement import round_down_to_step

FIRST_CHECKED_DAY = 60  # features need some history


def module_from_source(text, name="exported_trader"):
    """Load a generated trader file as a module (without writing it)."""
    module = types.ModuleType(name)
    exec(compile(text, f"<{name}>", "exec"), module.__dict__)  # noqa: S102 (our own code)
    return module


def equivalence_mismatches(genome, module, store, caps_mw, days, seed=0):
    """(rows checked, bids checked, mismatches) of the file against the engine."""
    generator = np.random.Generator(np.random.PCG64(seed))
    features = genome.features()
    rows_checked = bids_checked = 0
    mismatches = []
    with tempfile.TemporaryDirectory() as folder:
        for day_index in days:
            decisions = trader_decisions(genome, store, day_index, day_index + 1, caps_mw)
            path = Path(folder) / f"day_{day_index}.csv"
            path.write_text(rows_to_csv(input_rows(store, day_index, caps_mw, features), features))
            scale = float(generator.uniform(0.05, 1.0))
            for row in module.read_rows(str(path)):
                rows_checked += 1
                location = store.locations.index(row["location"])
                hour = int(row["hour"]) - 1
                side = int(decisions.side[0, hour, location])
                bid = module.decide(row, row["cap_mw"])
                expected = (
                    None
                    if side == 0
                    else (
                        side,
                        decisions.limit_usd_per_mwh[0, hour, location],
                        decisions.full_size_mw[0, hour, location],
                    )
                )
                if bid is None or expected is None:
                    if bid != expected:
                        mismatches.append((store.days[day_index], row["location"], hour + 1))
                    continue
                bids_checked += 1
                scaled_file = module.round_down_to_step(scale * bid[2])
                scaled_engine = round_down_to_step(scale * expected[2])
                if tuple(bid) != expected or scaled_file != scaled_engine:
                    mismatches.append((store.days[day_index], row["location"], hour + 1))
    return rows_checked, bids_checked, mismatches


def export_bot(genome, record, evaluator, path, check_days=200, seed=0):
    """Write the trader's file after the equivalence test passes.

    Args:
        genome: the trader.
        record: header fields (trader_id required; parent_ids, operator, evaluation, run_id).
        evaluator: the run's evaluator (its store and caps are the test data).
        path: where to write the file.
        check_days: random days to check.
        seed: the day and scale draws.

    Returns:
        {"path", "days_checked", "rows_checked", "bids_checked", "mismatches"}.

    Raises:
        AssertionError: when the file and the engine disagree anywhere (nothing is written).
    """
    text = trader_source(genome, record)
    module = module_from_source(text)
    store = evaluator.store
    generator = np.random.Generator(np.random.PCG64(seed))
    first = min(FIRST_CHECKED_DAY, len(store.days) - 1)
    days = sorted(
        int(day)
        for day in generator.choice(
            np.arange(first, len(store.days)),
            size=min(check_days, len(store.days) - first),
            replace=False,
        )
    )
    rows, bids, mismatches = equivalence_mismatches(
        genome, module, store, evaluator.caps_mw, days, seed
    )
    assert not mismatches, f"the file and the engine disagree at {mismatches[:5]}"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "path": str(path),
        "days_checked": len(days),
        "rows_checked": rows,
        "bids_checked": bids,
        "mismatches": len(mismatches),
    }
