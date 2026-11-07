"""Birth records and genomes of every trader a run evaluates (`docs/design_spec.md` §9.4).

`runs/<run>/lineage.sqlite` holds one row per evaluated trader (about 200 bytes): ids, name,
run, birth number, generation (1 + the deepest parent's), parents, operator, the seed of the
operation, origin, window, fitness, cell, offspring count, and death. Genomes are stored for
every trader that entered the archive and all of its ancestors; any other trader is
regenerated exactly from its parents, operator and seed (runs are deterministic), so nothing is
lost (`regenerate`).

Lineage crosses runs: a Refine run names the parent run's trader as a parent, and
`LineageStore.attach` reads earlier runs' stores to follow ancestry across them.

Example:
    >>> store = LineageStore(":memory:")
    >>> fields = ("R1-1", "abc", "beh", "amber-heron", "R1", 1, 1, (), "random", 7, "random")
    >>> record = BirthRecord(*fields)
    >>> store.add(record)
    >>> store.record("R1-1").generation
    1
"""

import dataclasses
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS traders (
    trader_id TEXT PRIMARY KEY,
    genome_id TEXT NOT NULL,
    behaviour_id TEXT NOT NULL,
    name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    birth INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    parent_ids TEXT NOT NULL,
    operator TEXT NOT NULL,
    operation_seed INTEGER NOT NULL,
    origin TEXT NOT NULL,
    window_first_day TEXT,
    window_last_day TEXT,
    fitness REAL,
    cell_column INTEGER,
    cell_row INTEGER,
    offspring INTEGER NOT NULL DEFAULT 0,
    is_alive INTEGER,
    death_cause TEXT,
    death_day TEXT,
    has_entered_archive INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS genomes (genome_id TEXT PRIMARY KEY, genome_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS traders_by_name ON traders (name);
"""
COLUMNS = (
    "trader_id",
    "genome_id",
    "behaviour_id",
    "name",
    "run_id",
    "birth",
    "generation",
    "parent_ids",
    "operator",
    "operation_seed",
    "origin",
    "window_first_day",
    "window_last_day",
    "fitness",
    "cell_column",
    "cell_row",
    "offspring",
    "is_alive",
    "death_cause",
    "death_day",
    "has_entered_archive",
)


@dataclasses.dataclass
class BirthRecord:
    """One evaluated trader's record (see the module docstring)."""

    trader_id: str
    genome_id: str
    behaviour_id: str
    name: str
    run_id: str
    birth: int
    generation: int
    parent_ids: tuple
    operator: str
    operation_seed: int
    origin: str
    window_first_day: str | None = None
    window_last_day: str | None = None
    fitness: float | None = None
    cell_column: int | None = None
    cell_row: int | None = None
    offspring: int = 0
    is_alive: bool | None = None
    death_cause: str | None = None
    death_day: str | None = None
    has_entered_archive: bool = False

    def row(self):
        """Values in COLUMNS order (parents as JSON)."""
        values = dataclasses.asdict(self)
        values["parent_ids"] = json.dumps(list(self.parent_ids))
        return tuple(values[column] for column in COLUMNS)


class LineageStore:
    """The SQLite lineage store of one run."""

    def __init__(self, path):
        """Open (or create) the store at path (":memory:" for tests)."""
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(SCHEMA)
        self.attached = []

    def add(self, record):
        """Insert a birth record, and count it as offspring of each parent in this store."""
        placeholders = ", ".join("?" for _ in COLUMNS)
        self.connection.execute(
            f"INSERT OR REPLACE INTO traders ({', '.join(COLUMNS)}) VALUES ({placeholders})",
            record.row(),
        )
        for parent in record.parent_ids:
            self.connection.execute(
                "UPDATE traders SET offspring = offspring + 1 WHERE trader_id = ?", (parent,)
            )

    def update_result(
        self, trader_id, fitness, cell, is_alive, death_cause, death_day, has_entered_archive
    ):
        """Fill in a trader's result after evaluation."""
        self.connection.execute(
            "UPDATE traders SET fitness = ?, cell_column = ?, cell_row = ?, is_alive = ?, "
            "death_cause = ?, death_day = ?, has_entered_archive = MAX(has_entered_archive, ?) "
            "WHERE trader_id = ?",
            (
                fitness,
                None if cell is None else cell[0],
                None if cell is None else cell[1],
                None if is_alive is None else int(is_alive),
                death_cause,
                death_day,
                int(has_entered_archive),
                trader_id,
            ),
        )

    def store_genome(self, genome_id, genome_json):
        """Keep a genome (archive entrants and their ancestors)."""
        self.connection.execute(
            "INSERT OR IGNORE INTO genomes (genome_id, genome_json) VALUES (?, ?)",
            (genome_id, genome_json),
        )

    def commit(self):
        """Write pending changes (at checkpoints)."""
        self.connection.commit()

    def attach(self, other_path):
        """Also search another run's store (lineage across runs)."""
        self.attached.append(LineageStore(other_path))

    def record(self, trader_id):
        """The BirthRecord of a trader (this store, then attached ones), or None."""
        row = self.connection.execute(
            f"SELECT {', '.join(COLUMNS)} FROM traders WHERE trader_id = ?", (trader_id,)
        ).fetchone()
        if row is None:
            for other in self.attached:
                found = other.record(trader_id)
                if found is not None:
                    return found
            return None
        values = dict(zip(COLUMNS, row))
        values["parent_ids"] = tuple(json.loads(values["parent_ids"]))
        values["is_alive"] = None if values["is_alive"] is None else bool(values["is_alive"])
        values["has_entered_archive"] = bool(values["has_entered_archive"])
        return BirthRecord(**values)

    def genome_json(self, genome_id):
        """A stored genome's JSON, or None."""
        row = self.connection.execute(
            "SELECT genome_json FROM genomes WHERE genome_id = ?", (genome_id,)
        ).fetchone()
        if row is None:
            for other in self.attached:
                found = other.genome_json(genome_id)
                if found is not None:
                    return found
        return None if row is None else row[0]

    def ancestors(self, trader_id, limit=10_000):
        """Every ancestor id of a trader (breadth-first, across attached stores)."""
        seen, queue = [], [trader_id]
        while queue and len(seen) < limit:
            record = self.record(queue.pop(0))
            if record is None:
                continue
            for parent in record.parent_ids:
                if parent not in seen:
                    seen.append(parent)
                    queue.append(parent)
        return seen

    def children(self, trader_id):
        """Ids of a trader's direct children in this store."""
        rows = self.connection.execute(
            "SELECT trader_id, parent_ids FROM traders WHERE parent_ids LIKE ? ORDER BY birth",
            (f'%"{trader_id}"%',),
        ).fetchall()
        return [child for child, parents in rows if trader_id in json.loads(parents)]

    def descendants(self, trader_id, limit=10_000):
        """Every descendant id (breadth-first)."""
        seen, queue = [], [trader_id]
        while queue and len(seen) < limit:
            for child in self.children(queue.pop(0)):
                if child not in seen:
                    seen.append(child)
                    queue.append(child)
        return seen

    def search(self, text="", limit=100, is_archive_only=False, offset=0):
        """Records whose id, name or origin contains text (newest first), skipping `offset`."""
        query = (
            "SELECT trader_id FROM traders WHERE "
            "(trader_id LIKE ? OR name LIKE ? OR origin LIKE ? OR operator LIKE ?)"
        )
        if is_archive_only:
            query += " AND has_entered_archive = 1"
        query += " ORDER BY birth DESC LIMIT ? OFFSET ?"
        pattern = f"%{text}%"
        rows = self.connection.execute(
            query, (pattern, pattern, pattern, pattern, limit, offset)
        ).fetchall()
        return [self.record(row[0]) for row in rows]

    def count(self):
        """Number of traders recorded."""
        return self.connection.execute("SELECT COUNT(*) FROM traders").fetchone()[0]

    def distinct_behaviours(self):
        """Number of distinct behaviour ids (the trial count of G2)."""
        return self.connection.execute(
            "SELECT COUNT(DISTINCT behaviour_id) FROM traders"
        ).fetchone()[0]

    def dump(self):
        """Every row, sorted, as text (byte-identical comparisons of runs)."""
        lines = [
            repr(row)
            for row in self.connection.execute(
                f"SELECT {', '.join(COLUMNS)} FROM traders ORDER BY birth, trader_id"
            )
        ]
        lines += [
            repr(row) for row in self.connection.execute("SELECT * FROM genomes ORDER BY genome_id")
        ]
        return "\n".join(lines)

    def close(self):
        """Close the database (and attached ones)."""
        self.connection.close()
        for other in self.attached:
            other.close()
