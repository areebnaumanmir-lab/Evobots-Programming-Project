"""The report card: how deployable a trader is, as JSON (`docs/design_spec.md` §12, M7).

`report_card(context, elite)` scores one trader against every gate and returns plain data;
`evobots.assess.report_html` draws it in the app and as one self-contained HTML file.

- G1 survival: 1,000 stationary-bootstrap paths of the trader's daily returns over the whole
  evolution period (2005–2025); the share that stays within the 50 % loss mandate (≥ 95 % passes)
- G2 skill vs trials: deflated Sharpe ratio over the whole period, against the run's effective
  number of trials; and MinBTL: the years needed so that this many trials can't produce the Sharpe
  ratio by luck, against the years available
- G3 overfitting: probability of backtest overfitting (CSCV, 8 blocks) across the archive's elites
  on the training window (≤ 0.5 passes)
- G4 cost stress: the unseen year, and the whole period, with fees and uplift doubled: still
  positive
- G5 scale-up: at the MW cap (no position scaling): still alive; and, when the Stage C store is
  built, re-scored on every location over the unseen year (`evobots.assess.scale_up`): still alive
- G6 walk-forward: the unseen year after the training window: positive growth, drawdown within the
  mandate
- G7 shock periods: results through each event of the calendar: alive through all of them (reported,
  with each event's return)
- G8 hold-out: the sealed 12 months, once per finished run, through `evobots final-test` only

Also reported (never used for selection): the rolling next-year results of every window,
fitness with and without the named storms, the hindsight check (re-scored with `epu` and the
gas features missing), MW by hub, the features read, O7's Reality Check / SPA / Romano–Wolf
against "do nothing", a bootstrap interval on the yearly log growth, the smallest Sharpe ratio
the data could detect, and an honest-expectation note. A "What happened" paragraph opens it.

Example:
    >>> from evobots.qd.evaluation import Evaluator
    >>> from evobots.qd.run import Run, SearchSettings
    >>> settings = SearchSettings(run_id="R1", evaluations=60, batch_size=30, seed=1)
    >>> run = Run(settings, Evaluator.synthetic(days=1500, seed=3))
    >>> run.run_until_done()
    >>> elite = next(iter(run.archive.values()))
    >>> card = report_card(ReportContext.from_run(run), elite, bootstrap_paths=50)
    >>> sorted(card["gates"])[:2]
    ['G1 survival', 'G2 skill vs trials']
"""

import dataclasses
import datetime
import math

import numpy as np

from evobots.assess.inference import (
    bootstrap_interval,
    minimum_detectable_sharpe,
    reality_check_significance,
    romano_wolf_step_down,
    spa_significance,
)
from evobots.assess.statistics import (
    deflated_sharpe_ratio,
    minimum_backtest_length_years,
    politis_white_block_length,
    probability_of_backtest_overfitting,
    sharpe_ratio,
)
from evobots.bots.trader import describe, genome_id
from evobots.features.catalogue import FEATURE_BY_NAME, HINDSIGHT_CHECK_FEATURES
from evobots.qd.gates import (
    DEFLATED_SHARPE_REQUIRED,
    MANDATE_DRAWDOWN_FRACTION,
    SURVIVAL_SHARE_REQUIRED,
    bootstrap_survival,
    effective_trials,
    null_sharpe_variance,
)
from evobots.simulate.settlement import settle
from evobots.storms import fitness_with_and_without_storms

