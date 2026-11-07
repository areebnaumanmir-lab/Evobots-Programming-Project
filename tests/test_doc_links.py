"""Internal-link checker for the Markdown docs (docs/design_spec.md §14.2: "docs are tested").

Every relative link in a tracked Markdown file must point at a file that exists, and a
`#fragment` must match a heading in the target. External http(s) and mailto links are
not fetched: the suite runs offline.
"""

import re
from pathlib import Path

import pytest

from evobots.service import MISO_DERIVED_FILES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKIPPED_DIRECTORY_NAMES = {".git", ".venv", "data", "runs", "node_modules", ".pytest_cache"}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCED_BLOCK_PATTERN = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
CODE_SPAN_PATTERN = re.compile(r"`[^`\n]*`")
HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def markdown_paths():
    return sorted(
        path
        for path in REPOSITORY_ROOT.rglob("*.md")
        if not SKIPPED_DIRECTORY_NAMES.intersection(path.relative_to(REPOSITORY_ROOT).parts)
    )


def text_without_code(markdown_text):
    return CODE_SPAN_PATTERN.sub("", FENCED_BLOCK_PATTERN.sub("", markdown_text))


def heading_anchor(heading_text):
    """GitHub-style anchor: lower case, punctuation dropped, spaces to hyphens."""
    anchor = re.sub(r"[^\w\- ]", "", heading_text.strip().lower())
    return anchor.replace(" ", "-")


def anchors_in(markdown_path):
    text = FENCED_BLOCK_PATTERN.sub("", markdown_path.read_text(encoding="utf-8"))
    return {heading_anchor(heading) for heading in HEADING_PATTERN.findall(text)}


def broken_links(markdown_path):
    problems = []
    for target in LINK_PATTERN.findall(
        text_without_code(markdown_path.read_text(encoding="utf-8"))
    ):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target):
            continue
        path_part, _, fragment = target.partition("#")
        target_path = (markdown_path.parent / path_part).resolve() if path_part else markdown_path
        if not target_path.exists():
            # A downloaded copy of the app leaves MISO-derived tables out on purpose.
            is_inside = target_path.is_relative_to(REPOSITORY_ROOT)
            relative = target_path.relative_to(REPOSITORY_ROOT).as_posix() if is_inside else ""
            if relative not in MISO_DERIVED_FILES:
                problems.append(f"{target}: no such file")
        elif fragment and target_path.suffix == ".md" and fragment not in anchors_in(target_path):
            problems.append(f"{target}: no heading #{fragment}")
    return problems


@pytest.mark.parametrize(
    "markdown_path", markdown_paths(), ids=lambda path: str(path.relative_to(REPOSITORY_ROOT))
)
def test_internal_links_resolve(markdown_path):
    assert broken_links(markdown_path) == []


def test_checker_catches_a_broken_link(tmp_path):
    (tmp_path / "target.md").write_text("# Real heading\n", encoding="utf-8")
    source_path = tmp_path / "source.md"
    source_path.write_text(
        "[ok](target.md) [ok anchor](target.md#real-heading) [web](https://example.org)\n"
        "[missing](nowhere.md) [bad anchor](target.md#no-such-heading)\n"
        "`[in code](ignored.md)`\n",
        encoding="utf-8",
    )
    assert broken_links(source_path) == [
        "nowhere.md: no such file",
        "target.md#no-such-heading: no heading #no-such-heading",
    ]
