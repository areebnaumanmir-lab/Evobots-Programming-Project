"""Daily point-in-time vintages of the revisable series (M9; `docs/design_spec.md` §7.6–7.7).

EPU is revised for about 30 days after publication, and GPR and Henry Hub files are
re-issued whole, so a history downloaded today may differ from what a trader could see on
the day. From now on `evobots paper --fetch` saves each day's copy of the three files under
`data/vintages/<source>/<YYYY-MM-DD>_<file name>` (git-ignored), so forward tests can use
true point-in-time values. This needs internet; everything else works offline.

Politeness as in `tools/fetch_series.py`: one request at a time, 0.5 s apart, a User-Agent
with the contact email from the git-ignored `config/local.toml`. MISO files are never
fetched (its terms forbid automated access; drop them into `data/inbox/miso/`).

Example:
    >>> vintage_path(Path("data/vintages"), "epu", "https://x/All_Daily_Policy_Data.csv",
    ...     datetime.date(2026, 11, 7)).as_posix()
    'data/vintages/epu/2026-11-07_All_Daily_Policy_Data.csv'
"""

import datetime
import hashlib
import time
import tomllib
import urllib.request
from pathlib import Path

VINTAGE_DIRECTORY = Path("data/vintages")
CONFIG_PATH = Path("config/local.toml")
URL_BY_SOURCE = {
    "epu": "https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv",
    "gpr": "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls",
    "eia_henry_hub": "https://www.eia.gov/dnav/ng/hist_xls/RNGWHHDd.xls",
}
SECONDS_BETWEEN_REQUESTS = 0.5
TIMEOUT_SECONDS = 120


def vintage_path(directory, source, url, day):
    """Where one day's copy of a source's file goes."""
    return Path(directory) / source / f"{day.isoformat()}_{url.rsplit('/', 1)[-1]}"


def user_agent(config_path=CONFIG_PATH):
    """The User-Agent with the contact email, or None when the local config has none."""
    if not Path(config_path).exists():
        return None
    with Path(config_path).open("rb") as handle:
        email = tomllib.load(handle).get("network", {}).get("contact_email", "")
    return f"evobots/0.1 (research; contact: {email})" if email else None


def save_vintages(directory=VINTAGE_DIRECTORY, today=None, opener=urllib.request.urlopen):
    """Download today's copy of each file once; returns one line per source."""
    today = today or datetime.date.today()
    agent = user_agent()
    if agent is None:
        return [f"Set [network] contact_email in {CONFIG_PATH} first (config/local.example.toml)."]
    lines = []
    for source, url in URL_BY_SOURCE.items():
        path = vintage_path(directory, source, url, today)
        if path.exists():
            lines.append(f"{source}: already saved today ({path})")
            continue
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": agent})
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read()
        except OSError as error:
            lines.append(f"{source}: not saved ({error}); try again later")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".part")
        partial.write_bytes(body)
        partial.replace(path)
        digest = hashlib.sha256(body).hexdigest()[:12]
        lines.append(f"{source}: saved {path} ({len(body):,} bytes, sha256 {digest}…)")
    return lines
