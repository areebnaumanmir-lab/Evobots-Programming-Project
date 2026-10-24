"""Parse the downloaded MISO LMP archive into the hub price table, location list and coverage.

Usage:
    python tools/build_miso_hub_prices.py [--workers 4]

Reads only data/raw/miso/ (written by tools/fetch_miso_prices.py). It never opens the sealed
hold-out in data/holdout/ (CLAUDE.md §7.2); hold-out files are only counted by name.

Writes (all git-ignored except the coverage doc):
  data/store/hub_prices.csv.gz   one row per operating day × hour × trading hub:
                                 date, hour_ending_est, hub, da_lmp, rt_lmp, da_mcc, rt_mcc,
                                 da_mlc, rt_mlc ($/MWh; empty = not published)
  data/store/locations.csv       every priced location: name, type, first and last day seen
                                 in DA and RT, and the number of days seen
  data/store/daily_coverage.csv  per operating day and market: source file, locations priced,
                                 trading hubs priced, whether congestion/loss components exist
  docs/data_coverage.md          the human-readable coverage report

File layout facts this relies on (obs., 2026-10-24, see docs/data_coverage.md):
  * every daily CSV has a few preamble lines, then a header line starting "Node,Type";
  * before 2008-ish the header has no "Value" column: one LMP row per location, with names and
    types right-padded with spaces; later files have LMP, MCC and MLC rows per location;
  * hours are "Hours-Ending" in Eastern Standard Time all year, so every day has 24 hours;
  * a trading hub is a row whose Type is "Hub" and whose name ends in ".HUB".
For days covered by two DA files (2015-02-19 → 28), the ex-post file is used, because MISO
settles virtual bids at the DA ex-post LMP (docs/market_rules.md §1).
"""

import argparse
import csv
import datetime
import gzip
import json
import math
import re
import zipfile
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

RAW_DIRECTORY = Path("data/raw/miso")
HOLDOUT_RAW_DIRECTORY = Path("data/holdout/raw/miso")
STORE_DIRECTORY = Path("data/store")
COVERAGE_DOC_PATH = Path("docs/data_coverage.md")
HOURS_PER_DAY = 24
VALUE_TYPES = ("LMP", "MCC", "MLC")
MEMBER_DATE_PATTERN = re.compile(r"(\d{8})_(da|rt)_")


def parse_daily_csv(text):
    """Parse one day's LMP CSV.

    Returns (hub_values, location_types, has_components):
      hub_values: {(hub, value_type): [24 floats or None]}
      location_types: {location name: location type} for every location with an LMP row
      has_components: True when MCC/MLC rows exist
    """
    lines = text.splitlines()
    header_index = next(index for index, line in enumerate(lines) if line.startswith("Node,"))
    header = [field.strip() for field in lines[header_index].split(",")]
    has_value_column = len(header) > 2 and header[2] == "Value"
    first_hour_column = 3 if has_value_column else 2
    hub_values = {}
    location_types = {}
    has_components = False
    for line in lines[header_index + 1 :]:
        if not line.strip():
            continue
        fields = line.split(",")
        if len(fields) < first_hour_column + HOURS_PER_DAY:
            continue
        name = fields[0].strip()
        location_type = fields[1].strip()
        if not name:
            # One malformed blank-name line exists (RT, 2005-04-20; obs. round 20).
            continue
        value_type = fields[2].strip() if has_value_column else "LMP"
        if value_type not in VALUE_TYPES:
            continue
        if value_type == "LMP":
            location_types[name] = location_type
        else:
            has_components = True
        if location_type == "Hub" and name.endswith(".HUB"):
            hour_texts = fields[first_hour_column : first_hour_column + HOURS_PER_DAY]
            hub_values[(name, value_type)] = [
                float(hour_text) if hour_text.strip() else None for hour_text in hour_texts
            ]
    return hub_values, location_types, has_components


