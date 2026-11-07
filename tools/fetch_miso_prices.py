"""Download MISO's day-ahead and real-time LMP archive for every location, 2005-04 to today.

Usage:
    python tools/fetch_miso_prices.py [--config config/local.toml] [--start 2005-04-01]
                                      [--end YYYY-MM-DD] [--workers 2]
                                      [--report prices|cleared_bids]

Needs internet (prices about 5.5 GB; cleared bids about 4 GB). Resumable: files already on
disk with a recorded SHA-256 are skipped. Polite (docs/design_spec.md §5.4): at most --workers
parallel
requests (≤ 4), 0.5 s between requests per worker, 3 retries with backoff, 404 recorded as
"file doesn't exist", write-then-rename, and every file's URL, SHA-256, size and download
time recorded.

Sealed hold-out (docs/design_spec.md §7.2): files whose operating day falls in 2025-09-22 →
2026-09-21
are written to data/holdout/raw/miso/ and are never opened here except to hash them.
Everything else goes to data/raw/miso/. The download log is data/raw/miso/downloads.jsonl;
tools/write_data_manifest.py turns it into data/manifest.toml.

File eras (docs/design_spec.md §7.3):
    2005-04 → 2015-01   {YYYYMM}_da_lmp_csv.zip            {YYYYMM}_rt_lmp_final_csv.zip
    2015-02             both {YYYYMM}_da_lmp_csv.zip and {YYYYMM}_da_expost_lmp_csv.zip
    2015-03 → 2022-12   {YYYYMM}_da_expost_lmp_csv.zip     {YYYYMM}_rt_lmp_final_csv.zip
    2023-01 → today     {YYYYMMDD}_da_expost_lmp.csv       {YYYYMMDD}_rt_lmp_final.csv

--report cleared_bids (docs/design_spec.md §6.2, §20.12): for every day from 2023-01-01, the cleared
virtual bids {YYYYMMDD}_bids_cb.zip and the DA ex-ante prices {YYYYMMDD}_da_exante_lmp.csv
used to attribute them to hubs. Cleared bids appear about 90 days late (obs., 2026-10-24:
newest 2026-07-25), so a recent 404 is retried for CLEARED_BIDS_RETRY_MISSING_DAYS.
"""

import argparse
import datetime
import hashlib
import http.client
import json
import ssl
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MARKET_REPORTS_URL = "https://docs.misoenergy.org/marketreports/"
RAW_DIRECTORY = Path("data/raw/miso")
HOLDOUT_RAW_DIRECTORY = Path("data/holdout/raw/miso")
DOWNLOAD_LOG_PATH = RAW_DIRECTORY / "downloads.jsonl"
# Sealed hold-out, docs/design_spec.md §7.2.
HOLDOUT_FIRST_DAY = datetime.date(2025, 9, 22)
HOLDOUT_LAST_DAY = datetime.date(2026, 9, 21)
# MISO's energy market opened on 2005-04-01; nothing older is on the server (obs., 2026-10-24).
MARKET_FIRST_DAY = datetime.date(2005, 4, 1)
FIRST_DAILY_FILE_DAY = datetime.date(2023, 1, 1)
SECONDS_BETWEEN_REQUESTS = 0.5
RETRY_COUNT = 3
TIMEOUT_SECONDS = 180
MAX_WORKERS_PER_HOST = 4
# A 404 for a day younger than this is retried later: the file may not be published yet.
RETRY_MISSING_DAYS = 14
# Cleared bids are published about 90 days after the operating day (obs., 2026-10-24).
CLEARED_BIDS_RETRY_MISSING_DAYS = 150

log_lock = threading.Lock()


def user_agent_from_config(config_path):
    """Return the User-Agent with the contact email from the git-ignored local config."""
    contact_email = ""
    if config_path.exists():
        with config_path.open("rb") as config_file:
            contact_email = tomllib.load(config_file).get("network", {}).get("contact_email", "")
    if not contact_email:
        sys.exit(f"Set [network] contact_email in {config_path} (see config/local.example.toml).")
    return f"evobots/0.1 (research; contact: {contact_email})"


def month_starts(first_day, last_day):
    """Yield the first day of every month from first_day's month to last_day's month."""
    month_start = first_day.replace(day=1)
    while month_start <= last_day:
        yield month_start
        month_start = (month_start + datetime.timedelta(days=32)).replace(day=1)


