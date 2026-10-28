"""Read MISO's day-ahead and real-time LMP files from every era into one normalised form.

MISO has published its price archive in three file eras (CLAUDE.md §7.3, obs. round 20):

    2005-04 → 2015-02   monthly zips {YYYYMM}_da_lmp_csv.zip, {YYYYMM}_rt_lmp_final_csv.zip
    2015-03 → 2022-12   monthly zips {YYYYMM}_da_expost_lmp_csv.zip, {YYYYMM}_rt_lmp_final_csv.zip
    2023-01 → today     daily files {YYYYMMDD}_da_expost_lmp.csv, {YYYYMMDD}_rt_lmp_final.csv

Every daily CSV has a few preamble lines, then a header starting "Node,Type". The earliest
files have no "Value" column (one LMP row per location, names right-padded with spaces); later
files have LMP, MCC and MLC rows per location. Hours are hour-ending Eastern Standard Time all
year, so every day has 24 hours.

Which day-ahead file is used (decided round 26): MISO's Extended LMP went live on 2015-03-01,
and the ex-post DA files belong to it (Wang, Chatterjee, Li & Merring, "Price Enhancements for
Real-Time and Day-Ahead Markets", FERC technical conference, June 2015: "ELMP went live in the
day-ahead and real-time energy markets on March 1, 2015"). Before that day there was one DA
price, in the `da_lmp` files. The single earlier ex-post file (2015-02-19) disagrees with that
day's real-time prices and is not used (docs/rounds/round26_m1_start.md).

This module only reads files it is given. It never decides whether a day is in the sealed
hold-out; `read_day` refuses hold-out days unless its caller passes the hold-out accessor's
permission (CLAUDE.md §12.4).
"""

import datetime
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from evobots.data.periods import is_in_holdout

HOURS_PER_DAY = 24
# The value types MISO publishes per location: the LMP and its congestion and loss components.
VALUE_TYPES = ("LMP", "MCC", "MLC")
MARKETS = ("da", "rt")
# Extended LMP and the ex-post DA files start here (see the module docstring).
FIRST_EXPOST_DAY = datetime.date(2015, 3, 1)
# Daily files replace monthly zips from this day (obs., round 20).
FIRST_DAILY_FILE_DAY = datetime.date(2023, 1, 1)
MEMBER_DATE_PATTERN = re.compile(r"(\d{8})_(da|rt)_")


class HoldoutRefusedError(RuntimeError):
    """Raised when code without the hold-out accessor's permission asks for a hold-out day."""


@dataclass(frozen=True)
class DailyPrices:
    """One operating day of one market, every location.

    Attributes:
        operating_day: the day D the prices are for.
        market: "da" (day-ahead) or "rt" (real-time, final).
        hours_by_location_and_value: {(location name, value type): 24 values in $/MWh, None
            where MISO published nothing}; value type is "LMP", "MCC" or "MLC".
        type_by_location: {location name: MISO's location type, e.g. "Hub", "Gennode"}.
        has_components: True when the file carries MCC and MLC rows.
        source: "file name" or "zip name/member name" the day was read from.
    """

    operating_day: datetime.date
    market: str
    hours_by_location_and_value: dict = field(repr=False)
    type_by_location: dict = field(repr=False)
    has_components: bool
    source: str

    def trading_hubs(self):
        """Names of the trading hubs priced this day: type "Hub" and a name ending ".HUB"."""
        return sorted(
            name
            for name, location_type in self.type_by_location.items()
            if location_type == "Hub" and name.endswith(".HUB")
        )


