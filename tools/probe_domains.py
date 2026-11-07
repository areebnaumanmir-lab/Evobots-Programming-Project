"""Probe every data domain in docs/design_spec.md §7.9 with one polite HEAD request.

Usage:
    python tools/probe_domains.py [--config config/local.toml]

Prints a Markdown table (domain, result, HTTP status or error) for the round docs.
One request per domain, no retries: a blocked domain is reported, never worked
around (docs/design_spec.md §5.4 rule 2). The contact email for the User-Agent comes from
the git-ignored config/local.toml, never from code.
"""

import argparse
import ssl
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

# (domain, path) pairs. The path is the site root unless a small known file is cheaper.
PROBE_TARGETS = [
    ("docs.misoenergy.org", "/marketreports/"),
    ("cdn.misoenergy.org", "/"),
    ("www.misoenergy.org", "/"),
    ("help.misoenergy.org", "/"),
    ("mesonet.agron.iastate.edu", "/"),
    ("www.eia.gov", "/"),
    ("api.eia.gov", "/"),
    ("www.policyuncertainty.com", "/"),
    ("www.matteoiacoviello.com", "/"),
    ("thedocs.worldbank.org", "/"),
    ("oasis.caiso.com", "/"),
    ("www.ams.org", "/"),
    ("arxiv.org", "/"),
    ("export.arxiv.org", "/"),
    ("pypi.org", "/"),
    ("files.pythonhosted.org", "/"),
    ("github.com", "/"),
]

TIMEOUT_SECONDS = 20


def user_agent_from_config(config_path):
    contact_email = ""
    if config_path.exists():
        with config_path.open("rb") as config_file:
            contact_email = tomllib.load(config_file).get("network", {}).get("contact_email", "")
    if contact_email:
        return f"evobots/0.1 (research; environment probe; contact: {contact_email})"
    return "evobots/0.1 (research; environment probe)"


def probe(domain, path, user_agent):
    """Return (result, detail): result is 'reachable' or 'blocked' or 'error'."""
    request = urllib.request.Request(
        f"https://{domain}{path}", method="HEAD", headers={"User-Agent": user_agent}
    )
    # The default context reads SSL_CERT_FILE, which points at the environment's CA bundle.
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=context) as response:
            return "reachable", f"HTTP {response.status}"
    except urllib.error.HTTPError as error:
        # Any HTTP answer means the site itself was reached.
        return "reachable", f"HTTP {error.code}"
    except (urllib.error.URLError, OSError) as error:
        reason = str(getattr(error, "reason", error))
        if "403" in reason or "Tunnel connection failed" in reason:
            return "blocked", reason
        return "error", reason


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/local.toml"))
    arguments = parser.parse_args()
    user_agent = user_agent_from_config(arguments.config)
    print("| Domain | Result | Detail |")
    print("|---|---|---|")
    for domain, path in PROBE_TARGETS:
        result, detail = probe(domain, path, user_agent)
        print(f"| `{domain}` | {result} | {detail} |")


if __name__ == "__main__":
    main()
