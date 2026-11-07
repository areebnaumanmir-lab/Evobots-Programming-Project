"""Score one trader on one window: bids → settlement → career → fitness (§10, §11).

An `Evaluator` holds everything shared by a run: the market, the feature store, each
location's hard cap, the account and career rules, the cost table and the risk-free rate.
`evaluate(genome, start, end)` returns an `Evaluation`, the numbers MAP-Elites and the gates
need: fitness, survival, the two map descriptors, drawdown and the daily P&L stream.

The risk-free rate is FRED's 3-month bill (DTB3), the rate in force each day, as a daily log
return (`docs/maths.md` §3.1); without the file it is zero and reports say so.

Example:
    >>> from evobots.bots.founders import FOUNDERS
    >>> evaluator = Evaluator.synthetic(days=900, seed=2)
    >>> evaluation = evaluator.evaluate(FOUNDERS["always_inc"], 500, 900)
    >>> evaluation.is_alive, round(evaluation.net_direction, 2)
    (True, -1.0)
"""

import dataclasses
import datetime
import math
from pathlib import Path

import numpy as np

from evobots.bots.grammar import EvaluationCache
from evobots.bots.trader import behaviour_id, trader_decisions
from evobots.career.model import PRESETS, apply_career
from evobots.config.capital import CapitalSettings
from evobots.data.sources.series import daily_risk_free_log_return, read_fred_dtb3
from evobots.features.inputs import load_feature_inputs, synthetic_feature_inputs
from evobots.features.store import build_feature_store, feature_summary
from evobots.simulate.fees import CostTable
from evobots.simulate.market import read_miso_hub_market, synthetic_hub_market
from evobots.simulate.settlement import SIZING_HISTORY_DAYS, AccountRules, settle

HOURS_PER_DAY = 24
FRED_DIRECTORY = Path("data/raw/series/fred_dtb3")
# Behaviour ids hash the bids on this many days ending at the reference day (§9.4).
BEHAVIOUR_WINDOW_DAYS = 120


@dataclasses.dataclass(frozen=True)
class Evaluation:
    """One trader on one window.

    Attributes:
        start: first window day index.
        end: one past the last.
        fitness: F (career-adjusted excess log growth minus parsimony).
        log_growth: ln(W_T/W_0).
        final_equity_usd: equity at the end.
        is_alive: never stopped by death or a career layer.
        stop_index: window day of the stop, or None.
        stop_cause: why it stopped, or None.
        net_direction: (DEC − INC) ÷ cleared MWh.
        selectivity: share of priced location-hours bid.
        max_drawdown_fraction: worst fall from a peak.
        cleared_mwh: total cleared MWh.
        fees_usd: total fees.
        daily_pnl_usd: float32 daily P&L (for the gates).
        equity_usd: float32 end-of-day equity.
    """

    start: int
    end: int
    fitness: float
    log_growth: float
    final_equity_usd: float
    is_alive: bool
    stop_index: int | None
    stop_cause: str | None
    net_direction: float
    selectivity: float
    max_drawdown_fraction: float
    cleared_mwh: float
    fees_usd: float
    daily_pnl_usd: np.ndarray
    equity_usd: np.ndarray

    def daily_returns(self, starting_capital_usd):
        """P&L ÷ equity at the start of each day."""
        before = np.concatenate([[starting_capital_usd], self.equity_usd[:-1].astype(float)])
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(before > 0, self.daily_pnl_usd / before, 0.0)


def risk_free_by_day(days, root=Path(".")):
    """Daily risk-free log return for each day (rate in force that day), or None."""
    files = sorted((Path(root) / FRED_DIRECTORY).glob("*.csv"))
    if not files:
        return None
    series = read_fred_dtb3(files[-1])
    observation_days = [day.toordinal() for day in series.days]
    rates = np.array(series.values)
    index = np.searchsorted(observation_days, [day.toordinal() for day in days], side="right") - 1
    returns = np.array(
        [
            daily_risk_free_log_return(rates[position]) if position >= 0 else 0.0
            for position in index
        ]
    )
    return returns


