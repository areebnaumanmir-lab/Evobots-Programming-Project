"""Download the small keyless series files once: gas, oil, policy uncertainty, risk, capacity.

Usage:
    python tools/fetch_series.py [--only fred_dtb3,epu] [--force]
    python tools/fetch_series.py --eia-860m-vintages 2016-01,2017-01

The second form downloads archived EIA-860M monthly workbooks (source "eia_860m_archive"),
used to measure how much EIA corrects past months between vintages (docs/design_spec.md §7.8).

Each source is one file (docs/design_spec.md §7.5–7.8, round 28 for FRED). Files go to
data/raw/series/<source>/ with write-then-rename, and every attempt is appended to
data/raw/series/downloads.jsonl (URL, SHA-256, size, UTC time) for data/manifest.toml.
A file already logged as downloaded is skipped unless --force is given; a later --force
download keeps the earlier copy under its own date, so revisions can be compared
(EIA-860M corrections, EPU's 30-day revisions; docs/design_spec.md §7.7–7.8).

The files hold whole time series that run into the sealed hold-out (2025-09-22 →
2026-09-21). They are stored whole; the readers in src/evobots/data/sources/ cut every
series at the end of the evolution period unless the hold-out accessor gives permission.

Politeness (docs/design_spec.md §5.4): one request at a time, 0.5 s apart, 3 retries with backoff,
a User-Agent with the contact email from the git-ignored config/local.toml. The Pink Sheet
URL changes with each monthly release; it is read from the World Bank's commodity-markets
page. EIA-860M's newest monthly file is found by stepping back month by month: a
superseded month answers with a redirect to the archive.
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

RAW_DIRECTORY = Path("data/raw/series")
DOWNLOAD_LOG_PATH = RAW_DIRECTORY / "downloads.jsonl"
CONFIG_PATH = Path("config/local.toml")
SECONDS_BETWEEN_REQUESTS = 0.5
RETRY_COUNT = 3
TIMEOUT_SECONDS = 120
# The World Bank commodity-markets page links the current monthly Pink Sheet file.
PINK_SHEET_PAGE_URL = "https://www.worldbank.org/en/research/commodity-markets"
PINK_SHEET_LINK_PATTERN = re.compile(
    r"https://thedocs\.worldbank\.org/[^\"']*CMO-Historical-Data-Monthly\.xlsx"
)
EIA_GENERATOR_INVENTORY_URL_TEMPLATE = (
    "https://www.eia.gov/electricity/data/eia860m/xls/{month_name}_generator{year}.xlsx"
)
EIA_GENERATOR_INVENTORY_MONTHS_TO_TRY = 6
EIA_GENERATOR_INVENTORY_ARCHIVE_URL_TEMPLATE = (
    "https://www.eia.gov/electricity/data/eia860m/archive/xls/{month_name}_generator{year}.xlsx"
)
FIXED_URL_BY_SOURCE = {
    # Risk-free rate (round 28): 3-month T-bill, discount basis, percent, daily.
    "fred_dtb3": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3",
    # Henry Hub natural gas spot, $/MMBtu, daily (bot input, features 19–21).
    "eia_henry_hub": "https://www.eia.gov/dnav/ng/hist_xls/RNGWHHDd.xls",
    # WTI crude spot, $/barrel, daily (reporting only).
    "eia_wti": "https://www.eia.gov/dnav/pet/hist_xls/RWTCd.xls",
    # US Economic Policy Uncertainty, daily (bot input, feature 22).
    "epu": "https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv",
    # Geopolitical Risk, daily (reporting only).
    "gpr": "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls",
}
ALL_SOURCES = (*FIXED_URL_BY_SOURCE, "worldbank_pink_sheet", "eia_860m")


def user_agent_from_config(config_path):
    """User-Agent with the contact email from the git-ignored local config."""
    contact_email = ""
    if config_path.exists():
        with config_path.open("rb") as config_file:
            contact_email = tomllib.load(config_file).get("network", {}).get("contact_email", "")
    if not contact_email:
        sys.exit(f"Set [network] contact_email in {config_path} (see config/local.example.toml).")
    return f"evobots/0.1 (research; contact: {contact_email})"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Report redirects as errors, so a superseded EIA-860M month is recognised."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def response_status_and_body(url, user_agent, can_follow_redirects=True):
    """(HTTP status, body bytes or None) for one GET, with retries on network errors."""
    handlers = [] if can_follow_redirects else [NoRedirectHandler()]
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    for attempt in range(RETRY_COUNT + 1):
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308, 404):
                return error.code, None
            if attempt == RETRY_COUNT:
                return error.code, None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == RETRY_COUNT:
                print(f"  failed: {url}: {error}", flush=True)
                return None, None
        time.sleep(2**attempt)
    return None, None


def pink_sheet_url(user_agent):
    """The current Pink Sheet file's URL, read from the commodity-markets page."""
    status, body = response_status_and_body(PINK_SHEET_PAGE_URL, user_agent)
    if status != 200 or body is None:
        return None
    links = sorted(set(PINK_SHEET_LINK_PATTERN.findall(body.decode("utf-8", "replace"))))
    return links[0] if links else None


