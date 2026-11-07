"""Paper trading on forward data (M9; `docs/design_spec.md` §7.2, §12.4, §15).

The deployable bot (or a named trader) trades the trading hubs on forward days, 2026-09-22
onward, with simulated money and the same rules as evolution (sizing, credit limit, daily
cap, fees, death). Nothing is sent to MISO.

**Inputs.** MISO's daily files for forward days, dropped by hand into `data/inbox/miso/`
(or already in `data/raw/miso/`): `{YYYYMMDD}_da_expost_lmp.csv` and
`{YYYYMMDD}_rt_lmp_final.csv`. MISO's terms forbid automated downloads, so there is no
MISO fetcher (round 25). Gas and policy uncertainty come from the downloaded series files,
forward dates included; `evobots paper fetch` (needs internet) saves today's copies of the
EPU, GPR and Henry Hub files as dated vintages.

**The sealed year stays sealed.** Features look back up to 400 days, and the days before
2026-09-22 are the hold-out. Those days are treated as missing here (never read), so a
feature whose window reaches into them is missing and the bot doesn't trade on it. Spread
statistics fill in after about 33 forward days; the hub-area code after 90. This is the
price of keeping the hold-out clean (a decision for Areeb to revisit once the run's final
test is spent).

**Sizing.** The position scale uses the trader's last 365 *observed* days of full-size P&L
(`evobots.simulate.settlement`), so across the sealed year it uses the evolution period's
last year: real history, not the hold-out.

**Ledger.** For every forward day with both DA and final RT: bids, cleared MWh, P&L after
fees, equity, the position scale. Days with DA but no final RT yet are "waiting for RT".
The next operating day's bids (the day after the newest DA file) are listed with their
full-size MW, the current position scale and the limit prices.

Outputs, under `runs/paper/<run>/`: `ledger.csv`, `bids_<day>.csv`, `summary.json`.

Example:
    >>> import datetime
    >>> forward_days_with_files([], datetime.date(2026, 9, 22))
    []
"""

import csv
import dataclasses
import datetime
import json
from pathlib import Path

import numpy as np

from evobots.config.capital import STAGE_A_HUBS
from evobots.data.periods import FORWARD_FIRST_DAY, HOLDOUT_FIRST_DAY, MARKET_FIRST_DAY
from evobots.data.sources.miso_eras import file_and_member_for, read_day
from evobots.simulate.market import HubMarket, read_miso_hub_market

INBOX_DIRECTORY = Path("data/inbox/miso")
RAW_DIRECTORY = Path("data/raw/miso")
PAPER_DIRECTORY = Path("runs/paper")
HOURS_PER_DAY = 24
LEDGER_COLUMNS = (
    "day",
    "status",
    "bids",
    "cleared_mwh",
    "fees_usd",
    "pnl_usd",
    "equity_usd",
    "position_scale",
)


def forward_days_with_files(directories, first_day=FORWARD_FIRST_DAY, today=None):
    """Forward operating days whose DA file is in one of the directories, in order."""
    today = today or datetime.date.today()
    days = []
    day = first_day
    while day <= today + datetime.timedelta(days=1):
        name, _ = file_and_member_for(day, "da")
        if any((Path(directory) / name).exists() for directory in directories):
            days.append(day)
        day += datetime.timedelta(days=1)
    return days


def read_forward_day(directories, day, market):
    """A forward day's prices from the first directory that has them, or None."""
    for directory in directories:
        prices = read_day(directory, day, market)
        if prices is not None:
            return prices
    return None


