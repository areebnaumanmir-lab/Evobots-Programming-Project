"""Build a static preview of the evobots visual style from the real MISO data.

Usage:
    python tools/build_design_preview.py

Reads data/store/ (from tools/build_miso_hub_prices.py) and docs/design/theme.css, and
writes docs/design/preview_data_page.html: one self-contained page (CSS inlined, charts as
inline SVG drawn here in Python, no JavaScript, no external files). It previews the Data
page planned for M2, so the visual rules of docs/design_rationale.md part E can be judged
on real numbers before the app exists. Nothing on it is invented: every number comes from
the store, and the hold-out period is absent because the store excludes it.
"""

import csv
import datetime
import gzip
import html
from collections import defaultdict
from pathlib import Path

STORE_DIRECTORY = Path("data/store")
THEME_PATH = Path("docs/design/theme.css")
OUTPUT_PATH = Path("docs/design/preview_data_page.html")
EVOLUTION_LAST_DAY = "2025-09-21"
CHART_WIDTH = 1080
CHART_HEIGHT = 220
CHART_MARGIN_LEFT = 48
CHART_MARGIN_BOTTOM = 24


def monthly_mean_spreads(hub):
    """{YYYY-MM: mean DA − RT in $/MWh} for one hub over the evolution period."""
    totals = defaultdict(lambda: [0.0, 0])
    with gzip.open(STORE_DIRECTORY / "hub_prices.csv.gz", "rt", encoding="utf-8") as hub_file:
        for row in csv.DictReader(hub_file):
            if row["hub"] != hub or row["date"] > EVOLUTION_LAST_DAY:
                continue
            if row["da_lmp"] and row["rt_lmp"]:
                month_total = totals[row["date"][:7]]
                month_total[0] += float(row["da_lmp"]) - float(row["rt_lmp"])
                month_total[1] += 1
    return {month: total / count for month, (total, count) in sorted(totals.items())}


def line_chart_svg(points, axis_label_format="{:.0f}", is_zero_line=True):
    """Inline SVG line chart in ink with hairline axes. points: [(x_label, value)]."""
    values = [value for _, value in points]
    low, high = min(values + [0.0]), max(values + [0.0])
    plot_width = CHART_WIDTH - CHART_MARGIN_LEFT
    plot_height = CHART_HEIGHT - CHART_MARGIN_BOTTOM

    def horizontal_position(index):
        return CHART_MARGIN_LEFT + index * plot_width / max(len(points) - 1, 1)

    def vertical_position(value):
        return 8 + (high - value) * (plot_height - 16) / (high - low or 1)

    parts = [f'<svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" width="100%" role="img">']
    for tick in (low, (low + high) / 2, high):
        parts.append(
            f'<line x1="{CHART_MARGIN_LEFT}" x2="{CHART_WIDTH}" y1="{vertical_position(tick):.1f}" '
            f'y2="{vertical_position(tick):.1f}" stroke="var(--colour-hairline)"/>'
            f'<text x="0" y="{vertical_position(tick) + 4:.1f}">{axis_label_format.format(tick)}</text>'
        )
    if is_zero_line:
        parts.append(
            f'<line x1="{CHART_MARGIN_LEFT}" x2="{CHART_WIDTH}" y1="{vertical_position(0):.1f}" '
            f'y2="{vertical_position(0):.1f}" stroke="var(--colour-ink)" stroke-width="0.5"/>'
        )
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{horizontal_position(index):.1f},{vertical_position(value):.1f}"
        for index, (_, value) in enumerate(points)
    )
    parts.append(f'<path d="{path}" fill="none" stroke="var(--colour-ink)" stroke-width="1.2"/>')
    previous_label = None
    for index, (label, _) in enumerate(points):
        year = label[:4]
        if year != previous_label and int(year) % 2 == 1:
            parts.append(
                f'<text x="{horizontal_position(index):.1f}" y="{CHART_HEIGHT - 4}">{year}</text>'
            )
        previous_label = year
    parts.append("</svg>")
    return "".join(parts)