def daily_texts_in_file(path):
    """Yield (operating_day, market, member_name, text) for every daily CSV in a raw file."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member_name in sorted(archive.namelist()):
                match = MEMBER_DATE_PATTERN.search(member_name)
                if not match:
                    continue
                day = datetime.datetime.strptime(match.group(1), "%Y%m%d").date()
                text = archive.read(member_name).decode("utf-8", errors="replace")
                yield day, match.group(2), member_name, text
    else:
        match = MEMBER_DATE_PATTERN.search(path.name)
        day = datetime.datetime.strptime(match.group(1), "%Y%m%d").date()
        yield day, match.group(2), path.name, path.read_text(encoding="utf-8", errors="replace")


def parse_raw_file(path_text):
    """Worker: parse every day in one raw file. Returns a list of per-day results."""
    path = Path(path_text)
    results = []
    for day, market, member_name, text in daily_texts_in_file(path):
        hub_values, location_types, has_components = parse_daily_csv(text)
        results.append(
            {
                "day": day.isoformat(),
                "market": market,
                "source_file": path.name,
                "member": member_name,
                "is_expost": "expost" in member_name,
                "hub_values": {
                    f"{hub}|{value}": hours for (hub, value), hours in hub_values.items()
                },
                "location_types": location_types,
                "has_components": has_components,
            }
        )
    return results


def chosen_day_results(all_results):
    """One result per (day, market); prefer the ex-post DA file where two exist."""
    chosen = {}
    for result in all_results:
        key = (result["day"], result["market"])
        if key not in chosen or (result["is_expost"] and not chosen[key]["is_expost"]):
            chosen[key] = result
    return chosen


def write_hub_prices(chosen):
    rows_by_key = defaultdict(dict)
    for (day, market), result in chosen.items():
        for hub_and_value, hours in result["hub_values"].items():
            hub, value_type = hub_and_value.split("|")
            for hour_index, value in enumerate(hours):
                column = f"{market}_{value_type.lower()}"
                rows_by_key[(day, hour_index + 1, hub)][column] = value
    columns = ["da_lmp", "rt_lmp", "da_mcc", "rt_mcc", "da_mlc", "rt_mlc"]
    output_path = STORE_DIRECTORY / "hub_prices.csv.gz"
    partial_path = output_path.with_name(output_path.name + ".part")
    with gzip.open(partial_path, "wt", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(["date", "hour_ending_est", "hub", *columns])
        for day, hour, hub in sorted(rows_by_key):
            values = rows_by_key[(day, hour, hub)]
            writer.writerow(
                [day, hour, hub]
                + [
                    "" if values.get(column) is None else f"{values[column]:g}"
                    for column in columns
                ]
            )
    partial_path.replace(output_path)
    return rows_by_key


def write_locations(chosen):
    seen = {}
    for (day, market), result in sorted(chosen.items()):
        for name, location_type in result["location_types"].items():
            entry = seen.setdefault(
                name,
                {"type": location_type, "da_days": 0, "rt_days": 0, "first": {}, "last": {}},
            )
            entry["type"] = location_type
            entry[f"{market}_days"] += 1
            entry["first"].setdefault(market, day)
            entry["last"][market] = day
    output_path = STORE_DIRECTORY / "locations.csv"
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(
            [
                "name",
                "type",
                "first_day_da",
                "last_day_da",
                "days_da",
                "first_day_rt",
                "last_day_rt",
                "days_rt",
            ]
        )
        for name in sorted(seen):
            entry = seen[name]
            writer.writerow(
                [
                    name,
                    entry["type"],
                    entry["first"].get("da", ""),
                    entry["last"].get("da", ""),
                    entry["da_days"],
                    entry["first"].get("rt", ""),
                    entry["last"].get("rt", ""),
                    entry["rt_days"],
                ]
            )
    return seen


def write_daily_coverage(chosen):
    output_path = STORE_DIRECTORY / "daily_coverage.csv"
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(
            ["date", "market", "source_file", "locations_priced", "trading_hubs", "has_components"]
        )
        for day, market in sorted(chosen):
            result = chosen[(day, market)]
            hubs = sorted({key.split("|")[0] for key in result["hub_values"]})
            writer.writerow(
                [
                    day,
                    market,
                    result["source_file"],
                    len(result["location_types"]),
                    " ".join(hubs),
                    result["has_components"],
                ]
            )


def spread_statistics(rows_by_key, first_day, last_day):
    """Per hub: hours, mean, median |s|, std, excess kurtosis of s = DA − RT on the period."""
    spreads_by_hub = defaultdict(list)
    for (day, _hour, hub), values in rows_by_key.items():
        if first_day <= day <= last_day:
            if values.get("da_lmp") is not None and values.get("rt_lmp") is not None:
                spreads_by_hub[hub].append(values["da_lmp"] - values["rt_lmp"])
    statistics = {}
    for hub, spreads in sorted(spreads_by_hub.items()):
        count = len(spreads)
        mean = sum(spreads) / count
        variance = sum((spread - mean) ** 2 for spread in spreads) / (count - 1)
        fourth_moment = sum((spread - mean) ** 4 for spread in spreads) / count
        absolute_spreads = sorted(abs(spread) for spread in spreads)
        middle = count // 2
        median_absolute = (
            absolute_spreads[middle]
            if count % 2
            else (absolute_spreads[middle - 1] + absolute_spreads[middle]) / 2
        )
        statistics[hub] = {
            "hours": count,
            "mean": mean,
            "median_absolute": median_absolute,
            "std": math.sqrt(variance),
            "excess_kurtosis": fourth_moment / (variance**2) - 3,
        }
    return statistics


def write_coverage_doc(chosen, seen, rows_by_key, holdout_file_count, download_counts):
    days_by_market = defaultdict(set)
    for day, market in chosen:
        days_by_market[market].add(day)
    all_days = sorted(days_by_market["da"] | days_by_market["rt"])
    first_day = datetime.date.fromisoformat(all_days[0])
    last_day = datetime.date.fromisoformat(all_days[-1])
    holdout_first = datetime.date(2025, 9, 22)
    holdout_last = datetime.date(2026, 9, 21)
    expected_days = [
        (first_day + datetime.timedelta(days=offset)).isoformat()
        for offset in range((last_day - first_day).days + 1)
        if not holdout_first <= first_day + datetime.timedelta(days=offset) <= holdout_last
    ]
    missing_by_market = {
        market: [day for day in expected_days if day not in days_by_market[market]]
        for market in ("da", "rt")
    }
    hubs_by_day = defaultdict(set)
    for (day, _hour, hub), values in rows_by_key.items():
        if values.get("da_lmp") is not None:
            hubs_by_day[day].add(hub)
    hub_first_last = {}
    for day in sorted(hubs_by_day):
        for hub in hubs_by_day[day]:
            hub_first_last.setdefault(hub, [day, day])[1] = day
    component_first_day = {
        market: next(
            (
                day
                for (day, result_market), result in sorted(chosen.items())
                if result_market == market and result["has_components"]
            ),
            "never",
        )
        for market in ("da", "rt")
    }
    locations_by_year = defaultdict(set)
    for (day, market), result in chosen.items():
        if market == "da":
            locations_by_year[day[:4]].update(result["location_types"])
    type_counts = defaultdict(int)
    for entry in seen.values():
        type_counts[entry["type"]] += 1
    statistics = spread_statistics(rows_by_key, "2019-01-01", "2025-09-21")

    lines = [
        "# MISO price data coverage",
        "",
        f"Generated by `tools/build_miso_hub_prices.py` on {datetime.date.today().isoformat()} "
        "from the archive downloaded by `tools/fetch_miso_prices.py` (obs.). Raw files, the "
        "store and the hold-out are git-ignored; their URLs and SHA-256 are in "
        "`data/manifest.toml`.",
        "",
        "## Summary",
        "",
        f"- Operating days covered: **{all_days[0]} → {all_days[-1]}**, excluding the sealed "
        "hold-out 2025-09-22 → 2026-09-21.",
        f"- Download log: {dict(sorted(download_counts.items()))}.",
        f"- Sealed hold-out: {holdout_file_count} raw files present in `data/holdout/raw/miso/`, "
        "never opened by this script.",
        f"- Days with DA prices: {len(days_by_market['da'])}; with RT prices: "
        f"{len(days_by_market['rt'])}.",
        f"- Missing days outside the hold-out: DA {len(missing_by_market['da'])}, "
        f"RT {len(missing_by_market['rt'])} (listed below).",
        "- Congestion and loss components (MCC, MLC) first appear: "
        f"DA {component_first_day['da']}, "
        f"RT {component_first_day['rt']}. Before that, files carry LMP only.",
        f"- Distinct locations ever priced: {len(seen)} "
        f"({', '.join(f'{kind} {count}' for kind, count in sorted(type_counts.items()))}).",
        "- Hours are hour-ending Eastern Standard Time all year (the files say so), so every "
        "day has 24 hours.",
        "",
        "## Trading hubs (Type `Hub`, name ending `.HUB`), first and last day with DA prices",
        "",
        "| Hub | First day | Last day |",
        "|---|---|---|",
    ]
    lines += [
        f"| {hub} | {first} | {last} |"
        for hub, (first, last) in sorted(hub_first_last.items(), key=lambda item: item[1][0])
    ]
    lines += [
        "",
        "## Locations priced in the DA market, by year",
        "",
        "| Year | Distinct locations |",
        "|---|---|",
    ]
    lines += [f"| {year} | {len(names)} |" for year, names in sorted(locations_by_year.items())]
    lines += [
        "",
        "## Hub spread statistics, 2019-01-01 → 2025-09-21 (check against Claude Science)",
        "",
        "s = DA − RT in $/MWh, over hours where both prices exist. `CLAUDE.md` §13 quotes "
        "(obs. in Claude Science): mean $0.04–0.96, median |s| $2.6–4.7, std $30–62, excess "
        "kurtosis 560–3,300, and 58,944 hours per hub.",
        "",
        "| Hub | Hours | Mean | Median abs | Std | Excess kurtosis |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {hub} | {values['hours']} | {values['mean']:.2f} | {values['median_absolute']:.2f} | "
        f"{values['std']:.1f} | {values['excess_kurtosis']:.0f} |"
        for hub, values in statistics.items()
    ]
    for market in ("da", "rt"):
        missing = missing_by_market[market]
        lines += ["", f"## Missing {market.upper()} days ({len(missing)})", ""]
        lines.append(", ".join(missing) if missing else "None.")
    COVERAGE_DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()
    STORE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    raw_paths = sorted(
        str(path) for path in RAW_DIRECTORY.iterdir() if path.suffix in (".zip", ".csv")
    )
    with Pool(arguments.workers) as pool:
        all_results = [
            result
            for results in pool.imap(parse_raw_file, raw_paths, chunksize=4)
            for result in results
        ]
    chosen = chosen_day_results(all_results)
    rows_by_key = write_hub_prices(chosen)
    seen = write_locations(chosen)
    write_daily_coverage(chosen)
    download_counts = defaultdict(int)
    log_path = RAW_DIRECTORY / "downloads.jsonl"
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            download_counts[json.loads(line)["status"]] += 1
    holdout_file_count = (
        sum(1 for _ in HOLDOUT_RAW_DIRECTORY.glob("*")) if HOLDOUT_RAW_DIRECTORY.exists() else 0
    )
    write_coverage_doc(chosen, seen, rows_by_key, holdout_file_count, download_counts)
    print(f"days parsed: {len(chosen)}; hub rows: {len(rows_by_key)}; locations: {len(seen)}")


if __name__ == "__main__":
    main()