@dataclasses.dataclass
class Evaluator:
    """Shared inputs of a run, and the scoring function."""

    market: object
    store: object
    capital: CapitalSettings = dataclasses.field(default_factory=CapitalSettings)
    career: object = PRESETS["individual"]
    cost_table: CostTable = dataclasses.field(default_factory=CostTable.estimates)
    risk_free_daily: np.ndarray | None = None
    cache: EvaluationCache = dataclasses.field(default_factory=lambda: EvaluationCache(256 * 2**20))
    behaviour_reference_end: int | None = None

    def __post_init__(self):
        """Each location's hard cap and the full-size footprint."""
        caps_by_hub = self.capital.hub_caps_mw()
        default_cap = self.capital.max_mw_per_hub_hour
        self.caps_mw = np.array(
            [caps_by_hub.get(name, default_cap) for name in self.store.locations]
        )
        self.footprint_mwh = float(self.caps_mw.sum() * HOURS_PER_DAY)
        if self.behaviour_reference_end is None:
            self.behaviour_reference_end = len(self.store.days)
        self.summary = None

    @classmethod
    def from_store(
        cls, root=Path("."), capital=None, career=None, stage="A", first_day=None, last_day=None
    ):
        """The MISO evaluator from the data built on this machine, or None without data.

        Args:
            root: the project folder.
            capital: capital settings (default when None).
            career: career preset (default when None).
            stage: "A" (trading hubs), "D" (yearly cluster representatives) or "C" (every
                location; give first_day and last_day, since the whole period doesn't fit in
                memory).
            first_day: first day for stages D and C (default: 2005-04-01).
            last_day: last day for stages D and C (default: 2025-09-21).
        """
        root = Path(root)
        blank = None
        if stage == "A":
            market = read_miso_hub_market(
                root / "data/store/hub_prices.csv.gz", root / "data/store/hub_arrays.npz"
            )
        else:
            market, blank = location_market(root, stage, first_day, last_day)
        if market is None:
            return None
        store = build_feature_store(market, load_feature_inputs(root))
        if blank is not None:
            blank(market)  # Stage D: trade only where a location represents its year
        return cls(
            market,
            store,
            capital or CapitalSettings(),
            career or PRESETS["individual"],
            risk_free_daily=risk_free_by_day(market.days, root),
        )

    @classmethod
    def synthetic(cls, days=3653, seed=0, market=None, inputs=None, capital=None, career=None):
        """A demo evaluator on synthetic prices and inputs (labelled demo data)."""
        market = market or synthetic_hub_market(days=days, seed=seed)
        inputs = inputs or synthetic_feature_inputs(market.days, market.hubs, seed=seed + 1)
        store = build_feature_store(market, inputs)
        return cls(market, store, capital or CapitalSettings(), career or PRESETS["individual"])

    def constant_summary(self):
        """Feature quantiles over the store (cached), for constant ranges."""
        if self.summary is None:
            self.summary = feature_summary(self.store)
        return self.summary

    def account_rules(self, genome, cost_multiple=1.0):
        """The AccountRules for a genome: capital settings plus its risk genes."""
        return AccountRules(
            starting_capital_usd=self.capital.starting_capital_usd,
            daily_risk_budget_fraction=self.capital.daily_risk_budget_fraction,
            credit_share_fraction=self.capital.credit_share_fraction,
            max_mwh_per_day=genome.daily_cap_fraction * self.footprint_mwh,
            pause_loss_fraction=genome.pause_loss_fraction if genome.pause_days else math.inf,
            pause_days=int(genome.pause_days),
            cost_multiple=cost_multiple,
        )

    def decisions(self, genome, start, end):
        """Full-size bids for days start … end−1 (from the start of the sizing history)."""
        history_start = max(0, start - SIZING_HISTORY_DAYS)
        return trader_decisions(genome, self.store, history_start, end, self.caps_mw, self.cache)

    def behaviour(self, genome):
        """Behaviour id: hash of the bids on the fixed reference window (§9.4)."""
        end = self.behaviour_reference_end
        start = max(0, end - BEHAVIOUR_WINDOW_DAYS)
        return behaviour_id(
            trader_decisions(genome, self.store, start, end, self.caps_mw, self.cache)
        )

    def evaluate(self, genome, start, end, cost_multiple=1.0, career=None):
        """Score a genome on days start … end−1 (see the module docstring)."""
        decisions = self.decisions(genome, start, end)
        result = settle(
            decisions,
            self.market,
            start,
            end,
            self.account_rules(genome, cost_multiple),
            self.cost_table,
        )
        risk_free = None if self.risk_free_daily is None else self.risk_free_daily[start:end]
        outcome = apply_career(result, career or self.career, genome.node_count(), risk_free)
        return Evaluation(
            start=start,
            end=end,
            fitness=float(outcome.fitness),
            log_growth=float(outcome.log_growth),
            final_equity_usd=float(outcome.equity_usd[-1])
            if len(outcome.equity_usd)
            else self.capital.starting_capital_usd,
            is_alive=outcome.stop_index is None,
            stop_index=outcome.stop_index,
            stop_cause=outcome.stop_cause,
            net_direction=result.net_direction,
            selectivity=result.selectivity,
            max_drawdown_fraction=max_drawdown(
                outcome.equity_usd, self.capital.starting_capital_usd
            ),
            cleared_mwh=result.cleared_mwh,
            fees_usd=float(result.fees_usd.sum()),
            daily_pnl_usd=outcome.daily_pnl_usd.astype(np.float32),
            equity_usd=outcome.equity_usd.astype(np.float32),
        )

    def day(self, index):
        """The operating day at a store index."""
        return self.store.days[index]

    def index_of(self, day):
        """The store index of an operating day (the first on or after it)."""
        ordinals = [value.toordinal() for value in self.store.days]
        return int(np.searchsorted(ordinals, day.toordinal()))


