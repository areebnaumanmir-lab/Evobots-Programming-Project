"""Build tools/capital_explorer.html: the capital explorer, with every number computed in Python.

Usage:
    python tools/build_capital_explorer.py

The original explorer (Claude Science) computed its numbers in JavaScript, had a syntax error
(an unescaped apostrophe) and never reached this repository. This replacement follows
docs/design_spec.md §14.5: the page holds no formulas. This script evaluates
`evobots.cli.calibration_capital_summary` (the same function the `capital` command uses) on
every combination of the page's controls and writes the formatted results into the page as
lookup tables; the page's script only picks the entry for the current controls.

Controls: starting capital $250k–$5M in $50k steps; daily risk budget 0.5–5 % in 0.5 % steps;
cleared share 0.25 / 0.50 / 0.72 / 1.00; capital floor off / two-thirds of capital / $1M.
The page is replaced by the Capital page of the app at M1.5.
"""

import html
import json
from pathlib import Path

from evobots.cli import (
    CALIBRATION_ONLY_FULL_SAMPLE_P99_USD,
    CALIBRATION_ONLY_FULL_SAMPLE_WORST_20_DAY_LOSS_USD,
    calibration_capital_summary,
)
from evobots.config.capital import CapitalSettings

THEME_PATH = Path("docs/design/theme.css")
OUTPUT_PATH = Path("tools/capital_explorer.html")
CAPITALS_USD = list(range(250_000, 5_000_001, 50_000))
BUDGETS_FRACTION = [round(0.005 * step, 3) for step in range(1, 11)]
CLEARED_SHARES_FRACTION = [0.25, 0.50, 0.72, 1.00]
FLOORS = [
    ("off", {}),
    ("two-thirds", {"ruin_floor_fraction": 2 / 3}),
    ("$1,000,000", {"ruin_floor_usd": 1_000_000.0}),
]
DEFAULT_CAPITAL_USD = 1_500_000
DEFAULT_BUDGET_FRACTION = 0.02
DEFAULT_SHARE_INDEX = 2
DEFAULT_FLOOR_INDEX = 0

# (element id, title, one-line description); the value comes from the lookup tables.
METRICS = [
    (
        "scale",
        "Share of the cap used",
        "Position scale on day one: min(1, budget × capital ÷ 1-in-100-day loss).",
    ),
    (
        "full_size_capital",
        "Full size reached at",
        "The capital at which bids reach every hub's cap.",
    ),
    (
        "fixed_cost",
        "Fixed cost per cleared MWh",
        "$50,000 a year of assumed fixed costs spread over the cleared MWh.",
    ),
    (
        "worst_full",
        "Worst 20 days, full-sample sizing",
        "Loss over the worst 20 days of 2019–2025 at a constant scale, share of capital.",
    ),
    (
        "worst_point_in_time",
        "Worst 20 days, point-in-time sizing",
        "The same with the trailing 1-in-100 estimate the simulator uses (capital_sizing.md §6b).",
    ),
    ("floor", "Capital floor", "Optional career layer L1; the default death is out of money."),
    ("headroom", "Headroom", "Share of starting capital that can be lost before the floor."),
    (
        "virtual_limit",
        "Virtual MWh Limit",
        "MWh per day the pledged credit (25 % of capital) supports at the $12 MPD floor.",
    ),
]


def summary_for(capital_usd, budget_fraction, share_fraction, floor_settings):
    """(summary, rejection message or None) for one combination of the controls."""
    try:
        settings = CapitalSettings(
            starting_capital_usd=capital_usd,
            daily_risk_budget_fraction=budget_fraction,
            **floor_settings,
        )
        rejection = None
    except ValueError as error:
        settings = CapitalSettings(
            starting_capital_usd=capital_usd, daily_risk_budget_fraction=budget_fraction
        )
        rejection = f"Floor rejected: {error}."
    return calibration_capital_summary(settings, share_fraction), rejection