def hub_timeline_svg(hub_spans, first_day, last_day):
    """One thin ink line per hub from its first to its last day with prices."""
    row_height = 22
    height = row_height * len(hub_spans) + 24
    span_days = (last_day - first_day).days
    left = 120

    def horizontal_position(day_text):
        day = datetime.date.fromisoformat(day_text)
        return left + (day - first_day).days * (CHART_WIDTH - left) / span_days

    parts = [f'<svg viewBox="0 0 {CHART_WIDTH} {height}" width="100%" role="img">']
    for index, (hub, first, last) in enumerate(hub_spans):
        row_top = 12 + index * row_height
        parts.append(
            f'<text x="0" y="{row_top + 4}">{html.escape(hub.replace(".HUB", ""))}</text>'
            f'<line x1="{horizontal_position(first):.1f}" x2="{horizontal_position(last):.1f}" y1="{row_top}" y2="{row_top}" '
            f'stroke="var(--colour-ink)" stroke-width="2"/>'
        )
    for year in range(first_day.year + 1, last_day.year + 1, 3):
        year_position = horizontal_position(f"{year}-01-01")
        parts.append(
            f'<line x1="{year_position:.1f}" x2="{year_position:.1f}" y1="0" y2="{height - 18}" '
            f'stroke="var(--colour-hairline)"/><text x="{year_position - 14:.1f}" y="{height - 4}">{year}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def coverage_facts():
    days_by_market = defaultdict(set)
    locations_by_year = defaultdict(set)
    with (STORE_DIRECTORY / "daily_coverage.csv").open(encoding="utf-8") as coverage_file:
        for row in csv.DictReader(coverage_file):
            days_by_market[row["market"]].add(row["date"])
    with (STORE_DIRECTORY / "locations.csv").open(encoding="utf-8") as locations_file:
        location_rows = list(csv.DictReader(locations_file))
    for row in location_rows:
        if row["first_day_da"]:
            for year in range(int(row["first_day_da"][:4]), int(row["last_day_da"][:4]) + 1):
                locations_by_year[str(year)].add(row["name"])
    hub_spans = sorted(
        (
            (row["name"], row["first_day_da"], row["last_day_da"])
            for row in location_rows
            if row["type"] == "Hub" and row["name"].endswith(".HUB")
        ),
        key=lambda span: span[1],
    )
    return days_by_market, locations_by_year, hub_spans, len(location_rows)


def spread_table_rows():
    """Read the spread statistics already computed in docs/data_coverage.md."""
    lines = Path("docs/data_coverage.md").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("| Hub | Hours"))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def main():
    days_by_market, locations_by_year, hub_spans, location_count = coverage_facts()
    all_days = sorted(days_by_market["da"] | days_by_market["rt"])
    first_day = datetime.date.fromisoformat(all_days[0])
    last_day = datetime.date.fromisoformat(all_days[-1])
    monthly_spreads = monthly_mean_spreads("MINN.HUB")
    spread_points = list(monthly_spreads.items())
    worst_month, worst_value = min(spread_points, key=lambda point: point[1])
    location_points = [
        (f"{year}-01", len(names)) for year, names in sorted(locations_by_year.items())
    ]

    spread_rows_html = "".join(
        "<tr>"
        + f"<td>{html.escape(row[0].replace('.HUB', ''))}</td>"
        + "".join(
            f'<td class="number{" negative" if cell.startswith("-") else ""}">{cell}</td>'
            for cell in row[1:]
        )
        + "</tr>"
        for row in spread_table_rows()
    )
    theme = THEME_PATH.read_text(encoding="utf-8")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>evobots · Data (style preview)</title>
<!-- Preview of the M2 Data page. Generated by tools/build_design_preview.py from data/store/.
     Style rules: docs/design_rationale.md part E. Theme: docs/design/theme.css (inlined). -->
<style>{theme}</style></head>
<body><div class="layout">
<nav class="navigation" aria-label="Main">
  <a href="#">Home</a>
  <a href="#" class="is-active">Data</a>
  <div class="sub"><a href="#" class="is-active">Coverage</a><a href="#">Prices</a><a href="#">Locations</a><a href="#">Features</a></div>
  <a href="#">Traders</a>
  <a href="#">Evolution</a>
  <a href="#">Report card</a>
  <a href="#">Methods</a>
  <a href="#">Docs</a>
  <a href="#">Settings</a>
</nav>
<main class="content">
  <div class="top"><h1>Data</h1>
    <div class="actions"><input class="search" placeholder="Search traders, pages, terms" aria-label="Search">
    <a href="#">Best bot</a></div></div>
  <div class="filters"><span>{first_day.isoformat()} → {last_day.isoformat()}</span><span>All trading hubs</span>
    <a href="#">Change period</a><a href="#">Download CSV</a><a href="#">How this was built</a></div>

  <div class="metrics">
    <div class="metric"><h2>Days with day-ahead prices</h2>
      <p class="description">Operating days for which MISO published a day-ahead (DA) price file. The sealed 12-month test period is not counted.</p>
      <div class="value">{len(days_by_market["da"]):,}</div></div>
    <div class="metric"><h2>Days with real-time prices</h2>
      <p class="description">Days with a final real-time (RT) price file. The newest days appear about 4–5 days late.</p>
      <div class="value">{len(days_by_market["rt"]):,}</div></div>
    <div class="metric"><h2>Locations ever priced</h2>
      <p class="description">Distinct places MISO publishes a price for: generators, load zones, interfaces and hubs.</p>
      <div class="value">{location_count:,}</div></div>
    <div class="metric"><h2>Sealed 12-month test</h2>
      <p class="description">2025-09-22 → 2026-09-21, kept apart for one final test per run.</p>
      <div class="value">Never opened</div></div>
  </div>

  <section class="section"><h2>Average DA − RT spread, Minnesota hub, by month</h2>
    <p class="description">How much the day-ahead price exceeded the real-time price on average, in $/MWh. Above zero, selling in day-ahead (INC) earned money that month. Lowest month: {worst_month} ({worst_value:,.0f} $/MWh).</p>
    {line_chart_svg(spread_points)}</section>

  <section class="section"><h2>Trading hubs over time</h2>
    <p class="description">Each line runs from a hub's first to its last day with prices. CINERGY and INDIANA overlap for ten months in 2011 with different prices, so they are treated as different hubs.</p>
    {hub_timeline_svg(hub_spans, first_day, last_day)}</section>

  <section class="section"><h2>Locations priced per year</h2>
    <p class="description">How many distinct locations had a day-ahead price at some point in each year.</p>
    {line_chart_svg(location_points, is_zero_line=False)}</section>

  <section class="section"><h2>Spread by hub, 2019-01-01 → 2025-09-21</h2>
    <p class="description">s = DA − RT in $/MWh per hour. Std is the standard deviation; excess kurtosis above 0 means more extreme hours than a normal distribution would give. <a href="#" class="help" title="Glossary: spread, kurtosis">?</a></p>
    <table><thead><tr><th>Hub</th><th class="number">Hours</th><th class="number">Mean</th><th class="number">Median |s|</th><th class="number">Std</th><th class="number">Excess kurtosis</th></tr></thead>
    <tbody>{spread_rows_html}</tbody></table></section>
</main></div></body></html>
"""
    OUTPUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
