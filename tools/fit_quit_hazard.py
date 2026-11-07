"""Fit the L3 quit hazard to losing random traders on the real hub data (M5 done-when).

"Fit β so that a population of *losing* baseline bots (random bots after costs) reproduces
about 44 % / 24 % / 15 % survival at 1 / 2 / 3 years" (design spec §10.1). Random PTC2
traders are scored over 2019-09 → 2023-09 (four years) after estimated costs; those that lose
money form the population. Writes docs/data/quit_hazard_fit.json (summary statistics only).

Run: `uv run python tools/fit_quit_hazard.py [--traders 400]`
"""

import argparse
import datetime
import json
from pathlib import Path

import numpy as np

from evobots.bots.random_trees import ConstantRanges
from evobots.bots.variation import random_genome
from evobots.career.hazard import fit_quit_hazard, monthly_covariates
from evobots.career.model import monthly_index_ends
from evobots.qd.evaluation import Evaluator

OUTPUT_PATH = Path("docs/data/quit_hazard_fit.json")
FIRST_DAY = datetime.date(2019, 9, 22)
YEARS = 4


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--traders", type=int, default=400)
    parser.add_argument("--seed", type=int, default=1)
    arguments = parser.parse_args()
    evaluator = Evaluator.from_store()
    if evaluator is None:
        raise SystemExit("needs the MISO hub table (evobots data build --stage A)")
    ranges = ConstantRanges.from_summary(evaluator.constant_summary())
    generator = np.random.Generator(np.random.PCG64(arguments.seed))
    start = evaluator.index_of(FIRST_DAY)
    end = start + int(round(YEARS * 365.25))
    paths, losing, scored = [], 0, 0
    for _ in range(arguments.traders):
        genome = random_genome(generator, ranges)
        evaluation = evaluator.evaluate(genome, start, end)
        scored += 1
        if evaluation.cleared_mwh == 0 or evaluation.log_growth >= 0:
            continue
        losing += 1
        equity = evaluation.equity_usd.astype(float)
        months = monthly_index_ends(len(equity))
        paths.append(monthly_covariates(equity, evaluator.capital.starting_capital_usd, months))
    paths = [path for path in paths if len(path) >= 36]
    fit = fit_quit_hazard(paths, seed=arguments.seed)
    summary = {
        "traders_scored": scored,
        "losing_traders_used": len(paths),
        "window": [evaluator.day(start).isoformat(), evaluator.day(end - 1).isoformat()],
        "costs": "estimated (labelled), cost multiple 1",
        "beta": list(fit.hazard.beta),
        "fixed_by_assumption": fit.fixed,
        "standard_errors_beta0_beta1": list(fit.standard_errors),
        "fitted_survival": {str(months): value for months, value in fit.fitted_survival.items()},
        "target_survival": {str(months): value for months, value in fit.target_survival.items()},
        "source_of_targets": "Barber, Lee, Liu, Odean & Zhang (2020), Taiwanese day traders",
    }
    OUTPUT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
