"""Draw a report card (JSON) as one self-contained HTML file (`docs/design_spec.md` §12.2).

One renderer serves the app's Report page and the exported file. The page uses the project's
visual style: white surfaces, ink and greys, one signal colour for losses, hairlines between
sections, every chart and metric with a title, a one-line description and a value. Charts are
inline SVG, the CSS is inline, and nothing loads from the network.

Example:
    >>> identity = {"trader_id": "R1-1", "name": "early-curlew", "rules": [], "features_read": []}
    >>> charts = {"equity": [], "drawdown": []}
    >>> card = {"identity": identity, "what_happened": "…", "gates": {}, "charts": charts}
    >>> html_text = report_html(card)
    >>> html_text.startswith("<!doctype html>") and "R1-1" in html_text
    True
"""

import html
from pathlib import Path

THEME_PATH = Path(__file__).resolve().parents[1] / "app" / "static" / "theme.css"
CHART_WIDTH = 720
CHART_HEIGHT = 180


def escape(value):
    """HTML-escaped text."""
    return html.escape(str(value))


def line_chart(points, label, is_fraction=False):
    """An inline SVG line chart of (day, value) points, ink on white, min/max labelled."""
    if len(points) < 2:
        return '<p class="description">Not enough data to draw.</p>'
    values = [value for _, value in points]
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = (CHART_WIDTH - 2) / (len(points) - 1)
    plot_height = CHART_HEIGHT - 40
    coordinates = " ".join(
        f"{index * step + 1:.1f},{CHART_HEIGHT - 20 - (value - low) / span * plot_height:.1f}"
        for index, (_, value) in enumerate(points)
    )

    def show(value):
        return f"{value:.0%}" if is_fraction else f"${value:,.0f}"

    return (
        f'<svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" width="100%" role="img" '
        f'aria-label="{escape(label)}">'
        f'<polyline points="{coordinates}" fill="none" stroke="var(--colour-ink)" '
        'stroke-width="1"/>'
        f'<text x="2" y="12" class="axis">{escape(show(high))}</text>'
        f'<text x="2" y="{CHART_HEIGHT - 4}" class="axis">{escape(show(low))}</text>'
        f'<text x="{CHART_WIDTH - 2}" y="{CHART_HEIGHT - 4}" text-anchor="end" class="axis">'
        f"{escape(points[0][0])} → {escape(points[-1][0])}</text></svg>"
    )


def section(title, description, body):
    """A titled section with its one-line description."""
    return (
        f'<section class="section"><h2>{escape(title)}</h2>'
        f'<p class="description">{escape(description)}</p>{body}</section>'
    )


def table(headers, rows):
    """A plain table (strings are escaped)."""
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def report_html(card, theme_css=None):
    """The report card as a complete HTML document."""
    css = (
        theme_css
        if theme_css is not None
        else (THEME_PATH.read_text(encoding="utf-8") if THEME_PATH.exists() else "")
    )
    identity = card["identity"]
    gate_rows = [
        (name, entry["status"], entry["detail"]) for name, entry in card.get("gates", {}).items()
    ]
    parts = [
        f'<div class="top"><h1>Report card: {escape(identity["name"])} '
        f"({escape(identity['trader_id'])})</h1></div>",
        f'<p class="description">{escape(card.get("what_happened", ""))}</p>',
        section(
            "Gates",
            "Each test a trader must pass before it counts as deployable (design spec §12.2).",
            table(["Gate", "Result", "Detail"], gate_rows),
        ),
        section(
            "Rules",
            "The trader's program in plain English.",
            '<ul class="rules">'
            + "".join(f"<li>{escape(line)}</li>" for line in identity["rules"])
            + "</ul>",
        ),
        section(
            "Equity",
            "Account value each day over the whole evolution period (thinned, spikes kept).",
            line_chart(card["charts"]["equity"], "equity"),
        ),
        section(
            "Drawdown",
            "Fall from the running peak each day.",
            line_chart(card["charts"]["drawdown"], "drawdown", is_fraction=True),
        ),
    ]
    if card.get("rolling_next_years"):
        parts.append(
            section(
                "Next-year results",
                card.get("rolling_note", ""),
                table(
                    ["Year", "Log growth", "Max drawdown", "Alive"],
                    [
                        (
                            row["year"],
                            f"{row['log_growth']:+.3f}",
                            f"{row['max_drawdown_fraction']:.0%}",
                            "yes" if row["is_alive"] else "no",
                        )
                        for row in card["rolling_next_years"]
                    ],
                ),
            )
        )
    if card.get("shock_periods"):
        parts.append(
            section(
                "Shock periods",
                "Results through each event of the calendar (G7).",
                table(
                    ["Event", "Days", "Return", "Alive after"],
                    [
                        (
                            row["event"],
                            f"{row['first_day']} → {row['last_day']}",
                            f"{row['return_fraction']:+.1%}"
                            if row.get("return_fraction") is not None
                            else "not covered",
                            "yes" if row.get("is_alive_after", True) else "no",
                        )
                        for row in card["shock_periods"]
                    ],
                ),
            )
        )
    if card.get("storms"):
        storms = card["storms"]
        parts.append(
            section(
                "Storm sensitivity",
                "Fitness with all days and with the named storm days set flat (reporting only).",
                table(
                    ["All days", "Without storms"],
                    [
                        (
                            f"{storms['fitness_all_days']:+.3f}",
                            f"{storms['fitness_without_storms']:+.3f}",
                        )
                    ],
                ),
            )
        )
    if card.get("hindsight_check"):
        check = card["hindsight_check"]
        parts.append(
            section(
                "Hindsight check",
                "Re-scored with policy uncertainty and the gas features missing (their downloaded "
                "history may hold revised values).",
                table(
                    ["Uses them", "Log growth with", "Without", "Suspect"],
                    [
                        (
                            "yes" if check["uses_them"] else "no",
                            f"{check['log_growth_with']:+.3f}",
                            f"{check['log_growth_without']:+.3f}",
                            "yes" if check["is_hindsight_suspect"] else "no",
                        )
                    ],
                ),
            )
        )
    if card.get("inference", {}).get("status") == "run":
        inference = card["inference"]
        parts.append(
            section(
                "Is any elite better than doing nothing?",
                inference["note"],
                table(
                    ["Reality Check", "SPA", "Romano–Wolf: elites beating it at 5 %"],
                    [
                        (
                            f"{inference['reality_check_significance']:.3f}",
                            f"{inference['spa_significance']:.3f}",
                            ", ".join(inference["romano_wolf_beating_do_nothing_at_5_percent"])
                            or "none",
                        )
                    ],
                ),
            )
        )
    parts.append(
        section(
            "Caveats",
            "What these numbers assume.",
            "<ul>"
            + "".join(f"<li>{escape(line)}</li>" for line in card.get("caveats", []))
            + "</ul>",
        )
    )
    parts.append(
        section("Honest expectation", "", f"<p>{escape(card.get('honest_expectation', ''))}</p>")
    )
    body = "".join(parts)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Report card {escape(identity['trader_id'])}</title><style>{css}</style></head>"
        f'<body><main class="single">{body}</main></body></html>'
    )