REPORT_VERSION = 1
BOOTSTRAP_PATHS = 1000
MAX_CHART_POINTS = 2000
# Locations listed by name in the MW table; the rest are summed (Stages D and C).
LOCATIONS_LISTED = 20
PBO_REQUIRED = 0.5
# The event calendar (G7). Dates from the project's own data checks where marked (obs.).
EVENT_CALENDAR = {
    "Polar vortex": (
        "2014-01-06",
        "2014-01-08",
        "obs. round 27: hub mean RT $189.9/MWh on 2014-01-07",
    ),
    "COVID-19 lockdowns": ("2020-03-09", "2020-04-30", "the EPU window of round 28"),
    "Winter Storm Uri": (
        "2021-02-15",
        "2021-02-19",
        "storm window of capital_sizing.md §7b (obs.)",
    ),
    "2022 gas price spike": (
        "2022-05-01",
        "2022-09-30",
        "Henry Hub above $7/MMBtu most days (assumption: approximate months)",
    ),
    "Winter Storm Elliott": (
        "2022-12-23",
        "2022-12-25",
        "storm window of capital_sizing.md §7b (obs.)",
    ),
}
HONEST_EXPECTATION = (
    "Virtual bidding is a thin, competitive edge. Published studies that model fees and uplift "
    "find "
    "small or no profits after costs; a trader that passes these gates on 20 years of history has "
    "a "
    "better chance than one that doesn't, not a guarantee. Fees and uplift are estimates until "
    "MISO's "
    "rate file is supplied, the Constraint Management Charge is not modelled, and bids are assumed "
    "not to move prices (5 MW cap). Real trading needs MISO registration and collateral."
)


@dataclasses.dataclass
class ReportContext:
    """What a report needs from its run.

    Attributes:
        evaluator: the run's Evaluator.
        run_id: the run.
        window: (train start, train end, forward end) of the current window.
        windows: every rolling window of the run.
        elites: the archive's elites (for G3 and O7).
        reservoir: the run's reservoir of P&L streams (for effective trials).
        distinct_behaviours: distinct behaviours searched (plus prior runs').
        is_holdout_used: the lineage's sealed test was already opened.
        final_test: the logged G8 result, if any.
    """

    evaluator: object
    run_id: str
    window: tuple
    windows: list
    elites: list
    reservoir: list
    distinct_behaviours: int
    is_holdout_used: bool = False
    final_test: dict | None = None

    @classmethod
    def from_run(cls, run, final_test=None):
        """The context of a Run."""
        return cls(
            evaluator=run.evaluator,
            run_id=run.settings.run_id,
            window=run.window(),
            windows=run.windows,
            elites=list(run.archive.values()),
            reservoir=list(run.reservoir),
            distinct_behaviours=run.lineage.distinct_behaviours() + run.settings.prior_trials,
            is_holdout_used=run.settings.is_holdout_used,
            final_test=final_test,
        )


def thinned(values, max_points=MAX_CHART_POINTS):
    """At most max_points (index, value) pairs, keeping each bucket's min and max (spikes stay)."""
    values = np.asarray(values, dtype=float)
    if len(values) <= max_points:
        return [(index, float(value)) for index, value in enumerate(values)]
    bucket = math.ceil(len(values) / (max_points / 2))
    points = []
    for start in range(0, len(values), bucket):
        part = values[start : start + bucket]
        low, high = int(np.argmin(part)), int(np.argmax(part))
        for offset in sorted({low, high}):
            points.append((start + offset, float(part[offset])))
    return points


def evaluation_summary(evaluation, days):
    """The headline numbers of an Evaluation."""
    return {
        "first_day": days[evaluation.start].isoformat(),
        "last_day": days[evaluation.end - 1].isoformat(),
        "fitness": evaluation.fitness,
        "log_growth": evaluation.log_growth,
        "final_equity_usd": evaluation.final_equity_usd,
        "max_drawdown_fraction": evaluation.max_drawdown_fraction,
        "is_alive": evaluation.is_alive,
        "stop_cause": evaluation.stop_cause,
        "stop_day": None
        if evaluation.stop_index is None
        else days[evaluation.start + evaluation.stop_index].isoformat(),
        "cleared_mwh": evaluation.cleared_mwh,
        "fees_usd": evaluation.fees_usd,
        "net_direction": evaluation.net_direction,
        "selectivity": evaluation.selectivity,
    }


