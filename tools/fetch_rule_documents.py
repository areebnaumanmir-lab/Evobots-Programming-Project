"""Download the documents behind docs/market_rules.md and check their SHA-256.

Usage:
    python tools/fetch_rule_documents.py [--config config/local.toml] [--output data/raw/rules]

Needs internet. Polite by design (CLAUDE.md §5.4): one request at a time, 1 s apart,
3 retries with backoff, 404 means "not there", write-then-rename. The contact email
for the User-Agent comes from the git-ignored config/local.toml.

A PDF whose hash differs from the one recorded here has been replaced on the server:
re-read it before trusting docs/market_rules.md. Help-centre pages are dynamic HTML,
so for them a changed hash is only a warning.
"""

import argparse
import hashlib
import ssl
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

# (file name, URL, SHA-256 when read on 2026-10-23). Keep in step with docs/market_rules.md §8.
RULE_DOCUMENTS = [
    (
        "virtual_trading_in_miso_624133.pdf",
        "https://cdn.misoenergy.org/Virtual%20Trading%20In%20MISO624133.pdf",
        "5c59d443745bff8e514710ad4b3abdad2643feac1c8f81b81e885bfda94d90df",
    ),
    (
        "attachment_l_586302.pdf",
        "https://cdn.misoenergy.org/Attachment%20L%20-%20Credit%20Policy586302.pdf",
        "025606b28c4d662fc17b5c187fd3091f79337b4c11ee171ecb1b033bf5f7df1a",
    ),
    (
        "er25_2845_707828.pdf",
        "https://cdn.misoenergy.org/2025-07-14%20Docket%20No.%20ER25-2845-000707828.pdf",
        "26c7666213b0eabcb3703d04a53636604265d8b939e0dd247a0daf3cb6d88ff5",
    ),
    (
        "cpett_20230915_630201.pdf",
        "https://cdn.misoenergy.org/20230915%20CPETT%20Item%2002-05%20Presentation630201.pdf",
        "e98e9e63df55ede0b4daf8835c8954e2c378ea38c7e5825890771d8495212b52",
    ),
    (
        "ms_op_029_r58_745017.pdf",
        "https://cdn.misoenergy.org/MS-OP-029-r58_Market_Settlements_5_Minute_Calculation_Guide"
        "_DRAFT%20(UDE%20changes)745017.pdf",
        "9c65862ab3e543d5bb3e2cf2dc99cc3a12e97768206854d595c70135d4bd4386",
    ),
    (
        "som_2022_appendix_629423.pdf",
        "https://cdn.misoenergy.org/2022%20State%20of%20the%20Market%20Analytical%20Appendix629423.pdf",
        "045c7e5e0631cbda32e2612b12b2e6c1afc2facfa8ec9ddc4f17e4e4b34e9a60",
    ),
    (
        "som_2024_appendix.pdf",
        "https://www.potomaceconomics.com/wp-content/uploads/2025/07/2024-MISO-SOM_Appendix_Final.pdf",
        "6392a233bb81d4f92fec9f68a1242a6617490014e3e7939d0f91bc99014bf8eb",
    ),
    (
        "ceepr_2017_003.pdf",
        "https://ceepr.mit.edu/wp-content/uploads/2021/09/2017-003.pdf",
        "3f6e196850bc0f46622a40be72cb478f3c1b8a2beb4a4fc7ad7cf76dc2827c7c",
    ),
    (
        "ferc_153_61317.pdf",
        "https://ferc.gov/sites/default/files/2020-05/E-8_57.pdf",
        "f0e34de44991dfb288c592b64dfcb24c7e960dd48f9106685c6c535f852c54d0",
    ),
    (
        "naesb_r05007_rec.doc",
        "https://www.naesb.org/pdf2/r05007_rec.doc",
        "a73d5d6527ec956eb7354756684e3f2bffddbfd66dd83b27f3d907c67fe7c34f",
    ),
    (
        "pjm_2027_business_calendar.pdf",
        "https://www.pjm.com/-/media/DotCom/markets-ops/settlements/2027-business-calendar.pdf",
        "9f4e1f05fd74867da3212fff86a68ab98a897bb2f1c7a46d241119a3fb9fc822",
    ),
    (
        "ka01129_da_timetable.html",
        "https://help.misoenergy.org/knowledgebase/article/KA-01129/en-us",
        "85daba287c9d361608c8e6e9ede2b601e4ee44b68defd797870870c931ae2b25",
    ),
    (
        "ka01086_credit_collateral.html",
        "https://help.misoenergy.org/knowledgebase/article/KA-01086/en-us",
        "993d466e94e44e780373f15dcceb3e0e55783134fe28a812c856aa23b77dda06",
    ),
]

SECONDS_BETWEEN_REQUESTS = 1.0
RETRY_COUNT = 3
TIMEOUT_SECONDS = 120


def user_agent_from_config(config_path):
    contact_email = ""
    if config_path.exists():
        with config_path.open("rb") as config_file:
            contact_email = tomllib.load(config_file).get("network", {}).get("contact_email", "")
    if not contact_email:
        sys.exit(f"Set [network] contact_email in {config_path} (see config/local.example.toml).")
    return f"evobots/0.1 (research; contact: {contact_email})"


def download_bytes(url, user_agent):
    """Return the body, or None for a 404. Retries other failures with backoff."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    context = ssl.create_default_context()
    for attempt in range(RETRY_COUNT + 1):
        try:
            with urllib.request.urlopen(
                request, timeout=TIMEOUT_SECONDS, context=context
            ) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if attempt == RETRY_COUNT:
                raise
        except (urllib.error.URLError, OSError):
            if attempt == RETRY_COUNT:
                raise
        time.sleep(2 ** (attempt + 1))
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/local.toml"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/rules"))
    arguments = parser.parse_args()
    user_agent = user_agent_from_config(arguments.config)
    arguments.output.mkdir(parents=True, exist_ok=True)
    has_changed_pdf = False
    for file_name, url, expected_sha256 in RULE_DOCUMENTS:
        body = download_bytes(url, user_agent)
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        if body is None:
            print(f"MISSING  {file_name}  (404 at {url})")
            continue
        partial_path = arguments.output / (file_name + ".part")
        partial_path.write_bytes(body)
        partial_path.replace(arguments.output / file_name)
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if actual_sha256 == expected_sha256:
            print(f"OK       {file_name}")
        elif file_name.endswith(".html"):
            print(f"CHANGED  {file_name}  (dynamic page; re-read it)")
        else:
            print(f"CHANGED  {file_name}  sha256 {actual_sha256}")
            has_changed_pdf = True
    sys.exit(1 if has_changed_pdf else 0)


if __name__ == "__main__":
    main()
