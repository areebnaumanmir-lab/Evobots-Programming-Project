"""Parser for NWS Point Forecast Matrices (PFM), the weather forecasts bots see.

One downloaded file (`tools/fetch_nws_forecasts.py`) holds the newest PFM issue of one
forecast office before 10:30 EPT on a decision day (`docs/design_spec.md` §7.4). The issue is a series
of town blocks separated by `$$`. Each block has a zone line (`MNZ041-020301-`), the town
name, its coordinates (`45.87N  95.38W`, with `Elev. … ft` from about 2010), the issue time,
then two tables: 3-hourly for about 60 hours and 6-hourly for the following days.

**Parsing rules** (`docs/design_spec.md` §7.4 parser traps; obs., round 28, on 2005–2016 files):
- Case changes over the years (ALL CAPS before 2016-20, mixed case after), so labels are
  compared in upper case.
- Column positions are read from each table's UTC hour row, never fixed offsets. A value
  belongs to the hour whose two digits end at the same character position.
- Before about 2012 the UTC row comes before the local row; after, the order flips. Both
  are found by their labels.
- A town block can appear twice in one file; the first copy is kept.
- Some archived products have corrupted lines (a row spliced into another, obs. in about
  0.1 % of 2005–2016 files). A block whose hour rows don't line up or don't step by 3 or
  6 hours is skipped and reported, never repaired; the other towns of that issue are kept.
- Issue lines may carry extra spaces ("400 AM  EST THU APR 7 2005").

The parser keeps raw values: numbers for temperature, dew point, humidity, wind speed,
precipitation chance and amount, and the max/min row; text codes for cloud cover and wind
direction. Turning them into features (high, low, degree-days, wind, cloud fraction for
operating day D) belongs to the feature layer (M2).

Example:
    >>> product = parse_product(EXAMPLE_PRODUCT)
    >>> product.problems
    ()
    >>> town = product.towns[0]
    >>> town.name, town.latitude_degrees, town.longitude_degrees
    ('ALEXANDRIA-DOUGLAS MN', 45.87, -95.38)
    >>> town.issued_at_utc.isoformat()
    '2005-04-01T12:01:00+00:00'
    >>> [(column.valid_at_utc.isoformat(), value) for column, value in town.values("MAX/MIN")]
    [('2005-04-02T00:00:00+00:00', 52.0), ('2005-04-02T12:00:00+00:00', 28.0)]
"""

import dataclasses
import datetime
import re

# UTC offsets, in hours, of the time-zone abbreviations MISO's offices use in issue lines.
UTC_OFFSET_HOURS_BY_ZONE = {"EST": -5, "EDT": -4, "CST": -6, "CDT": -5}
# Row labels whose values are numbers; other rows keep their text codes.
NUMERIC_LABELS = frozenset(
    {
        "MAX/MIN",
        "MIN/MAX",
        "TEMP",
        "DEWPT",
        "RH",
        "WIND SPD",
        "POP 12HR",
        "QPF 12HR",
        "WIND CHILL",
        "MIN CHILL",
        "HEAT INDEX",
    }
)
# Text-coded rows kept for the feature layer.
TEXT_LABELS = frozenset({"CLOUDS", "AVG CLOUDS", "WIND DIR", "PWIND DIR", "WIND CHAR"})
# Width of the row-label field: values start after it in every era (obs., round 28).
LABEL_WIDTH = 14
# A value is at most three characters wide ("100" for humidity) and right-aligned.
VALUE_WIDTH = 3
ZONE_LINE_PATTERN = re.compile(r"^[A-Z]{2}Z\d{3}[-\d>]*-\s*$", re.IGNORECASE)
COORDINATE_PATTERN = re.compile(r"^\s*(\d+\.\d+)N\s+(\d+\.\d+)W", re.IGNORECASE)
ISSUE_LINE_PATTERN = re.compile(
    r"^(\d{1,2})(\d{2})\s+(AM|PM)\s+([A-Z]{3})\s+[A-Z]{3}\s+([A-Z]{3})\s+(\d{1,2})\s+(\d{4})\s*$",
    re.IGNORECASE,
)
HOUR_ROW_PATTERN = re.compile(r"^(UTC|[ECMP][SD]T) +([36])HRLY", re.IGNORECASE)
TWO_DIGITS_PATTERN = re.compile(r"\d\d")
MONTH_NUMBER_BY_ABBREVIATION = {
    name: number
    for number, name in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        start=1,
    )
}


