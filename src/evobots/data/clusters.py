"""Stage D: clustered representative locations, recomputed every year (`docs/design_spec.md` §7.10).

Stage D sits between the 8 trading hubs (Stage A) and every location (Stage C). For each
calendar year Y it groups the locations whose DA − RT spreads move together and keeps one
location per group, so a run sees the market's distinct congestion patterns at a fraction
of Stage C's cost. It follows the idea of correlation clustering of nodal price series used
for CAISO in arXiv 2210.06543 (Stage D's grouping step only; the details below are this
project's choices, round 40).

**Point-in-time.** The groups for year Y use only spreads a trader could see before Y starts:
final RT is public through D−6, so the window is the 365 days ending 6 days before 1 January
Y. A year with under 90 priced days in its window (2005) uses the hubs alone.

**Steps for one year:**
1. The daily mean spread (DA − RT, $/MWh) of every location over the window.
2. Keep locations priced on at least 90 % of the window's priced days and on its last day
   (still in the market).
3. Spearman correlation between every pair (ranks, so a few $1,000 spikes don't dominate);
   missing days take the location's median rank.
4. Average-linkage hierarchical clustering on the distance 1 − ρ, cut at
   `CLUSTER_DISTANCE_THRESHOLD` = 0.25 (round 40: 9–77 groups a year; 0.5 leaves 3–13
   because MISO's spreads share system-wide RT shocks, 0.15 gives up to 154 with many
   singletons).
5. Groups of one location are dropped (outliers, not patterns).
6. One representative per group: a trading hub when the group has one (hubs are the most
   liquid points); else last year's representative when one is in the group (so a period's
   Stage D market stays small); else the medoid (the member with the highest mean correlation
   to the others).

The trading hubs are always columns, so the hub-area code of every location (feature 9) can
be computed. The Stage D market of a period holds every location that represents a group in
any of its years; prices of the other years are kept for the features but traders can't
trade there (those years are NaN in the settlement market).

Example:
    >>> generator = np.random.default_rng(0)
    >>> base = generator.normal(size=(200, 2))
    >>> series = np.column_stack([base[:, 0], base[:, 0] + 0.1 * generator.normal(size=200),
    ...     base[:, 1], base[:, 1] + 0.1 * generator.normal(size=200)])
    >>> labels, _ = correlation_clusters(series, 0.5)
    >>> len(set(labels)), bool(labels[0] == labels[1]), bool(labels[0] == labels[2])
    (2, True, False)
"""

import dataclasses
import datetime
import json
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import rankdata

from evobots.data.location_store import LocationStore
from evobots.data.periods import EVOLUTION_LAST_DAY, MARKET_FIRST_DAY

CLUSTERS_PATH = Path("data/store/stage_d_clusters.json")
CLUSTER_DISTANCE_THRESHOLD = 0.25
# A group of one location is an outlier, not a pattern; it gets no representative.
MINIMUM_GROUP_SIZE = 2
LOOKBACK_DAYS = 365
VISIBLE_LAG_DAYS = 6
MINIMUM_COVERAGE = 0.9
# Fewer priced days than this in the window: no groups that year (Stage A's hubs only).
MINIMUM_HISTORY_DAYS = 90


def is_trading_hub(name, location_type):
    """A trading hub: type "Hub" and a name ending ".HUB" (Stage A's rule)."""
    return location_type == "Hub" and name.endswith(".HUB")


def correlation_clusters(series, threshold):
    """Group the columns of series [day, location] by Spearman correlation.

    Args:
        series: daily values, NaN = missing.
        threshold: cut height on the distance 1 − ρ (average linkage).

    Returns:
        (labels 1…k per column, the correlation matrix).
    """
    ranks = np.empty_like(series, dtype=float)
    for column in range(series.shape[1]):
        values = series[:, column]
        known = ~np.isnan(values)
        column_ranks = np.full(len(values), np.nan)
        column_ranks[known] = rankdata(values[known]) / max(known.sum(), 1)
        column_ranks[~known] = np.nanmedian(column_ranks) if known.any() else 0.5
        ranks[:, column] = column_ranks
    if series.shape[1] == 1:
        return np.array([1]), np.ones((1, 1))
    correlation = np.corrcoef(ranks, rowvar=False)
    correlation = np.nan_to_num(correlation, nan=0.0)
    np.fill_diagonal(correlation, 1.0)
    distance = np.clip(1.0 - correlation, 0.0, 2.0)
    distance = (distance + distance.T) / 2
    np.fill_diagonal(distance, 0.0)
    tree = linkage(squareform(distance, checks=False), method="average")
    return fcluster(tree, threshold, criterion="distance"), correlation


@dataclasses.dataclass
class YearClusters:
    """The groups chosen for one year."""

    year: int
    window: tuple
    candidates: int
    representatives: list
    sizes: list

    def to_json(self):
        """JSON-ready dict."""
        return dataclasses.asdict(self)


