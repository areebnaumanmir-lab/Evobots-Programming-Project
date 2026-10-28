"""Tests for the NWS Point Forecast Matrices parser (`evobots.data.sources.nws_pfm`).

The products below are trimmed copies of real archived issues (Iowa Environmental Mesonet;
public domain): the layout, spacing and values are as downloaded, with towns and rows cut.
"""

import datetime

from evobots.data.sources import nws_pfm

# Minneapolis office, 2024-07-15: mixed case, the local hour row before the UTC row, and
# the extended 6-hourly table.
MIXED_CASE_PRODUCT = """
FOUS53 KMPX 151046
PFMMPX

Point Forecast Matrices
National Weather Service Twin Cities/Chanhassen MN
546 AM CDT Mon Jul 15 2024

MNZ041-152100-
Alexandria-Douglas MN
45.87N  95.38W Elev. 1424 ft
546 AM CDT Mon Jul 15 2024

Date             Mon 07/15/24            Tue 07/16/24            Wed 07/17/24
CDT 3hrly     04 07 10 13 16 19 22 01 04 07 10 13 16 19 22 01 04 07 10 13 16 19
UTC 3hrly     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

Max/Min                      80          59          75          54          73
Temp             68 73 76 79 77 68 63 61 61 68 71 73 71 63 59 56 55 64 69 71 70
RH               90 79 71 60 58 76 87 90 90 68 59 53 55 75 80 86 90 65 53 47 49
Wind spd          9 10 13 14 12  8  5  4  4  6 10 11  9  5  5  5  5  8  9  9  8
Clouds           B2 B1 B1 SC SC FW FW FW FW SC SC SC FW FW CL CL CL CL FW FW FW


Date          Thu 07/18/24  Fri 07/19/24  Sat 07/20/24  Sun 07/21/24
CDT 6hrly     01 07 13 19   01 07 13 19   01 07 13 19   01 07 13 19
UTC 6hrly     06 12 18 00   06 12 18 00   06 12 18 00   06 12 18 00

Min/Max          54    77      57    79      62    81      62    81
Temp          58 57 72 73   60 59 75 76   64 64 77 76   65 65 78 77
Avg clouds    FW FW CL FW   CL FW FW SC   SC SC FW SC   FW FW FW SC

$$
MNZ041-152100-
Alexandria-Douglas MN
45.87N  95.38W Elev. 1424 ft
546 AM CDT Mon Jul 15 2024

Date             Mon 07/15/24            Tue 07/16/24            Wed 07/17/24
CDT 3hrly     04 07 10 13 16 19 22 01 04 07 10 13 16 19 22 01 04 07 10 13 16 19
UTC 3hrly     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

Temp             99 99 99 99 99 99 99 99 99 99 99 99 99 99 99 99 99 99 99 99 99

$$
"""

# Indianapolis office, 2009-04-23: a corrupted UTC row (another row spliced into it), as
# archived. The town before it must survive; the corrupted block is reported.
CORRUPTED_PRODUCT = """
FOUS53 KIND 230957
PFMIND

POINT FORECAST MATRICES
NATIONAL WEATHER SERVICE INDIANAPOLIS IN
557 AM EDT THU APR 23 2009

INZ047-232100-
INDIANAPOLIS-MARION IN
39.73N  86.28W
557 AM EDT THU APR 23 2009

DATE             THU 04/23/09            FRI 04/24/09            SAT 04/25/09
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

TEMP                55 66 74 77 72 66 62 60 61 70 78 80 74 68 65 63 66 74 80 82

$$
INZ048-232100-
SHELBYVILLE-SHELBY IN
39.53N  85.78W
557 AM EDT THU APR 23 2009

DATE             THU 04/23/09            FRI 04/24/09            SAT 04/25/09
EDT 3HRLY     05 08 11 14 17 20 23 02 05 08 11 14 17 20 23 02 05 08 11 14 17 20
UTC 3HRLY     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

TEMP                55 66 74 77 72 66 62 60 61 70 78 80 74 68 65 63 66 74 80 82

DATE          SUN 04/26/09  MON 04/27/09  TUE 04/28/09  WED 04/29/09
EDT 6HRLY     02 08 14 20   02 08 14 20   02 08 14 20   02 08 14 20
UTC 6HRLY     06 12 18 00   06 14 59 68 72 69 63 60 57 58 69 76 79 76 70 67 64 65

$$
"""


