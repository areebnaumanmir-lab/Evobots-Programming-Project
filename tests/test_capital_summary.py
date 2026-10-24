"""capital_summary against capital_sizing.md §10 (the explorer's expected values)."""

import pytest

from evobots.cli import calibration_capital_summary
from evobots.config.capital import CapitalSettings

# (capital, share of cap used, fixed cost per cleared MWh at share 0.72, worst 20 days with
#  full-sample sizing, ruin floor, headroom, worst 20 days point-in-time); §10's table.
SECTION_10_ROWS = [
    (1_500_000, 1.000, 0.203, 0.323, 1_000_000, 0.333, 0.246),
    (1_050_000, 0.753, 0.270, 0.347, 700_000, 0.333, 0.345),
    (5_000_000, 1.000, 0.203, 0.097, 3_333_333, 0.333, 0.082),
]


@pytest.mark.parametrize("row", SECTION_10_ROWS, ids=lambda row: f"{row[0]:,}")
def test_section_10_explorer_values(row):
    capital, scale, cost, worst_full, floor, headroom, worst_pit = row
    settings = CapitalSettings(starting_capital_usd=capital, ruin_floor_fraction=2 / 3)
    summary = calibration_capital_summary(settings, cleared_share_fraction=0.72)
    assert summary["position_scale_fraction"] == pytest.approx(scale, abs=5e-4)
    assert summary["fixed_cost_usd_per_cleared_mwh"] == pytest.approx(cost, abs=5e-4)
    assert summary["worst_20_day_loss_full_sample_fraction"] == pytest.approx(worst_full, abs=5e-4)
    assert summary["ruin_floor_usd"] == pytest.approx(floor, abs=1)
    assert summary["headroom_fraction"] == pytest.approx(headroom, abs=5e-4)
    assert summary["worst_20_day_loss_point_in_time_fraction"] == pytest.approx(worst_pit, abs=5e-4)
    assert summary["full_size_mwh_per_day"] == 936


# §10 prints $0.195 at $1.05M; the formula gives 50,000 / (0.75277 × 341,640) = $0.1944, and
# §10's own $0.270 at share 0.72 needs $0.1944 (0.195 / 0.72 = 0.271). Recorded in round 23.
@pytest.mark.parametrize(
    ("capital", "expected_cost"), [(1_500_000, 0.146), (5_000_000, 0.146), (1_050_000, 0.1944)]
)
def test_fixed_cost_at_cleared_share_one(capital, expected_cost):
    summary = calibration_capital_summary(
        CapitalSettings(starting_capital_usd=capital), cleared_share_fraction=1.0
    )
    assert summary["fixed_cost_usd_per_cleared_mwh"] == pytest.approx(expected_cost, abs=5e-4)


def test_section_10_warnings():
    def warnings_at(capital):
        settings = CapitalSettings(starting_capital_usd=capital, ruin_floor_fraction=2 / 3)
        return calibration_capital_summary(settings)["warnings"]

    assert warnings_at(1_500_000) == []
    at_1_05 = warnings_at(1_050_000)
    assert len(at_1_05) == 1 and at_1_05[0].startswith("The floor leaves 33.3%")
    at_5 = warnings_at(5_000_000)
    assert len(at_5) == 2
    assert "only 8.2%" in at_5[0]
    assert "full-size point" in at_5[1]


def test_no_floor_means_no_headroom():
    summary = calibration_capital_summary(CapitalSettings())
    assert summary["ruin_floor_usd"] is None and summary["headroom_fraction"] is None
    assert summary["collateral_at_full_size_usd"] == 22_464
