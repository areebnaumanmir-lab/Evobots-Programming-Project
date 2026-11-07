"""Rebuild docs/data/hub_capacity_monthly.csv from the newest EIA-860M workbook (M2).

Run: `uv run python tools/build_capacity_table.py`
"""

import sys
from pathlib import Path

from evobots.data.sources.eia860m import read_units
from evobots.features.inputs import (
    CAPACITY_TABLE_PATH,
    GENERATOR_INVENTORY_DIRECTORY,
    capacity_table_from_units,
    newest_file,
    write_capacity_table,
)


def main():
    workbook = newest_file(GENERATOR_INVENTORY_DIRECTORY, "*.xlsx")
    if workbook is None:
        sys.exit(f"no EIA-860M workbook in {GENERATOR_INVENTORY_DIRECTORY}")
    write_capacity_table(capacity_table_from_units(read_units(workbook)))
    print(f"wrote {CAPACITY_TABLE_PATH} from {Path(workbook).name}")


if __name__ == "__main__":
    main()
