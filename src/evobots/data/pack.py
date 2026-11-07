"""A data pack: the built data and runs of one machine, unpacked by another.

Since round 42 the app ships with the hub data (`evobots.data.bundled`), so a pack mainly
carries runs: searches, report cards and paper-trading ledgers. `evobots serve` (so the
one-click start scripts too) looks for `evobots-data-pack*.zip` in the evobots folder and in
the user's Downloads folder, and unpacks it once. Nothing is downloaded and nothing leaves
the computer.

**What a pack holds** (`PACK_PATHS`):
- the hub price and forecast tables;
- the newest gas, policy-uncertainty and risk-free series files;
- `runs/`: runs, report cards, paper-trading ledgers.

**What it never holds:**
- the sealed hold-out (its folder is named only by the hold-out accessor);
- the raw MISO archive;
- the Stage C store (4 GB; rebuilt with `evobots data build --stage D`).

**Safety:** only members under the allowed folders are extracted, never absolute paths or
"..". Existing files are replaced, and the pack's SHA-256 is recorded in
`data/imported_packs.txt` so it is unpacked once.

Example:
    >>> import tempfile
    >>> root = Path(tempfile.mkdtemp())
    >>> (root / "data/store").mkdir(parents=True)
    >>> _ = (root / "data/store/hub_prices.csv.gz").write_bytes(b"x")
    >>> pack = build_data_pack(root, root / "evobots-data-pack.zip")
    >>> target = Path(tempfile.mkdtemp())
    >>> import_data_pack(target, [root])[0].startswith("Imported")
    True
    >>> (target / "data/store/hub_prices.csv.gz").read_bytes(), import_data_pack(target, [root])
    (b'x', [])
"""

import hashlib
import zipfile
from pathlib import Path, PurePosixPath

PACK_FILE_PATTERN = "evobots-data-pack*.zip"
IMPORT_LOG = Path("data/imported_packs.txt")
ALLOWED_PREFIXES = ("data/store/", "data/raw/series/", "runs/")
PACK_PATHS = (
    "data/store/hub_prices.csv.gz",
    "data/store/hub_forecasts.csv.gz",
    "data/store/daily_coverage.csv",
    "data/store/locations.csv",
)
NEWEST_SERIES = ("eia_henry_hub", "epu", "fred_dtb3", "gpr")
RUN_FILES = ("checkpoint.pickle", "lineage.sqlite", "status.json")


def default_search_folders(root):
    """The evobots folder, then the user's Downloads folder."""
    return [Path(root), Path.home() / "Downloads"]


def is_allowed(name):
    """True for a relative member under an allowed folder, without '..'."""
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and any(name.startswith(prefix) for prefix in ALLOWED_PREFIXES)
        and not name.endswith("/")
    )


def build_data_pack(root, output, run_ids=None):
    """Write a pack of this machine's built data and runs (see the module docstring)."""
    root = Path(root)
    members = [root / name for name in PACK_PATHS if (root / name).exists()]
    for source in NEWEST_SERIES:
        folder = root / "data/raw/series" / source
        files = sorted(folder.glob("*.*"), key=lambda path: path.stat().st_mtime)
        if files:
            members.append(files[-1])
    runs = root / "runs"
    for run in sorted(runs.glob("R*")) if runs.exists() else []:
        if run_ids and run.name not in run_ids:
            continue
        members += [run / name for name in RUN_FILES if (run / name).exists()]
        members += sorted((run / "deployable").glob("*")) + sorted(run.glob("report_*"))
        members += sorted(run.glob("final_test.json"))
    if (runs / "paper").exists():
        members += sorted(path for path in (runs / "paper").rglob("*") if path.is_file())
    output = Path(output)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            archive.write(path, path.relative_to(root).as_posix())
    return output


def file_digest(path):
    """SHA-256 of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(2**20), b""):
            digest.update(block)
    return digest.hexdigest()


def import_data_pack(root, folders=None):
    """Unpack every new pack found in the folders; returns one message per pack imported."""
    root = Path(root)
    log_path = root / IMPORT_LOG
    done = set(log_path.read_text().split()) if log_path.exists() else set()
    messages = []
    for folder in folders or default_search_folders(root):
        for pack in sorted(Path(folder).glob(PACK_FILE_PATTERN)) if Path(folder).is_dir() else []:
            digest = file_digest(pack)
            if digest in done:
                continue
            try:
                with zipfile.ZipFile(pack) as archive:
                    names = [name for name in archive.namelist() if is_allowed(name)]
                    for name in names:
                        target = root / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
            except zipfile.BadZipFile:
                messages.append(f"Skipped {pack}: not a readable zip file.")
                continue
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(digest + "\n")
            done.add(digest)
            messages.append(f"Imported {len(names)} files from {pack}.")
    return messages