def parse_lmp_csv(text, operating_day, market, source=""):
    r"""Parse one day's LMP CSV of any era.

    The header line is found by searching for the line starting "Node," (never a fixed row).
    Names and types are stripped of padding. Rows with a blank name are skipped (one exists:
    RT, 2005-04-20; obs. round 20). Rows of other value types are ignored.

    Args:
        text: the file's text.
        operating_day: the day the file is for (a datetime.date).
        market: "da" or "rt".
        source: where the text came from, recorded in the result.

    Returns:
        A DailyPrices.

    Raises:
        ValueError: when no header line exists.

    Example:
        >>> text = "Day Ahead Market LMPs\n04/01/2005\n\nNode,Type," + ",".join(
        ...     f"HE {hour}" for hour in range(1, 25)) + "\nMINN.HUB  ,Hub ," + ",".join(
        ...     ["30.5"] * 24)
        >>> prices = parse_lmp_csv(text, datetime.date(2005, 4, 1), "da")
        >>> prices.hours_by_location_and_value[("MINN.HUB", "LMP")][0], prices.trading_hubs()
        (30.5, ['MINN.HUB'])
    """
    lines = text.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("Node,")), None
    )
    if header_index is None:
        raise ValueError(f"no header line starting 'Node,' in {source or 'the text'}")
    header = [column.strip() for column in lines[header_index].split(",")]
    has_value_column = len(header) > 2 and header[2] == "Value"
    first_hour_column = 3 if has_value_column else 2
    hours_by_location_and_value = {}
    type_by_location = {}
    has_components = False
    for line in lines[header_index + 1 :]:
        columns = line.split(",")
        if len(columns) < first_hour_column + HOURS_PER_DAY:
            continue
        name = columns[0].strip()
        if not name:
            continue
        value_type = columns[2].strip() if has_value_column else "LMP"
        if value_type not in VALUE_TYPES:
            continue
        if value_type == "LMP":
            type_by_location[name] = columns[1].strip()
        else:
            has_components = True
        hour_texts = columns[first_hour_column : first_hour_column + HOURS_PER_DAY]
        hours_by_location_and_value[(name, value_type)] = tuple(
            float(hour_text) if hour_text.strip() else None for hour_text in hour_texts
        )
    return DailyPrices(
        operating_day=operating_day,
        market=market,
        hours_by_location_and_value=hours_by_location_and_value,
        type_by_location=type_by_location,
        has_components=has_components,
        source=source,
    )


def file_and_member_for(operating_day, market):
    """The archive file and, for zips, the member that hold one day's prices.

    This is the date-range dispatch between the three eras, with the ELMP rule for DA files.

    Args:
        operating_day: a datetime.date.
        market: "da" or "rt".

    Returns:
        (file name, member name or None for a plain CSV).

    Example:
        >>> file_and_member_for(datetime.date(2015, 2, 19), "da")
        ('201502_da_lmp_csv.zip', '20150219_da_lmp.csv')
        >>> file_and_member_for(datetime.date(2015, 3, 1), "da")
        ('201503_da_expost_lmp_csv.zip', '20150301_da_expost_lmp.csv')
        >>> file_and_member_for(datetime.date(2023, 1, 1), "rt")
        ('20230101_rt_lmp_final.csv', None)
    """
    if market not in MARKETS:
        raise ValueError(f"market must be one of {MARKETS}, not {market!r}")
    day_text = f"{operating_day:%Y%m%d}"
    if market == "rt":
        kind = "rt_lmp_final"
    elif operating_day >= FIRST_EXPOST_DAY:
        kind = "da_expost_lmp"
    else:
        kind = "da_lmp"
    if operating_day >= FIRST_DAILY_FILE_DAY:
        return f"{day_text}_{kind}.csv", None
    return f"{operating_day:%Y%m}_{kind}_csv.zip", f"{day_text}_{kind}.csv"


def read_day(raw_directory, operating_day, market, holdout_permission=None):
    """Read one day of one market from the raw archive.

    Args:
        raw_directory: the folder holding the downloaded files (data/raw/miso for evolution).
        operating_day: a datetime.date.
        market: "da" or "rt".
        holdout_permission: required for hold-out days; only the hold-out accessor creates it.

    Returns:
        A DailyPrices, or None when the file or member doesn't exist (a missing day stays
        missing; gaps are never filled).

    Raises:
        HoldoutRefusedError: for a hold-out day without permission.
    """
    if is_in_holdout(operating_day) and holdout_permission is None:
        raise HoldoutRefusedError(
            f"{operating_day} is in the sealed hold-out; only the final-test path may read it"
        )
    file_name, member_name = file_and_member_for(operating_day, market)
    path = Path(raw_directory) / file_name
    if not path.exists():
        return None
    if member_name is None:
        text = path.read_text(encoding="utf-8", errors="replace")
        source = file_name
    else:
        with zipfile.ZipFile(path) as archive:
            if member_name not in archive.namelist():
                return None
            text = archive.read(member_name).decode("utf-8", errors="replace")
        source = f"{file_name}/{member_name}"
    return parse_lmp_csv(text, operating_day, market, source)


def days_in_file(path):
    """(operating day, market, member name) for every daily CSV in one archive file.

    Args:
        path: a monthly zip or a daily CSV.

    Returns:
        A list, sorted by member name; members whose names carry no date are skipped.
    """
    path = Path(path)
    names = [path.name]
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = sorted(archive.namelist())
    found = []
    for name in names:
        match = MEMBER_DATE_PATTERN.search(name)
        if match:
            day = datetime.datetime.strptime(match.group(1), "%Y%m%d").date()
            found.append((day, match.group(2), name))
    return found
