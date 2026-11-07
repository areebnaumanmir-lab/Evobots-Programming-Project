"""MISO credit for virtual trading: collateral, the Virtual MWh Limit and the MPD.

Attachment L §IV.A (`docs/market_rules.md` §4.1): virtual potential exposure includes
DMWhL × MPD × VMEW, with VMEW = 2 days and MPD = the greater of the 50th-percentile DA−RT
differential over the prior twelve months (reset each May 1) and the $12 floor.

Decided in round 28: until MISO's published MPDs are supplied, every year uses the $12 floor,
labelled "estimate" (`tools/compute_mpd_history.py` showed our own reconstruction is not
MISO's method). At Stage A it changes no result: full-size collateral is $22,464.

Example:
    >>> collateral_usd(936)
    22464.0
    >>> round(virtual_mwh_limit(1_500_000 * 0.25))
    15625
    >>> mpd_for_day(None)
    (12.0, 'estimate')
"""

from evobots.config.capital import MINIMUM_MPD_USD_PER_MWH, VIRTUAL_EXPOSURE_WINDOW_DAYS


def mpd_for_day(day):
    """(MPD in $/MWh, label) used for an operating day: the $12 floor, "estimate" (round 28)."""
    del day  # every year uses the floor until MISO's published values are supplied
    return MINIMUM_MPD_USD_PER_MWH, "estimate"


def collateral_usd(daily_virtual_mwh, mpd_usd_per_mwh=MINIMUM_MPD_USD_PER_MWH):
    """Collateral for a daily Virtual MWh Limit: MWh × MPD × 2 days, USD."""
    return float(daily_virtual_mwh) * mpd_usd_per_mwh * VIRTUAL_EXPOSURE_WINDOW_DAYS


def virtual_mwh_limit(pledged_credit_usd, mpd_usd_per_mwh=MINIMUM_MPD_USD_PER_MWH):
    """The daily Virtual MWh Limit a pledged credit amount supports, MWh."""
    return float(pledged_credit_usd) / (mpd_usd_per_mwh * VIRTUAL_EXPOSURE_WINDOW_DAYS)
