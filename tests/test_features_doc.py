"""docs/features.md carries the catalogue exactly as the code defines it."""

import importlib.util
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_features_doc_catalogue_matches_code():
    specification = importlib.util.spec_from_file_location(
        "build_feature_docs", REPOSITORY_ROOT / "tools/build_feature_docs.py"
    )
    tool = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(tool)
    text = (REPOSITORY_ROOT / "docs/features.md").read_text(encoding="utf-8")
    assert tool.catalogue_table() in text, "run tools/build_feature_docs.py and paste the table"