@dataclasses.dataclass(frozen=True)
class ForecastColumn:
    """One time column of a forecast table.

    Attributes:
        valid_at_utc: the time the column describes (timezone-aware, UTC).
        local_hour: the hour on the local clock printed above the column (0–23).
        utc_offset_hours: local time minus UTC for this column, in hours (−6 … −4).
        step_hours: 3 for the near-term table, 6 for the extended one.
    """

    valid_at_utc: datetime.datetime
    local_hour: int
    utc_offset_hours: int
    step_hours: int

    def local_date(self):
        """The local calendar date of this column."""
        return (self.valid_at_utc + datetime.timedelta(hours=self.utc_offset_hours)).date()


@dataclasses.dataclass(frozen=True)
class TownForecast:
    """One town's forecast from one PFM issue.

    Attributes:
        zone_code: the NWS zone, e.g. "MNZ041".
        name: the town line as printed, upper-cased and stripped.
        latitude_degrees: north latitude, or None when the line is missing.
        longitude_degrees: longitude, negative west, or None when the line is missing.
        issued_at_utc: issue time (timezone-aware, UTC).
        value_by_label_and_column: (row label, column) → number or text code.
    """

    zone_code: str
    name: str
    latitude_degrees: float | None
    longitude_degrees: float | None
    issued_at_utc: datetime.datetime
    value_by_label_and_column: dict

    def values(self, label):
        """(column, value) pairs of one row, in time order.

        Args:
            label: an upper-case row label, e.g. "TEMP" or "MAX/MIN".

        Returns:
            A list of (ForecastColumn, value) pairs; columns left blank are absent.
        """
        pairs = [
            (column, value)
            for (row_label, column), value in self.value_by_label_and_column.items()
            if row_label == label
        ]
        return sorted(pairs, key=lambda pair: pair[0].valid_at_utc)


class ForecastFormatError(ValueError):
    """A PFM product doesn't have the layout the parser expects."""


@dataclasses.dataclass(frozen=True)
class ParsedProduct:
    """The towns parsed from one PFM product, and the blocks that had to be skipped.

    Attributes:
        towns: TownForecast objects in printed order, first copy of each town only.
        problems: one text per skipped block: its zone line and the reason.
    """

    towns: tuple
    problems: tuple


def issue_time_utc(line):
    """Parse an issue line such as "601 AM CST FRI APR 1 2005" into an aware UTC datetime.

    Args:
        line: the issue line.

    Returns:
        The issue time in UTC, or None when the line isn't an issue line.

    Example:
        >>> issue_time_utc("546 AM CDT Mon Jul 15 2024").isoformat()
        '2024-07-15T10:46:00+00:00'
    """
    match = ISSUE_LINE_PATTERN.match(line.strip())
    if not match:
        return None
    hour, minute, meridiem, zone, month, day, year = match.groups()
    zone = zone.upper()
    if zone not in UTC_OFFSET_HOURS_BY_ZONE:
        return None
    hour_24 = int(hour) % 12 + (12 if meridiem.upper() == "PM" else 0)
    local = datetime.datetime(
        int(year), MONTH_NUMBER_BY_ABBREVIATION[month.upper()], int(day), hour_24, int(minute)
    )
    utc_naive = local - datetime.timedelta(hours=UTC_OFFSET_HOURS_BY_ZONE[zone])
    return utc_naive.replace(tzinfo=datetime.UTC)


