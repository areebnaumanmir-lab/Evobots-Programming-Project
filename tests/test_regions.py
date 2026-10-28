"""Tests for the hub areas (`evobots.data.regions`, decided in round 28)."""

import pytest

from evobots.config.capital import STAGE_A_HUBS
from evobots.data import regions


def test_every_hub_has_a_forecast_town():
    assert sorted(regions.FORECAST_TOWN_BY_HUB) == sorted(STAGE_A_HUBS)


def test_each_town_is_in_its_own_area():
    for hub, town in regions.FORECAST_TOWN_BY_HUB.items():
        assert regions.nearest_hub(town.latitude_degrees, town.longitude_degrees) == hub


def test_town_identity_ignores_case_and_county_suffix():
    beaumont = regions.FORECAST_TOWN_BY_HUB["TEXAS.HUB"]
    # The county part of the printed name changed over the years (obs., round 28).
    assert beaumont.is_town("TXZ215", "BEAUMONT-TEXAS TX")
    assert beaumont.is_town("TXZ215", "Beaumont-Jefferson TX")
    assert not beaumont.is_town("TXZ216", "BEAUMONT-TEXAS TX")


@pytest.mark.parametrize(
    ("latitude", "longitude", "hub"),
    [
        (46.88, -96.79, "MINN.HUB"),  # Fargo ND
        (41.59, -93.62, "ILLINOIS.HUB"),  # Des Moines IA: 345 km from Peoria, 367 from Minneapolis
        (38.63, -90.20, "ILLINOIS.HUB"),  # St Louis MO (Ameren Missouri)
        (37.97, -87.57, "INDIANA.HUB"),  # Evansville IN
        (30.45, -91.19, "LOUISIANA.HUB"),  # Baton Rouge LA
        (30.23, -93.22, "TEXAS.HUB"),  # Lake Charles LA: nearer Beaumont than New Orleans
    ],
)
def test_nearest_hub_examples(latitude, longitude, hub):
    assert regions.nearest_hub(latitude, longitude) == hub


def test_great_circle_known_distance():
    # One degree of longitude on the equator is 2πR/360 = 111.19 km.
    assert regions.great_circle_kilometres(0, 0, 0, 1) == pytest.approx(111.195, abs=0.001)