def paper_market(root=Path("."), directories=None, today=None):
    """The trading hubs from 2005 to the day after the newest forward DA file.

    Evolution-period prices come from the Stage A store; hold-out days are NaN (not read);
    forward days are read from the inbox or the raw archive. The last day is the next
    operating day, unpriced, so its bids can be computed.

    Returns:
        (HubMarket, newest DA day or None).
    """
    root = Path(root)
    directories = directories or [root / INBOX_DIRECTORY, root / RAW_DIRECTORY]
    history = read_miso_hub_market(
        root / "data/store/hub_prices.csv.gz", root / "data/store/hub_arrays.npz"
    )
    if history is None:
        return None, None
    forward_days = forward_days_with_files(directories, today=today)
    newest = forward_days[-1] if forward_days else None
    last_day = (newest or FORWARD_FIRST_DAY - datetime.timedelta(days=1)) + datetime.timedelta(
        days=1
    )
    day_count = (last_day - MARKET_FIRST_DAY).days + 1
    hubs = tuple(STAGE_A_HUBS)
    shape = (day_count, HOURS_PER_DAY, len(hubs))
    day_ahead, real_time, congestion = (np.full(shape, np.nan) for _ in range(3))
    offset = (history.days[0] - MARKET_FIRST_DAY).days
    columns = [history.hubs.index(hub) for hub in hubs]
    span = slice(offset, offset + len(history.days))
    day_ahead[span] = history.day_ahead[:, :, columns]
    real_time[span] = history.real_time[:, :, columns]
    if history.day_ahead_congestion is not None:
        congestion[span] = history.day_ahead_congestion[:, :, columns]
    for day in forward_days:
        index = (day - MARKET_FIRST_DAY).days
        for market, target in (("da", day_ahead), ("rt", real_time)):
            prices = read_forward_day(directories, day, market)
            if prices is None:
                continue
            for column, hub in enumerate(hubs):
                hours = prices.hours_by_location_and_value.get((hub, "LMP"))
                if hours is not None:
                    target[index, :, column] = [
                        np.nan if value is None else value for value in hours
                    ]
                mcc = prices.hours_by_location_and_value.get((hub, "MCC"))
                if market == "da" and mcc is not None:
                    congestion[index, :, column] = [
                        np.nan if value is None else value for value in mcc
                    ]
    days = tuple(MARKET_FIRST_DAY + datetime.timedelta(days=offset) for offset in range(day_count))
    market = HubMarket(days, hubs, day_ahead, real_time, "MISO (paper)", congestion, None)
    return market, newest


@dataclasses.dataclass
class PaperResult:
    """One paper-trading pass."""

    ledger: list
    next_day: datetime.date | None
    next_bids: list
    summary: dict