def lookup_tables():
    """Formatted values indexed [capital][budget][share][floor], with shared warning texts."""
    warning_texts = []
    values = []
    for capital_usd in CAPITALS_USD:
        by_budget = []
        for budget_fraction in BUDGETS_FRACTION:
            by_share = []
            for share_fraction in CLEARED_SHARES_FRACTION:
                by_floor = []
                for _, floor_settings in FLOORS:
                    summary, rejection = summary_for(
                        capital_usd, budget_fraction, share_fraction, floor_settings
                    )
                    messages = ([rejection] if rejection else []) + summary["warnings"]
                    for message in messages:
                        if message not in warning_texts:
                            warning_texts.append(message)
                    floor_usd = summary["ruin_floor_usd"]
                    by_floor.append(
                        [
                            f"{summary['position_scale_fraction']:.1%}",
                            f"${summary['full_size_capital_usd']:,.0f}",
                            f"${summary['fixed_cost_usd_per_cleared_mwh']:.3f}",
                            f"{summary['worst_20_day_loss_full_sample_fraction']:.1%}",
                            f"{summary['worst_20_day_loss_point_in_time_fraction']:.1%}",
                            "off" if floor_usd is None else f"${floor_usd:,.0f}",
                            "–" if floor_usd is None else f"{summary['headroom_fraction']:.1%}",
                            f"{summary['virtual_mwh_limit_mwh_per_day']:,.0f}",
                            [warning_texts.index(message) for message in messages],
                        ]
                    )
                by_share.append(by_floor)
            by_budget.append(by_share)
        values.append(by_budget)
    return values, warning_texts


def choice_words(group, labels, selected_index):
    """A row of clickable words (no button boxes, docs/design_spec.md §14.5)."""
    words = []
    for index, label in enumerate(labels):
        state = "true" if index == selected_index else "false"
        words.append(
            f'<a href="#" class="choice" data-group="{group}" data-index="{index}" '
            f'aria-pressed="{state}">{html.escape(label)}</a>'
        )
    return " ".join(words)


