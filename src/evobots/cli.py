"""Command line.

- `python -m evobots.cli capital [config] [--starting-capital …]`: the capital settings.
- `python -m evobots.cli data build --stage A [--raw …] [--store …] [--workers N]`: the hub
  price store from the MISO files on disk, checked against the recorded statistics (M1).
- `evobots serve [--port 8765] [--no-browser] [--demo]`: the local app in the browser.
"""

import argparse
import sys
from pathlib import Path

from evobots.capital_summary import capital_summary
from evobots.config import load_capital
from evobots.config.capital import MINIMUM_MPD_USD_PER_MWH, VIRTUAL_EXPOSURE_WINDOW_DAYS

# Full-sample 1-in-100-day full-size loss, 2019-01-01 → 2025-09-21, worse direction (always-INC),
# USD (capital_sizing.md §4; reproduced in round 21). CALIBRATION ONLY: it contains every storm
# of the sample, so simulation code must never use it; tests/test_sizing.py enforces that.
CALIBRATION_ONLY_FULL_SAMPLE_P99_USD = 27_897
# Worst 20-day full-size loss over the same sample (always-INC, ending in Winter Storm Elliott),
# USD (capital_sizing.md §5; reproduced in round 22). CALIBRATION ONLY, as above.
CALIBRATION_ONLY_FULL_SAMPLE_WORST_20_DAY_LOSS_USD = 484_372


def calibration_capital_summary(settings, cleared_share_fraction=0.72):
    """capital_summary at the full-sample calibration losses (for display, never simulation).

    Example:
        >>> from evobots.config.capital import CapitalSettings
        >>> round(calibration_capital_summary(CapitalSettings())["full_size_capital_usd"])
        1394850
    """
    return capital_summary(
        settings,
        CALIBRATION_ONLY_FULL_SAMPLE_P99_USD,
        CALIBRATION_ONLY_FULL_SAMPLE_WORST_20_DAY_LOSS_USD,
        cleared_share_fraction,
    )


def capital_report_lines(settings):
    """Plain-English lines describing a CapitalSettings, for the `capital` command."""
    summary = calibration_capital_summary(settings)
    caps = settings.hub_caps_mw()
    full_size_mwh = summary["full_size_mwh_per_day"]
    lines = [
        f"Starting capital: ${settings.starting_capital_usd:,.0f}",
        f"Daily risk budget: {settings.daily_risk_budget_fraction:.1%} of equity on a 1-in-100 day",
        "Per-hub caps (MW): " + ", ".join(f"{hub} {cap:g}" for hub, cap in caps.items()),
        f"Full size: {sum(caps.values()):g} MW x 24 h = {full_size_mwh:g} MWh per day",
        f"Full size is reached at ${summary['full_size_capital_usd']:,.0f} (full-sample p99, "
        "calibration only; point-in-time it varies, capital_sizing.md §4b)",
        f"MISO collateral at full size: {full_size_mwh:g} MWh x ${MINIMUM_MPD_USD_PER_MWH:g} MPD x "
        f"{VIRTUAL_EXPOSURE_WINDOW_DAYS} days = ${summary['collateral_at_full_size_usd']:,.0f}",
        "Virtual MWh Limit the pledged credit supports: "
        f"{summary['virtual_mwh_limit_mwh_per_day']:,.0f} MWh per day",
    ]
    if summary["ruin_floor_usd"] is None:
        lines.append("Death: out of money (no capital floor set)")
    else:
        lines.append(
            f"Capital floor: ${summary['ruin_floor_usd']:,.0f}; "
            f"headroom {summary['headroom_fraction']:.1%}"
        )
    lines += [f"Warning: {message}" for message in summary["warnings"]]
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
    data = commands.add_parser("data", help="build the data store (offline)")
    data_commands = data.add_subparsers(dest="data_command", required=True)
    build = data_commands.add_parser("build", help="build and check a stage's store")
    build.add_argument("--stage", choices=["A", "D", "C"], default="A")
    build.add_argument("--raw", type=Path, default=Path("data/raw/miso"))
    build.add_argument("--store", type=Path, default=Path("data/store"))
    build.add_argument("--workers", type=int, default=4)
    serve = commands.add_parser("serve", help="open the app in the browser (localhost only)")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--demo", action="store_true", help="use synthetic demo data")
    arguments = parser.parse_args(argv)
    if arguments.command == "serve":
        return run_serve(arguments)
    if arguments.command == "data":
        return run_data_build(arguments)
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


def run_serve(arguments):
    """`serve`: start the app on localhost and open the browser."""
    import threading
    import webbrowser

    import uvicorn

    from evobots.app import server
    from evobots.service import Service

    print("Loading data …")
    server.service_holder["service"] = Service(is_synthetic=arguments.demo)
    address = f"http://127.0.0.1:{arguments.port}/"
    print(f"evobots is running at {address} (close this window or press Ctrl+C to stop)")
    if not arguments.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(address)).start()
    uvicorn.run(server.app, host="127.0.0.1", port=arguments.port, log_level="warning")
    return 0


def run_data_build(arguments):
    """`data build`: build the store for a stage and print the checks; 1 if any fails."""
    if arguments.stage != "A":
        print(f"Stage {arguments.stage} is built at M8; only stage A exists so far.")
        return 1
    from evobots.data.build import build_stage_a

    lines, is_passing = build_stage_a(arguments.raw, arguments.store, arguments.workers)
    print("\n".join(lines))
    return 0 if is_passing else 1


if __name__ == "__main__":
    sys.exit(main())
