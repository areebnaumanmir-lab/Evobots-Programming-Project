"""Hub prices as arrays [day, hour, hub], and the point-in-time features traders read.

The arrays come from the Stage A store (`data/store/hub_prices.csv.gz`, evolution period
only) or, when MISO data hasn't been built on this machine, from the synthetic market
(`evobots.data.synthetic`), clearly labelled as demo data.

**What a trader sees for operating day D** (decision at 10:30 Eastern on D−1,
`evobots.data.visible`):
- DA prices up to day D−1 (published 16:30 on D−2), so `da_last` is DA of the same hour on
  D−1;
- final RT prices up to day D−6, so every spread statistic uses days D−6 and earlier.

Features (a subset of the 25 in `docs/design_spec.md` §8; weather, gas and capacity features arrive
with the feature layer, M2):

| Name | Unit | Meaning |
|---|---|---|
| spread_mean_7d | $/MWh | mean DA − RT, this hub and hour, days D−12 … D−6 |
| spread_mean_28d | $/MWh | the same over days D−33 … D−6 |
| spread_std_28d | $/MWh | standard deviation over days D−33 … D−6 |
| spread_pos_frac_28d | fraction | share of those days with DA > RT |
| spread_spike_frac_28d | fraction | share of those days with abs(DA − RT) > $50/MWh |
| da_last | $/MWh | DA price of this hub and hour on D−1 |
| hour | hour | hour ending, 1–24 |
| weekday | day | 0 = Monday … 6 = Sunday, of day D |

Example:
    >>> market = synthetic_hub_market(days=60, seed=1)
    >>> features = point_in_time_features(market)
    >>> float(features["hour"][0, 13, 0]), bool(np.isnan(features["spread_mean_7d"][5, 0, 0]))
    (14.0, True)
"""

import csv
import dataclasses
import datetime
import gzip
from pathlib import Path

import numpy as np

from evobots.config.capital import STAGE_A_HUBS
from evobots.data.periods import EVOLUTION_LAST_DAY
from evobots.data.synthetic import synthetic_market

HUB_PRICES_PATH = Path("data/store/hub_prices.csv.gz")
# A cached copy of the arrays, rebuilt when the CSV changes (git-ignored, under data/store).
ARRAY_CACHE_PATH = Path("data/store/hub_arrays.npz")
# Bumped when the cached arrays change, so an old cache is rebuilt.
ARRAY_CACHE_VERSION = 2
HOURS_PER_DAY = 24
# Demo data: a planted DA premium (DA above RT on average) in hours ending 7–22, like the
# real MISO premium at every hub (capital_sizing.md §1), so the search has something it can
# find from the price features. Demo only; real data has no planted pattern.
DEMO_PREMIUM_USD_PER_MWH = 2.0
DEMO_PREMIUM_HOURS = (7, 22)
# Final RT for day t is public from t+5, so on decision day D−1 the newest is D−6.
NEWEST_SPREAD_LAG_DAYS = 6
SHORT_WINDOW_DAYS = 7
LONG_WINDOW_DAYS = 28
SPIKE_THRESHOLD_USD_PER_MWH = 50.0
FEATURE_UNITS = {
    "spread_mean_7d": "$/MWh",
    "spread_mean_28d": "$/MWh",
    "spread_std_28d": "$/MWh",
    "spread_pos_frac_28d": "fraction",
    "spread_spike_frac_28d": "fraction",
    "da_last": "$/MWh",
    "hour": "hour",
    "weekday": "day",
}
FEATURE_DISPLAY_NAMES = {
    "spread_mean_7d": "Average DA − RT spread, last 7 visible days ($/MWh)",
    "spread_mean_28d": "Average DA − RT spread, last 28 visible days ($/MWh)",
    "spread_std_28d": "Spread volatility, last 28 visible days ($/MWh)",
    "spread_pos_frac_28d": "Share of days with DA above RT, last 28 visible days",
    "spread_spike_frac_28d": "Share of days with a spread above $50, last 28 visible days",
    "da_last": "Yesterday's DA price, same hour ($/MWh)",
    "hour": "Hour ending (1–24)",
    "weekday": "Day of week (0 = Monday)",
}
FEATURE_NAMES = tuple(FEATURE_UNITS)