def newest_eia_860m_url(user_agent, today):
    """The newest EIA-860M monthly file that is still on the current (non-archive) path."""
    year, month = today.year, today.month
    for _ in range(EIA_GENERATOR_INVENTORY_MONTHS_TO_TRY):
        month_name = datetime.date(year, month, 1).strftime("%B").lower()
        url = EIA_GENERATOR_INVENTORY_URL_TEMPLATE.format(month_name=month_name, year=year)
        status, _ = response_status_and_body(url, user_agent, can_follow_redirects=False)
        if status == 200:
            return url
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return None


def logged_records():
    """Every record in the download log, oldest first."""
    if not DOWNLOAD_LOG_PATH.exists():
        return []
    return [
        json.loads(line)
        for line in DOWNLOAD_LOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def download_source(source, url, user_agent):
    """Download one source file with write-then-rename and return its log record."""
    retrieved_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    status, body = response_status_and_body(url, user_agent)
    record = {
        "source": source,
        "url": url,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "http_status": status,
    }
    if status != 200 or body is None:
        record["status"] = "missing" if status == 404 else "failed"
        return record
    original_name = url.rsplit("/", 1)[-1].split("?")[0]
    if source == "fred_dtb3":
        original_name = "DTB3.csv"
    file_name = f"{retrieved_at.date().isoformat()}_{original_name}"
    directory = RAW_DIRECTORY / source
    directory.mkdir(parents=True, exist_ok=True)
    temporary_path = directory / (file_name + ".part")
    temporary_path.write_bytes(body)
    temporary_path.replace(directory / file_name)
    record.update(
        status="downloaded",
        file_name=f"{source}/{file_name}",
        sha256=hashlib.sha256(body).hexdigest(),
        size_bytes=len(body),
    )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="comma-separated sources (default: all)")
    parser.add_argument("--force", action="store_true", help="download again even if logged")
    parser.add_argument(
        "--eia-860m-vintages", default="", help="comma-separated YYYY-MM archived workbooks"
    )
    arguments = parser.parse_args()
    if arguments.eia_860m_vintages:
        user_agent = user_agent_from_config(CONFIG_PATH)
        logged_urls = {
            record["url"] for record in logged_records() if record["status"] == "downloaded"
        }
        for vintage in arguments.eia_860m_vintages.split(","):
            year, month = (int(part) for part in vintage.split("-"))
            month_name = datetime.date(year, month, 1).strftime("%B").lower()
            url = EIA_GENERATOR_INVENTORY_ARCHIVE_URL_TEMPLATE.format(
                month_name=month_name, year=year
            )
            if url in logged_urls:
                print(f"{vintage}: already downloaded", flush=True)
                continue
            record = download_source("eia_860m_archive", url, user_agent)
            with DOWNLOAD_LOG_PATH.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(record, sort_keys=True) + "\n")
            print(f"{vintage}: {record['status']} {record.get('size_bytes', '')}", flush=True)
        return
    sources = [name for name in arguments.only.split(",") if name] or list(ALL_SOURCES)
    unknown = sorted(set(sources) - set(ALL_SOURCES))
    if unknown:
        sys.exit(f"Unknown sources: {unknown}. Known: {list(ALL_SOURCES)}")
    user_agent = user_agent_from_config(CONFIG_PATH)
    downloaded_sources = {
        record["source"] for record in logged_records() if record["status"] == "downloaded"
    }
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if source in downloaded_sources and not arguments.force:
            print(f"{source}: already downloaded (use --force for a new copy)", flush=True)
            continue
        if source == "worldbank_pink_sheet":
            url = pink_sheet_url(user_agent)
        elif source == "eia_860m":
            url = newest_eia_860m_url(user_agent, datetime.date.today())
        else:
            url = FIXED_URL_BY_SOURCE[source]
        if url is None:
            print(f"{source}: could not find the current file's URL", flush=True)
            continue
        record = download_source(source, url, user_agent)
        with DOWNLOAD_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, sort_keys=True) + "\n")
        print(f"{source}: {record['status']} {record.get('size_bytes', '')} {url}", flush=True)


if __name__ == "__main__":
    main()