def page_html(values, warning_texts):
    """The whole page as one string: inline CSS, inline data, a lookup-only script."""
    theme = THEME_PATH.read_text(encoding="utf-8")
    metrics = "\n".join(
        f'<div class="metric"><h2>{html.escape(title)}</h2>'
        f'<p class="description">{html.escape(description)}</p>'
        f'<div class="value" id="{element_id}"></div></div>'
        for element_id, title, description in METRICS
    )
    data = json.dumps(
        {
            "values": values,
            "warnings": warning_texts,
            "capitals": [f"${capital:,.0f}" for capital in CAPITALS_USD],
            "budgets": [f"{budget:.1%}" for budget in BUDGETS_FRACTION],
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )
    # "</" inside a script would end it early; JSON allows the escaped form.
    data = data.replace("</", "<\\/")
    capital_index = CAPITALS_USD.index(DEFAULT_CAPITAL_USD)
    budget_index = BUDGETS_FRACTION.index(DEFAULT_BUDGET_FRACTION)
    share_words = choice_words(
        "share", [f"{share:.2f}" for share in CLEARED_SHARES_FRACTION], DEFAULT_SHARE_INDEX
    )
    floor_words = choice_words("floor", [label for label, _ in FLOORS], DEFAULT_FLOOR_INDEX)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capital explorer</title>
<!-- Generated by tools/build_capital_explorer.py from evobots.cli.calibration_capital_summary.
     Do not edit by hand. Every number is computed in Python; the script below only looks up
     the entry for the current controls (docs/design_spec.md §14.5). Maths: docs/maths.md §1. -->
<style>
{theme}
.controls {{ display: grid; grid-template-columns: 220px 1fr; gap: var(--space-3) var(--space-4);
  padding: var(--space-4) 0; border-bottom: 1px solid var(--colour-hairline); align-items: baseline; }}
.controls input[type=range] {{ width: 100%; max-width: 420px; accent-color: var(--colour-ink); }}
.choice {{ color: var(--colour-secondary-text); margin-right: var(--space-3); }}
.choice[aria-pressed=true] {{ color: var(--colour-ink); font-weight: 600; text-decoration: underline; }}
.metrics {{ column-gap: var(--space-4); }}
.metric + .metric {{ border-left: none; padding-left: 0; }}
.warnings p {{ color: var(--colour-signal); margin: var(--space-1) 0; max-width: 90ch; }}
</style>
</head>
<body>
<div class="content">
<div class="top"><h1>Capital</h1></div>
<p class="description">What a starting capital and risk budget imply at Stage A (8 hubs).
Calibration view: it uses the full-sample 1-in-100-day loss (${CALIBRATION_ONLY_FULL_SAMPLE_P99_USD:,})
and worst 20-day loss (${CALIBRATION_ONLY_FULL_SAMPLE_WORST_20_DAY_LOSS_USD:,}) of 2019-01 → 2025-09,
which contain every storm of the sample; traders never see these numbers.
Full size is 936 MWh a day (39 MW × 24 h); collateral at full size is $22,464.</p>
<div class="controls">
<label for="capital">Starting capital <span id="capital-value"></span></label>
<input type="range" id="capital" min="0" max="{len(CAPITALS_USD) - 1}" step="1" value="{capital_index}">
<label for="budget">Daily risk budget <span id="budget-value"></span></label>
<input type="range" id="budget" min="0" max="{len(BUDGETS_FRACTION) - 1}" step="1" value="{budget_index}">
<span>Cleared share</span><span>{share_words}</span>
<span>Capital floor</span><span>{floor_words}</span>
</div>
<div class="metrics">
{metrics}
</div>
<div class="section warnings" id="warnings"></div>
</div>
<script id="lookup" type="application/json">{data}</script>
<script>
"use strict";
// Lookup only: no formulas here (docs/design_spec.md §14.5, §18).
const lookup = JSON.parse(document.getElementById("lookup").textContent);
const fieldIds = ["scale", "full_size_capital", "fixed_cost", "worst_full",
  "worst_point_in_time", "floor", "headroom", "virtual_limit"];
const selected = {{share: {DEFAULT_SHARE_INDEX}, floor: {DEFAULT_FLOOR_INDEX}}};
function show() {{
  const capitalIndex = Number(document.getElementById("capital").value);
  const budgetIndex = Number(document.getElementById("budget").value);
  document.getElementById("capital-value").textContent = lookup.capitals[capitalIndex];
  document.getElementById("budget-value").textContent = lookup.budgets[budgetIndex];
  const entry = lookup.values[capitalIndex][budgetIndex][selected.share][selected.floor];
  fieldIds.forEach((fieldId, position) => {{
    document.getElementById(fieldId).textContent = entry[position];
  }});
  const warnings = document.getElementById("warnings");
  warnings.replaceChildren(...entry[fieldIds.length].map((warningIndex) => {{
    const paragraph = document.createElement("p");
    paragraph.textContent = lookup.warnings[warningIndex];
    return paragraph;
  }}));
}}
document.querySelectorAll(".choice").forEach((word) => {{
  word.addEventListener("click", (event) => {{
    event.preventDefault();
    selected[word.dataset.group] = Number(word.dataset.index);
    document.querySelectorAll(`.choice[data-group="${{word.dataset.group}}"]`).forEach((other) => {{
      other.setAttribute("aria-pressed", String(other === word));
    }});
    show();
  }});
}});
document.getElementById("capital").addEventListener("input", show);
document.getElementById("budget").addEventListener("input", show);
show();
</script>
</body>
</html>
"""


def main():
    values, warning_texts = lookup_tables()
    OUTPUT_PATH.write_text(page_html(values, warning_texts), encoding="utf-8")
    print(
        f"wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size:,} bytes, "
        f"{len(warning_texts)} distinct warnings)"
    )


if __name__ == "__main__":
    main()
