"""The change ledger lists every round (CLAUDE.md §14.2)."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHANGE_LEDGER_PATH = REPOSITORY_ROOT / "docs" / "change_ledger.md"
ROUNDS_DIRECTORY = REPOSITORY_ROOT / "docs" / "rounds"


def test_every_round_doc_is_in_the_change_ledger():
    ledger_text = CHANGE_LEDGER_PATH.read_text(encoding="utf-8")
    missing_round_docs = [
        round_path.name
        for round_path in sorted(ROUNDS_DIRECTORY.glob("round*.md"))
        if f"rounds/{round_path.name}" not in ledger_text
    ]
    assert missing_round_docs == []
