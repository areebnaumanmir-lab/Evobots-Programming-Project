"""Write docs/features.md and docs/data/feature_distributions_by_year.csv (M2).

The catalogue table comes from `evobots.features.catalogue`; the yearly distributions come
from the feature store built on this machine (MISO hub prices plus the other inputs). The
CSV holds summary statistics only (no price series) and is listed as MISO-derived in
`evobots.service.MISO_DERIVED_FILES`.

Run: `uv run python tools/build_feature_docs.py`
"""

import csv
import sys
from pathlib import Path

import numpy as np

from evobots.features.catalogue import FEATURE_BY_NAME, FEATURES
from evobots.features.inputs import load_feature_inputs
from evobots.features.store import build_feature_store
from evobots.simulate.market import read_miso_hub_market

DISTRIBUTION_PATH = Path("docs/data/feature_distributions_by_year.csv")
FEATURES_DOC_PATH = Path("docs/features.md")
# A yearly median that moves by more than this many inter-quartile ranges from the previous
# year is listed as a step to explain.
STEP_IQR_MULTIPLE = 1.0


def catalogue_table():
    """The catalogue as a Markdown table (one row per feature)."""
    lines = [
        "| # | Code name | Display name | Unit | Level | Kind | Meaning |",
        "|---|---|---|---|---|---|---|",
    ]
    for number, feature in enumerate(FEATURES, start=1):
        unit = feature.unit.label() if feature.kind == "number" else feature.kind
        if feature.kind == "category":
            unit = "category: " + ", ".join(feature.categories)
        lines.append(
            f"| {number} | `{feature.name}` | {feature.display_name} | {unit} | {feature.level} "
            f"| {feature.kind} | {feature.meaning} |"
        )
    return "\n".join(lines)


def yearly_distributions(store):
    """Rows (feature, year, missing_fraction, p5, p25, p50, p75, p95) for number features."""
    years = np.array([day.year for day in store.days])
    rows = []
    for feature in FEATURES:
        if feature.kind != "number":
            continue
        full = store.full(feature.name)
        for year in sorted(set(years.tolist())):
            values = full[years == year]
            finite = values[~np.isnan(values)]
            row = {
                "feature": feature.name,
                "year": year,
                "missing_fraction": float(np.isnan(values).mean()),
            }
            for label, quantile in (("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95)):
                row[label] = float(np.percentile(finite, quantile)) if finite.size else None
            rows.append(row)
    return rows


def steps(rows):
    """(feature, year, previous median, median, IQR) where the median moved > 1 IQR."""
    found = []
    previous = {}
    for row in rows:
        if row["p50"] is None:
            continue
        last = previous.get(row["feature"])
        if last is not None:
            spread = max(row["p75"] - row["p25"], last["p75"] - last["p25"], 1e-9)
            if abs(row["p50"] - last["p50"]) > STEP_IQR_MULTIPLE * spread:
                found.append((row["feature"], row["year"], last["p50"], row["p50"], spread))
        previous[row["feature"]] = row
    return found


def main():
    market = read_miso_hub_market()
    if market is None:
        sys.exit("no hub table: run `evobots data build --stage A` first")
    store = build_feature_store(market, load_feature_inputs())
    rows = yearly_distributions(store)
    DISTRIBUTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISTRIBUTION_PATH, "w", newline="", encoding="utf-8") as table:
        writer = csv.writer(table, lineterminator="\n")
        writer.writerow(["feature", "year", "missing_fraction", "p5", "p25", "p50", "p75", "p95"])
        for row in rows:
            writer.writerow(
                [row["feature"], row["year"], f"{row['missing_fraction']:.4f}"]
                + [
                    "" if row[label] is None else f"{row[label]:.4g}"
                    for label in ("p5", "p25", "p50", "p75", "p95")
                ]
            )
    for feature, year, before, after, spread in steps(rows):
        print(
            f"step: {feature} {year}: median {before:.4g} -> {after:.4g} "
            f"(IQR {spread:.4g}) [{FEATURE_BY_NAME[feature].unit.label()}]"
        )
    print(f"wrote {DISTRIBUTION_PATH}")


if __name__ == "__main__":
    main()