def utc(year, month, day, hour):
    return datetime.datetime(year, month, day, hour, tzinfo=datetime.UTC)


def test_mixed_case_issue_coordinates_and_duplicate_town():
    product = nws_pfm.parse_product(MIXED_CASE_PRODUCT)
    assert product.problems == ()
    assert len(product.towns) == 1  # the second copy (all 99s) is dropped
    town = product.towns[0]
    assert town.zone_code == "MNZ041"
    assert town.name == "ALEXANDRIA-DOUGLAS MN"
    assert (town.latitude_degrees, town.longitude_degrees) == (45.87, -95.38)
    assert town.issued_at_utc == utc(2024, 7, 15, 10) + datetime.timedelta(minutes=46)


def test_columns_follow_the_utc_row_and_local_dates():
    town = nws_pfm.parse_product(MIXED_CASE_PRODUCT).towns[0]
    temperatures = town.values("TEMP")
    first_column, first_value = temperatures[0]
    # The 04 CDT column falls before the 5:46 AM issue and is blank, so the first value
    # (68 °F) sits under 07 CDT = 12 UTC.
    assert first_column.valid_at_utc == utc(2024, 7, 15, 12)
    assert (first_column.local_hour, first_column.utc_offset_hours) == (7, -5)
    assert first_value == 68.0
    # The 3-hourly table ends at 00 UTC on 07/18; the 6-hourly one starts at 06 UTC that day.
    three_hourly = [column for column, _ in temperatures if column.step_hours == 3]
    six_hourly = [column for column, _ in temperatures if column.step_hours == 6]
    assert three_hourly[-1].valid_at_utc == utc(2024, 7, 18, 0)
    assert six_hourly[0].valid_at_utc == utc(2024, 7, 18, 6)
    assert six_hourly[-1].valid_at_utc == utc(2024, 7, 22, 0)
    assert six_hourly[-1].local_date() == datetime.date(2024, 7, 21)


def test_max_min_values_sit_under_evening_and_morning_columns():
    town = nws_pfm.parse_product(MIXED_CASE_PRODUCT).towns[0]
    near_term = [
        (column.local_date().isoformat(), column.local_hour, value)
        for column, value in town.values("MAX/MIN")
    ]
    assert near_term == [
        ("2024-07-15", 19, 80.0),
        ("2024-07-16", 7, 59.0),
        ("2024-07-16", 19, 75.0),
        ("2024-07-17", 7, 54.0),
        ("2024-07-17", 19, 73.0),
    ]
    extended = [(column.local_hour, value) for column, value in town.values("MIN/MAX")][:2]
    assert extended == [(7, 54.0), (19, 77.0)]


def test_text_codes_kept_raw():
    town = nws_pfm.parse_product(MIXED_CASE_PRODUCT).towns[0]
    assert town.values("CLOUDS")[0][1] == "B2"
    assert town.values("AVG CLOUDS")[0][1] == "FW"


def test_corrupted_block_skipped_and_reported():
    product = nws_pfm.parse_product(CORRUPTED_PRODUCT)
    assert [town.zone_code for town in product.towns] == ["INZ047"]
    assert len(product.problems) == 1
    assert product.problems[0].startswith("INZ048-232100-:")


def test_issue_line_with_extra_space():
    assert nws_pfm.issue_time_utc("400 AM  EST THU APR 7 2005") == utc(2005, 4, 7, 9)
    assert nws_pfm.issue_time_utc("POINT FORECAST MATRICES") is None
