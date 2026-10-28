"""The sealed hold-out's single, logged way in (`CLAUDE.md` §7.2, §12.4).

The hold-out (2025-09-22 → 2026-09-21) is stored apart, under data/holdout/, and every reader
refuses hold-out days unless it is handed a `HoldoutPermission`. This module is the only
place such a permission is made, and making one appends a line to the access log before
anything is read. Only the final-test path (M7) may import it; `tests/test_holdout.py`
fails if any other module does.

The access log is committed to git (unlike the data), so the Home page and anyone reading
the repository can see whether the hold-out was ever opened, by whom, for which run and
trader.

Example:
    >>> import tempfile, pathlib
    >>> log_path = pathlib.Path(tempfile.mkdtemp()) / "access.jsonl"
    >>> holdout_status(log_path)
    'Sealed: never opened'
    >>> permission = open_holdout("R1", "R1-42", "doctest", log_path)
    >>> holdout_status(log_path).startswith("Opened on ")
    True
"""

import dataclasses
import datetime
import json
from pathlib import Path

# The committed record of every opening (one JSON object per line).
ACCESS_LOG_PATH = Path("data/holdout_access_log.jsonl")
# Where hold-out files live; evolution workers are given a data root without it.
HOLDOUT_DIRECTORY = Path("data/holdout")
# Private marker: a HoldoutPermission made without it is refused.
_MADE_BY_OPEN_HOLDOUT = object()


@dataclasses.dataclass(frozen=True)
class HoldoutPermission:
    """Proof that the hold-out was opened through `open_holdout` and logged.

    Attributes:
        run_id: the run whose chosen trader is being tested, e.g. "R12".
        trader_id: the trader being tested, e.g. "R12-184213".
        opened_by: who asked (a user name or "final-test").
        opened_at_utc: when, timezone-aware UTC.
    """

    run_id: str
    trader_id: str
    opened_by: str
    opened_at_utc: datetime.datetime
    marker: object = dataclasses.field(default=None, repr=False, compare=False)

    def __post_init__(self):
        """Refuse permissions not made by `open_holdout`."""
        if self.marker is not _MADE_BY_OPEN_HOLDOUT:
            raise PermissionError("a HoldoutPermission can only come from open_holdout()")


def open_holdout(run_id, trader_id, opened_by, log_path=ACCESS_LOG_PATH):
    """Log an opening of the sealed hold-out and return the permission readers require.

    Args:
        run_id: the run being tested.
        trader_id: the trader being tested.
        opened_by: who asked.
        log_path: the access log (the committed default except in tests).

    Returns:
        A HoldoutPermission.
    """
    opened_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    record = {
        "opened_at_utc": opened_at.isoformat(),
        "opened_by": opened_by,
        "run_id": run_id,
        "trader_id": trader_id,
    }
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True) + "\n")
    return HoldoutPermission(run_id, trader_id, opened_by, opened_at, _MADE_BY_OPEN_HOLDOUT)


def holdout_openings(log_path=ACCESS_LOG_PATH):
    """Every logged opening, oldest first (an empty list when never opened)."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def holdout_status(log_path=ACCESS_LOG_PATH):
    """One line for the Home page: never opened, or the latest opening.

    Returns:
        "Sealed: never opened" or "Opened on <date> for <trader> in <run>".
    """
    openings = holdout_openings(log_path)
    if not openings:
        return "Sealed: never opened"
    latest = openings[-1]
    return (
        f"Opened on {latest['opened_at_utc'][:10]} for {latest['trader_id']} "
        f"in {latest['run_id']} ({len(openings)} opening(s) in total)"
    )