def hour_tokens(line):
    """(end position, hour) for every two-digit hour after the label field.

    Example:
        >>> hour_tokens("UTC 3HRLY     09 12")
        [(16, 9), (19, 12)]
    """
    return [
        (match.end(), int(match.group()))
        for match in TWO_DIGITS_PATTERN.finditer(line)
        if match.start() >= LABEL_WIDTH
    ]


def nearest_time_with_hour(anchor, hour):
    """The datetime with the given UTC hour (minute 0) closest to the anchor.

    Example:
        >>> anchor = datetime.datetime(2005, 4, 1, 12, 1, tzinfo=datetime.UTC)
        >>> nearest_time_with_hour(anchor, 9).isoformat()
        '2005-04-01T09:00:00+00:00'
        >>> nearest_time_with_hour(anchor, 0).isoformat()
        '2005-04-02T00:00:00+00:00'
    """
    same_day = anchor.replace(hour=hour, minute=0, second=0, microsecond=0)
    candidates = [same_day + datetime.timedelta(days=offset) for offset in (-1, 0, 1)]
    return min(candidates, key=lambda candidate: abs(candidate - anchor))


def table_columns(utc_line, local_line, start_after):
    """The time columns of one table, keyed by the character position where each ends.

    Args:
        utc_line: the table's UTC hour row.
        local_line: the table's local-time hour row.
        start_after: for the first table, the issue time (the first column is the nearest
            time with its hour); for later tables, the previous table's last column time
            (the first column is the next time with its hour).

    Returns:
        A dict from end position to ForecastColumn.

    Raises:
        ForecastFormatError: when the two hour rows don't line up.
    """
    utc_hours = hour_tokens(utc_line)
    local_hours = dict(hour_tokens(local_line))
    step_hours = int(HOUR_ROW_PATTERN.match(utc_line.strip()).group(2))
    column_by_end = {}
    previous = None
    for end, hour in utc_hours:
        if end not in local_hours:
            raise ForecastFormatError(f"local hour row doesn't line up at position {end}")
        if hour > 23 or local_hours[end] > 23:
            raise ForecastFormatError(f"hour {hour} at position {end} is not a clock hour")
        if previous is not None and (hour - previous.hour) % 24 != step_hours:
            raise ForecastFormatError(f"hours don't step by {step_hours} at position {end}")
        if previous is None and start_after[1] == "issue":
            valid_at = nearest_time_with_hour(start_after[0], hour)
        else:
            base = previous if previous is not None else start_after[0]
            whole_hour = base.replace(minute=0, second=0, microsecond=0)
            # The next time strictly after `base` whose UTC hour is `hour`.
            valid_at = whole_hour + datetime.timedelta(hours=(hour - whole_hour.hour - 1) % 24 + 1)
        offset = (local_hours[end] - hour + 12) % 24 - 12
        column_by_end[end] = ForecastColumn(valid_at, local_hours[end], offset, step_hours)
        previous = valid_at
    return column_by_end


def row_values(line, column_by_end):
    """The raw value text under each column of one data row (blank cells left out)."""
    values = {}
    for end, column in column_by_end.items():
        cell = line[max(LABEL_WIDTH, end - VALUE_WIDTH) : end].strip()
        if cell:
            values[column] = cell
    return values


