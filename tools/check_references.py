"""Check every reference in docs/references.csv against Crossref (and arXiv) and save abstracts.

Usage:
    python tools/check_references.py [--config config/local.toml]

Needs internet: one request per reference to api.crossref.org, one to
api.semanticscholar.org for an abstract Crossref lacks, and export.arxiv.org for arXiv
entries; 1 s apart. (OpenAlex was tried first; its search now needs paid credits.)
For each reference it finds the best title match, then checks
the first author's surname and the year (±1, for online-first vs issue dates).

Writes:
  docs/data/references_checked.json  metadata and abstract per reference (the evidence)
  docs/references.md                 the bibliography, with each entry's check status

Status values: "verified" (title, surname and year match), "partial" (title matches but the
surname or year doesn't; read the note), "manual" (no Crossref or arXiv record, but the
`manual_record` column of references.csv names the primary record that was read, e.g. a
conference bibliography entry or the paper's PDF; added in round 27), "not found". Only
"verified" and "manual" entries may be cited without a [verify] marker (CLAUDE.md §2.2).

Abstracts already saved in references_checked.json are reused when the DOI is unchanged, so a
rerun asks Semantic Scholar only for new entries.
"""

import argparse
import csv
import datetime
import difflib
import json
import re
import ssl
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REFERENCES_CSV_PATH = Path("docs/references.csv")
CHECKED_JSON_PATH = Path("docs/data/references_checked.json")
BIBLIOGRAPHY_PATH = Path("docs/references.md")
CROSSREF_URL = "https://api.crossref.org/works"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/"
ARXIV_URL = "https://export.arxiv.org/api/query"
SECONDS_BETWEEN_REQUESTS = 1.0
TITLE_MATCH_THRESHOLD = 0.85
SEMANTIC_SCHOLAR_SECONDS_BETWEEN_REQUESTS = 3.0


def contact_email_from_config(config_path):
    if config_path.exists():
        with config_path.open("rb") as config_file:
            return tomllib.load(config_file).get("network", {}).get("contact_email", "")
    return ""


def fetch_text(url, user_agent):
    time.sleep(SECONDS_BETWEEN_REQUESTS)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(
        request, timeout=60, context=ssl.create_default_context()
    ) as response:
        return response.read().decode("utf-8")


def normalised_title(title):
    """Lower-case letters, digits and spaces only; markup like <i>…</i> is dropped first."""
    without_markup = re.sub(r"<[^>]+>", " ", title or "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", without_markup.lower())).strip()


def best_crossref_match(reference, user_agent, contact_email):
    """Best Crossref work for the reference's title, scored by title, surname and year."""
    query = urllib.parse.urlencode(
        {
            "query.bibliographic": f"{reference['title']} {reference['first_author_surname']}",
            "rows": "8",
            "mailto": contact_email,
            "select": "DOI,title,author,issued,container-title,type,abstract,"
            "is-referenced-by-count",
        }
    )
    items = json.loads(fetch_text(f"{CROSSREF_URL}?{query}", user_agent))["message"]["items"]
    wanted_title = normalised_title(reference["title"])
    scored = []
    for item in items:
        title = (item.get("title") or [""])[0]
        similarity = difflib.SequenceMatcher(None, wanted_title, normalised_title(title)).ratio()
        surnames = [author.get("family", "") for author in item.get("author", [])]
        has_surname = any(
            reference["first_author_surname"].lower() in name.lower() for name in surnames
        )
        year = ((item.get("issued") or {}).get("date-parts") or [[0]])[0][0] or 0
        year_gap = abs(year - int(reference["year"]))
        scored.append((similarity + 0.1 * has_surname - 0.02 * min(year_gap, 5), item, similarity))
    if not scored:
        return None, 0.0
    _, item, similarity = max(scored, key=lambda entry: entry[0])
    return item, similarity


