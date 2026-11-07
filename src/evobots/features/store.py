"""The feature store: every catalogue feature for every operating day, hour and location.

`build_feature_store(market, inputs)` computes the 25 features of `catalogue.FEATURES` from a
`HubMarket` and `FeatureInputs`, using only what was public at each decision time (10:30
Eastern on D−1; `evobots.data.visible`):

| Data | Newest day visible for operating day D |
|---|---|
| DA prices and congestion | D−1 (published 16:30 on D−2) |
| final RT prices | D−6 (published at the start of t+5) |
| forecasts | the issue fetched for decision day D−1 (≤ 24 h before the decision) |
| capacity | the month of D−1 |
| Henry Hub | trade days t with t + 1 business day ≤ D−1 |
| EPU | days t with t + 2 days ≤ D−1 |

Arrays keep their natural shape and are broadcast to (days, 24, locations) on reading, so
the 25 features of the eight hubs over 20 years take about 100 MB, not 25 full cubes
(`docs/design_spec.md` §8: "three tables at three granularities"). Categories are stored
as float codes (index into the catalogue's category list) and booleans as 0/1; missing is
NaN everywhere, and any comparison with a missing value is false (§8).

Example:
    >>> from evobots.simulate.market import synthetic_hub_market
    >>> from evobots.features.inputs import synthetic_feature_inputs
    >>> market = synthetic_hub_market(days=200, seed=4)
    >>> store = build_feature_store(market, synthetic_feature_inputs(market.days, market.hubs, 1))
    >>> store.window("hour", 0, 2).shape
    (2, 24, 8)
    >>> sorted(store.arrays) == sorted(FEATURE_NAMES)
    True
"""

import dataclasses
import datetime

import numpy as np

from evobots.data.periods import EVOLUTION_LAST_DAY
from evobots.data.visible import add_business_days
from evobots.features.calendar import is_nerc_holiday
from evobots.features.catalogue import (
    FEATURE_BY_NAME,
    FEATURE_NAMES,
    LOCATION_TYPES,
    REGIONS,
)
from evobots.simulate.market import lagged_window_statistics

HOURS_PER_DAY = 24
# Newest final-RT day visible for operating day D is D−6; newest DA day is D−1.
SPREAD_LAG_DAYS = 6
DAY_AHEAD_LAG_DAYS = 1
SHORT_WINDOW_DAYS = 7
LONG_WINDOW_DAYS = 28
SPIKE_THRESHOLD_USD_PER_MWH = 50.0
# Congestion share: a 28-day mean DA price closer to zero than this gives a missing share
# (a ratio of near-zero means is noise, not information).
MINIMUM_MEAN_PRICE_FOR_SHARE_USD_PER_MWH = 1.0
# loc_region: correlation of daily mean DA prices over the past 365 visible days, needing at
# least 90 days with both prices (docs/design_spec.md §8, feature 9).
REGION_WINDOW_DAYS = 365
REGION_MINIMUM_DAYS = 90
# Degree-day base temperature, °F (US convention).
DEGREE_DAY_BASE_DEGF = 65.0
GAS_CHANGE_TRADING_DAYS = 5
GAS_VOLATILITY_TRADING_DAYS = 20
# Publication lags (days after the observation; business days for gas), as in
# `evobots.data.sources.series.PUBLICATION_LAG_DAYS_BY_SERIES`.
GAS_LAG_BUSINESS_DAYS = 1
EPU_LAG_DAYS = 2
LOCATION_CHUNK = 512


@dataclasses.dataclass
class FeatureStore:
    """Feature arrays for one market.

    Attributes:
        days: operating days, consecutive.
        locations: location names (the columns).
        arrays: {feature name: float64 array broadcastable to (days, 24, locations)}.
        source: where the prices came from ("MISO" or "synthetic demo data").
        inputs_description: where the other inputs came from.
    """

    days: tuple
    locations: tuple
    arrays: dict
    source: str = ""
    inputs_description: str = ""

    def window(self, name, start, end):
        """Feature `name` for days start … end−1, as a read-only (days, 24, locations) view."""
        array = self.arrays[name]
        part = array[start:end] if array.shape[0] > 1 else array
        return np.broadcast_to(part, (end - start, HOURS_PER_DAY, len(self.locations)))

    def full(self, name):
        """Feature `name` for every day, as a (days, 24, locations) view."""
        return self.window(name, 0, len(self.days))

    def with_missing(self, names):
        """A copy in which the named features are missing everywhere (the hindsight check)."""
        arrays = dict(self.arrays)
        for name in names:
            arrays[name] = np.full((1, 1, 1), np.nan)
        return dataclasses.replace(self, arrays=arrays)