def shock_results(evaluation, days, starting_capital_usd):
    """G7 rows: each event's return and whether the trader was alive through it."""
    rows = []
    window_days = days[evaluation.start : evaluation.end]
    equity = np.concatenate([[starting_capital_usd], evaluation.equity_usd.astype(float)])
    for name, (first, last, source) in EVENT_CALENDAR.items():
        first_day, last_day = datetime.date.fromisoformat(first), datetime.date.fromisoformat(last)
        if not (window_days and window_days[0] <= last_day and window_days[-1] >= first_day):
            rows.append(
                {
                    "event": name,
                    "first_day": first,
                    "last_day": last,
                    "source": source,
                    "is_covered": False,
                }
            )
            continue
        start = next(index for index, day in enumerate(window_days) if day >= first_day)
        end = max(index for index, day in enumerate(window_days) if day <= last_day) + 1
        before, after = equity[start], equity[end]
        stopped = evaluation.stop_index is not None and evaluation.stop_index < end
        rows.append(
            {
                "event": name,
                "first_day": first,
                "last_day": last,
                "source": source,
                "is_covered": True,
                "pnl_usd": float(after - before),
                "return_fraction": float(after / before - 1) if before > 0 else None,
                "is_alive_after": not stopped,
            }
        )
    return rows


def mw_by_location(evaluator, genome, start, end):
    """Cleared MWh at full size by location, and by location type.

    Stages D and C list the LOCATIONS_LISTED largest and sum the rest.
    """
    decisions = evaluator.decisions(genome, start, end)
    rows = slice(start - decisions.first_day_index, end - decisions.first_day_index)
    side = decisions.side[rows].astype(float)
    day_ahead = evaluator.market.day_ahead[start:end]
    real_time = evaluator.market.real_time[start:end]
    priced = ~np.isnan(day_ahead) & ~np.isnan(real_time)
    with np.errstate(invalid="ignore"):
        cleared = priced & (
            ((side > 0) & (day_ahead <= decisions.limit_usd_per_mwh[rows]))
            | ((side < 0) & (day_ahead >= decisions.limit_usd_per_mwh[rows]))
        )
    power = np.where(cleared, decisions.full_size_mw[rows], 0.0).sum(axis=(0, 1))
    by_location = {
        name: float(power[index]) for index, name in enumerate(evaluator.store.locations)
    }
    by_type = {}
    for name, kind in zip(evaluator.store.locations, evaluator.market.types()):
        by_type[kind] = by_type.get(kind, 0.0) + by_location[name]
    if len(by_location) > LOCATIONS_LISTED:
        ranked_names = sorted(by_location, key=by_location.get, reverse=True)
        rest = ranked_names[LOCATIONS_LISTED:]
        by_location = {name: by_location[name] for name in ranked_names[:LOCATIONS_LISTED]}
        by_location[f"{len(rest):,} other locations"] = float(
            sum(power) - sum(by_location.values())
        )
    return by_location, by_type


def what_happened(identity, full, unseen, gates, shocks):
    """A deterministic paragraph from templates (§15.2; no language model)."""
    parts = [
        f"{identity['name']} ({identity['trader_id']}) turned "
        f"${full['final_equity_usd'] / math.exp(full['log_growth']):,.0f} "
        f"into ${full['final_equity_usd']:,.0f} over {full['first_day']} to {full['last_day']} "
        f"(log growth {full['log_growth']:+.3f}, worst fall {full['max_drawdown_fraction']:.0%})."
    ]
    if not full["is_alive"]:
        parts.append(f"It stopped on {full['stop_day']} ({full['stop_cause']}).")
    if unseen is not None:
        parts.append(
            f"On the unseen year {unseen['first_day']} to {unseen['last_day']} its log growth was "
            f"{unseen['log_growth']:+.3f}."
        )
    worst = [
        row for row in shocks if row.get("is_covered") and row.get("return_fraction") is not None
    ]
    if worst:
        hardest = min(worst, key=lambda row: row["return_fraction"])
        parts.append(
            f"Its hardest event was {hardest['event']} ({hardest['return_fraction']:+.1%})."
        )
    failed = [name for name, gate in gates.items() if gate["status"] == "fail"]
    parts.append(
        "It passes every gate checked." if not failed else "It fails " + ", ".join(failed) + "."
    )
    return " ".join(parts)