@dataclasses.dataclass(frozen=True)
class HubMarket:
    """DA and RT prices for every day, hour and hub of a period.

    Attributes:
        days: operating days, consecutive, as datetime.date.
        hubs: hub names, in array order.
        day_ahead: DA prices, $/MWh, shape (days, 24, hubs); NaN where not published.
        real_time: final RT prices, $/MWh, same shape.
        source: "MISO" or "synthetic demo data".
        day_ahead_congestion: DA congestion components (MCC), $/MWh, same shape; NaN where
            not published (before 2005-06-16) or None when the source has none.
        location_types: MISO location type of each column ("Hub" at Stage A); None = hubs.
    """

    days: tuple
    hubs: tuple
    day_ahead: np.ndarray
    real_time: np.ndarray
    source: str
    day_ahead_congestion: np.ndarray | None = None
    location_types: tuple | None = None

    @property
    def locations(self):
        """Column names (hubs at Stage A, every location at Stage C)."""
        return self.hubs

    def types(self):
        """Location type of every column."""
        return self.location_types or ("Hub",) * len(self.hubs)

    def day_index(self, day):
        """Index of a date in `days` (the first day on or after it)."""
        return int(np.searchsorted(np.array(self.days, dtype="datetime64[D]"), np.datetime64(day)))