def semantic_scholar_abstract(doi, user_agent):
    """Abstract from Semantic Scholar by DOI, or "" when unavailable."""
    url = f"{SEMANTIC_SCHOLAR_URL}DOI:{urllib.parse.quote(doi)}?fields=abstract"
    for attempt in range(4):
        # Semantic Scholar throttles unauthenticated clients hard; stay well under it.
        time.sleep(SEMANTIC_SCHOLAR_SECONDS_BETWEEN_REQUESTS)
        try:
            return json.loads(fetch_text(url, user_agent)).get("abstract") or ""
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return ""
            time.sleep(20 * (attempt + 1))
    return ""


def arxiv_record(arxiv_id, user_agent):
    text = fetch_text(f"{ARXIV_URL}?id_list={arxiv_id}", user_agent)
    entry = text.split("<entry>")[1] if "<entry>" in text else ""

    def field(name):
        match = re.search(rf"<{name}>(.*?)</{name}>", entry, re.S)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

    return {
        "title": field("title"),
        "authors": re.findall(r"<name>(.*?)</name>", entry),
        "published": field("published")[:10],
        "abstract": field("summary"),
    }


def check_reference(reference, user_agent, contact_email, saved_abstract_by_doi=None):
    """Match one reference; see the module docstring for the status values."""
    result = {"key": reference["key"], "query_title": reference["title"]}
    if reference.get("doi"):
        # A DOI given in references.csv is checked, not trusted: the title must still match.
        item = json.loads(fetch_text(f"{CROSSREF_URL}/{reference['doi']}", user_agent))["message"]
        similarity = difflib.SequenceMatcher(
            None,
            normalised_title(reference["title"]),
            normalised_title((item.get("title") or [""])[0]),
        ).ratio()
    else:
        item, similarity = best_crossref_match(reference, user_agent, contact_email)
    if item is not None and similarity >= TITLE_MATCH_THRESHOLD:
        authors = [
            " ".join(part for part in (author.get("given"), author.get("family")) if part)
            for author in item.get("author", [])
        ]
        doi = item.get("DOI", "")
        abstract = re.sub(r"<[^>]+>", " ", item.get("abstract") or "")
        if not abstract.strip() and doi:
            abstract = (saved_abstract_by_doi or {}).get(doi.lower()) or semantic_scholar_abstract(
                doi, user_agent
            )
        result.update(
            {
                "title": (item.get("title") or [""])[0],
                "authors": authors,
                "year": ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0],
                "venue": (item.get("container-title") or [None])[0],
                "doi": doi,
                "type": item.get("type"),
                "cited_by_count": item.get("is-referenced-by-count"),
                "abstract": re.sub(r"\s+", " ", abstract).strip(),
                "title_similarity": round(similarity, 3),
            }
        )
    if reference.get("arxiv_id") and "title" in result:
        # A Crossref title match by another author (e.g. a software package named after the
        # paper) is dropped in favour of the arXiv record.
        crossref_authors = " ".join(result.get("authors", [])).lower()
        if reference["first_author_surname"].lower() not in crossref_authors:
            for field_name in ("title", "authors", "year", "venue", "doi", "type", "abstract"):
                result.pop(field_name, None)
    if reference.get("arxiv_id"):
        arxiv = arxiv_record(reference["arxiv_id"], user_agent)
        result["arxiv_id"] = reference["arxiv_id"]
        result["arxiv"] = arxiv
        if not result.get("abstract"):
            result["abstract"] = arxiv["abstract"]
        if "title" not in result and arxiv["title"]:
            result.update(
                {
                    "title": arxiv["title"],
                    "authors": arxiv["authors"],
                    "year": int(arxiv["published"][:4]),
                    "venue": f"arXiv {reference['arxiv_id']}",
                    "title_similarity": round(
                        difflib.SequenceMatcher(
                            None,
                            normalised_title(reference["title"]),
                            normalised_title(arxiv["title"]),
                        ).ratio(),
                        3,
                    ),
                }
            )
    if "title" not in result:
        if reference.get("manual_record"):
            result.update(
                {
                    "status": "manual",
                    "title": reference["title"],
                    "manual_record": reference["manual_record"],
                }
            )
        else:
            result["status"] = "not found"
        return result
    authors = result.get("authors", [])
    # Some Crossref records (books, some journals) carry no author list; title, year and
    # DOI then have to carry the match, and the entry says so.
    has_surname = not authors or any(
        reference["first_author_surname"].lower() in author.lower() for author in authors[:3]
    )
    if not authors:
        result["note"] = "no author metadata in Crossref; matched on title, year and DOI"
    is_year_close = abs((result.get("year") or 0) - int(reference["year"])) <= 1
    result["status"] = "verified" if has_surname and is_year_close else "partial"
    if result["status"] == "partial" and reference.get("manual_record"):
        # Crossref found a related record (e.g. a review of a book) but not the work itself.
        return {
            "key": reference["key"],
            "query_title": reference["title"],
            "status": "manual",
            "title": reference["title"],
            "manual_record": reference["manual_record"],
        }
    if result["status"] == "partial":
        result["note"] = (
            f"surname match: {has_surname}; year {result.get('year')} vs {reference['year']}"
        )
    return result