def report_card(context, elite, bootstrap_paths=BOOTSTRAP_PATHS, seed=0, scale_up=None):
    """The full report card of one elite (see the module docstring).

    `scale_up` is the Stage C re-score of `evobots.assess.scale_up` (None when that store
    isn't built here); G5 then also needs the trader alive on every location.
    """
    evaluator = context.evaluator
    days = evaluator.store.days
    capital = evaluator.capital.starting_capital_usd
    genome = elite.genome
    train_start, train_end, forward_end = context.window
    full_end = context.windows[-1][2] if context.windows else len(days)
    full = evaluator.evaluate(genome, 0, full_end)
    full_doubled = evaluator.evaluate(genome, 0, full_end, cost_multiple=2.0)
    unseen = evaluator.evaluate(genome, train_end, forward_end) if forward_end > train_end else None
    unseen_doubled = (
        evaluator.evaluate(genome, train_end, forward_end, cost_multiple=2.0) if unseen else None
    )
    returns = full.daily_returns(capital)
    traded = (
        returns[np.flatnonzero(full.daily_pnl_usd != 0)[0] :]
        if (full.daily_pnl_usd != 0).any()
        else returns
    )
    years = len(traded) / 365.0
    survival = bootstrap_survival(traded, capital, paths=bootstrap_paths, seed=seed)
    trials = effective_trials(context.reservoir, context.distinct_behaviours)
    deflated = deflated_sharpe_ratio(traded, null_sharpe_variance(len(traded)), trials)
    annual_sharpe = sharpe_ratio(traded)
    minimum_years = (
        minimum_backtest_length_years(annual_sharpe, trials) if annual_sharpe > 0 else math.inf
    )
    elite_matrix = (
        np.column_stack([candidate.evaluation.daily_pnl_usd for candidate in context.elites])
        if len(context.elites) >= 4
        else None
    )
    pbo = probability_of_backtest_overfitting(elite_matrix)[0] if elite_matrix is not None else None
    at_cap_rules = dataclasses.replace(evaluator.account_rules(genome), is_scaled=False)
    at_cap = settle(
        evaluator.decisions(genome, 0, full_end),
        evaluator.market,
        0,
        full_end,
        at_cap_rules,
        evaluator.cost_table,
    )
    shocks = shock_results(full, days, capital)
    gates = {
        "G1 survival": gate(
            survival >= SURVIVAL_SHARE_REQUIRED,
            f"{survival:.1%} of {bootstrap_paths:,} stationary-bootstrap paths (mean block "
            f"{politis_white_block_length(traded):.1f} days) stay within a "
            f"{MANDATE_DRAWDOWN_FRACTION:.0%} loss",
        ),
        "G2 skill vs trials": gate(
            deflated >= DEFLATED_SHARPE_REQUIRED and years >= minimum_years,
            f"deflated Sharpe {deflated:.2f} (needs {DEFLATED_SHARPE_REQUIRED}) against "
            f"{trials:,.0f} "
            f"effective trials; annual Sharpe {annual_sharpe:.2f} needs {minimum_years:.1f} years "
            "of data "
            f"(MinBTL), {years:.1f} available",
        ),
        "G3 overfitting": gate(
            None if pbo is None else pbo <= PBO_REQUIRED,
            "probability of backtest overfitting "
            + (
                "not computed (fewer than 4 elites)"
                if pbo is None
                else f"{pbo:.2f} across {len(context.elites)} elites (needs ≤ {PBO_REQUIRED})"
            ),
        ),
        "G4 cost stress": gate(
            unseen_doubled is not None
            and unseen_doubled.log_growth > 0
            and full_doubled.log_growth > 0,
            "log growth with doubled costs: unseen year "
            + (f"{unseen_doubled.log_growth:+.3f}" if unseen_doubled else "–")
            + f", whole period {full_doubled.log_growth:+.3f}",
        ),
        "G5 scale-up": gate(
            at_cap.is_alive and (scale_up is None or scale_up["stage_c"]["is_alive"]),
            f"at the MW cap without scaling: {'alive' if at_cap.is_alive else 'out of money'}, "
            f"final equity ${at_cap.final_equity_usd:,.0f}; " + scale_up_text(scale_up),
        ),
        "G6 walk-forward": gate(
            unseen is not None
            and unseen.log_growth > 0
            and unseen.max_drawdown_fraction < MANDATE_DRAWDOWN_FRACTION,
            "unseen year: "
            + (
                f"log growth {unseen.log_growth:+.3f}, drawdown {unseen.max_drawdown_fraction:.0%}"
                if unseen
                else "none"
            ),
        ),
        "G7 shock periods": gate(
            all(row.get("is_alive_after", True) for row in shocks),
            "alive through every covered event: "
            + ", ".join(
                f"{row['event']} {row['return_fraction']:+.1%}"
                for row in shocks
                if row.get("is_covered") and row.get("return_fraction") is not None
            ),
        ),
        "G8 hold-out": final_test_gate(context),
    }
    rolling = []
    for start, end, next_end in context.windows:
        if next_end <= end:
            continue
        next_year = evaluator.evaluate(genome, end, next_end)
        rolling.append(
            {
                "year": f"{days[end].isoformat()} → {days[next_end - 1].isoformat()}",
                "log_growth": next_year.log_growth,
                "max_drawdown_fraction": next_year.max_drawdown_fraction,
                "is_alive": next_year.is_alive,
            }
        )
    storm_days = [day.isoformat() for day in days[0:full_end]]
    storms = fitness_with_and_without_storms(full.daily_pnl_usd.astype(float), storm_days, capital)
    hindsight_evaluator = dataclasses.replace(
        evaluator, store=evaluator.store.with_missing(HINDSIGHT_CHECK_FEATURES)
    )
    hindsight_evaluator.cache = type(evaluator.cache)()
    uses_hindsight = bool(set(genome.features()) & set(HINDSIGHT_CHECK_FEATURES))
    hindsight = hindsight_evaluator.evaluate(genome, 0, full_end) if uses_hindsight else full
    by_location, by_type = mw_by_location(evaluator, genome, 0, full_end)
    inference = inference_section(context, unseen, seed)
    identity = {
        "trader_id": elite.trader_id,
        "name": elite.record.name,
        "genome_id": genome_id(genome),
        "run_id": context.run_id,
        "origin": elite.record.origin,
        "generation": elite.record.generation,
        "parent_ids": list(elite.record.parent_ids),
        "rules": describe(genome),
        "features_read": [
            {"name": name, "display_name": FEATURE_BY_NAME[name].display_name}
            for name in genome.features()
        ],
        "node_count": genome.node_count(),
    }
    full_summary = evaluation_summary(full, days)
    unseen_summary = evaluation_summary(unseen, days) if unseen else None
    for name, entry in gates.items():
        entry["name"] = name
    yearly_growth = bootstrap_interval(
        traded,
        lambda sample: float(np.log1p(sample).sum() / max(len(sample) / 365, 1e-9)),
        seed=seed,
        draws=min(bootstrap_paths, 500),
    )
    return {
        "report_version": REPORT_VERSION,
        "data": evaluator.store.source,
        "identity": identity,
        "what_happened": what_happened(identity, full_summary, unseen_summary, gates, shocks),
        "gates": gates,
        "full_period": full_summary,
        "full_period_doubled_costs": evaluation_summary(full_doubled, days),
        "unseen_year": unseen_summary,
        "training_window": [days[train_start].isoformat(), days[train_end - 1].isoformat()],
        "rolling_next_years": rolling,
        "rolling_note": (
            "Each row is the year after one rolling training window. The run evolved through "
            "earlier windows, so only the last row is unseen by the trader's lineage."
        ),
        "shock_periods": shocks,
        "storms": storms,
        "hindsight_check": {
            "features_blanked": list(HINDSIGHT_CHECK_FEATURES),
            "uses_them": uses_hindsight,
            "log_growth_with": full.log_growth,
            "log_growth_without": hindsight.log_growth,
            "is_hindsight_suspect": uses_hindsight and hindsight.log_growth < full.log_growth - 0.1,
        },
        "mw_by_location": by_location,
        "scale_up": scale_up,
        "mw_by_location_type": by_type,
        "inference": inference,
        "yearly_log_growth_interval_90": yearly_growth,
        "minimum_detectable_annual_sharpe": minimum_detectable_sharpe(
            max(years, 0.1), trials=max(int(trials), 1)
        ),
        "charts": {
            "equity": [
                (days[full.start + index].isoformat(), value)
                for index, value in thinned(full.equity_usd)
            ],
            "drawdown": [
                (days[full.start + index].isoformat(), value)
                for index, value in thinned(drawdown_path(full.equity_usd, capital))
            ],
        },
        "costs": sorted(evaluator.cost_table.labels(days[:full_end])),
        "caveats": [
            "Fees and uplift are labelled estimates until MISO's Market Settlements Rates Factors "
            "file is supplied.",
            "MPD is the $12 floor every year (estimate).",
            "The Constraint Management Charge is not modelled.",
            "Price-taker: bids are assumed not to move prices (cap 5 MW per hub-hour, 5 % of "
            "typical volume).",
            "L5 peers are not modelled; traders don't interact.",
        ],
        "honest_expectation": HONEST_EXPECTATION,
        "is_holdout_used": context.is_holdout_used,
        "measured": [
            "every P&L, growth, drawdown and gate statistic above, from the downloaded prices and "
            "the simulator",
        ],
        "assumed": [
            "fee and RSG rates; MPD; gate thresholds (95 %, 0.95, 0.5, 50 % loss mandate); the "
            "event windows marked as assumptions",
        ],
    }