def paper_trade(genome, evaluator, newest_da_day, label):
    """Settle the forward days and list the next day's bids.

    Args:
        genome: the trader (None: "do nothing", an empty ledger with zero P&L).
        evaluator: an Evaluator over `paper_market` (features with forward inputs).
        newest_da_day: the newest forward day with a DA file.
        label: who is trading ("R101 deployable bot", "R101-29627", …).

    Returns:
        A PaperResult.
    """
    from evobots.bots.trader import trader_decisions
    from evobots.simulate.settlement import SIZING_HISTORY_DAYS, settle

    days = evaluator.store.days
    start = days.index(FORWARD_FIRST_DAY) if FORWARD_FIRST_DAY in days else len(days) - 1
    end = len(days) - 1  # the last day is the next operating day, not yet priced
    capital = evaluator.capital.starting_capital_usd
    ledger = []
    next_bids = []
    market = evaluator.market
    if genome is not None and end > start:
        # Sizing reads the last 365 observed days; the sealed year isn't observed here, so
        # the history reaches back past it to the end of the evolution period.
        gap_start = days.index(HOLDOUT_FIRST_DAY) if HOLDOUT_FIRST_DAY in days else start
        history_start = max(0, gap_start - SIZING_HISTORY_DAYS)
        decisions = trader_decisions(
            genome, evaluator.store, history_start, end + 1, evaluator.caps_mw
        )
        result = settle(
            decisions,
            market,
            start,
            end,
            evaluator.account_rules(genome),
            evaluator.cost_table,
            history_start=history_start,
        )
        offset = start - decisions.first_day_index
        for position, index in enumerate(range(start, end)):
            has_da = not np.isnan(market.day_ahead[index]).all()
            has_rt = not np.isnan(market.real_time[index]).all()
            status = "settled" if has_da and has_rt else "waiting for RT" if has_da else "no file"
            bids = int((decisions.side[offset + position] != 0).sum())
            cleared = result.cleared_dec_mwh[position] + result.cleared_inc_mwh[position]
            ledger.append(
                [
                    days[index].isoformat(),
                    status,
                    bids,
                    round(float(cleared), 1),
                    round(float(result.fees_usd[position]), 2),
                    round(float(result.daily_pnl_usd[position]), 2),
                    round(float(result.equity_usd[position]), 2),
                    round(float(result.position_scale[position]), 4),
                ]
            )
        scale = float(result.position_scale[-1]) if len(result.position_scale) else 0.0
        last = offset + (end - start)
        for hour in range(HOURS_PER_DAY):
            for column, hub in enumerate(market.hubs):
                side = int(decisions.side[last, hour, column])
                if side == 0:
                    continue
                next_bids.append(
                    {
                        "hub": hub,
                        "hour_ending": hour + 1,
                        "side": "DEC" if side > 0 else "INC",
                        "full_size_mw": round(float(decisions.full_size_mw[last, hour, column]), 1),
                        "position_scale": round(scale, 4),
                        "limit_usd_per_mwh": round(
                            float(decisions.limit_usd_per_mwh[last, hour, column]), 2
                        ),
                    }
                )
    else:
        for index in range(start, end):
            has_da = not np.isnan(market.day_ahead[index]).all()
            has_rt = not np.isnan(market.real_time[index]).all()
            status = "settled" if has_da and has_rt else "waiting for RT" if has_da else "no file"
            ledger.append([days[index].isoformat(), status, 0, 0.0, 0.0, 0.0, capital, 0.0])
    settled = [row for row in ledger if row[1] == "settled"]
    final_equity = settled[-1][6] if settled else capital
    summary = {
        "trader": label,
        "is_doing_nothing": genome is None,
        "first_forward_day": FORWARD_FIRST_DAY.isoformat(),
        "newest_da_day": newest_da_day.isoformat() if newest_da_day else None,
        "settled_days": len(settled),
        "waiting_days": sum(1 for row in ledger if row[1] == "waiting for RT"),
        "starting_capital_usd": capital,
        "equity_usd": final_equity,
        "pnl_usd": round(final_equity - capital, 2),
        "cleared_mwh": round(sum(row[3] for row in settled), 1),
        "next_day": days[end].isoformat() if newest_da_day else None,
        "next_bids": len(next_bids),
        "note": (
            "Hold-out days (2025-09-22 → 2026-09-21) are missing, never read, so features "
            "that look back into them are missing for the first forward weeks."
        ),
    }
    return PaperResult(ledger, days[end] if newest_da_day else None, next_bids, summary)


def write_paper_result(result, directory):
    """Write ledger.csv, bids_<day>.csv and summary.json."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "ledger.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(LEDGER_COLUMNS)
        writer.writerows(result.ledger)
    if result.next_day:
        fields = [
            "hub",
            "hour_ending",
            "side",
            "full_size_mw",
            "position_scale",
            "limit_usd_per_mwh",
        ]
        with (directory / f"bids_{result.next_day.isoformat()}.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(result.next_bids)
    (directory / "summary.json").write_text(json.dumps(result.summary, indent=2), encoding="utf-8")


def read_paper_result(directory):
    """(summary, ledger rows, next bids) from a written pass, or None."""
    directory = Path(directory)
    if not (directory / "summary.json").exists():
        return None
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    with (directory / "ledger.csv").open(encoding="utf-8") as handle:
        ledger = list(csv.DictReader(handle))
    bids = []
    if summary.get("next_day"):
        path = directory / f"bids_{summary['next_day']}.csv"
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                bids = list(csv.DictReader(handle))
    return summary, ledger, bids