def location_market(root, stage, first_day=None, last_day=None):
    """(market, blank or None) of Stage D or C, or (None, None) when not built.

    For Stage D, `blank(market)` must be applied after the features are built (it removes the
    years a location doesn't represent a group, in place).
    """
    from evobots.data.clusters import CLUSTERS_PATH, clustered_market, read_clusters
    from evobots.data.location_store import LOCATION_STORE_DIRECTORY, LocationStore
    from evobots.data.periods import EVOLUTION_LAST_DAY, MARKET_FIRST_DAY

    store = LocationStore(Path(root) / LOCATION_STORE_DIRECTORY)
    if not store.years():
        return None, None
    first_day = first_day or MARKET_FIRST_DAY
    last_day = min(last_day or EVOLUTION_LAST_DAY, EVOLUTION_LAST_DAY)
    if stage == "C":
        return store.market(first_day, last_day), None
    if stage != "D":
        raise ValueError(f"stage must be A, D or C, not {stage!r}")
    clusters = read_clusters(Path(root) / CLUSTERS_PATH)
    if clusters is None:
        return None, None
    return clustered_market(first_day, last_day, store, clusters)


def max_drawdown(equity_usd, starting_capital_usd):
    """Largest fall from a running peak, as a share of the peak."""
    if not len(equity_usd):
        return 0.0
    path = np.concatenate([[starting_capital_usd], np.asarray(equity_usd, dtype=float)])
    peaks = np.maximum.accumulate(path)
    return float(np.max(1 - path / peaks))


def days_between(first, last):
    """Calendar days from first to last."""
    return (last - first).days if isinstance(first, datetime.date) else int(last - first)
