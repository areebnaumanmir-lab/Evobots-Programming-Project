# Round 33: M2, the feature layer

Date: 2026-11-07. Part of "finish all of this" (round 32).

## What was built
- `src/evobots/units.py`: unit algebra for features and formulas (products and quotients of base units; `+ − > <` need equal units).
- `src/evobots/features/catalogue.py`: the 25 features of `docs/design_spec.md` §8, each with code name, display name, unit, level, kind, meaning and sources; categories for `loc_type`, `loc_region` and `weekday`.
- `src/evobots/features/calendar.py`: the six NERC holidays with the Sunday-and-Monday rule (D2).
- `src/evobots/features/inputs.py`: forecasts, capacity, gas and EPU in one structure, read from the store or generated for tests; the capacity table by hub area (`docs/data/hub_capacity_monthly.csv`, EIA-860M, MISO South from 2013-12).
- `src/evobots/features/store.py`: every feature for every day, hour and location, point-in-time, stored at its natural granularity and broadcast on reading. 20.5 years × 8 hubs build in about 1 s from the store (obs.: 0.33 s on synthetic 10 years, `benchmarks/results.csv`).
- `docs/features.md`, `docs/data/feature_distributions_by_year.csv`, `tools/build_feature_docs.py`, `tools/build_capacity_table.py`.
- `HubMarket` now carries DA congestion (MCC) and location types (cache version 2).

## Done-when check (§16, M2)
- **All 25 features computed and unit-tagged:** yes (`tests/test_features.py`).
- **Look-ahead clean:** the corruption test replaces everything published after a decision and finds no change at four decision days; a control leak is detected.
- **No unexplained breaks 2005–2025:** ten yearly steps of more than one IQR, all in gas and EPU, each explained in `docs/features.md` §4; none in prices or weather.
- **Data page:** built with the app pages (M1.5, later in this build).

## Decisions taken under delegation
| Topic | Decision | Reason |
|---|---|---|
| `congestion_share_28d` | ratio of 28-day means of DA MCC and DA LMP (days D−28 … D−1), missing when the mean price is within $1/MWh of zero | a mean of hourly ratios explodes near zero prices |
| A hub's area | a hub is its own area on every day | round 28 defines the areas by hub; the 90-day rule applies to other locations |
| Cloud fraction | midpoints of the PFM codes' eighths of sky [verify the code table] | the forecast gives categories, the feature is a fraction |
| `gas_vol_20d` unit | fraction per day instead of %/day | §14.1: code stores fractions, never percent |

## Measured vs assumed
- **Measured:** feature values, coverage and yearly distributions from the downloaded data; MISO wind 1.3 GW in 2005-04 and 32.7 GW in 2025-09 across the eight areas.
- **Assumed:** cloud-code midpoints, the 65 °F degree-day base, the $1/MWh floor for the congestion share.