def read_miso_hub_market(path=HUB_PRICES_PATH, cache_path=ARRAY_CACHE_PATH):
    """Load the Stage A hub table into a HubMarket (evolution period only), with a cache.

    Returns:
        A HubMarket, or None when the table doesn't exist on this machine.
    """
    path, cache_path = Path(path), Path(cache_path)
    if not path.exists():
        return None
    if cache_path.exists() and cache_path.stat().st_mtime >= path.stat().st_mtime:
        cached = np.load(cache_path, allow_pickle=False)
        if "version" in cached and int(cached["version"]) == ARRAY_CACHE_VERSION:
            days = tuple(
                datetime.date.fromisoformat(text) for text in cached["days"].astype(str).tolist()
            )
            return HubMarket(
                days,
                tuple(cached["hubs"].astype(str).tolist()),
                cached["da"],
                cached["rt"],
                "MISO",
                day_ahead_congestion=cached["da_mcc"],
            )
    first_day, last_day = None, EVOLUTION_LAST_DAY
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as table:
        for row in csv.DictReader(table):
            day = datetime.date.fromisoformat(row["date"])
            if day > last_day or row["hub"] not in STAGE_A_HUBS:
                continue
            first_day = day if first_day is None else min(first_day, day)
            rows.append(row)
    days = tuple(
        first_day + datetime.timedelta(days=offset)
        for offset in range((last_day - first_day).days + 1)
    )
    hubs = tuple(STAGE_A_HUBS)
    hub_index = {hub: index for index, hub in enumerate(hubs)}
    day_ahead = np.full((len(days), HOURS_PER_DAY, len(hubs)), np.nan)
    real_time = np.full_like(day_ahead, np.nan)
    day_ahead_congestion = np.full_like(day_ahead, np.nan)
    for row in rows:
        day = (datetime.date.fromisoformat(row["date"]) - first_day).days
        hour = int(row["hour_ending_est"]) - 1
        hub = hub_index[row["hub"]]
        if row["da_lmp"]:
            day_ahead[day, hour, hub] = float(row["da_lmp"])
        if row["rt_lmp"]:
            real_time[day, hour, hub] = float(row["rt_lmp"])
        if row["da_mcc"]:
            day_ahead_congestion[day, hour, hub] = float(row["da_mcc"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = cache_path.with_name(cache_path.stem + ".part.npz")
    np.savez(
        partial_path,
        days=np.array([day.isoformat() for day in days]),
        hubs=np.array(hubs),
        da=day_ahead,
        rt=real_time,
        da_mcc=day_ahead_congestion,
        version=np.array(ARRAY_CACHE_VERSION),
    )
    partial_path.replace(cache_path)
    return HubMarket(
        days, hubs, day_ahead, real_time, "MISO", day_ahead_congestion=day_ahead_congestion
    )


def synthetic_hub_market(days=3653, seed=0, last_day=EVOLUTION_LAST_DAY):
    """A demo HubMarket: GARCH spreads plus a planted DA premium in hours 7–22 (see above)."""
    generated = synthetic_market(
        days=days,
        hubs=len(STAGE_A_HUBS),
        model="garch",
        seed=seed,
        planted_premium_usd_per_mwh=6.0,
    )
    hour_ending = np.arange(1, HOURS_PER_DAY + 1)
    is_premium_hour = (hour_ending >= DEMO_PREMIUM_HOURS[0]) & (
        hour_ending <= DEMO_PREMIUM_HOURS[1]
    )
    real_time = generated.real_time - DEMO_PREMIUM_USD_PER_MWH * is_premium_hour[None, :, None]
    first_day = last_day - datetime.timedelta(days=days - 1)
    day_list = tuple(first_day + datetime.timedelta(days=offset) for offset in range(days))
    # Demo congestion: each hub's DA difference from the all-hub mean, so the share feature
    # has something location-specific in it (illustrative, not a model of congestion).
    congestion = generated.day_ahead - generated.day_ahead.mean(axis=2, keepdims=True)
    return HubMarket(
        day_list,
        tuple(STAGE_A_HUBS),
        generated.day_ahead,
        real_time,
        "synthetic demo data",
        day_ahead_congestion=congestion,
    )


def lagged_window_statistics(values, window_days, lag_days):
    """Mean, standard deviation and count over days t−lag−window+1 … t−lag, per hour and hub.

    Args:
        values: array (days, 24, hubs); NaN = unknown.
        window_days: window length in days.
        lag_days: the newest day used is t − lag_days.

    Returns:
        (mean, standard deviation with ddof 0, count) arrays of the same shape; NaN where
        fewer than half the window is known.
    """
    is_known = ~np.isnan(values)
    filled = np.where(is_known, values, 0.0)
    zeros = np.zeros((1, *values.shape[1:]))
    cumulative_sum = np.concatenate([zeros, np.cumsum(filled, axis=0)])
    cumulative_square = np.concatenate([zeros, np.cumsum(filled**2, axis=0)])
    cumulative_count = np.concatenate([zeros, np.cumsum(is_known, axis=0)])
    day_count = values.shape[0]
    end = np.arange(day_count) - lag_days + 1  # exclusive end index into the cumulative arrays
    start = end - window_days
    end_clipped = np.clip(end, 0, day_count)
    start_clipped = np.clip(start, 0, day_count)
    total = cumulative_sum[end_clipped] - cumulative_sum[start_clipped]
    square_total = cumulative_square[end_clipped] - cumulative_square[start_clipped]
    count = cumulative_count[end_clipped] - cumulative_count[start_clipped]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / count
        variance = np.maximum(square_total / count - mean**2, 0.0)
    is_enough = (count >= window_days / 2) & (start[:, None, None] >= 0)
    return (
        np.where(is_enough, mean, np.nan),
        np.where(is_enough, np.sqrt(variance), np.nan),
        count,
    )


def point_in_time_features(market):
    """Every feature for every operating day, hour and hub, using only visible data.

    Returns:
        {feature name: array (days, 24, hubs)}, NaN where not available.
    """
    spread = market.day_ahead - market.real_time
    mean_short, _, _ = lagged_window_statistics(spread, SHORT_WINDOW_DAYS, NEWEST_SPREAD_LAG_DAYS)
    mean_long, deviation_long, _ = lagged_window_statistics(
        spread, LONG_WINDOW_DAYS, NEWEST_SPREAD_LAG_DAYS
    )
    is_known = ~np.isnan(spread)
    positive = np.where(is_known, (spread > 0).astype(float), np.nan)
    spike = np.where(is_known, (np.abs(spread) > SPIKE_THRESHOLD_USD_PER_MWH).astype(float), np.nan)
    positive_share, _, _ = lagged_window_statistics(
        positive, LONG_WINDOW_DAYS, NEWEST_SPREAD_LAG_DAYS
    )
    spike_share, _, _ = lagged_window_statistics(spike, LONG_WINDOW_DAYS, NEWEST_SPREAD_LAG_DAYS)
    day_ahead_last = np.full_like(market.day_ahead, np.nan)
    day_ahead_last[1:] = market.day_ahead[:-1]
    shape = market.day_ahead.shape
    hour = np.broadcast_to(np.arange(1, HOURS_PER_DAY + 1, dtype=float)[None, :, None], shape)
    weekday = np.array([day.weekday() for day in market.days], dtype=float)
    return {
        "spread_mean_7d": mean_short,
        "spread_mean_28d": mean_long,
        "spread_std_28d": deviation_long,
        "spread_pos_frac_28d": positive_share,
        "spread_spike_frac_28d": spike_share,
        "da_last": day_ahead_last,
        "hour": np.array(hour),
        "weekday": np.broadcast_to(weekday[:, None, None], shape).copy(),
    }


def planted_hub_market(
    days, seed=0, planted_premium_usd_per_mwh=6.0, model="noise", last_day=EVOLUTION_LAST_DAY
):
    """A test market from `evobots.data.synthetic.synthetic_market` without the demo premium.

    Returns (HubMarket, forecast high per day and hub): on hub-hours where the synthetic
    forecast high exceeds 85 °F and the hour ending is 14–19, RT is raised by the planted
    premium (0 = pure noise), so a DEC bid there earns it on average (M4's planted-signal test).
    """
    generated = synthetic_market(
        days=days,
        hubs=len(STAGE_A_HUBS),
        model=model,
        seed=seed,
        planted_premium_usd_per_mwh=planted_premium_usd_per_mwh,
    )
    first_day = last_day - datetime.timedelta(days=days - 1)
    day_list = tuple(first_day + datetime.timedelta(days=offset) for offset in range(days))
    congestion = generated.day_ahead - generated.day_ahead.mean(axis=2, keepdims=True)
    market = HubMarket(
        day_list,
        tuple(STAGE_A_HUBS),
        generated.day_ahead,
        generated.real_time,
        "synthetic test data",
        day_ahead_congestion=congestion,
    )
    return market, generated.forecast_high_degf, generated.is_planted
