"""Hand-written starting traders, each with its reason (`docs/design_spec.md` §9.5).

Founders are small (a few nodes) so the parsimony penalty treats them fairly. Each is tagged
`founder:<name>` in its birth record, so the report can show whether winning lineages descend
from founders or from random trees.

- always_inc: INC at every location-hour; mean DA − RT is slightly positive at every hub
  (capital_sizing.md §1)
- always_dec: DEC at every location-hour; the mirror; profits in RT spikes
- persistence: follow the sign of the newest visible week's spread; baseline (§12.1)
- premium_follow: side = sign of the 28-day mean spread (INC when DA ran above RT); bets the recent
  premium continues
- premium_fade: the opposite; bets it reverses
- heat_dec: DEC on afternoons with cooling degree-days; hypothesis: hot days surprise RT upward
  [unverified]
- wind_inc: INC when forecast wind × wind capacity is high; hypothesis: windy days push RT down
  [unverified]

Signs: score > 0 means "RT will be above DA" (DEC). The spread is DA − RT, so following a
positive spread means a negative score.

Example:
    >>> sorted(FOUNDERS)[:3]
    ['always_dec', 'always_inc', 'heat_dec']
    >>> FOUNDERS["always_inc"].node_count()
    3
"""

from evobots.bots.grammar import Binary, Compare, Constant, Feature, Flag, Logic, Negate, Truth
from evobots.bots.trader import Genome
from evobots.units import DEGF_DAY, HOUR, MPH, MW, USD_PER_MWH

ALWAYS = Truth(True)


def score_constant(value):
    """A constant score in $/MWh."""
    return Constant(value, USD_PER_MWH)


FOUNDERS = {
    "always_inc": Genome(ALWAYS, ALWAYS, score_constant(-1.0), size_score_scale_usd_per_mwh=0.5),
    "always_dec": Genome(ALWAYS, ALWAYS, score_constant(1.0), size_score_scale_usd_per_mwh=0.5),
    "persistence": Genome(
        ALWAYS,
        ALWAYS,
        Binary("*", Constant(-1.0), Feature("spread_mean_7d")),
        dec_threshold_usd_per_mwh=0.5,
        inc_threshold_usd_per_mwh=0.5,
        size_score_scale_usd_per_mwh=5.0,
    ),
    "premium_follow": Genome(
        ALWAYS,
        ALWAYS,
        Binary("*", Constant(-1.0), Feature("spread_mean_28d")),
        size_score_scale_usd_per_mwh=5.0,
    ),
    "premium_fade": Genome(
        ALWAYS, ALWAYS, Feature("spread_mean_28d"), size_score_scale_usd_per_mwh=5.0
    ),
    "heat_dec": Genome(
        ALWAYS,
        Logic(
            "and",
            Compare(">", Feature("hour"), Constant(13.0, HOUR)),
            Logic(
                "and", Compare("<", Feature("hour"), Constant(20.0, HOUR)), Negate(Flag("holiday"))
            ),
        ),
        Binary("*", Constant(0.4, USD_PER_MWH / DEGF_DAY), Feature("cdd_fcst")),
        dec_threshold_usd_per_mwh=2.0,
        size_score_scale_usd_per_mwh=10.0,
    ),
    "wind_inc": Genome(
        ALWAYS,
        ALWAYS,
        Binary(
            "*",
            Constant(-2e-5, USD_PER_MWH / (MPH * MW)),
            Binary("*", Feature("wind_fcst"), Feature("wind_cap_region")),
        ),
        inc_threshold_usd_per_mwh=2.0,
        size_score_scale_usd_per_mwh=10.0,
    ),
}
