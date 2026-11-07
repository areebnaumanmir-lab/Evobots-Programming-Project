"""Measure how much EIA corrects MISO's past capacity between EIA-860M vintages.

Usage:
    python tools/fetch_series.py --eia-860m-vintages 2017-01,2018-01,...   (once)
    python tools/compare_eia860m_vintages.py

EIA says 860M "estimates will be corrected without specific acknowledgment" (design spec §7.8),
and the capacity features are built from the newest workbook, so a trader in, say, 2019
would have seen slightly different numbers. For each archived January workbook this
computes MISO nameplate capacity by technology in three months (2010-01, 2015-01 and the
June before the vintage) and compares it with the newest workbook.

Units are matched to MISO by (plant id, generator id) as listed in the newest workbook,
because workbooks before 2021 have no balancing-authority column (obs., round 28). The
January 2016 workbook has no nameplate column and is skipped. Months after 2025-09 are not
computed (hold-out). Writes docs/data/eia860m_vintage_comparison.csv.
"""

import csv
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from evobots.data.sources import eia860m  # noqa: E402

ARCHIVE_DIRECTORY = Path("data/raw/series/eia_860m_archive")
NEWEST_DIRECTORY = Path("data/raw/series/eia_860m")
OUTPUT_PATH = Path("docs/data/eia860m_vintage_comparison.csv")
GROUPS = ("Wind", "Solar", "Coal", "Natural Gas")


def archived_units(path, miso_unit_keys):
    """MISO units of an archived workbook, matched by (plant id, generator id)."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    units = []
    for sheet_name, is_retired_sheet in (("Operating", False), ("Retired", True)):
        rows = list(workbook[sheet_name].iter_rows(values_only=True))
        header_index = next(
            index
            for index, row in enumerate(rows[:5])
            if row and "Plant ID" in [str(cell).strip() if cell else "" for cell in row]
        )
        header = [str(cell).strip() if cell else "" for cell in rows[header_index]]
        if "Nameplate Capacity (MW)" not in header:
            return None
        column = {name: index for index, name in enumerate(header)}
        for row in rows[header_index + 1 :]:
            if not row or row[column["Plant ID"]] in (None, ""):
                continue
            key = (int(row[column["Plant ID"]]), str(row[column["Generator ID"]]))
            if key not in miso_unit_keys:
                continue
            operating_year = eia860m.number_or_none(row[column["Operating Year"]])
            operating_month = eia860m.number_or_none(row[column["Operating Month"]])
            nameplate = eia860m.number_or_none(row[column["Nameplate Capacity (MW)"]])
            if operating_year is None or operating_month is None or nameplate is None:
                continue
            retirement_month = None
            if is_retired_sheet:
                retired_year = eia860m.number_or_none(row[column["Retirement Year"]])
                retired_month = eia860m.number_or_none(row[column["Retirement Month"]])
                if retired_year and retired_month:
                    retirement_month = (int(retired_year), int(retired_month))
            units.append(
                eia860m.GeneratorUnit(
                    key[0],
                    key[1],
                    str(row[column["Technology"]]),
                    nameplate,
                    (int(operating_year), int(operating_month)),
                    retirement_month,
                    "",
                    None,
                    None,
                )
            )
    workbook.close()
    return units


def main():
    newest_path = sorted(NEWEST_DIRECTORY.glob("*.xlsx"))[-1]
    newest_units = eia860m.read_units(newest_path)
    miso_unit_keys = {(unit.plant_id, unit.generator_id) for unit in newest_units}
    rows = []
    for path in sorted(ARCHIVE_DIRECTORY.glob("*.xlsx")):
        vintage_year = int(path.stem.split("generator")[1])
        units = archived_units(path, miso_unit_keys)
        if units is None:
            print(f"{path.name}: no nameplate column, skipped")
            continue
        for month in ((2010, 1), (2015, 1), (vintage_year - 1, 6)):
            archived = eia860m.nameplate_mw_by_group(units, month)
            newest = eia860m.nameplate_mw_by_group(newest_units, month)
            for group in GROUPS:
                archived_mw, newest_mw = archived.get(group, 0.0), newest.get(group, 0.0)
                rows.append(
                    {
                        "vintage": f"{vintage_year}-01",
                        "month": f"{month[0]}-{month[1]:02d}",
                        "group": group,
                        "vintage_mw": round(archived_mw, 1),
                        "newest_mw": round(newest_mw, 1),
                        "difference_fraction": round(archived_mw / newest_mw - 1, 4)
                        if newest_mw
                        else "",
                    }
                )
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUTPUT_PATH} ({len(rows)} rows) against {newest_path.name}")


if __name__ == "__main__":
    main()
