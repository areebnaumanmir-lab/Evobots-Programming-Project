"""The MISO era reader on hand-made files of each era, plus the real archive when present."""

import datetime
import zipfile
from pathlib import Path

import pytest

from evobots.data.sources.miso_eras import (
    HoldoutRefusedError,
    days_in_file,
    file_and_member_for,
    parse_lmp_csv,
    read_day,
)

HOUR_HEADER = ",".join(f"HE {hour}" for hour in range(1, 25))
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = REPOSITORY_ROOT / "data/raw/miso"


def hours(start):
    return ",".join(str(start + hour) for hour in range(24))


EARLY_ERA_TEXT = (  # 2005 style: no Value column, names and types padded
    "Day Ahead Market LMPs\n04/01/2005\n\n"
    f"Node,Type,{HOUR_HEADER}\n"
    f"MINN.HUB      ,Hub      ,{hours(30)}\n"
    f"ALTW.ALTW     ,Loadzone ,{hours(20)}\n"
)
LATER_ERA_TEXT = (  # 2015+ style: preamble, Value column, components, a blank-name line
    "Day Ahead Market ExPost LMPs\n03/01/2015\n\n"
    ",,,All Hours-Ending are Eastern Standard Time (EST)\n"
    f"Node,Type,Value,{HOUR_HEADER}\n"
    f"INDIANA.HUB,Hub,LMP,{hours(40)}\n"
    f"INDIANA.HUB,Hub,MCC,{hours(1)}\n"
    f"INDIANA.HUB,Hub,MLC,{hours(-2)}\n"
    f"AMIL.BGS6,Gennode,LMP,{','.join([''] + [str(hour) for hour in range(23)])}\n"
    f",,LMP,{hours(0)}\n"
    f"ARKANSAS.HUB,Hub,XYZ,{hours(0)}\n"
)


def test_early_era_without_value_column():
    prices = parse_lmp_csv(EARLY_ERA_TEXT, datetime.date(2005, 4, 1), "da", "test")
    assert prices.trading_hubs() == ["MINN.HUB"]
    assert prices.type_by_location == {"MINN.HUB": "Hub", "ALTW.ALTW": "Loadzone"}
    assert prices.hours_by_location_and_value[("MINN.HUB", "LMP")][23] == 53.0
    assert not prices.has_components


def test_later_era_with_components_and_quirks():
    prices = parse_lmp_csv(LATER_ERA_TEXT, datetime.date(2015, 3, 1), "da")
    values = prices.hours_by_location_and_value
    assert prices.has_components
    assert values[("INDIANA.HUB", "MLC")][0] == -2.0
    assert values[("AMIL.BGS6", "LMP")][0] is None  # an empty hour stays missing
    assert "" not in prices.type_by_location  # the blank-name line is skipped
    assert ("ARKANSAS.HUB", "XYZ") not in values  # unknown value types are ignored
    assert prices.trading_hubs() == ["INDIANA.HUB"]


def test_missing_header_is_an_error():
    with pytest.raises(ValueError, match="no header"):
        parse_lmp_csv("nothing here\n", datetime.date(2005, 4, 1), "da")


@pytest.mark.parametrize(
    ("day", "market", "expected"),
    [
        ("2005-04-01", "da", ("200504_da_lmp_csv.zip", "20050401_da_lmp.csv")),
        ("2015-02-19", "da", ("201502_da_lmp_csv.zip", "20150219_da_lmp.csv")),
        ("2015-02-28", "da", ("201502_da_lmp_csv.zip", "20150228_da_lmp.csv")),
        ("2015-03-01", "da", ("201503_da_expost_lmp_csv.zip", "20150301_da_expost_lmp.csv")),
        ("2015-02-19", "rt", ("201502_rt_lmp_final_csv.zip", "20150219_rt_lmp_final.csv")),
        ("2022-12-31", "da", ("202212_da_expost_lmp_csv.zip", "20221231_da_expost_lmp.csv")),
        ("2023-01-01", "da", ("20230101_da_expost_lmp.csv", None)),
        ("2025-09-21", "rt", ("20250921_rt_lmp_final.csv", None)),
    ],
)
def test_file_dispatch_by_era(day, market, expected):
    assert file_and_member_for(datetime.date.fromisoformat(day), market) == expected


def test_unknown_market_is_an_error():
    with pytest.raises(ValueError, match="market"):
        file_and_member_for(datetime.date(2010, 1, 1), "fx")


def test_read_day_from_zip_and_csv(tmp_path):
    with zipfile.ZipFile(tmp_path / "200504_da_lmp_csv.zip", "w") as archive:
        archive.writestr("20050401_da_lmp.csv", EARLY_ERA_TEXT)
    (tmp_path / "20230101_da_expost_lmp.csv").write_text(LATER_ERA_TEXT)
    early = read_day(tmp_path, datetime.date(2005, 4, 1), "da")
    assert early.source == "200504_da_lmp_csv.zip/20050401_da_lmp.csv"
    later = read_day(tmp_path, datetime.date(2023, 1, 1), "da")
    assert later.trading_hubs() == ["INDIANA.HUB"]
    assert read_day(tmp_path, datetime.date(2005, 4, 2), "da") is None  # member missing
    assert read_day(tmp_path, datetime.date(2010, 1, 1), "da") is None  # file missing
    assert [entry[:2] for entry in days_in_file(tmp_path / "200504_da_lmp_csv.zip")] == [
        (datetime.date(2005, 4, 1), "da")
    ]


def test_holdout_day_is_refused_without_permission(tmp_path):
    with pytest.raises(HoldoutRefusedError):
        read_day(tmp_path, datetime.date(2026, 2, 28), "da")


@pytest.mark.skipif(not RAW_DIRECTORY.exists(), reason="downloaded MISO archive not present")
def test_real_archive_2015_02_19_uses_the_da_lmp_file():
    # Round 26: the old-style file agrees with that day's real-time prices; the ex-post one
    # does not (MINN.HUB daily mean DA 68.7 vs RT 71.2; ex-post file 30.9).
    prices = read_day(RAW_DIRECTORY, datetime.date(2015, 2, 19), "da")
    minn = [value for value in prices.hours_by_location_and_value[("MINN.HUB", "LMP")]]
    assert round(sum(minn) / 24, 1) == 68.7
