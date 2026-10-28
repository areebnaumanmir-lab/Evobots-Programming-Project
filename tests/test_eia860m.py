"""Tests for the EIA-860M reader (`evobots.data.sources.eia860m`).

Hand-made rows check the selection and month rules. When the downloaded workbook exists in
data/raw/series/eia_860m/ (git-ignored), MISO's fleet is checked against `CLAUDE.md` §7.8.
"""

from pathlib import Path

import pytest

from evobots.data.sources import eia860m

WORKBOOK_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "raw" / "series" / "eia_860m"
HEADER = [
    "Plant ID",
    "Plant State",
    "Balancing Authority Code",
    "Generator ID",
    "Nameplate Capacity (MW)",
    "Technology",
    "Operating Month",
    "Operating Year",
    "Retirement Month",
    "Retirement Year",
    "Latitude",
    "Longitude",
]


def test_units_selected_by_balancing_authority_and_months():
    rows = [
        HEADER,
        [1, "MN", "MISO", "W1", 100, "Onshore Wind Turbine", 6, 2010, " ", " ", 45.0, -95.0],
        [2, "PA", "PJM", "G1", 500, "Natural Gas Fired Combined Cycle", 1, 2005, 1, 2020, 40, -77],
        [3, "IL", "MISO", "C1", 600, "Conventional Steam Coal", 1, 1970, 4, 2015, 39.0, -89.0],
        [4, "IA", "MISO", "X1", " ", "Batteries", 1, 2020, " ", " ", 41.0, -93.0],
    ]
    retired = eia860m.units_from_rows(rows, is_retired_sheet=True)
    assert [unit.plant_id for unit in retired] == [1, 3]  # PJM and blank capacity skipped
    coal = retired[1]
    assert coal.retirement_month == (2015, 4)
    assert coal.is_operating_in((2015, 3)) and not coal.is_operating_in((2015, 4))
    assert eia860m.nameplate_mw_by_group(retired, (2012, 1)) == {"Wind": 100.0, "Coal": 600.0}


def test_area_keys():
    rows = [HEADER, [1, "MN", "MISO", "W1", 100, "Onshore Wind Turbine", 6, 2010, "", "", 45, -95]]
    units = eia860m.units_from_rows(rows, is_retired_sheet=False)
    totals = eia860m.nameplate_mw_by_group(units, (2011, 1), area_by_unit={units[0]: "MINN"})
    assert totals == {("MINN", "Wind"): 100.0}


def test_holdout_months_refused():
    with pytest.raises(eia860m.HoldoutMonthRefusedError):
        eia860m.nameplate_mw_by_group([], (2025, 10))
    assert eia860m.nameplate_mw_by_group([], (2025, 9)) == {}
    assert eia860m.nameplate_mw_by_group([], (2025, 10), holdout_permission=object()) == {}


def test_real_fleet_matches_briefing():
    # CLAUDE.md §7.8 (Claude Science, from an earlier monthly file). Coal, wind and solar
    # agree to 0.1 GW; gas is 0.7 GW lower in every month (`round28_answers.md` §4).
    paths = sorted(WORKBOOK_DIRECTORY.glob("*.xlsx"))
    if not paths:
        pytest.skip("no EIA-860M workbook in data/raw/series (run tools/fetch_series.py)")
    units = eia860m.read_units(paths[-1])

    def gigawatts(month):
        totals = eia860m.nameplate_mw_by_group(units, month)
        return {group: round(megawatts / 1000, 1) for group, megawatts in totals.items()}

    april_2005 = gigawatts((2005, 4))
    january_2015 = gigawatts((2015, 1))
    assert (april_2005["Coal"], april_2005["Wind"]) == (71.1, 1.3)
    assert (january_2015["Coal"], january_2015["Wind"], january_2015["Solar"]) == (73.8, 14.3, 0.1)
    assert april_2005["Natural Gas"] == pytest.approx(79.3 - 0.7, abs=0.05)
    assert january_2015["Natural Gas"] == pytest.approx(83.9 - 0.7, abs=0.05)