def price_features(market):
    """Features 1–7 from DA, RT and DA congestion, shape (days, 24, locations)."""
    spread = market.day_ahead - market.real_time
    mean_short, _, _ = lagged_window_statistics(spread, SHORT_WINDOW_DAYS, SPREAD_LAG_DAYS)
    mean_long, deviation_long, _ = lagged_window_statistics(
        spread, LONG_WINDOW_DAYS, SPREAD_LAG_DAYS
    )
    is_known = ~np.isnan(spread)
    positive = np.where(is_known, (spread > 0).astype(float), np.nan)
    spike = np.where(is_known, (np.abs(spread) > SPIKE_THRESHOLD_USD_PER_MWH).astype(float), np.nan)
    positive_share, _, _ = lagged_window_statistics(positive, LONG_WINDOW_DAYS, SPREAD_LAG_DAYS)
    spike_share, _, _ = lagged_window_statistics(spike, LONG_WINDOW_DAYS, SPREAD_LAG_DAYS)
    day_ahead_last = np.full_like(market.day_ahead, np.nan)
    day_ahead_last[1:] = market.day_ahead[:-1]
    congestion_share = np.full_like(market.day_ahead, np.nan)
    if market.day_ahead_congestion is not None:
        congestion = market.day_ahead_congestion
        both = ~np.isnan(congestion) & ~np.isnan(market.day_ahead)
        mean_congestion, _, _ = lagged_window_statistics(
            np.where(both, congestion, np.nan), LONG_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS
        )
        mean_price, _, _ = lagged_window_statistics(
            np.where(both, market.day_ahead, np.nan), LONG_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            congestion_share = np.where(
                np.abs(mean_price) >= MINIMUM_MEAN_PRICE_FOR_SHARE_USD_PER_MWH,
                mean_congestion / mean_price,
                np.nan,
            )
    return {
        "spread_mean_7d": mean_short,
        "spread_mean_28d": mean_long,
        "spread_std_28d": deviation_long,
        "spread_pos_frac_28d": positive_share,
        "spread_spike_frac_28d": spike_share,
        "da_last": day_ahead_last,
        "congestion_share_28d": congestion_share,
    }


def rolling_sums(values, window_days, lag_days):
    """Sums over days t−lag−window+1 … t−lag along axis 0 (cumulative-sum form)."""
    zeros = np.zeros((1, *values.shape[1:]))
    cumulative = np.concatenate([zeros, np.cumsum(values, axis=0)])
    day_count = values.shape[0]
    end = np.clip(np.arange(day_count) - lag_days + 1, 0, day_count)
    start = np.clip(end - window_days, 0, day_count)
    return cumulative[end] - cumulative[start]


def location_region_codes(market):
    """Feature 9: each location's hub area per day, as a code into REGIONS (NaN = unknown).

    For operating day D, the daily mean DA price of each location is correlated with that of
    each hub area over days D−365 … D−1 (DA is visible through D−1); the area with the
    highest correlation wins, given at least 90 days with both prices. A hub of REGIONS is
    its own area on every day.
    """
    known_hours = (~np.isnan(market.day_ahead)).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        daily = np.where(known_hours > 0, np.nansum(market.day_ahead, axis=1) / known_hours, np.nan)
    region_columns = [market.hubs.index(hub) if hub in market.hubs else None for hub in REGIONS]
    day_count, location_count = daily.shape
    best_correlation = np.full((day_count, location_count), -np.inf)
    codes = np.full((day_count, location_count), np.nan)
    for region_code, column in enumerate(region_columns):
        if column is None:
            continue
        region = daily[:, column]
        for chunk_start in range(0, location_count, LOCATION_CHUNK):
            chunk = daily[:, chunk_start : chunk_start + LOCATION_CHUNK]
            mask = (~np.isnan(chunk) & ~np.isnan(region)[:, None]).astype(float)
            location_values = np.where(mask > 0, chunk, 0.0)
            region_values = np.where(mask > 0, region[:, None], 0.0)
            count = rolling_sums(mask, REGION_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS)
            location_sum = rolling_sums(location_values, REGION_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS)
            region_sum = rolling_sums(region_values, REGION_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS)
            location_square_sum = rolling_sums(
                location_values**2, REGION_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS
            )
            region_square_sum = rolling_sums(
                region_values**2, REGION_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS
            )
            cross_sum = rolling_sums(
                location_values * region_values, REGION_WINDOW_DAYS, DAY_AHEAD_LAG_DAYS
            )
            with np.errstate(invalid="ignore", divide="ignore"):
                covariance = cross_sum - location_sum * region_sum / count
                location_variance = location_square_sum - location_sum**2 / count
                region_variance = region_square_sum - region_sum**2 / count
                correlation = covariance / np.sqrt(location_variance * region_variance)
            correlation = np.where(count >= REGION_MINIMUM_DAYS, correlation, np.nan)
            # A location that is itself an area's hub belongs to that area by definition
            # (round 28: each hub is its own area), from its first day.
            location_names = market.hubs[chunk_start : chunk_start + LOCATION_CHUNK]
            is_self = np.array([name == REGIONS[region_code] for name in location_names])
            correlation = np.where(is_self[None, :], 2.0, correlation)
            target = slice(chunk_start, chunk_start + chunk.shape[1])
            is_better = np.nan_to_num(correlation, nan=-np.inf) > best_correlation[:, target]
            best_correlation[:, target] = np.where(
                is_better, correlation, best_correlation[:, target]
            )
            codes[:, target] = np.where(is_better, region_code, codes[:, target])
    return codes


def regional_inputs(days, inputs):
    """Regional features 10–18 as {name: array (days, regions)} from FeatureInputs."""
    day_count = len(days)
    shape = (day_count, len(REGIONS))
    arrays = {
        name: np.full(shape, np.nan)
        for name in (
            "temp_max_fcst",
            "temp_min_fcst",
            "temp_fcst_change",
            "hdd_fcst",
            "cdd_fcst",
            "wind_fcst",
            "cloud_fcst",
            "wind_cap_region",
            "solar_cap_region",
        )
    }
    one_day = datetime.timedelta(days=1)
    for day_index, day in enumerate(days):
        decision_day = day - one_day
        month = (decision_day.year, decision_day.month)
        for region_index, hub in enumerate(REGIONS):
            today = inputs.forecasts.get((decision_day, hub, day))
            if today is not None:
                high, low, wind, cloud = today
                if high is not None:
                    arrays["temp_max_fcst"][day_index, region_index] = high
                if low is not None:
                    arrays["temp_min_fcst"][day_index, region_index] = low
                if high is not None and low is not None:
                    mean = (high + low) / 2
                    arrays["hdd_fcst"][day_index, region_index] = max(
                        0.0, DEGREE_DAY_BASE_DEGF - mean
                    )
                    arrays["cdd_fcst"][day_index, region_index] = max(
                        0.0, mean - DEGREE_DAY_BASE_DEGF
                    )
                if wind is not None:
                    arrays["wind_fcst"][day_index, region_index] = wind
                if cloud is not None:
                    arrays["cloud_fcst"][day_index, region_index] = cloud
                yesterday = inputs.forecasts.get((decision_day - one_day, hub, day))
                if high is not None and yesterday is not None and yesterday[0] is not None:
                    arrays["temp_fcst_change"][day_index, region_index] = high - yesterday[0]
            capacity = inputs.capacity.get((*month, hub))
            if capacity is not None:
                arrays["wind_cap_region"][day_index, region_index] = capacity[0]
                arrays["solar_cap_region"][day_index, region_index] = capacity[1]
    return arrays


def newest_visible_index(observation_days, operating_days, lag_days, is_business):
    """For each operating day D, the index of the newest observation usable at the decision.

    An observation of day t is usable from the start of t + lag (business days when
    is_business), so at 10:30 on D−1 when that day is on or before D−1. −1 = none.
    """
    if is_business:
        available = [add_business_days(day, lag_days) for day in observation_days]
    else:
        available = [day + datetime.timedelta(days=lag_days) for day in observation_days]
    available_ordinals = np.array([day.toordinal() for day in available])
    decision_ordinals = np.array([day.toordinal() - 1 for day in operating_days])
    return np.searchsorted(available_ordinals, decision_ordinals, side="right") - 1


def global_features(days, inputs):
    """Global features 19–22 as {name: array (days,)}."""
    count = len(days)
    arrays = {
        name: np.full(count, np.nan) for name in ("gas_price", "gas_chg_5d", "gas_vol_20d", "epu")
    }
    if inputs.gas is not None and inputs.gas.days:
        values = np.array(inputs.gas.values, dtype=float)
        index = newest_visible_index(inputs.gas.days, days, GAS_LAG_BUSINESS_DAYS, True)
        has_value = index >= 0
        arrays["gas_price"][has_value] = values[index[has_value]]
        has_change = index >= GAS_CHANGE_TRADING_DAYS
        arrays["gas_chg_5d"][has_change] = (
            values[index[has_change]] - values[index[has_change] - GAS_CHANGE_TRADING_DAYS]
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            log_changes = np.diff(np.log(np.where(values > 0, values, np.nan)))
        volatility_by_observation = np.full(len(values), np.nan)
        for observation in range(GAS_VOLATILITY_TRADING_DAYS, len(values)):
            window = log_changes[observation - GAS_VOLATILITY_TRADING_DAYS : observation]
            if not np.isnan(window).any():
                volatility_by_observation[observation] = float(np.std(window, ddof=1))
        arrays["gas_vol_20d"][has_value] = volatility_by_observation[index[has_value]]
    if inputs.epu is not None and inputs.epu.days:
        values = np.array(inputs.epu.values, dtype=float)
        index = newest_visible_index(inputs.epu.days, days, EPU_LAG_DAYS, False)
        has_value = index >= 0
        arrays["epu"][has_value] = values[index[has_value]]
    return arrays


def build_feature_store(market, inputs):
    """Compute every catalogue feature for a market (see the module docstring).

    Args:
        market: a `HubMarket` (hubs at Stage A, all locations at Stage C).
        inputs: `FeatureInputs` (forecasts, capacity, gas, EPU).

    Returns:
        A FeatureStore.
    """
    arrays = price_features(market)
    type_codes = np.array([LOCATION_TYPES.index(kind) for kind in market.types()], dtype=float)
    arrays["loc_type"] = type_codes[None, None, :]
    region_codes = location_region_codes(market)
    arrays["loc_region"] = region_codes[:, None, :]
    regional = regional_inputs(market.days, inputs)
    # Broadcast area values to each location through its area code (missing area → missing).
    safe_codes = np.nan_to_num(region_codes, nan=0).astype(int)
    for name, values in regional.items():
        per_location = np.take_along_axis(values, safe_codes, axis=1)
        arrays[name] = np.where(np.isnan(region_codes), np.nan, per_location)[:, None, :]
    for name, values in global_features(market.days, inputs).items():
        arrays[name] = values[:, None, None]
    arrays["hour"] = np.arange(1, HOURS_PER_DAY + 1, dtype=float)[None, :, None]
    arrays["weekday"] = np.array([day.weekday() for day in market.days], dtype=float)[:, None, None]
    arrays["holiday"] = np.array([is_nerc_holiday(day) for day in market.days], dtype=float)[
        :, None, None
    ]
    assert sorted(arrays) == sorted(FEATURE_NAMES), set(FEATURE_NAMES) ^ set(arrays)
    return FeatureStore(
        days=tuple(market.days),
        locations=tuple(market.hubs),
        arrays=arrays,
        source=market.source,
        inputs_description=inputs.description,
    )


def feature_summary(store, last_day=EVOLUTION_LAST_DAY):
    """Per numeric feature: populated days and quantiles over the evolution period.

    Returns:
        {name: {"first_day", "last_day", "missing_fraction", "p5", "p25", "p50", "p75", "p95"}}
        computed over days ≤ last_day ("populated" status of `docs/design_spec.md` §8).
    """
    day_count = sum(1 for day in store.days if day <= last_day)
    summary = {}
    for name in FEATURE_NAMES:
        values = store.window(name, 0, day_count)
        known_by_day = (~np.isnan(values)).any(axis=(1, 2))
        known_days = [store.days[index] for index in np.flatnonzero(known_by_day)]
        finite = values[~np.isnan(values)]
        entry = {
            "first_day": known_days[0] if known_days else None,
            "last_day": known_days[-1] if known_days else None,
            "missing_fraction": float(np.isnan(values).mean()) if values.size else 1.0,
        }
        if FEATURE_BY_NAME[name].kind == "number" and finite.size:
            sample = finite if finite.size <= 2_000_000 else finite[:: finite.size // 2_000_000 + 1]
            for label, quantile in (("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95)):
                entry[label] = float(np.percentile(sample, quantile))
        summary[name] = entry
    return summary
