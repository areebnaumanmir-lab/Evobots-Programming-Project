"""Hub attribution of cleared virtual bids, on a hand-made day."""

import datetime

import pytest

from evobots.data.sources.miso_cleared_bids import (
    hub_hour_volumes,
    hub_volume_statistics,
    observable_hub_prices,
)
from evobots.data.sources.miso_eras import parse_lmp_csv

HOUR_HEADER = ",".join(f"HE {hour}" for hour in range(1, 25))
DAY = datetime.date(2023, 1, 15)


def price_row(name, location_type, first_two_hours):
    rest = ",".join(["50"] * 22)
    return f"{name},{location_type},LMP,{first_two_hours[0]},{first_two_hours[1]},{rest}\n"


# Hour 1: MINN.HUB 20.00 unique, INDIANA.HUB 30.00 shared with a generator (unobservable).
# Hour 2: both unique. Hours 3–24: everyone at 50, so nothing is observable.
EXANTE_TEXT = (
    "Day Ahead Market ExAnte LMPs\n01/15/2023\n\n"
    f"Node,Type,Value,{HOUR_HEADER}\n"
    + price_row("MINN.HUB", "Hub", (20.0, 21.0))
    + price_row("INDIANA.HUB", "Hub", (30.0, 31.0))
    + price_row("GEN.ONE", "Gennode", (30.0, 25.0))
)


def bid(hour, side, mw, price, participant="A", region=""):
    return {
        "Region": region,
        "Market Participant Code": participant,
        "Date/Time Beginning (EST)": f"01/15/2023 {hour:02d}:00:00",
        "MW": str(mw),
        "LMP": str(price),
        "Type of Bid": side,
    }


def test_observable_hub_hours():
    observable = observable_hub_prices(parse_lmp_csv(EXANTE_TEXT, DAY, "da"))
    assert observable == {("MINN.HUB", 0): 20.0, ("MINN.HUB", 1): 21.0, ("INDIANA.HUB", 1): 31.0}


def test_attribution_rules():
    rows = [
        bid(0, "D", 5, 20.0, "A"),
        bid(0, "I", 2.5, 20.004, "B"),  # same price to the cent
        bid(0, "D", 7, 20.0, "C", region="North"),  # a Region: not a hub bid
        bid(0, "F", 9, 20.0, "D"),  # not a virtual side
        bid(0, "D", 0, 20.0, "E"),  # not cleared
        bid(0, "D", 4, 30.0, "F"),  # INDIANA hour 1 is unobservable
        bid(1, "I", 3, 31.0, "A"),
    ]
    volumes = hub_hour_volumes(rows, parse_lmp_csv(EXANTE_TEXT, DAY, "da"))
    by_key = {(volume.hub, volume.hour_ending): volume for volume in volumes}
    assert set(by_key) == {("MINN.HUB", 1), ("MINN.HUB", 2), ("INDIANA.HUB", 2)}
    minn_first = by_key[("MINN.HUB", 1)]
    assert (minn_first.dec_mw, minn_first.inc_mw, minn_first.participant_count) == (5, 2.5, 2)
    assert by_key[("MINN.HUB", 2)].total_mw == 0  # observable with no bid counts as zero
    assert by_key[("INDIANA.HUB", 2)].inc_mw == 3


def test_statistics_columns():
    rows = [bid(0, "D", 10, 20.0), bid(1, "I", 30, 21.0), bid(1, "I", 4, 31.0)]
    volumes = hub_hour_volumes(rows, parse_lmp_csv(EXANTE_TEXT, DAY, "da"))
    statistics = hub_volume_statistics(volumes, sample_hour_count=24)
    minn = statistics["MINN.HUB"]
    assert minn["observable_hub_hours"] == 2
    assert minn["observable_share"] == pytest.approx(2 / 24)
    assert minn["total_mw_median"] == 20.0
    assert minn["total_mw_p10"] == pytest.approx(12.0)
