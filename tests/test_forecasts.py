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
    # The example issue (06:01 CST on 2005-04-01) serves decision day 2005-04-01, whose
    # targets are 04-02 (the operating day) and 04-03.
    decision_day = datetime.date(2005, 4, 1)
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
    assert [row["target_day"] for row in minneapolis] == ["2005-04-02", "2005-04-03"]
    operating_day = minneapolis[0]
    # The trimmed example has the 04-02 morning low (28 °F) but not its evening high.
    assert operating_day["min_temp_degf"] == 28.0 and operating_day["max_temp_degf"] == ""
    # 00, 03, … 18 CST on 04-02 carry 3-hourly values: 7 columns.
    assert operating_day["three_hour_columns"] == 7
    assert operating_day["cloud_codes"] == "FW SC SC SC SC SC SC"
    assert minneapolis[1]["three_hour_columns"] == 0


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


def test_issue_time_outside_the_window_is_marked_not_repaired(tmp_path):
    decision_day = datetime.date(2005, 4, 1)
    typo_product = MINNEAPOLIS_PRODUCT.replace("APR 1 2005", "APR 1 4305")
    write_issue(tmp_path, "MPX", decision_day, typo_product)
    rows = forecasts.forecast_rows_for_decision_day(tmp_path, decision_day)
    minneapolis = [row for row in rows if row["hub"] == "MINN.HUB"]
    assert {row["status"] for row in minneapolis} == {"bad issue time"}
    assert all(row["max_temp_degf"] == "" for row in minneapolis)
