"""CapitalSettings: defaults, bounds, caps, collateral, floors, loading, CLI (capital_sizing.md)."""

import csv
from pathlib import Path

import pytest

from evobots.cli import capital_report_lines, main
from evobots.config import load_capital
from evobots.config.capital import (
    HUB_MEDIAN_CLEARED_VIRTUAL_MW,
    CapitalSettings,
    round_to_bid_step_mw,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_defaults_match_the_briefing():
    settings = CapitalSettings()
    assert settings.starting_capital_usd == 1_500_000
    assert settings.daily_risk_budget_fraction == 0.02
    assert settings.credit_share_fraction == 0.25
    assert settings.max_mw_per_hub_hour == 5.0


def test_default_death_has_no_capital_floor():
    # Round 19: the default death is "out of money"; floors are optional.
    settings = CapitalSettings()
    assert settings.effective_ruin_floor_usd() is None
    assert settings.headroom_fraction() == 1.0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("starting_capital_usd", 200_000),
        ("starting_capital_usd", 5_500_000),
        ("daily_risk_budget_fraction", 0.06),
        ("credit_share_fraction", 0.9),
        ("ruin_floor_fraction", 0.95),
    ],
)
def test_out_of_bounds_values_are_rejected(name, value):
    with pytest.raises(ValueError):
        CapitalSettings(**{name: value})


def test_caps_are_five_mw_except_ms_hub():
    caps = CapitalSettings().hub_caps_mw()
    assert caps.pop("MS.HUB") == 4.0
    assert set(caps.values()) == {5.0}


def test_full_size_is_936_not_960_mwh_per_day():
    assert CapitalSettings().full_size_mwh_per_day() == 936


def test_full_size_before_ms_hub_existed_is_840_mwh_per_day():
    hubs_before_2017_12 = [hub for hub in HUB_MEDIAN_CLEARED_VIRTUAL_MW if hub != "MS.HUB"]
    assert CapitalSettings().full_size_mwh_per_day(hubs_before_2017_12) == 840


def test_rounding_to_the_bid_step_rounds_halves_up():
    assert round_to_bid_step_mw(3.95) == 4.0
    assert round_to_bid_step_mw(3.94) == 3.9


def test_volume_constants_equal_the_volume_table():
    with (REPOSITORY_ROOT / "docs/data/hub_volume_stats.csv").open(encoding="utf-8") as table:
        medians = {row["hub"]: float(row["total_MW_median"]) for row in csv.DictReader(table)}
    assert medians == HUB_MEDIAN_CLEARED_VIRTUAL_MW


def test_collateral_at_full_size_is_22464_usd():
    full_size_mwh = CapitalSettings().full_size_mwh_per_day()
    assert full_size_mwh * 12 * 2 == 22_464


def test_virtual_mwh_limit_at_defaults_is_about_15600():
    # capital_sizing.md §7: "about 15,600 MWh/day, 16x more than liquidity allows".
    settings = CapitalSettings()
    assert settings.virtual_mwh_limit() == pytest.approx(15_625)
    assert settings.virtual_mwh_limit() / settings.full_size_mwh_per_day() > 16


def test_mpd_below_the_floor_is_raised_to_12():
    settings = CapitalSettings()
    assert settings.virtual_mwh_limit(4.89) == settings.virtual_mwh_limit(12.0)


@pytest.mark.parametrize(
    ("capital_usd", "floor_usd"),
    [(250_000, 166_667), (1_050_000, 700_000), (1_500_000, 1_000_000), (5_000_000, 3_333_333)],
)
def test_relative_floor_preset(capital_usd, floor_usd):
    settings = CapitalSettings(starting_capital_usd=capital_usd, ruin_floor_fraction=2 / 3)
    assert settings.effective_ruin_floor_usd() == pytest.approx(floor_usd, abs=1)
    assert settings.headroom_fraction() == pytest.approx(1 / 3)


def test_absolute_floor_with_under_10_percent_headroom_is_rejected():
    with pytest.raises(ValueError, match="4.8%"):
        CapitalSettings(starting_capital_usd=1_050_000, ruin_floor_usd=1_000_000)


def test_both_floors_at_once_are_rejected():
    with pytest.raises(ValueError):
        CapitalSettings(ruin_floor_fraction=0.5, ruin_floor_usd=500_000)


def test_headroom_warning_at_1_05m_with_the_relative_floor():
    settings = CapitalSettings(starting_capital_usd=1_050_000, ruin_floor_fraction=2 / 3)
    assert any("storm like Uri" in message for message in settings.warnings())


def test_no_warning_at_the_default():
    assert CapitalSettings().warnings() == []


def test_load_capital_precedence(tmp_path):
    config_path = tmp_path / "capital.toml"
    config_path.write_text(
        "[capital]\nstarting_capital_usd = 2_000_000\ndaily_risk_budget_fraction = 0.01\n"
    )
    settings = load_capital(
        config_path, {"starting_capital_usd": 3_000_000, "ruin_floor_usd": None}
    )
    assert settings.starting_capital_usd == 3_000_000
    assert settings.daily_risk_budget_fraction == 0.01


def test_load_capital_rejects_unknown_keys(tmp_path):
    config_path = tmp_path / "capital.toml"
    config_path.write_text("[capital]\nstarting_capital = 2_000_000\n")
    with pytest.raises(ValueError, match="unknown"):
        load_capital(config_path)


def test_shipped_config_loads_to_the_defaults():
    assert load_capital(REPOSITORY_ROOT / "configs/10_miso_hubs.toml") == CapitalSettings()


def test_cli_prints_936_and_never_960(capsys):
    main(["capital", str(REPOSITORY_ROOT / "configs/10_miso_hubs.toml")])
    output = capsys.readouterr().out
    assert "936 MWh per day" in output
    assert "960" not in output
    assert "$22,464" in output


def test_report_lines_mention_out_of_money_by_default():
    assert "Death: out of money (no capital floor set)" in capital_report_lines(CapitalSettings())
