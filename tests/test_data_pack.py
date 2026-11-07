"""The personal data pack: unpacked once, and only into the allowed folders."""

import zipfile

from evobots.data.pack import build_data_pack, import_data_pack, is_allowed


def test_only_allowed_relative_paths_are_unpacked(tmp_path):
    source = tmp_path / "evobots-data-pack.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("data/store/hub_prices.csv.gz", b"prices")
        archive.writestr("runs/R1/status.json", b"{}")
        archive.writestr("../escape.txt", b"no")
        archive.writestr("data/holdout/raw/file.csv", b"no")
        archive.writestr("src/evobots/cli.py", b"no")
        archive.writestr("/etc/evil", b"no")
    target = tmp_path / "copy"
    target.mkdir()
    messages = import_data_pack(target, [tmp_path])
    assert messages == [f"Imported 2 files from {source}."]
    assert (target / "data/store/hub_prices.csv.gz").read_bytes() == b"prices"
    assert not (tmp_path / "escape.txt").exists()
    assert not (target / "data/holdout").exists() and not (target / "src").exists()
    assert import_data_pack(target, [tmp_path]) == []  # once only
    assert not is_allowed("runs/../../x") and is_allowed("runs/R1/lineage.sqlite")


def test_a_pack_never_contains_the_holdout(tmp_path):
    (tmp_path / "data/holdout").mkdir(parents=True)
    (tmp_path / "data/holdout/secret.csv").write_text("sealed")
    (tmp_path / "data/store").mkdir(parents=True)
    (tmp_path / "data/store/hub_prices.csv.gz").write_bytes(b"x")
    pack = build_data_pack(tmp_path, tmp_path / "pack.zip")
    names = zipfile.ZipFile(pack).namelist()
    assert names == ["data/store/hub_prices.csv.gz"]