def scale_up_text(scale_up):
    """G5's Stage C sentence."""
    if scale_up is None:
        return "every location (Stage C): store not built here"
    every, own = scale_up["stage_c"], scale_up["own_stage"]
    return (
        f"every location (Stage C, {scale_up['locations']:,}), {scale_up['period'][0]} → "
        f"{scale_up['period'][1]}: log growth {every['log_growth']:+.3f} on "
        f"{every['locations_traded']:,} locations traded "
        f"({'alive' if every['is_alive'] else 'out of money'}), against {own['log_growth']:+.3f} "
        f"on its own {scale_up['own_stage_locations']:,}"
    )


def gate(passed, detail):
    """A gate entry: status pass / fail / not run, with its detail."""
    status = "not run" if passed is None else ("pass" if passed else "fail")
    return {"status": status, "detail": detail}


def final_test_gate(context):
    """G8 from the logged final test, if run."""
    if context.final_test is None:
        return {
            "status": "not run",
            "detail": "Sealed: run `evobots final-test` once for the run's chosen trader.",
        }
    result = context.final_test
    passed = result["log_growth"] > 0 and result["is_alive"]
    return {
        "status": "pass" if passed else "fail",
        "detail": f"sealed 12 months, opened {result['opened_at_utc'][:10]}: "
        f"log growth {result['log_growth']:+.3f}, "
        f"drawdown {result['max_drawdown_fraction']:.0%}",
    }


