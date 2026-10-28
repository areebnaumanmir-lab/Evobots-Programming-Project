"""Tests for the hub forecast table (`evobots.data.forecasts`)."""

import datetime

from evobots.data import forecasts, visible
from evobots.data.sources.nws_pfm import EXAMPLE_PRODUCT

# The parser's example issue, moved to Minneapolis's zone and name so MINN.HUB finds it.
MINNEAPOLIS_PRODUCT = EXAMPLE_PRODUCT.replace("MNZ041", "MNZ060").replace(
    "ALEXANDRIA-DOUGLAS MN", "MINNEAPOLIS-HENNEPIN MN"
)


def write_issue(raw_directory, office, decision_day, text):
    folder = raw_directory / office
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{decision_day:%Y%m%d}.txt").write_text(text, encoding="utf-8")


def test_statuses_and_values(tmp_path):
    decision_day = datetime.date(2005, 3, 31)
    write_issue(tmp_path, "MPX", decision_day, MINNEAPOLIS_PRODUCT)
    write_issue(tmp_path, "DTX", decision_day, EXAMPLE_PRODUCT)  # Detroit not in it
    write_issue(tmp_path, "IND", decision_day, "ERROR: Could not Find: PFMIND")
    rows = forecasts.forecast_rows_for_decision_day(tmp_path, decision_day)
    status_by_hub = {row["hub"]: row["status"] for row in rows}
    assert status_by_hub["MINN.HUB"] == "ok"
    assert status_by_hub["MICHIGAN.HUB"] == "missing town"
    assert status_by_hub["INDIANA.HUB"] == "unparsed issue"
    assert status_by_hub["TEXAS.HUB"] == "missing file"
    minneapolis = [row for row in rows if row["hub"] == "MINN.HUB"]
    assert [row["target_day"] for row in minneapolis] == ["2005-04-01", "2005-04-02"]
    first = minneapolis[0]
    assert first["max_temp_degf"] == 52.0 and first["min_temp_degf"] == ""
    # Values start at 09 CST (the issue is 06:01 CST); 09–21 CST on 04/01 give 5 columns.
    assert first["three_hour_columns"] == 5
    assert first["cloud_codes"] == "CL CL CL FW FW"
    assert minneapolis[1]["min_temp_degf"] == 28.0


def test_issue_is_before_the_decision_time(tmp_path):
    # The example was issued 2005-04-01 06:01 CST and is stored as decision day 2005-04-01,
    # whose decision time is 10:30 Eastern that day (bids for 2005-04-02).
    decision_day = datetime.date(2005, 4, 1)
    write_issue(tmp_path, "MPX", decision_day, MINNEAPOLIS_PRODUCT)
    rows = forecasts.forecast_rows_for_decision_day(tmp_path, decision_day)
    minneapolis = next(row for row in rows if row["hub"] == "MINN.HUB")
    issued = datetime.datetime.fromisoformat(minneapolis["issued_at_utc"])
    operating_day = decision_day + datetime.timedelta(days=1)
    assert issued <= visible.decision_time(operating_day)


def test_no_target_after_the_evolution_period(tmp_path):
    rows = forecasts.forecast_rows_for_decision_day(tmp_path, datetime.date(2025, 9, 20))
    assert {row["target_day"] for row in rows} == {"2025-09-21"}
    assert forecasts.forecast_rows_for_decision_day(tmp_path, datetime.date(2025, 9, 21)) == []
