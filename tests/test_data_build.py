"""Tests for the Stage A builder (`evobots.data.build`) on a two-day hand-made archive.

The full build on the real archive is checked by running `evobots data build --stage A`
(round 28: every value of hub_price_stats.csv and hub_volume_stats.csv agrees).
"""

import csv
import datetime
import gzip

import numpy as np
import pytest

from evobots import cli
from evobots.data import build

HOUR_HEADER = ",".join(f"HE {hour}" for hour in range(1, 25))


def daily_file_text(title, hub_start, loadzone_start):
    """A 2023-era daily LMP file: preamble, header with Value, one hub with components."""
    hub_hours = ",".join(str(hub_start + hour) for hour in range(24))
    component_hours = ",".join("1" for _ in range(24))
    loadzone_hours = ",".join(str(loadzone_start) for _ in range(24))
    return (
        f"{title}\n01/02/2023\n\n,,,All Hours-Ending are Eastern Standard Time (EST)\n"
        f"Node,Type,Value,{HOUR_HEADER}\n"
        f"MINN.HUB,Hub,LMP,{hub_hours}\n"
        f"MINN.HUB,Hub,MCC,{component_hours}\n"
        f"MINN.HUB,Hub,MLC,{component_hours}\n"
        f"ALTW.ALTW,Loadzone,LMP,{loadzone_hours}\n"
    )


@pytest.fixture
def raw_directory(tmp_path):
    directory = tmp_path / "raw"
    directory.mkdir()
    for day in ("20230102", "20230103"):
        (directory / f"{day}_da_expost_lmp.csv").write_text(
            daily_file_text("Day Ahead Market ExPost LMPs", 30, 20), encoding="utf-8"
        )
    # RT for 2023-01-03 is missing on purpose: it must stay missing, never filled.
    (directory / "20230102_rt_lmp_final.csv").write_text(
        daily_file_text("Real-Time Market LMPs", 28, 20), encoding="utf-8"
    )
    return directory


def test_hub_rows_keep_hubs_only_and_missing_markets_missing(raw_directory, tmp_path):
    output_path = tmp_path / "store" / "hub_prices.csv.gz"
    row_count = build.build_hub_prices(
        raw_directory,
        output_path,
        datetime.date(2023, 1, 2),
        datetime.date(2023, 1, 3),
        worker_count=1,
    )
    assert row_count == 48
    with gzip.open(output_path, "rt", encoding="utf-8") as table:
        rows = list(csv.DictReader(table))
    assert {row["hub"] for row in rows} == {"MINN.HUB"}
    first = rows[0]
    assert (first["date"], first["hour_ending_est"]) == ("2023-01-02", "1")
    assert (first["da_lmp"], first["rt_lmp"], first["da_mcc"]) == ("30", "28", "1")
    second_day = [row for row in rows if row["date"] == "2023-01-03"]
    assert all(row["rt_lmp"] == "" and row["da_lmp"] for row in second_day)
    spreads = build.read_hub_spreads(
        output_path, datetime.date(2023, 1, 1), datetime.date(2023, 1, 31)
    )
    day_ahead, real_time = spreads["MINN.HUB"]
    assert len(day_ahead) == 24  # only hours with both markets
    assert np.allclose(day_ahead - real_time, 2.0)


def test_build_refuses_holdout_days(raw_directory, tmp_path):
    from evobots.data.sources.miso_eras import HoldoutRefusedError

    with pytest.raises(HoldoutRefusedError):
        build.build_hub_prices(
            raw_directory,
            tmp_path / "out.csv.gz",
            datetime.date(2025, 9, 21),
            datetime.date(2025, 9, 22),
            worker_count=1,
        )


def test_comparison_reports_each_difference(tmp_path):
    reference = tmp_path / "reference.csv"
    reference.write_text("hub,spread_mean,hours\nMINN.HUB,0.431,10\n", encoding="utf-8")
    agreeing, disagreements = build.compare_with_reference(
        {"MINN.HUB": {"spread_mean": 0.4312, "hours": 11}}, reference
    )
    assert agreeing == 1
    assert disagreements == ["MINN.HUB hours: 11 vs 10"]


def test_volume_sample_days():
    days = build.volume_sample_days()
    assert (days[0], days[-1], len(days)) == (
        datetime.date(2023, 1, 15),
        datetime.date(2025, 9, 15),
        33,
    )


def test_cli_later_stages_not_built_yet(capsys):
    assert cli.main(["data", "build", "--stage", "D"]) == 1
    assert "M8" in capsys.readouterr().out
