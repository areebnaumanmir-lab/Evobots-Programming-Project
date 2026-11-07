"""Calendar features: weekday and the NERC off-peak holidays (`docs/design_spec.md` §8, 23–25).

The six NERC holidays (`docs/market_rules.md` §6): New Year's Day, Memorial Day (last Monday
of May), Independence Day, Labor Day (first Monday of September), Thanksgiving (fourth
Thursday of November) and Christmas. A holiday is flagged on its calendar date; when it falls
on a Sunday, the Monday after is flagged too (decided round 20, D2, confirmed round 28).
Saturday holidays stay on Saturday.

Example:
    >>> import datetime
    >>> is_nerc_holiday(datetime.date(2022, 12, 26))  # Christmas 2022 was a Sunday
    True
    >>> is_nerc_holiday(datetime.date(2024, 11, 28))  # Thanksgiving
    True
    >>> is_nerc_holiday(datetime.date(2024, 11, 29))
    False
"""

import datetime


def nth_weekday(year, month, weekday, nth):
    """The nth (1-based) given weekday (0 = Monday) of a month."""
    first = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + datetime.timedelta(days=offset + 7 * (nth - 1))


def last_weekday(year, month, weekday):
    """The last given weekday (0 = Monday) of a month."""
    next_month = datetime.date(year + month // 12, month % 12 + 1, 1)
    last = next_month - datetime.timedelta(days=1)
    return last - datetime.timedelta(days=(last.weekday() - weekday) % 7)


def nerc_holidays(year):
    """The six NERC holiday dates of a year, on their calendar dates."""
    return (
        datetime.date(year, 1, 1),
        last_weekday(year, 5, 0),
        datetime.date(year, 7, 4),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4),
        datetime.date(year, 12, 25),
    )


def is_nerc_holiday(day):
    """True on a NERC holiday, or on the Monday after one that fell on a Sunday."""
    holidays = nerc_holidays(day.year)
    if day in holidays:
        return True
    yesterday = day - datetime.timedelta(days=1)
    return (
        day.weekday() == 0
        and yesterday.weekday() == 6
        and yesterday in nerc_holidays(yesterday.year)
    )
