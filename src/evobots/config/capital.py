"""Capital settings for Stage A (the MISO trading hubs): defaults, bounds, validation, formulas.

Every number here is explained in docs/capital_sizing.md and reproduced from the downloaded
archive by tools/check_against_claude_science.py (round 21).

Rebuilt in round 21 from capital_sizing.md (the original Claude Science file never arrived),
with two deliberate changes, both decided earlier:
  * names follow the naming standard (docs/design_spec.md §14.1): `daily_risk_budget_fraction`,
    `credit_share_fraction`, `liquidity_share_fraction`;
  * capital floors are optional and off by default; the default death is "out of money"
    (round 19, docs/design_spec.md §10.1). The round-16 relative floor (2/3) is a preset.
The MPD is not a setting any more: it comes from market data (docs/design_spec.md §13.1), so the
collateral functions take it as an argument.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# The eight Stage A trading hubs that exist today (docs/data_coverage.md).
STAGE_A_HUBS = (
    "ARKANSAS.HUB",
    "ILLINOIS.HUB",
    "INDIANA.HUB",
    "LOUISIANA.HUB",
    "MICHIGAN.HUB",
    "MINN.HUB",
    "MS.HUB",
    "TEXAS.HUB",
)

# Median cleared virtual MW per observable hub-hour, from MISO's cleared-bids report on the
# 15th of each month 2023-01 → 2025-09 (docs/data/hub_volume_stats.csv; capital_sizing.md §2).
HUB_MEDIAN_CLEARED_VIRTUAL_MW = {
    "ARKANSAS.HUB": 161.2,
    "ILLINOIS.HUB": 490.1,
    "INDIANA.HUB": 707.6,
    "LOUISIANA.HUB": 175.3,
    "MICHIGAN.HUB": 366.7,
    "MINN.HUB": 423.3,
    "MS.HUB": 79.0,
    "TEXAS.HUB": 160.25,
}

HOURS_PER_DAY = 24
# MISO's smallest virtual bid and bid step (docs/market_rules.md §1).
MINIMUM_BID_MW = 0.1
# Attachment L: the Minimum MPD Value, $/MWh (docs/market_rules.md §4.1).
MINIMUM_MPD_USD_PER_MWH = 12.0
# Attachment L: the Virtual Transactions Estimated Exposure Window (VMEW), days.
VIRTUAL_EXPOSURE_WINDOW_DAYS = 2
# An absolute floor must leave at least this share of starting capital to lose (round 16).
MINIMUM_HEADROOM_FRACTION = 0.10

# Worst 20-day loss of the benchmark positions as a share of equity, with point-in-time sizing,
# 2019-01 → 2025-09, by starting capital (capital_sizing.md §6b; headroom_trailing.csv).
# Used only for warnings, never in simulation. Linear interpolation between points.
WORST_20_DAY_LOSS_FRACTION_BY_CAPITAL_USD = {
    250_000: 0.504,
    500_000: 0.504,
    1_000_000: 0.360,
    1_050_000: 0.3452,
    1_100_000: 0.3319,
    1_200_000: 0.3078,
    1_300_000: 0.2852,
    1_400_000: 0.2641,
    1_500_000: 0.2457,
    2_000_000: 0.1842,
    3_000_000: 0.1234,
    5_000_000: 0.082,
}


def round_to_bid_step_mw(power_mw):
    """Round MW to MISO's 0.1 MW bid step, halves upwards (3.95 → 4.0).

    Args:
        power_mw: a size in MW.

    Returns:
        The size rounded to the nearest 0.1 MW, as a float.

    Example:
        >>> round_to_bid_step_mw(0.05 * 79.0)
        4.0
    """
    return float(Decimal(str(power_mw)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def worst_20_day_loss_fraction(starting_capital_usd):
    """Worst 20-day benchmark loss as a share of equity at this capital (warnings only).

    Args:
        starting_capital_usd: starting capital, USD.

    Returns:
        A fraction, linearly interpolated in WORST_20_DAY_LOSS_FRACTION_BY_CAPITAL_USD and
        held flat beyond its ends.

    Example:
        >>> worst_20_day_loss_fraction(1_500_000)
        0.2457
    """
    points = sorted(WORST_20_DAY_LOSS_FRACTION_BY_CAPITAL_USD.items())
    if starting_capital_usd <= points[0][0]:
        return points[0][1]
    for (low_capital, low_loss), (high_capital, high_loss) in zip(points, points[1:]):
        if starting_capital_usd <= high_capital:
            weight = (starting_capital_usd - low_capital) / (high_capital - low_capital)
            return low_loss + weight * (high_loss - low_loss)
    return points[-1][1]


@dataclass(frozen=True)
class CapitalSettings:
    """The money a trader starts with and the risk rules around it (docs/design_spec.md §13).

    Attributes:
        starting_capital_usd: starting equity, USD. Your choice; Stage A range $250k–$5M.
        daily_risk_budget_fraction: the share of equity a 1-in-100 day may cost (sizing rule).
        credit_share_fraction: share of capital pledged to MISO as collateral; it sets the
            daily Virtual MWh Limit (decisions log, round 14).
        max_mw_per_hub_hour: the absolute cap per hub-hour, MW.
        liquidity_share_fraction: the cap as a share of the hub's median cleared virtual MW.
        ruin_floor_fraction: optional relative floor (career layer L1), e.g. 2/3. None = off.
        ruin_floor_usd: optional absolute floor (career layer L1), USD. None = off.
        hub_median_cleared_virtual_mw: market data behind the liquidity cap, MW.
    """

    starting_capital_usd: float = 1_500_000.0
    daily_risk_budget_fraction: float = 0.02
    credit_share_fraction: float = 0.25
    max_mw_per_hub_hour: float = 5.0
    liquidity_share_fraction: float = 0.05
    ruin_floor_fraction: float | None = None
    ruin_floor_usd: float | None = None
    hub_median_cleared_virtual_mw: dict = field(
        default_factory=lambda: dict(HUB_MEDIAN_CLEARED_VIRTUAL_MW)
    )

    # (low, high) bounds per setting; capital_sizing.md §6 and docs/design_spec.md §13.
    BOUNDS = {
        "starting_capital_usd": (250_000.0, 5_000_000.0),
        "daily_risk_budget_fraction": (0.005, 0.05),
        "credit_share_fraction": (0.05, 0.80),
        "max_mw_per_hub_hour": (MINIMUM_BID_MW, 50.0),
        "liquidity_share_fraction": (0.0, 0.25),
        "ruin_floor_fraction": (0.0, 0.9),
    }

    def __post_init__(self):
        """Reject values outside their bounds and floors that leave too little headroom."""
        for name, (low, high) in self.BOUNDS.items():
            value = getattr(self, name)
            if value is None:
                continue
            if not low <= value <= high:
                raise ValueError(f"{name} = {value} is outside [{low}, {high}]")
        if self.ruin_floor_fraction is not None and self.ruin_floor_usd is not None:
            raise ValueError("set ruin_floor_fraction or ruin_floor_usd, not both")
        if self.ruin_floor_usd is not None:
            headroom = 1.0 - self.ruin_floor_usd / self.starting_capital_usd
            if headroom < MINIMUM_HEADROOM_FRACTION:
                raise ValueError(
                    f"ruin_floor_usd = {self.ruin_floor_usd:,.0f} leaves {headroom:.1%} of "
                    f"starting capital to lose; at least {MINIMUM_HEADROOM_FRACTION:.0%} "
                    "is required"
                )

    def hub_caps_mw(self):
        """Per-hub cap: min(max MW, liquidity share × median cleared MW), on the 0.1 MW step.

        Returns:
            {hub: cap in MW}. At the defaults: 5.0 MW at seven hubs and 4.0 MW at MS.HUB.

        Maths: docs/maths.md §1.2.
        """
        return {
            hub: round_to_bid_step_mw(
                min(self.max_mw_per_hub_hour, self.liquidity_share_fraction * median_mw)
            )
            for hub, median_mw in self.hub_median_cleared_virtual_mw.items()
        }

    def full_size_mwh_per_day(self, hubs=None):
        """MWh per day when bidding at every hub's cap in every hour (936 at the defaults).

        Args:
            hubs: the hubs that exist on the day; None = all hubs in the settings.

        Maths: docs/maths.md §1.2.
        """
        caps = self.hub_caps_mw()
        selected_hubs = caps if hubs is None else [hub for hub in hubs if hub in caps]
        return round(sum(caps[hub] for hub in selected_hubs) * HOURS_PER_DAY, 6)

    def virtual_mwh_limit(self, mpd_usd_per_mwh=MINIMUM_MPD_USD_PER_MWH):
        """Daily Virtual MWh Limit the pledged collateral supports, MWh.

        limit = credit share × capital / (MPD × VMEW), with MPD at least $12/MWh.

        Maths: docs/maths.md §1.3.
        """
        mpd = max(mpd_usd_per_mwh, MINIMUM_MPD_USD_PER_MWH)
        return (
            self.credit_share_fraction
            * self.starting_capital_usd
            / (mpd * VIRTUAL_EXPOSURE_WINDOW_DAYS)
        )

    def effective_ruin_floor_usd(self):
        """The equity at which career layer L1 ends a career, USD, or None when L1 is off."""
        if self.ruin_floor_usd is not None:
            return self.ruin_floor_usd
        if self.ruin_floor_fraction is not None:
            return self.ruin_floor_fraction * self.starting_capital_usd
        return None

    def headroom_fraction(self):
        """Share of starting capital that can be lost before L1 ends the career (1.0 if off)."""
        floor_usd = self.effective_ruin_floor_usd()
        if floor_usd is None:
            return 1.0
        return 1.0 - floor_usd / self.starting_capital_usd

    def full_size_capital_usd(self, p99_daily_loss_usd):
        """Capital at which bids reach full size: p99 loss ÷ daily risk budget, USD.

        Maths: docs/maths.md §1.1.
        """
        return p99_daily_loss_usd / self.daily_risk_budget_fraction

    def warnings(self):
        """Plain-English warnings about this combination of settings (never errors)."""
        messages = []
        worst_loss = worst_20_day_loss_fraction(self.starting_capital_usd)
        headroom = self.headroom_fraction()
        if self.effective_ruin_floor_usd() is not None and headroom <= worst_loss:
            messages.append(
                f"The floor leaves {headroom:.1%} to lose, but the worst 20 days of 2019–2025 cost "
                f"{worst_loss:.1%} at this capital: a storm like Uri can end the career."
            )
        if worst_loss < MINIMUM_HEADROOM_FRACTION:
            messages.append(
                f"The worst 20-day loss is only {worst_loss:.1%} of capital here: drawdown rules "
                "will rarely bind, and much of the capital sits idle at Stage A."
            )
        return messages
