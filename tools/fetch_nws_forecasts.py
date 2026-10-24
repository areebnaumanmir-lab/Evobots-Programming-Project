"""Download the NWS Point Forecast Matrix a trader could see at each day's bid deadline.

Usage:
    python tools/fetch_nws_forecasts.py [--config config/local.toml] [--start 2005-03-31]
                                        [--end YYYY-MM-DD] [--offices MPX,ILX,...] [--workers 2]

Needs internet: one request per office per decision day to the Iowa Environmental Mesonet
(about 71,000 requests, ~1.4 GB). For decision day d it asks for the newest PFM issue entered
in the 24 hours before 10:30 Eastern Prevailing Time on d, the decision time for operating day
d+1 (CLAUDE.md §6.4, decided round 20). The same issue also serves as "yesterday's forecast"
for operating day d+2 (feature `temp_fcst_change`).

Polite (CLAUDE.md §5.4): at most --workers parallel requests (≤ 4), 0.5 s between requests per
worker, 3 retries with backoff, an empty answer recorded as "missing", write-then-rename, the
contact email in the User-Agent. Resumable from data/raw/nws/downloads.jsonl.

Sealed hold-out: files whose operating day d+1 falls in 2025-09-22 → 2026-09-21 go to
data/holdout/raw/nws/ and are never opened here except to hash them.
"""

import argparse
import datetime
import hashlib
import json
import ssl
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

RETRIEVE_URL = "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
RAW_DIRECTORY = Path("data/raw/nws")
HOLDOUT_RAW_DIRECTORY = Path("data/holdout/raw/nws")
DOWNLOAD_LOG_PATH = RAW_DIRECTORY / "downloads.jsonl"
# The nine forecast offices covering MISO's hubs (CLAUDE.md §7.4).
OFFICES = ("MPX", "LOT", "ILX", "IND", "DTX", "LZK", "JAN", "LCH", "LIX")
EASTERN = ZoneInfo("America/New_York")
DECISION_TIME = datetime.time(10, 30)
LOOKBACK = datetime.timedelta(hours=24)
HOLDOUT_FIRST_DAY = datetime.date(2025, 9, 22)
HOLDOUT_LAST_DAY = datetime.date(2026, 9, 21)
# Decision day for MISO's first operating day, 2005-04-01.
FIRST_DECISION_DAY = datetime.date(2005, 3, 31)
SECONDS_BETWEEN_REQUESTS = 0.5
RETRY_COUNT = 3
TIMEOUT_SECONDS = 60
MAX_WORKERS_PER_HOST = 4

log_lock = threading.Lock()


def user_agent_from_config(config_path):
    """User-Agent with the contact email from the git-ignored local config."""
    contact_email = ""
    if config_path.exists():
        with config_path.open("rb") as config_file:
            contact_email = tomllib.load(config_file).get("network", {}).get("contact_email", "")
    if not contact_email:
        sys.exit(f"Set [network] contact_email in {config_path} (see config/local.example.toml).")
    return f"evobots/0.1 (research; contact: {contact_email})"


def decision_cutoff_utc(decision_day):
    """10:30 Eastern Prevailing Time on the decision day, as an aware UTC datetime."""
    local = datetime.datetime.combine(decision_day, DECISION_TIME, tzinfo=EASTERN)
    return local.astimezone(datetime.UTC)


def is_holdout_decision_day(decision_day):
    """True when the operating day this forecast serves lies in the sealed hold-out."""
    operating_day = decision_day + datetime.timedelta(days=1)
    return HOLDOUT_FIRST_DAY <= operating_day <= HOLDOUT_LAST_DAY


def recorded_keys():
    """(office, decision day) pairs already downloaded or confirmed missing."""
    keys = set()
    if DOWNLOAD_LOG_PATH.exists():
        for line in DOWNLOAD_LOG_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if record["status"] in ("downloaded", "missing"):
                    keys.add((record["office"], record["decision_day"]))
    return keys


def append_log_record(record):
    with log_lock, DOWNLOAD_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True) + "\n")


def fetch_forecast(office, decision_day, user_agent):
    """Download the newest PFM issue before the cutoff; record it in the log."""
    cutoff = decision_cutoff_utc(decision_day)
    query = urllib.parse.urlencode(
        {
            "pil": f"PFM{office}",
            "sdate": (cutoff - LOOKBACK).strftime("%Y-%m-%dT%H:%MZ"),
            "edate": cutoff.strftime("%Y-%m-%dT%H:%MZ"),
            "fmt": "text",
            "limit": "1",
        }
    )
    url = f"{RETRIEVE_URL}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    status, error_text, body = "failed", "", b""
    for attempt in range(RETRY_COUNT + 1):
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            with urllib.request.urlopen(
                request, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context()
            ) as response:
                body = response.read()
            status = "downloaded" if b"PFM" in body[:400] else "missing"
            break
        except (urllib.error.URLError, OSError) as error:
            error_text = str(error)
        time.sleep(2 ** (attempt + 1))
    is_holdout = is_holdout_decision_day(decision_day)
    record = {
        "office": office,
        "decision_day": decision_day.isoformat(),
        "cutoff_utc": cutoff.isoformat(timespec="minutes"),
        "url": url,
        "is_holdout": is_holdout,
        "status": status,
        "retrieved_at_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    if status == "downloaded":
        directory = (HOLDOUT_RAW_DIRECTORY if is_holdout else RAW_DIRECTORY) / office
        directory.mkdir(parents=True, exist_ok=True)
        target_path = directory / f"{decision_day:%Y%m%d}.txt"
        partial_path = target_path.with_name(target_path.name + ".part")
        partial_path.write_bytes(body)
        partial_path.replace(target_path)
        record.update(
            {
                "path": str(target_path),
                "size_bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    elif status == "failed":
        record["error"] = error_text
    append_log_record(record)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/local.toml"))
    parser.add_argument("--start", type=datetime.date.fromisoformat, default=FIRST_DECISION_DAY)
    parser.add_argument("--end", type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument("--offices", default=",".join(OFFICES))
    parser.add_argument("--workers", type=int, default=2)
    arguments = parser.parse_args()
    if not 1 <= arguments.workers <= MAX_WORKERS_PER_HOST:
        sys.exit(f"--workers must be between 1 and {MAX_WORKERS_PER_HOST} (CLAUDE.md §5.4).")
    user_agent = user_agent_from_config(arguments.config)
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    done = recorded_keys()
    offices = arguments.offices.split(",")
    tasks = []
    day = arguments.start
    while day <= arguments.end:
        tasks += [(office, day) for office in offices if (office, day.isoformat()) not in done]
        day += datetime.timedelta(days=1)
    print(f"{len(tasks)} forecasts to fetch ({len(done)} already recorded)", flush=True)
    counts = {}
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        for index, status in enumerate(
            executor.map(lambda task: fetch_forecast(*task, user_agent), tasks), 1
        ):
            counts[status] = counts.get(status, 0) + 1
            if index % 500 == 0 or index == len(tasks):
                print(f"{index}/{len(tasks)} {counts}", flush=True)
    print(f"done: {counts}", flush=True)


if __name__ == "__main__":
    main()