def cluster_year(store, year, threshold=CLUSTER_DISTANCE_THRESHOLD, previous=()):
    """The representatives for one year (see the module docstring).

    `previous` holds last year's representatives: a group containing one keeps it, so the
    Stage D market of a multi-year period stays small (round 40).
    """
    last_visible = datetime.date(year, 1, 1) - datetime.timedelta(days=VISIBLE_LAG_DAYS)
    first = max(last_visible - datetime.timedelta(days=LOOKBACK_DAYS - 1), MARKET_FIRST_DAY)
    types = store.location_types()
    if last_visible < MARKET_FIRST_DAY:
        return YearClusters(year, (None, None), 0, [], [])
    _, names, daily = store.daily_spreads(first, last_visible)
    priced_days = ~np.all(np.isnan(daily), axis=1)
    daily = daily[priced_days]
    if len(daily) < MINIMUM_HISTORY_DAYS:
        return YearClusters(year, (first.isoformat(), last_visible.isoformat()), 0, [], [])
    coverage = (~np.isnan(daily)).mean(axis=0)
    is_alive = ~np.isnan(daily[-1])
    keep = np.flatnonzero((coverage >= MINIMUM_COVERAGE) & is_alive)
    kept_names = [names[index] for index in keep]
    labels, correlation = correlation_clusters(daily[:, keep], threshold)
    representatives, sizes = [], []
    for label in np.unique(labels):
        members = np.flatnonzero(labels == label)
        if len(members) < MINIMUM_GROUP_SIZE:
            continue
        hubs = [
            index
            for index in members
            if is_trading_hub(kept_names[index], types.get(kept_names[index]))
        ]
        kept_before = [index for index in members if kept_names[index] in previous]
        if hubs:
            chosen = hubs[0]
        elif kept_before:
            within = correlation[np.ix_(kept_before, members)]
            chosen = kept_before[int(np.argmax(within.mean(axis=1)))]
        else:
            within = correlation[np.ix_(members, members)]
            chosen = members[int(np.argmax(within.mean(axis=1)))]
        representatives.append(kept_names[chosen])
        sizes.append(int(len(members)))
    order = np.argsort(sizes)[::-1]
    return YearClusters(
        year,
        (first.isoformat(), last_visible.isoformat()),
        len(kept_names),
        [representatives[index] for index in order],
        [sizes[index] for index in order],
    )


def build_clusters(store=None, path=CLUSTERS_PATH, threshold=CLUSTER_DISTANCE_THRESHOLD):
    """Cluster every year of the evolution period and write the JSON file."""
    store = store or LocationStore()
    years = range(MARKET_FIRST_DAY.year, EVOLUTION_LAST_DAY.year + 1)
    result = {
        "threshold": threshold,
        "lookback_days": LOOKBACK_DAYS,
        "minimum_coverage": MINIMUM_COVERAGE,
        "years": [],
    }
    previous = ()
    for year in years:
        entry = cluster_year(store, year, threshold, previous)
        result["years"].append(entry.to_json())
        previous = set(entry.representatives)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(result, indent=1), encoding="utf-8")
    partial.replace(path)
    return result


def read_clusters(path=CLUSTERS_PATH):
    """The clusters file, or None when Stage D isn't built."""
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def clustered_markets(first_day, last_day, store=None, clusters=None):
    """(feature market, settlement market) for Stage D over a period (see `clustered_market`)."""
    features, blank = clustered_market(first_day, last_day, store, clusters)
    settlement = dataclasses.replace(
        features,
        day_ahead=features.day_ahead.copy(),
        real_time=features.real_time.copy(),
        day_ahead_congestion=features.day_ahead_congestion.copy(),
    )
    blank(settlement)
    return features, settlement


def clustered_market(first_day, last_day, store=None, clusters=None):
    """The Stage D market of a period, and a function that blanks it for settlement.

    The market has every price of the period's representatives and the trading hubs (for the
    features). `blank(market)` then sets, in place, each representative's prices to NaN
    outside the years it represents a group, so it trades only there. Blanking in place
    after the features are built saves a second copy of the prices.
    """
    store = store or LocationStore()
    clusters = clusters or read_clusters()
    by_year = {entry["year"]: set(entry["representatives"]) for entry in clusters["years"]}
    types = store.location_types()
    hubs = {name for name, kind in types.items() if is_trading_hub(name, kind)}
    chosen = set(hubs)
    for year in range(first_day.year, last_day.year + 1):
        chosen |= by_year.get(year, set())
    market = store.market(first_day, last_day, sorted(chosen))

    def blank(target):
        years = np.array([day.year for day in target.days])
        for column, name in enumerate(target.hubs):
            if name in hubs:
                continue
            outside = ~np.isin(years, [year for year, names in by_year.items() if name in names])
            for array in (target.day_ahead, target.real_time, target.day_ahead_congestion):
                array[outside, :, column] = np.nan

    return market, blank