def planned_files(first_day, last_day):
    """Return (file_name, market, first_operating_day, last_operating_day) for every file."""
    files = []
    monthly_last_day = min(last_day, FIRST_DAILY_FILE_DAY - datetime.timedelta(days=1))
    for month_start in month_starts(first_day, monthly_last_day):
        month_end = (month_start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(
            days=1
        )
        month_text = f"{month_start:%Y%m}"
        if month_start < datetime.date(2015, 3, 1):
            files.append((f"{month_text}_da_lmp_csv.zip", "da", month_start, month_end))
        if month_start >= datetime.date(2015, 2, 1):
            files.append((f"{month_text}_da_expost_lmp_csv.zip", "da", month_start, month_end))
        files.append((f"{month_text}_rt_lmp_final_csv.zip", "rt", month_start, month_end))
    day = max(first_day, FIRST_DAILY_FILE_DAY)
    while day <= last_day:
        files.append((f"{day:%Y%m%d}_da_expost_lmp.csv", "da", day, day))
        files.append((f"{day:%Y%m%d}_rt_lmp_final.csv", "rt", day, day))
        day += datetime.timedelta(days=1)
    return files


def planned_cleared_bid_files(first_day, last_day):
    """Return (file_name, market, first_operating_day, last_operating_day) for cleared bids."""
    files = []
    day = max(first_day, FIRST_DAILY_FILE_DAY)
    while day <= last_day:
        files.append((f"{day:%Y%m%d}_bids_cb.zip", "cleared_bids", day, day))
        files.append((f"{day:%Y%m%d}_da_exante_lmp.csv", "da_exante", day, day))
        day += datetime.timedelta(days=1)
    return files


def is_holdout_file(first_operating_day, last_operating_day):
    """True when any operating day in the file lies in the sealed hold-out."""
    return first_operating_day <= HOLDOUT_LAST_DAY and last_operating_day >= HOLDOUT_FIRST_DAY


def recorded_file_names(today):
    """Names already downloaded, or confirmed missing long enough ago not to retry.

    A recent operating day's file may simply not be published yet (final RT appears about
    4-5 days late, docs/market_rules.md §2.2), so a 404 younger than RETRY_MISSING_DAYS
    is retried on the next run.
    """
    names = set()
    if DOWNLOAD_LOG_PATH.exists():
        for line in DOWNLOAD_LOG_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                last_day = datetime.date.fromisoformat(record["last_operating_day"])
                retry_days = (
                    CLEARED_BIDS_RETRY_MISSING_DAYS
                    if record["market"] == "cleared_bids"
                    else RETRY_MISSING_DAYS
                )
                is_settled_missing = (
                    record["status"] == "missing" and (today - last_day).days > retry_days
                )
                if record["status"] == "downloaded" or is_settled_missing:
                    names.add(record["file_name"])
    return names


def append_log_record(record):
    with log_lock, DOWNLOAD_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True) + "\n")


def download_file(planned_file, user_agent):
    """Download one file with retries; record it in the log. Returns the status string."""
    file_name, market, first_operating_day, last_operating_day = planned_file
    is_holdout = is_holdout_file(first_operating_day, last_operating_day)
    target_directory = HOLDOUT_RAW_DIRECTORY if is_holdout else RAW_DIRECTORY
    target_path = target_directory / file_name
    url = MARKET_REPORTS_URL + file_name
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    context = ssl.create_default_context()
    status = "failed"
    error_text = ""
    body = b""
    for attempt in range(RETRY_COUNT + 1):
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            with urllib.request.urlopen(
                request, timeout=TIMEOUT_SECONDS, context=context
            ) as response:
                body = response.read()
                expected_size = response.headers.get("Content-Length")
            if expected_size is not None and int(expected_size) != len(body):
                raise OSError(f"truncated: {len(body)} of {expected_size} bytes")
            status = "downloaded"
            break
        except urllib.error.HTTPError as error:
            if error.code == 404:
                status = "missing"
                break
            error_text = f"HTTP {error.code}"
        # A truncated chunked response raises IncompleteRead, an HTTPException.
        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            error_text = str(error)
        time.sleep(2 ** (attempt + 1))
    record = {
        "file_name": file_name,
        "url": url,
        "market": market,
        "first_operating_day": first_operating_day.isoformat(),
        "last_operating_day": last_operating_day.isoformat(),
        "is_holdout": is_holdout,
        "status": status,
        "retrieved_at_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    if status == "downloaded":
        partial_path = target_path.with_name(target_path.name + ".part")
        partial_path.write_bytes(body)
        partial_path.replace(target_path)
        record["path"] = str(target_path)
        record["size_bytes"] = len(body)
        record["sha256"] = hashlib.sha256(body).hexdigest()
    elif status == "failed":
        record["error"] = error_text
    append_log_record(record)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/local.toml"))
    parser.add_argument("--start", type=datetime.date.fromisoformat, default=MARKET_FIRST_DAY)
    parser.add_argument("--end", type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--report", choices=("prices", "cleared_bids"), default="prices")
    arguments = parser.parse_args()
    if not 1 <= arguments.workers <= MAX_WORKERS_PER_HOST:
        sys.exit(f"--workers must be between 1 and {MAX_WORKERS_PER_HOST} (design spec §5.4).")
    user_agent = user_agent_from_config(arguments.config)
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    HOLDOUT_RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)

    already_done = recorded_file_names(datetime.date.today())
    plan = planned_files if arguments.report == "prices" else planned_cleared_bid_files
    to_fetch = [
        planned_file
        for planned_file in plan(arguments.start, arguments.end)
        if planned_file[0] not in already_done
    ]
    print(f"{len(to_fetch)} files to fetch ({len(already_done)} already recorded)", flush=True)
    status_counts = {}
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        for index, status in enumerate(
            executor.map(lambda planned_file: download_file(planned_file, user_agent), to_fetch), 1
        ):
            status_counts[status] = status_counts.get(status, 0) + 1
            if index % 100 == 0 or index == len(to_fetch):
                print(f"{index}/{len(to_fetch)} {status_counts}", flush=True)
    print(f"done: {status_counts}", flush=True)


if __name__ == "__main__":
    main()
