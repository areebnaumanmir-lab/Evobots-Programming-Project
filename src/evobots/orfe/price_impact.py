"""O9: do virtual bids move prices? A test of the price-taker assumption (§20.12).

**Data:** MISO's cleared-bids reports (2023 on) with the hub attribution of
`capital_sizing.md` §2. Only observable hub-hours count (25–48 % of them): a bid is attributed to
a hub only when the hub uniquely has that ex-ante price and the Region field is blank.

**Estimate:** for each observable hub-hour, the DA − RT spread against the net cleared virtual
MW (DEC − INC), with hub-by-hour fixed effects (demeaning within each hub and hour):
    spread = a_{hub,hour} + β · net_MW + ε
Virtual demand raises DA, so a positive β is the expected sign: more net DEC, higher DA
relative to RT. β is in $/MWh per MW. Standard errors are clustered by day, and a bootstrap
over days gives the interval.

**Caveats (stated in every use):**
- **Endogeneity:** traders bid more DEC when they expect RT above DA, so β mixes impact with
  anticipation. Without an instrument this is an association, not a causal effect.
- **Selection:** only observable hub-hours are used, and they may differ from the rest.

**Use:** the spread change our 5 MW cap would cause under β, and an optional linear impact in
the simulator for a sensitivity run (`AccountRules.price_impact_usd_per_mwh_per_mw`): a
cleared bid of q MW moves its own DA price by β·q against itself, costing β·q² per hub-hour.
Price-taking stays the default.

Example:
    >>> import numpy as np
    >>> generator = np.random.Generator(np.random.PCG64(1))
    >>> net = generator.normal(0, 100, 2000); groups = generator.integers(0, 5, 2000)
    >>> days = np.repeat(np.arange(400), 5)
    >>> spread = 0.02 * net + groups + generator.normal(0, 2, 2000)
    >>> estimate = impact_regression(spread, net, groups, days)
    >>> abs(estimate["coefficient"] - 0.02) < 3 * estimate["clustered_standard_error"]
    True
"""

import datetime
from pathlib import Path

import numpy as np

from evobots.data.sources.miso_cleared_bids import read_day_volumes

BOOTSTRAP_DRAWS = 500


def demeaned(values, groups):
    """Values minus their group means (the fixed effects)."""
    values = np.asarray(values, dtype=float)
    groups = np.asarray(groups)
    result = values.copy()
    for group in np.unique(groups):
        member = groups == group
        result[member] -= values[member].mean()
    return result


def impact_regression(spread, net_mw, groups, days, seed=0):
    """β, its day-clustered standard error, and a day-bootstrap 90 % interval.

    Args:
        spread: DA − RT of each observable hub-hour ($/MWh).
        net_mw: net cleared virtual MW (DEC − INC).
        groups: fixed-effect group of each observation (hub × hour).
        days: day of each observation (the clusters).
        seed: bootstrap seed.
    """
    outcome = demeaned(spread, groups)
    regressor = demeaned(net_mw, groups)
    denominator = float(regressor @ regressor)
    coefficient = float(regressor @ outcome) / denominator
    residuals = outcome - coefficient * regressor
    days = np.asarray(days)
    cluster_sum = 0.0
    for day in np.unique(days):
        member = days == day
        cluster_sum += float(regressor[member] @ residuals[member]) ** 2
    clustered = (cluster_sum**0.5) / denominator
    generator = np.random.Generator(np.random.PCG64(seed))
    unique_days = np.unique(days)
    index_by_day = {day: np.flatnonzero(days == day) for day in unique_days}
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        chosen = np.concatenate(
            [index_by_day[day] for day in generator.choice(unique_days, len(unique_days))]
        )
        regressor_sample, outcome_sample = regressor[chosen], outcome[chosen]
        draws.append(
            float(regressor_sample @ outcome_sample) / float(regressor_sample @ regressor_sample)
        )
    return {
        "coefficient": coefficient,
        "clustered_standard_error": float(clustered),
        "bootstrap_interval_90": (float(np.quantile(draws, 0.05)), float(np.quantile(draws, 0.95))),
        "observations": int(len(outcome)),
        "days": int(len(unique_days)),
    }


def observations_from_raw(raw_directory, hub_prices, days):
    """(spread, net MW, group, day) arrays for the observable hub-hours of some days.

    Args:
        raw_directory: data/raw/miso with `{day}_bids_cb.zip` and `{day}_da_exante_lmp.csv`.
        hub_prices: {(day, hour_ending, hub): (DA, RT)} from the hub table.
        days: operating days to read.
    """
    spreads, nets, groups, day_numbers = [], [], [], []
    raw_directory = Path(raw_directory)
    for day in days:
        bids = raw_directory / f"{day:%Y%m%d}_bids_cb.zip"
        exante = raw_directory / f"{day:%Y%m%d}_da_exante_lmp.csv"
        if not bids.exists() or not exante.exists():
            continue
        for volume in read_day_volumes(bids, exante, day):
            prices = hub_prices.get((day, volume.hour_ending, volume.hub))
            if prices is None or None in prices:
                continue
            spreads.append(prices[0] - prices[1])
            nets.append(volume.dec_mw - volume.inc_mw)
            groups.append(f"{volume.hub}:{volume.hour_ending}")
            day_numbers.append(day.toordinal())
    return np.array(spreads), np.array(nets), np.array(groups), np.array(day_numbers)


def implied_spread_change(coefficient, megawatts=5.0):
    """Spread change our own bid of `megawatts` would cause under the estimate ($/MWh)."""
    return coefficient * megawatts


def cleared_bid_days(
    raw_directory, first=datetime.date(2023, 1, 1), last=datetime.date(2025, 9, 21)
):
    """Days with both cleared-bids and ex-ante files on disk (evolution period only)."""
    raw_directory = Path(raw_directory)
    days = []
    day = first
    while day <= last:
        if (raw_directory / f"{day:%Y%m%d}_bids_cb.zip").exists() and (
            raw_directory / f"{day:%Y%m%d}_da_exante_lmp.csv"
        ).exists():
            days.append(day)
        day += datetime.timedelta(days=1)
    return days
