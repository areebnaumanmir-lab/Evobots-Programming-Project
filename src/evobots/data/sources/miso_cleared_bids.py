"""Cleared virtual bids at the trading hubs, from MISO's cleared-bids report (2023 onward).

MISO's `{YYYYMMDD}_bids_cb.zip` lists every virtual bid-hour: an anonymous participant code, the
hour, the cleared MW, the cleared price, the side ("D" = DEC, "I" = INC; "F" and "P" rows also
exist and are not virtuals at a node in this sense), up to nine price/MW blocks and a Region. It
has no location field. A bid is attributed to a trading hub when (capital_sizing.md §2):

1. its Region is blank (every hub-matched bid has one: hubs span regions);
2. its price equals, to the cent, the hub's DA **ex-ante** LMP for that hour (the report's
   price is the ex-ante one: on 2024-06-15 all cleared bids matched an ex-ante price);
3. no other location has that same price in that hour. Hub-hours that share their price with
   another location are **unobservable** and left out, not counted as zero.

This reproduces `docs/data/hub_volume_stats.csv` exactly on its 33 sample days, the 15th of
each month 2023-01 → 2025-09 (obs., round 26: all 72 values).

Maths: docs/maths.md §1.2 uses the medians for the liquidity cap.
"""

import collections
import csv
import io
import zipfile
from dataclasses import dataclass

import numpy as np

from evobots.data.sources.miso_eras import parse_lmp_csv

# Sides counted as virtual volume: DEC (virtual demand) and INC (virtual supply).
VIRTUAL_SIDES = ("D", "I")
# The report's timestamps look like "01/15/2023 00:00:00"; the hour starts at character 11.
HOUR_START_CHARACTER = 11


@dataclass(frozen=True)
class HubHourVolume:
    """Cleared virtual volume at one trading hub in one observable hour.

    Attributes:
        hub: the trading hub's name, e.g. "MINN.HUB".
        hour_ending: 1–24, Eastern Standard Time.
        dec_mw: cleared DEC MW attributed to the hub.
        inc_mw: cleared INC MW attributed to the hub.
        participant_count: distinct anonymous participant codes among those bids.
    """

    hub: str
    hour_ending: int
    dec_mw: float
    inc_mw: float
    participant_count: int

    @property
    def total_mw(self):
        """DEC plus INC cleared MW."""
        return self.dec_mw + self.inc_mw


def observable_hub_prices(exante_prices):
    """{(hub, hour index 0–23): price rounded to the cent} for hub-hours with a unique price.

    Args:
        exante_prices: a DailyPrices parsed from `{YYYYMMDD}_da_exante_lmp.csv`.

    Returns:
        The hub-hours whose ex-ante LMP no other location shares that hour.
    """
    lmp_by_location = {
        name: hours
        for (name, value_type), hours in exante_prices.hours_by_location_and_value.items()
        if value_type == "LMP"
    }
    observable = {}
    for hour_index in range(24):
        price_counts = collections.Counter(
            round(hours[hour_index], 2)
            for hours in lmp_by_location.values()
            if hours[hour_index] is not None
        )
        for hub in exante_prices.trading_hubs():
            price = lmp_by_location[hub][hour_index]
            if price is not None and price_counts[round(price, 2)] == 1:
                observable[(hub, hour_index)] = round(price, 2)
    return observable


def hub_hour_volumes(cleared_bid_rows, exante_prices):
    """Attribute one day's cleared virtual bids to the trading hubs.

    Args:
        cleared_bid_rows: dicts with the report's columns ("Region", "Market Participant
            Code", "Date/Time Beginning (EST)", "MW", "LMP", "Type of Bid", …).
        exante_prices: the same day's DailyPrices from the DA ex-ante file.

    Returns:
        A HubHourVolume for every observable hub-hour, including those with no attributed bid
        (zero MW), sorted by hub then hour.
    """
    observable = observable_hub_prices(exante_prices)
    hub_by_hour_and_price = {
        (hour_index, price): hub for (hub, hour_index), price in observable.items()
    }
    totals = {key: [0.0, 0.0, set()] for key in observable}
    for row in cleared_bid_rows:
        side = row["Type of Bid"]
        if row["Region"] or side not in VIRTUAL_SIDES:
            continue
        cleared_mw = float(row["MW"] or 0)
        if cleared_mw <= 0:
            continue
        timestamp = row["Date/Time Beginning (EST)"]
        hour_index = int(timestamp[HOUR_START_CHARACTER : HOUR_START_CHARACTER + 2])
        hub = hub_by_hour_and_price.get((hour_index, round(float(row["LMP"]), 2)))
        if hub is None:
            continue
        total = totals[(hub, hour_index)]
        total[0 if side == "D" else 1] += cleared_mw
        total[2].add(row["Market Participant Code"])
    return [
        HubHourVolume(hub, hour_index + 1, dec_mw, inc_mw, len(participants))
        for (hub, hour_index), (dec_mw, inc_mw, participants) in sorted(totals.items())
    ]


def read_day_volumes(cleared_bids_zip_path, exante_csv_path, operating_day):
    """hub_hour_volumes for one day, read from the two downloaded files.

    Args:
        cleared_bids_zip_path: path of `{YYYYMMDD}_bids_cb.zip`.
        exante_csv_path: path of `{YYYYMMDD}_da_exante_lmp.csv`.
        operating_day: the day (a datetime.date).

    Returns:
        A list of HubHourVolume.
    """
    with open(exante_csv_path, encoding="utf-8", errors="replace") as exante_file:
        exante_prices = parse_lmp_csv(exante_file.read(), operating_day, "da", str(exante_csv_path))
    with zipfile.ZipFile(cleared_bids_zip_path) as archive:
        member = archive.namelist()[0]
        with archive.open(member) as raw_file:
            rows = csv.DictReader(io.TextIOWrapper(raw_file, encoding="utf-8", errors="replace"))
            return hub_hour_volumes(rows, exante_prices)


def hub_volume_statistics(volumes, sample_hour_count):
    """The columns of docs/data/hub_volume_stats.csv for each hub.

    Args:
        volumes: HubHourVolume records over the sample days.
        sample_hour_count: hub-hours in the sample (days × 24), for the observable share.

    Returns:
        {hub: dict with observable_hub_hours, observable_share, total_mw_p10, total_mw_median,
        total_mw_p90, dec_mw_median, inc_mw_median, participants_median}. Percentiles use
        linear interpolation (NumPy's default), which reproduces the recorded values.
    """
    volumes_by_hub = collections.defaultdict(list)
    for volume in volumes:
        volumes_by_hub[volume.hub].append(volume)
    statistics = {}
    for hub, hub_volumes in sorted(volumes_by_hub.items()):
        total_mw = np.array([volume.total_mw for volume in hub_volumes])
        statistics[hub] = {
            "observable_hub_hours": len(hub_volumes),
            "observable_share": len(hub_volumes) / sample_hour_count,
            "total_mw_p10": float(np.percentile(total_mw, 10)),
            "total_mw_median": float(np.median(total_mw)),
            "total_mw_p90": float(np.percentile(total_mw, 90)),
            "dec_mw_median": float(np.median([volume.dec_mw for volume in hub_volumes])),
            "inc_mw_median": float(np.median([volume.inc_mw for volume in hub_volumes])),
            "participants_median": float(
                np.median([volume.participant_count for volume in hub_volumes])
            ),
        }
    return statistics
