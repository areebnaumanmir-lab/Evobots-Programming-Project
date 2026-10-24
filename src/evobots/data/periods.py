"""The project's fixed periods (CLAUDE.md §7.2). Every other module imports them from here.

Example:
    >>> import datetime
    >>> is_in_holdout(datetime.date(2026, 2, 28))
    True
    >>> is_in_holdout(datetime.date(2025, 9, 21))
    False
"""

import datetime

# MISO's energy market opened on this day; nothing older exists (obs., round 20).
MARKET_FIRST_DAY = datetime.date(2005, 4, 1)
# Evolution and walk-forward validation run from MARKET_FIRST_DAY to this day, inclusive.
EVOLUTION_LAST_DAY = datetime.date(2025, 9, 21)
# The sealed hold-out: scored once per finished run through the logged final-test path only.
HOLDOUT_FIRST_DAY = datetime.date(2025, 9, 22)
HOLDOUT_LAST_DAY = datetime.date(2026, 9, 21)
# Forward (paper-live) data starts the day after the hold-out and grows daily.
FORWARD_FIRST_DAY = datetime.date(2026, 9, 22)


def is_in_holdout(operating_day):
    """True when the operating day lies in the sealed hold-out (both ends inclusive).

    Args:
        operating_day: a datetime.date.

    Returns:
        True for 2025-09-22 … 2026-09-21.
    """
    return HOLDOUT_FIRST_DAY <= operating_day <= HOLDOUT_LAST_DAY


def touches_holdout(first_day, last_day):
    """True when any day of the inclusive range first_day … last_day is in the hold-out.

    Example:
        >>> touches_holdout(datetime.date(2025, 9, 1), datetime.date(2025, 9, 30))
        True
        >>> touches_holdout(datetime.date(2005, 4, 1), EVOLUTION_LAST_DAY)
        False
    """
    return first_day <= HOLDOUT_LAST_DAY and last_day >= HOLDOUT_FIRST_DAY
