"""What a trader could see at its decision time: `visible(column, decision_time)`.

Every data column carries, for each observation, the moment it became public
(`available_at`). `visible` returns only the observations public at or before a decision
time, and it is the only way features read data (`CLAUDE.md` §6.4, §18). The publication
rules below are the single place each source's timing is written down.

**Decision time** (decided round 20, D1): 10:30 Eastern prevailing time on D−1, for every
year, for operating day D.

**Publication rules** (sources: `CLAUDE.md` §6.4, §7.4–7.8; `docs/market_rules.md` §1):

- **DA prices of day t:** 16:30 Eastern on t−1. Ex-post DA LMPs post then (BPM-002-r19);
  earlier eras posted DA results by 15:00 EST, so 16:30 is never early.
- **Final RT prices of day t:** the start of day t+5, Eastern. Final RT posts about t+5
  (obs.), so on decision day D−1 the newest is D−6, as in `sizing.py`.
- **Daily series** (gas, T-bill, EPU, GPR): the start of the day `lag` days after t, in
  business days for gas, oil and the T-bill (`series.PUBLICATION_LAG_DAYS_BY_SERIES`).
  Where a source's posting time of day is unknown or after 10:30, the lag includes one
  extra day (D-92, round 28).
- **NWS forecasts:** the issue time printed on the product. The fetch keeps the newest
  issue in the 24 hours before the decision time.
- **EIA-860M capacity in month m:** the start of month m ("capacity operating on D−1",
  `CLAUDE.md` §8, features 17–18).

Example:
    >>> import datetime
    >>> decision_time(datetime.date(2024, 7, 16)).isoformat()
    '2024-07-15T10:30:00-04:00'
    >>> real_time_final_available_at(datetime.date(2024, 7, 10)).date()
    datetime.date(2024, 7, 15)
"""

import bisect
import dataclasses
import datetime
from zoneinfo import ZoneInfo

from evobots.data.sources.series import PUBLICATION_LAG_DAYS_BY_SERIES

EASTERN = ZoneInfo("America/New_York")
# The decision is taken at 10:30 Eastern prevailing time on D−1 (decided round 20).
DECISION_TIME_OF_DAY = datetime.time(10, 30)
# Ex-post DA LMPs post at 16:30 EPT on D−1 (BPM-002-r19 Exhibit 7-1; round 27).
DAY_AHEAD_PUBLISHED_TIME_OF_DAY = datetime.time(16, 30)
# Final RT prices for day t post about t+5 (obs., round 18: on 2026-09-26 the newest final
# RT file was 2026-09-21).
REAL_TIME_FINAL_LAG_DAYS = 5
# Series published on business days (Monday–Friday); the others count calendar days.
BUSINESS_DAY_SERIES = frozenset(
    {"treasury_bill_3_month_discount_fraction", "henry_hub_usd_per_mmbtu", "wti_usd_per_barrel"}
)


def start_of_day(day):
    """Midnight at the start of a day, Eastern, timezone-aware."""
    return datetime.datetime.combine(day, datetime.time(0, 0), tzinfo=EASTERN)


def decision_time(operating_day):
    """When bids for operating day D are decided: 10:30 Eastern on D−1.

    Args:
        operating_day: D, a datetime.date.

    Returns:
        A timezone-aware datetime.
    """
    decision_day = operating_day - datetime.timedelta(days=1)
    return datetime.datetime.combine(decision_day, DECISION_TIME_OF_DAY, tzinfo=EASTERN)


def day_ahead_available_at(operating_day):
    """When DA prices for an operating day became public (16:30 Eastern the day before)."""
    published_day = operating_day - datetime.timedelta(days=1)
    return datetime.datetime.combine(published_day, DAY_AHEAD_PUBLISHED_TIME_OF_DAY, tzinfo=EASTERN)


def real_time_final_available_at(operating_day):
    """When final RT prices for an operating day became public (start of day t+5)."""
    return start_of_day(operating_day + datetime.timedelta(days=REAL_TIME_FINAL_LAG_DAYS))


def add_business_days(day, count):
    """The day `count` business days (Monday–Friday) after `day`.

    Example:
        >>> add_business_days(datetime.date(2024, 7, 12), 1)  # Friday → Monday
        datetime.date(2024, 7, 15)
    """
    result = day
    remaining = count
    while remaining > 0:
        result += datetime.timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1
    return result


def series_available_at(series_name, observation_day):
    """When one observation of a daily series became public.

    Args:
        series_name: a name in `PUBLICATION_LAG_DAYS_BY_SERIES`.
        observation_day: the observation's date.

    Returns:
        The start (Eastern) of the day `lag` days later; business days for gas, oil and
        the T-bill rate.
    """
    lag_days = PUBLICATION_LAG_DAYS_BY_SERIES[series_name]
    if series_name in BUSINESS_DAY_SERIES:
        return start_of_day(add_business_days(observation_day, lag_days))
    return start_of_day(observation_day + datetime.timedelta(days=lag_days))


def capacity_available_at(year, month):
    """When the capacity operating in a month counts as known: the start of that month."""
    return start_of_day(datetime.date(year, month, 1))


@dataclasses.dataclass(frozen=True)
class Column:
    """One data column: observations, each with the moment it became public.

    Attributes:
        name: code name with its unit, e.g. "henry_hub_usd_per_mmbtu".
        unit: unit of the values.
        keys: what each observation is about (e.g. an operating day, or (day, hour, hub)).
        available_at: when each became public, timezone-aware, in non-decreasing order.
        values: the observations.
    """

    name: str
    unit: str
    keys: tuple
    available_at: tuple
    values: tuple

    @classmethod
    def from_observations(cls, name, unit, observations):
        """Build a Column from (key, available_at, value) triples in any order.

        Example:
            >>> import datetime
            >>> later = datetime.datetime(2024, 1, 2, tzinfo=EASTERN)
            >>> earlier = datetime.datetime(2024, 1, 1, tzinfo=EASTERN)
            >>> column = Column.from_observations("x", "unit", [("b", later, 2), ("a", earlier, 1)])
            >>> column.keys
            ('a', 'b')
        """
        ordered = sorted(observations, key=lambda triple: (triple[1], str(triple[0])))
        return cls(
            name=name,
            unit=unit,
            keys=tuple(key for key, _, _ in ordered),
            available_at=tuple(moment for _, moment, _ in ordered),
            values=tuple(value for _, _, value in ordered),
        )

    def value_by_key(self):
        """The column as a mapping from key to value."""
        return dict(zip(self.keys, self.values))


def visible(column, at_time):
    """The part of a column that was public at a decision time.

    Args:
        column: a Column.
        at_time: the decision time, timezone-aware.

    Returns:
        A Column holding only observations with available_at ≤ at_time.

    Raises:
        ValueError: when at_time has no timezone (naive times are ambiguous).
    """
    if at_time.tzinfo is None:
        raise ValueError("decision times must be timezone-aware")
    count = bisect.bisect_right(column.available_at, at_time)
    return Column(
        name=column.name,
        unit=column.unit,
        keys=column.keys[:count],
        available_at=column.available_at[:count],
        values=column.values[:count],
    )