def parse_town_block(lines, product_issue_time):
    """Parse one town block (the lines between `$$` separators).

    Args:
        lines: the block's lines, starting at the zone line.
        product_issue_time: the product's issue time, used if the block has none.

    Returns:
        A TownForecast, or None when the block has no forecast table.

    Raises:
        ForecastFormatError: when a table's hour rows don't line up.
    """
    zone_code = lines[0].strip().split("-")[0].upper()
    name = lines[1].strip().upper() if len(lines) > 1 else ""
    latitude = longitude = None
    issued_at = product_issue_time
    for line in lines[2:5]:
        coordinates = COORDINATE_PATTERN.match(line)
        if coordinates:
            latitude = float(coordinates.group(1))
            longitude = -float(coordinates.group(2))
        parsed_issue = issue_time_utc(line)
        if parsed_issue is not None:
            issued_at = parsed_issue
    value_by_label_and_column = {}
    column_by_end = None
    pending_hour_row = None
    last_column_time = None
    for line in lines:
        label = line[:LABEL_WIDTH].strip().upper()
        if HOUR_ROW_PATTERN.match(line.strip()):
            if pending_hour_row is None:
                pending_hour_row = line
                continue
            utc_line, local_line = (
                (pending_hour_row, line)
                if pending_hour_row.strip().upper().startswith("UTC")
                else (line, pending_hour_row)
            )
            start = (issued_at, "issue") if last_column_time is None else (last_column_time, "")
            column_by_end = table_columns(utc_line, local_line, start)
            last_column_time = max(column.valid_at_utc for column in column_by_end.values())
            pending_hour_row = None
            continue
        if column_by_end is None or not (label in NUMERIC_LABELS or label in TEXT_LABELS):
            continue
        for column, cell in row_values(line, column_by_end).items():
            if label in NUMERIC_LABELS:
                try:
                    value = float(cell)
                except ValueError:
                    continue
            else:
                value = cell.upper()
            value_by_label_and_column[(label, column)] = value
    if not value_by_label_and_column:
        return None
    return TownForecast(
        zone_code=zone_code,
        name=name,
        latitude_degrees=latitude,
        longitude_degrees=longitude,
        issued_at_utc=issued_at,
        value_by_label_and_column=value_by_label_and_column,
    )


def parse_product(text):
    """Parse one PFM product into town forecasts, first copy of each town kept.

    Args:
        text: the downloaded file's text.

    Returns:
        A ParsedProduct: the towns in printed order and the skipped blocks.

    Raises:
        ForecastFormatError: when no issue time can be found.
    """
    lines = text.replace("\r", "").split("\n")
    product_issue_time = None
    for line in lines[:15]:
        product_issue_time = issue_time_utc(line)
        if product_issue_time is not None:
            break
    if product_issue_time is None:
        raise ForecastFormatError("no issue time in the product header")
    blocks = []
    current = None
    for line in lines:
        if ZONE_LINE_PATTERN.match(line.strip()):
            current = [line]
            blocks.append(current)
        elif line.strip() == "$$":
            current = None
        elif current is not None:
            current.append(line)
    towns = []
    problems = []
    seen = set()
    for block in blocks:
        try:
            town = parse_town_block(block, product_issue_time)
        except ForecastFormatError as error:
            problems.append(f"{block[0].strip()}: {error}")
            continue
        if town is None or (town.zone_code, town.name) in seen:
            continue
        seen.add((town.zone_code, town.name))
        towns.append(town)
    return ParsedProduct(towns=tuple(towns), problems=tuple(problems))


EXAMPLE_PRODUCT = """
FOUS53 KMPX 011202
PFMMPX

POINT FORECAST MATRICES...UPDATED
NATIONAL WEATHER SERVICE TWIN CITIES/CHANHASSEN MN
601 AM CST FRI APR 1 2005

MNZ041-020301-
ALEXANDRIA-DOUGLAS MN
45.87N  95.38W
601 AM CST FRI APR 1 2005

DATE             FRI 04/01/05            SAT 04/02/05
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00
CST 3HRLY     03 06 09 12 15 18 21 00 03 06 09 12 15 18

MAX/MIN                      52          28
TEMP                37 47 52 48 40 35 31 28 39 52 57 54
WIND SPD            11 13 13  9  8  6  6 10 16 16 19 13
CLOUDS              CL CL CL FW FW FW SC SC SC SC SC SC

$$
"""
