"""What a set of capital settings implies: scale, costs, losses, floor and warnings.

One function, `capital_summary`, computes every number the `capital` command, the capital
explorer and (from M1.5) the Capital page show, so none of them carries its own formulas
(CLAUDE.md §14.5). The loss figures it takes as arguments are calibration numbers; callers
pass them in, and this module holds no calibration constant (CLAUDE.md §13, §18).
"""

from evobots.calibration import fixed_cost_usd_per_cleared_mwh
from evobots.config.capital import (
    MINIMUM_MPD_USD_PER_MWH,
    VIRTUAL_EXPOSURE_WINDOW_DAYS,
    worst_20_day_loss_fraction,
)
from evobots.sizing import position_scale

# Capital at or above this multiple of the full-size point gets the "well above full size"
# warning. Assumed (round 23): capital_sizing.md §10 expects it at $5M (3.6×) but not at
# $1.5M (1.08×); the original explorer's threshold did not survive.
WELL_ABOVE_FULL_SIZE_MULTIPLE = 2.0


def capital_summary(
    settings,
    p99_daily_loss_usd,
    worst_20_day_full_size_loss_usd,
    cleared_share_fraction=0.72,
    fixed_cost_usd_per_year=50_000.0,
):
    """Every number the capital views show for one set of settings.

    Args:
        settings: a CapitalSettings.
        p99_daily_loss_usd: the 1-in-100-day full-size loss used for sizing, USD.
        worst_20_day_full_size_loss_usd: the worst 20-day loss at full size, USD.
        cleared_share_fraction: share of hub-hours with a cleared position (0.72 = the
            measured hub clearing rate of other traders, capital_sizing.md §2b).
        fixed_cost_usd_per_year: the company's fixed yearly costs, USD (an assumption, §10.1).

    Returns:
        A dict with:
        position_scale_fraction (share of the cap used on day one);
        full_size_mwh_per_day; full_size_capital_usd;
        fixed_cost_usd_per_cleared_mwh;
        worst_20_day_loss_full_sample_fraction (sizing at the given p99, constant scale);
        worst_20_day_loss_point_in_time_fraction (from headroom_trailing.csv);
        ruin_floor_usd (None when off) and headroom_fraction (None when off);
        collateral_at_full_size_usd; virtual_mwh_limit_mwh_per_day;
        warnings (a list of plain-English strings).

    Maths: docs/maths.md §1.1–1.3, §1.5, §1.7.

    Decision: capital_sizing.md §10 lists the values for $1.5M, $1.05M and $5M.

    Example:
        >>> from evobots.config.capital import CapitalSettings
        >>> summary = capital_summary(CapitalSettings(), 27_897, 484_372)
        >>> round(summary["fixed_cost_usd_per_cleared_mwh"], 3)
        0.203
        >>> round(summary["worst_20_day_loss_full_sample_fraction"], 3)
        0.323
    """
    capital_usd = settings.starting_capital_usd
    scale = position_scale(capital_usd, p99_daily_loss_usd, settings.daily_risk_budget_fraction)
    full_size_mwh = settings.full_size_mwh_per_day()
    full_size_capital_usd = settings.full_size_capital_usd(p99_daily_loss_usd)
    warnings = list(settings.warnings())
    if capital_usd >= WELL_ABOVE_FULL_SIZE_MULTIPLE * full_size_capital_usd:
        warnings.append(
            f"Capital is {capital_usd / full_size_capital_usd:.1f}× the full-size point "
            f"(${full_size_capital_usd:,.0f}): the caps bind, and the extra capital earns nothing "
            "at Stage A."
        )
    floor_usd = settings.effective_ruin_floor_usd()
    return {
        "position_scale_fraction": scale,
        "full_size_mwh_per_day": full_size_mwh,
        "full_size_capital_usd": full_size_capital_usd,
        "fixed_cost_usd_per_cleared_mwh": fixed_cost_usd_per_cleared_mwh(
            fixed_cost_usd_per_year, scale, full_size_mwh, cleared_share_fraction
        ),
        "worst_20_day_loss_full_sample_fraction": (
            worst_20_day_full_size_loss_usd * scale / capital_usd
        ),
        "worst_20_day_loss_point_in_time_fraction": worst_20_day_loss_fraction(capital_usd),
        "ruin_floor_usd": floor_usd,
        "headroom_fraction": None if floor_usd is None else settings.headroom_fraction(),
        "collateral_at_full_size_usd": (
            full_size_mwh * MINIMUM_MPD_USD_PER_MWH * VIRTUAL_EXPOSURE_WINDOW_DAYS
        ),
        "virtual_mwh_limit_mwh_per_day": settings.virtual_mwh_limit(),
        "warnings": warnings,
    }
