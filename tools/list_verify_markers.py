"""List every [verify] marker in docs/design_spec.md and docs/ by group, for Areeb to accept or resolve.

Usage:
    python tools/list_verify_markers.py

Writes docs/data/verify_markers.csv (one row per marker) and docs/verify_register.md (the
markers grouped, with a recommendation and Areeb's decision per group). Round docs are history
and are not listed. Line numbers move as documents change, so decisions are taken per group,
not per line; rerun this script after every change to see the current list.
"""

import csv
import re
from pathlib import Path

CSV_PATH = Path("docs/data/verify_markers.csv")
REGISTER_PATH = Path("docs/verify_register.md")
MARKER_PATTERN = re.compile(r"\[verify")

# Group letter → (title, recommendation, decision). Edit the decision when Areeb answers.
GROUPS = {
    "M": (
        "Mentions of the word, not claims",
        "nothing to accept: these define or discuss the marker itself",
        "not applicable",
    ),
    "F": (
        "Fee and RSG rates",
        "accept as labelled estimates now (decided D3, round 20); resolved by the Rates Factors "
        "file (request R1)",
        "Areeb downloads the Rates Factors file (round 28); labelled estimates until then",
    ),
    "P": (
        "MISO's published MPD",
        "see question 1 (round 27): MISO's method can't be reproduced from public data; "
        "collateral doesn't bind at Stage A",
        "decided round 28: the $12 floor every year, labelled estimate, until MISO's published "
        "values are supplied",
    ),
    "R": (
        "Facts Claude can measure from the downloaded data",
        "no acceptance needed: resolved by computation in M1 (pre-2015 DA files compared with "
        "the ex-post files on 2015-02-19 → 28; the size of MLC measured; which forecast issue "
        "is latest at the deadline)",
        "to be resolved by Claude in M1",
    ),
    "K": (
        "Library licences of packages not yet installed",
        "accept: each is read from the package metadata when it is installed",
        "resolved in round 27: every licence read from PyPI or the licence file",
    ),
    "O": (
        "Later ORFE modules (§20)",
        "accept for now: each is checked when its module is built, and no code is built on "
        "them before that",
        "resolved in round 27: citations and facts checked",
    ),
    "A": (
        "Rules and data details that don't change Stage A results",
        "accept: moot under decisions D1/D2, or too small to matter at 5 MW per hub-hour; "
        "the price caps return at M3",
        "resolved in round 27; risk-free source decided in round 28 (FRED DTB3); open: "
        "Areeb's commercial-use source",
    ),
    "L": (
        "Literature citations not yet checked",
        "accept: cited with [verify] until checked; nothing is coded on them",
        "resolved in round 27: all 82 references checked (72 Crossref/arXiv, 10 named records)",
    ),
}
# First matching rule wins. Each rule: (group, file suffix or None, list of text fragments).
RULES = [
    (
        "M",
        None,
        [
            "mark it [verify]",
            "**[verify]**: from memory",
            "Mark [verify] instead",
            "| (obs.) / [verify] |",
            "Resolve the [verify] list",
            "Done when:** no [verify]",
            "The M0 [verify] list",
            "marked [verify].",
            "M0 [verify] list",
            "Entries not marked",
            "**[verify]**: not yet read",
            "Status of the M0 [verify]",
            "So the [verify] in",
            "settles the `docs/design_spec.md` §20.6",
            "Resolves the round-19 [verify]",
            "= from a secondary source",
            "Decision at DA close",
            "accept remaining [verify]",
            "**(memory) [verify]**: the paper",
            "are always cited with [verify]",
        ],
    ),
    # History rows: the change ledger and the decisions log record what was open at the time.
    ("M", "change_ledger.md", []),
    ("M", "decisions_log.md", []),
    (
        "F",
        None,
        [
            "Schedule 17 + 24",
            "$0.0746",
            "$0.0156",
            "daily/hourly market rate",
            "sign convention itself",
            "| Admin fee |",
        ],
    ),
    ("P", None, ["published MPD", "true MPD", "*published* MPD", "| Published MPD |"]),
    ("R", None, ["pre-2015 `da_lmp`", "a few percent of the price", "verify on the parsed table"]),
    ("K", None, ["verify on install", "not installed in the environment"]),
    ("L", "references.md", []),
    (
        "L",
        "design_rationale.md",
        [
            "(memory",
            "44/24/15",
            "not found",
            "publication details",
            "(Koza",
            "Whigham",
            "Ray 1991",
            "luke1997",
        ],
    ),
    ("L", "docs/design_spec.md", ["Angeline", "Getmansky", "Cully & Demiris", "Barber"]),
]


def group_of(path, line_number, text):
    """The group letter for one marker."""
    for group, file_suffix, fragments in RULES:
        if file_suffix is not None and not str(path).endswith(file_suffix):
            continue
        if not fragments or any(fragment in text for fragment in fragments):
            return group
    if str(path) == "docs/design_spec.md" and line_number > 1300:
        return "O"
    return "A"


def marker_rows():
    """(id, group, file, line number, an excerpt around the marker) for every marker."""
    paths = [Path("docs/design_spec.md")] + sorted(
        path
        for path in Path("docs").rglob("*.md")
        if "rounds" not in path.parts and path != REGISTER_PATH
    )
    rows = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            text = re.sub(r"\s+", " ", line.strip())
            for match in MARKER_PATTERN.finditer(text):
                rows.append(
                    [
                        f"V{len(rows) + 1:03d}",
                        group_of(path, line_number, text),
                        str(path),
                        line_number,
                        excerpt(text, match.start()),
                    ]
                )
    return rows


def excerpt(text, position):
    """About 140 characters of the line around the marker at position."""
    start = max(0, position - 110)
    end = min(len(text), position + 30)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def register_markdown(rows):
    """docs/verify_register.md as a string."""
    lines = [
        "# Register of [verify] markers",
        "",
        "Generated by `tools/list_verify_markers.py`; do not edit by hand. Every `[verify]` in "
        "`docs/design_spec.md` and `docs/` (round docs excluded), grouped. M0 is done when each group is "
        "accepted by Areeb or resolved (`docs/design_spec.md` §16).",
        "",
        '**How to decide:** reply with the groups you accept, e.g. "accept F, P, K, O, A, L", '
        "and name any single marker you want resolved first by its file and line. The decision "
        "is then recorded here and in `decisions_log.md`.",
        "",
        "| Group | Markers | Recommendation | Decision |",
        "|---|---|---|---|",
    ]
    for group, (title, recommendation, decision) in GROUPS.items():
        count = sum(1 for row in rows if row[1] == group)
        lines.append(f"| **{group}**: {title} | {count} | {recommendation} | {decision} |")
    for group, (title, _, _) in GROUPS.items():
        members = [row for row in rows if row[1] == group]
        if not members or group == "M":
            continue
        lines += ["", f"## {group}: {title}", "", "| Where | Text |", "|---|---|"]
        lines += [
            f"| `{row[2]}:{row[3]}` | {row[4].replace('|', chr(92) + '|')} |" for row in members
        ]
    return "\n".join(lines) + "\n"


def main():
    rows = marker_rows()
    with CSV_PATH.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["id", "group", "file", "line", "excerpt"])
        writer.writerows(rows)
    REGISTER_PATH.write_text(register_markdown(rows), encoding="utf-8")
    counts = {group: sum(1 for row in rows if row[1] == group) for group in GROUPS}
    print(f"wrote {CSV_PATH} and {REGISTER_PATH}: {len(rows)} markers {counts}")


if __name__ == "__main__":
    main()
