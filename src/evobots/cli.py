"""Command line: `python -m evobots.cli capital [config] [--starting-capital …]`."""

import argparse

from evobots.config import load_capital
from evobots.config.capital import MINIMUM_MPD_USD_PER_MWH, VIRTUAL_EXPOSURE_WINDOW_DAYS

# Full-sample 1-in-100-day full-size loss, 2019-01-01 → 2025-09-21, worse direction (always-INC),
# USD (capital_sizing.md §4; reproduced in round 21). CALIBRATION ONLY: it contains every storm
# of the sample, so simulation code must never use it; tests/test_sizing.py enforces that.
CALIBRATION_ONLY_FULL_SAMPLE_P99_USD = 27_897


def capital_report_lines(settings):
    """Plain-English lines describing a CapitalSettings, for the `capital` command."""
    caps = settings.hub_caps_mw()
    full_size_mwh = settings.full_size_mwh_per_day()
    floor_usd = settings.effective_ruin_floor_usd()
    full_size_capital_usd = settings.full_size_capital_usd(CALIBRATION_ONLY_FULL_SAMPLE_P99_USD)
    collateral_usd = full_size_mwh * MINIMUM_MPD_USD_PER_MWH * VIRTUAL_EXPOSURE_WINDOW_DAYS
    lines = [
        f"Starting capital: ${settings.starting_capital_usd:,.0f}",
        f"Daily risk budget: {settings.daily_risk_budget_fraction:.1%} of equity on a 1-in-100 day",
        "Per-hub caps (MW): " + ", ".join(f"{hub} {cap:g}" for hub, cap in caps.items()),
        f"Full size: {sum(caps.values()):g} MW x 24 h = {full_size_mwh:g} MWh per day",
        f"Full size is reached at ${full_size_capital_usd:,.0f} (full-sample p99, calibration "
        "only; point-in-time it varies, capital_sizing.md §4b)",
        f"MISO collateral at full size: {full_size_mwh:g} MWh x ${MINIMUM_MPD_USD_PER_MWH:g} MPD x "
        f"{VIRTUAL_EXPOSURE_WINDOW_DAYS} days = ${collateral_usd:,.0f}",
        "Virtual MWh Limit the pledged credit supports: "
        f"{settings.virtual_mwh_limit():,.0f} MWh per day",
    ]
    if floor_usd is None:
        lines.append("Death: out of money (no capital floor set)")
    else:
        lines.append(
            f"Capital floor: ${floor_usd:,.0f}; headroom {settings.headroom_fraction():.1%}"
        )
    lines += [f"Warning: {message}" for message in settings.warnings()]
    return lines


def main(argv=None):
    """Entry point."""
    parser = argparse.ArgumentParser(prog="evobots")
    commands = parser.add_subparsers(dest="command", required=True)
    capital = commands.add_parser("capital", help="show the capital settings and what they imply")
    capital.add_argument("config", nargs="?", help="TOML file with a [capital] table")
    capital.add_argument("--starting-capital", type=float, dest="starting_capital_usd")
    capital.add_argument("--daily-risk-budget", type=float, dest="daily_risk_budget_fraction")
    capital.add_argument("--credit-share", type=float, dest="credit_share_fraction")
    capital.add_argument("--max-mw-per-hub-hour", type=float, dest="max_mw_per_hub_hour")
    capital.add_argument("--ruin-floor-fraction", type=float, dest="ruin_floor_fraction")
    capital.add_argument("--ruin-floor-usd", type=float, dest="ruin_floor_usd")
    arguments = parser.parse_args(argv)
    overrides = {
        name: getattr(arguments, name)
        for name in (
            "starting_capital_usd",
            "daily_risk_budget_fraction",
            "credit_share_fraction",
            "max_mw_per_hub_hour",
            "ruin_floor_fraction",
            "ruin_floor_usd",
        )
    }
    try:
        settings = load_capital(arguments.config, overrides)
    except ValueError as error:
        parser.error(str(error))
    print("\n".join(capital_report_lines(settings)))


if __name__ == "__main__":
    main()