def drawdown_path(equity_usd, starting_capital_usd):
    """Fall from the running peak each day, as a fraction."""
    path = np.concatenate([[starting_capital_usd], np.asarray(equity_usd, dtype=float)])
    return (1 - path / np.maximum.accumulate(path))[1:]


def inference_section(context, unseen, seed):
    """O7 against "do nothing" on the elites' unseen-year P&L (when there are enough)."""
    if unseen is None or len(context.elites) < 3:
        return {"status": "not run", "detail": "needs an unseen year and at least 3 elites"}
    evaluator = context.evaluator
    _, train_end, forward_end = context.window
    streams = [
        evaluator.evaluate(elite.genome, train_end, forward_end).daily_pnl_usd.astype(float)
        for elite in context.elites
    ]
    matrix = np.column_stack(streams)
    adjusted = romano_wolf_step_down(matrix, draws=500, seed=seed)
    return {
        "status": "run",
        "elites": len(context.elites),
        "reality_check_significance": reality_check_significance(matrix, draws=500, seed=seed),
        "spa_significance": spa_significance(matrix, draws=500, seed=seed),
        "romano_wolf_beating_do_nothing_at_5_percent": [
            context.elites[index].trader_id for index in np.flatnonzero(adjusted <= 0.05)
        ],
        "note": (
            "H0: no elite beats doing nothing on the unseen year "
            "(White 2000; Hansen 2005; Romano & Wolf 2005)."
        ),
    }