def bibliography_line(checked):
    if checked["status"] == "manual":
        return (
            f"- **{checked['key']}**: *{checked['title']}*. {checked['manual_record']}. "
            "Status: checked against the record named."
        )
    if checked["status"] == "not found":
        return f"- **{checked['key']}**: *{checked['query_title']}*. Not found: [verify]."
    authors = checked.get("authors", [])
    author_text = ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")
    identifiers = [f"doi {checked['doi']}"] if checked.get("doi") else []
    venue = checked.get("venue") or ""
    if checked.get("arxiv_id") and f"arXiv {checked['arxiv_id']}" not in venue:
        identifiers.append(f"arXiv {checked['arxiv_id']}")
    identifier = "; ".join(identifiers)
    if checked["status"] == "verified":
        status = "checked" + (f" ({checked['note']})" if checked.get("note") else "")
    else:
        status = f"partial ({checked['note']})"
    return (
        f"- **{checked['key']}**: {author_text} ({checked.get('year')}). *{checked['title']}*. "
        f"{venue}. {identifier + '. ' if identifier else ''}Status: {status}."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/local.toml"))
    arguments = parser.parse_args()
    contact_email = contact_email_from_config(arguments.config)
    user_agent = f"evobots/0.1 (research; reference check; contact: {contact_email})"
    with REFERENCES_CSV_PATH.open(encoding="utf-8") as references_file:
        references = list(csv.DictReader(references_file))
    saved_abstract_by_doi = {}
    if CHECKED_JSON_PATH.exists():
        for saved in json.loads(CHECKED_JSON_PATH.read_text(encoding="utf-8")):
            if saved.get("doi") and saved.get("abstract"):
                saved_abstract_by_doi[saved["doi"].lower()] = saved["abstract"]
    checked_references = []
    for reference in references:
        checked = check_reference(reference, user_agent, contact_email, saved_abstract_by_doi)
        checked_references.append(checked)
        print(f"{checked['status']:<10} {reference['key']}", flush=True)
    CHECKED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKED_JSON_PATH.write_text(
        json.dumps(checked_references, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    today = datetime.date.today().isoformat()
    lines = [
        "# References",
        "",
        f"Generated by `tools/check_references.py` on {today} from `references.csv`.",
        "Each entry was matched on Crossref (and arXiv where an ID is given) by title,",
        "first-author surname and year. Abstracts are in `data/references_checked.json`.",
        "Entries not marked **checked** must be cited with [verify]. Entries checked against a",
        "named record (no Crossref or arXiv entry exists) say which record was read.",
        "",
    ]
    lines += [bibliography_line(checked) for checked in checked_references]
    BIBLIOGRAPHY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    counts = {}
    for checked in checked_references:
        counts[checked["status"]] = counts.get(checked["status"], 0) + 1
    print(counts)


if __name__ == "__main__":
    main()
