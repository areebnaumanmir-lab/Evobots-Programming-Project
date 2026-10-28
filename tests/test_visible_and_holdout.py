"""Tests for point-in-time access (`evobots.data.visible`) and the hold-out accessor.

The look-ahead test (`CLAUDE.md` §6.4): change every observation that became public after a
decision time, add new ones, and check that nothing visible at that time changes.
"""

import datetime
import random
from pathlib import Path

import pytest

from evobots.data import holdout, visible
from evobots.sizing import NEWEST_VISIBLE_LAG_DAYS

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "evobots"
# Modules allowed to import the hold-out accessor: itself and the final-test path (M7).
HOLDOUT_IMPORT_ALLOWLIST = {"data/holdout.py", "final_test.py"}


def test_decision_sees_yesterdays_day_ahead_but_not_todays():
    operating_day = datetime.date(2022, 12, 23)
    at_time = visible.decision_time(operating_day)
    assert visible.day_ahead_available_at(operating_day) > at_time
    assert visible.day_ahead_available_at(operating_day - datetime.timedelta(days=1)) <= at_time


def test_newest_final_real_time_day_matches_sizing_rule():
    operating_day = datetime.date(2021, 2, 18)
    at_time = visible.decision_time(operating_day)
    newest = operating_day - datetime.timedelta(days=NEWEST_VISIBLE_LAG_DAYS)
    assert visible.real_time_final_available_at(newest) <= at_time
    assert visible.real_time_final_available_at(newest + datetime.timedelta(days=1)) > at_time


def test_decision_time_follows_daylight_saving():
    winter = visible.decision_time(datetime.date(2024, 1, 16))
    summer = visible.decision_time(datetime.date(2024, 7, 16))
    assert winter.utcoffset() == datetime.timedelta(hours=-5)
    assert summer.utcoffset() == datetime.timedelta(hours=-4)
    assert (winter.hour, winter.minute) == (summer.hour, summer.minute) == (10, 30)


def test_series_lags():
    friday = datetime.date(2024, 7, 12)
    gas = visible.series_available_at("henry_hub_usd_per_mmbtu", friday)
    assert gas.date() == datetime.date(2024, 7, 15)  # next business day: Monday
    epu = visible.series_available_at("epu_index", friday)
    assert epu.date() == datetime.date(2024, 7, 14)  # two calendar days: posting time unknown
    bill = visible.series_available_at("treasury_bill_3_month_discount_fraction", friday)
    assert bill.date() == datetime.date(2024, 7, 16)  # second business day: posted afternoons


def test_visible_refuses_naive_times():
    column = visible.Column.from_observations("x", "unit", [])
    with pytest.raises(ValueError):
        visible.visible(column, datetime.datetime(2024, 1, 1, 10, 30))


def random_column(generator, observation_count):
    """A column of random observations spread over 2020."""
    start = datetime.datetime(2020, 1, 1, tzinfo=visible.EASTERN)
    observations = [
        (
            index,
            start + datetime.timedelta(minutes=generator.randrange(366 * 24 * 60)),
            generator.random(),
        )
        for index in range(observation_count)
    ]
    return visible.Column.from_observations("random", "unit", observations), observations


def test_look_ahead_changing_the_future_changes_nothing_visible():
    generator = random.Random(20261028)
    column, observations = random_column(generator, 500)
    for _ in range(50):
        at_time = datetime.datetime(2020, 1, 1, tzinfo=visible.EASTERN) + datetime.timedelta(
            minutes=generator.randrange(366 * 24 * 60)
        )
        before = visible.visible(column, at_time)
        future_changed = [
            (key, moment, value if moment <= at_time else generator.random() * 1000)
            for key, moment, value in observations
        ] + [(10_000 + index, at_time + datetime.timedelta(seconds=1), -1.0) for index in range(5)]
        changed_column = visible.Column.from_observations("random", "unit", future_changed)
        after = visible.visible(changed_column, at_time)
        assert after == before
        assert all(moment <= at_time for moment in before.available_at)
        hidden = [key for key, moment, _ in observations if moment > at_time]
        assert not set(hidden) & set(before.keys)


def test_holdout_permission_only_from_open_holdout(tmp_path):
    with pytest.raises(PermissionError):
        holdout.HoldoutPermission("R1", "R1-1", "me", datetime.datetime.now(datetime.UTC))
    log_path = tmp_path / "access.jsonl"
    assert holdout.holdout_status(log_path) == "Sealed: never opened"
    permission = holdout.open_holdout("R7", "R7-123", "test", log_path)
    assert permission.trader_id == "R7-123"
    openings = holdout.holdout_openings(log_path)
    assert [opening["run_id"] for opening in openings] == ["R7"]
    assert "R7-123 in R7" in holdout.holdout_status(log_path)


def test_committed_access_log_says_sealed():
    # The hold-out has never been opened (CLAUDE.md §2.2). This fails, on purpose, the day
    # it is: update it then with the run and trader that were tested.
    repository_log = Path(__file__).resolve().parents[1] / holdout.ACCESS_LOG_PATH
    assert holdout.holdout_status(repository_log) == "Sealed: never opened"


def test_only_the_final_test_path_imports_the_holdout_accessor():
    offenders = []
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        imports_it = "evobots.data.holdout" in text or "from evobots.data import holdout" in text
        if imports_it and relative not in HOLDOUT_IMPORT_ALLOWLIST:
            offenders.append(relative)
    assert offenders == []


def test_only_the_accessor_names_the_holdout_folder():
    offenders = [
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*.py")
        if "data/holdout" in path.read_text(encoding="utf-8")
        and path.relative_to(SOURCE_ROOT).as_posix() not in HOLDOUT_IMPORT_ALLOWLIST
    ]
    assert offenders == []
