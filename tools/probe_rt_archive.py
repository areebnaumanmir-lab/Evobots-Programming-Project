"""Measure MISO's real-time price publication lag and the preliminary-RT archive depth.

Usage:
    python tools/probe_rt_archive.py [--config config/local.toml] [--today YYYY-MM-DD]

Needs internet: about 25 HEAD requests to docs.misoenergy.org, 0.6 s apart.
Prints:
  * the newest operating day with a final RT file ({date}_rt_lmp_final.csv), and the lag;
  * the newest and the oldest day with a preliminary RT file ({date}_rt_lmp_prelim.csv),
    found by binary search back to 2025-01-01, plus spot checks of older years.
Results from 2026-10-23 are in docs/market_rules.md §2.
"""

import argparse
import datetime
import ssl
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

MARKET_REPORTS_URL = "https://docs.misoenergy.org/marketreports/"
SECONDS_BETWEEN_REQUESTS = 0.6
OLDER_SPOT_CHECK_DAYS = [
    datetime.date(2023, 1, 1),
    datetime.date(2020, 1, 1),
    datetime.date(2015, 3, 1),
    datetime.date(2010, 6, 1),
    datetime.date(2005, 4, 1),
]


def user_agent_from_config(config_path):
    contact_email = ""
    if config_path.exists():
        with config_path.open("rb") as config_file:
            contact_email = tomllib.load(config_file).get("network", {}).get("contact_email", "")
    if contact_email:
        return f"evobots/0.1 (research; contact: {contact_email})"
    return "evobots/0.1 (research)"


def has_file(file_name, user_agent):
    """Return True when the market-reports server has the file (HTTP 200 to HEAD)."""
    request = urllib.request.Request(
        MARKET_REPORTS_URL + file_name, method="HEAD", headers={"User-Agent": user_agent}
    )
    time.sleep(SECONDS_BETWEEN_REQUESTS)
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl.create_default_context()):
            return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def newest_day_with(suffix, today, user_agent, days_back=10):
    for days_ago in range(days_back + 1):
        day = today - datetime.timedelta(days=days_ago)
        if has_file(f"{day:%Y%m%d}{suffix}", user_agent):
            return day
    return None


def oldest_day_with(suffix, newest_day, earliest_day, user_agent):
    """Binary search, assuming the files form one unbroken run ending at newest_day."""
    missing_day, present_day = earliest_day, newest_day
    while (present_day - missing_day).days > 1:
        middle_day = missing_day + (present_day - missing_day) // 2
        if has_file(f"{middle_day:%Y%m%d}{suffix}", user_agent):
            present_day = middle_day
        else:
            missing_day = middle_day
    return present_day


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/local.toml"))
    parser.add_argument("--today", type=datetime.date.fromisoformat, default=datetime.date.today())
    arguments = parser.parse_args()
    user_agent = user_agent_from_config(arguments.config)

    newest_final_day = newest_day_with("_rt_lmp_final.csv", arguments.today, user_agent)
    lag_days = (arguments.today - newest_final_day).days if newest_final_day else None
    print(f"newest final RT day: {newest_final_day} (lag {lag_days} days from {arguments.today})")

    newest_prelim_day = newest_day_with("_rt_lmp_prelim.csv", arguments.today, user_agent)
    print(f"newest preliminary RT day: {newest_prelim_day}")
    if newest_prelim_day is None:
        return
    earliest_day = datetime.date(2025, 1, 1)
    if has_file(f"{earliest_day:%Y%m%d}_rt_lmp_prelim.csv", user_agent):
        print(f"preliminary RT reaches back at least to {earliest_day}; extend the search")
        return
    oldest_prelim_day = oldest_day_with(
        "_rt_lmp_prelim.csv", newest_prelim_day, earliest_day, user_agent
    )
    print(f"oldest preliminary RT day: {oldest_prelim_day}")
    for day in OLDER_SPOT_CHECK_DAYS:
        is_present = has_file(f"{day:%Y%m%d}_rt_lmp_prelim.csv", user_agent)
        print(f"  {day}: preliminary file present = {is_present}")


if __name__ == "__main__":
    main()
