"""Draw the ORFE write-up's figures from docs/data/orfe/*.json (`docs/orfe_report/report.md`).

Usage:
    uv run python tools/build_orfe_figures.py

Writes standalone SVG files to docs/orfe_report/figures/ with the project's chart code
(`evobots.charts`). The app's colour tokens are replaced by their values so the files render
anywhere (GitHub, a browser, a PDF). The figures show aggregate results only (no MISO prices).
"""

import json
from pathlib import Path

from evobots import charts

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "data" / "orfe"
FIGURES = ROOT / "docs" / "orfe_report" / "figures"
TOKENS = {
    "var(--colour-ink)": "#111111",
    "var(--colour-signal)": "#a3271f",
    "var(--colour-hairline)": "#e4e4e4",
}
STYLE = (
    '<style>.axis{font:11px -apple-system,"Segoe UI",Roboto,Arial,sans-serif;fill:#5f5f5f}</style>'
)


def standalone(svg, title):
    """Inline the colour tokens, add the axis style, a white background and a title."""
    for token, value in TOKENS.items():
        svg = svg.replace(token, value)
    opening_end = svg.index(">") + 1
    opening = svg[:opening_end].replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return (
        opening
        + f"<title>{charts.escape(title)}</title>"
        + STYLE
        + '<rect width="100%" height="100%" fill="#ffffff"/>'
        + svg[opening_end:]
    )


def read(name):
    """One results file."""
    return json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))


def main():
    """Write every figure."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    figures = {}
    leaderboard = read("leaderboard")
    rows = [row for row in leaderboard["rows"] if not row["is_bound"]]
    figures["leaderboard_log_growth"] = (
        charts.bar_chart(
            [(row["strategy"], row["log_growth"]) for row in rows], "log growth", unit=""
        ),
        f"Log growth on the unseen year {leaderboard['period'][0]} → {leaderboard['period'][1]}",
    )
    figures["leaderboard_deflated_sharpe"] = (
        charts.bar_chart(
            [(row["strategy"], row["deflated_sharpe"]) for row in rows], "deflated Sharpe", unit=""
        ),
        "Deflated Sharpe ratio, each against its own class's trial count",
    )
    battery = read("battery")
    figures["battery_bound_ratio"] = (
        charts.bar_chart(
            [
                (name.replace("_", " "), ratio)
                for name, ratio in battery["bound_ratio"].items()
                if name != "perfect_foresight"
            ],
            "share of the perfect-foresight revenue",
            unit="%",
        ),
        "Battery revenue as a share of the perfect-foresight bound",
    )
    risk = read("risk")
    figures["risk_breach_rates"] = (
        charts.bar_chart(
            [
                (
                    f"{row['estimator'].replace('_', ' ')}, {row['period']}",
                    round(100 * row["breach_rate"], 2),
                )
                for row in risk["rows"]
            ],
            "breach rate, percent of days",
            unit="",
        ),
        "Percent of days the 99 % VaR was breached (1 is right)",
    )
    scenarios = read("scenarios")
    figures["scenario_crps"] = (
        charts.bar_chart(
            [
                (name, values["crps"])
                for name, values in scenarios["table"].items()
                if "crps" in values
            ],
            "CRPS",
            unit="",
        ),
        "CRPS of each scenario generator's forecast of the next day's mean spread ($/MWh)",
    )
    portfolio = read("portfolio")
    figures["portfolio_walk_forward"] = (
        charts.bar_chart(
            [
                (name, values["out_of_sample_log_growth"])
                for name, values in portfolio["walk_forward"].items()
            ],
            "log growth",
            unit="",
        ),
        "Portfolio of elites: walk-forward log growth (elites seen; weights unseen)",
    )
    for name, (svg, title) in figures.items():
        (FIGURES / f"{name}.svg").write_text(standalone(svg, title), encoding="utf-8")
        print(f"wrote docs/orfe_report/figures/{name}.svg")


if __name__ == "__main__":
    main()
