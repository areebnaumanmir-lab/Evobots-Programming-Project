"""Stage C: every priced location, one memory-mapped file set per year (§7.11).

`evobots data build --stage C` reads the raw MISO archive already on disk (offline; built
locally and never redistributed, round 25), one operating day at a time through the era reader,
for the evolution period 2005-04-01 → 2025-09-21 only (the reader refuses hold-out days). For
each calendar year it writes, under `data/store/prices/` (git-ignored):

- `{year}_da_lmp.npy`, `{year}_rt_lmp.npy`: float32 arrays [day, hour, location], $/MWh;
- `{year}_da_mcc.npy`: float16 DA congestion component (used only for the congestion-share
  feature, where float16's three significant digits are enough);
- `{year}.json`: the year's first day, day count, location names and MISO types, and the
  store version.

The columns of a year are the locations priced on any of its days, sorted by name; a location
not priced on a day is NaN that day (gaps are never filled). Each file is written then
renamed, and a year whose `.json` already exists with this version is skipped, so the build
is resumable.

`LocationStore.market(first_day, last_day, locations)` reads chosen columns back as a
`HubMarket`, memory-mapping each year so only those columns are loaded.

Example:
    >>> import tempfile
    >>> directory = Path(tempfile.mkdtemp())
    >>> write_year(directory, 2010, datetime.date(2010, 1, 1), ["A.HUB", "B"], ["Hub", "Gennode"],
    ...     np.ones((2, 24, 2)), np.zeros((2, 24, 2)), np.zeros((2, 24, 2)))
    >>> market = LocationStore(directory).market(datetime.date(2010, 1, 1),
    ...     datetime.date(2010, 1, 2), ["B"])
    >>> market.hubs, float(market.day_ahead[1, 5, 0] - market.real_time[1, 5, 0])
    (('B',), 1.0)
"""

import datetime
import json
import warnings
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from evobots.data.periods import EVOLUTION_LAST_DAY, MARKET_FIRST_DAY
from evobots.data.sources.miso_eras import read_day
from evobots.simulate.market import HubMarket

RAW_DIRECTORY = Path("data/raw/miso")
LOCATION_STORE_DIRECTORY = Path("data/store/prices")
STORE_VERSION = 1
HOURS_PER_DAY = 24
FIELD_TYPES = {"da_lmp": np.float32, "rt_lmp": np.float32, "da_mcc": np.float16}


def day_values(arguments):
    """One operating day: (day, {name: type}, {name: (da, rt, mcc)} with 24 values each).

    Args:
        arguments: (raw_directory, day), one tuple for multiprocessing.
    """
    raw_directory, day = arguments
    types = {}
    values = {}
    for market in ("da", "rt"):
        prices = read_day(raw_directory, day, market)
        if prices is None:
            continue
        types.update(prices.type_by_location)
        for (name, value_type), hours in prices.hours_by_location_and_value.items():
            field = f"{market}_{value_type.lower()}"
            if field not in FIELD_TYPES:
                continue
            row = np.array([np.nan if value is None else value for value in hours], np.float32)
            values.setdefault(name, {})[field] = row
    return day, types, values


def write_atomically(path, array):
    """np.save to path.part, then rename."""
    partial = path.with_name(path.name + ".part")
    with partial.open("wb") as handle:
        np.save(handle, array)
    partial.replace(path)


def write_year(directory, year, first_day, names, types, day_ahead, real_time, congestion):
    """Write one year's arrays and its index file (the index last, so it marks completion)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    arrays = {"da_lmp": day_ahead, "rt_lmp": real_time, "da_mcc": congestion}
    for field, array in arrays.items():
        write_atomically(directory / f"{year}_{field}.npy", np.asarray(array, FIELD_TYPES[field]))
    index = {
        "version": STORE_VERSION,
        "year": year,
        "first_day": first_day.isoformat(),
        "day_count": int(np.shape(day_ahead)[0]),
        "locations": list(names),
        "types": list(types),
    }
    partial = directory / f"{year}.json.part"
    partial.write_text(json.dumps(index), encoding="utf-8")
    partial.replace(directory / f"{year}.json")


def build_year(year, raw_directory, directory, pool, last_day=EVOLUTION_LAST_DAY):
    """Read every day of one year (within the evolution period) and write its files."""
    first_day = max(datetime.date(year, 1, 1), MARKET_FIRST_DAY)
    final_day = min(datetime.date(year, 12, 31), last_day)
    days = [
        first_day + datetime.timedelta(days=offset)
        for offset in range((final_day - first_day).days + 1)
    ]
    results = list(pool.imap(day_values, [(Path(raw_directory), day) for day in days], chunksize=4))
    types = {}
    for _, day_types, _ in results:
        types.update(day_types)
    names = sorted(types)
    column = {name: position for position, name in enumerate(names)}
    shape = (len(days), HOURS_PER_DAY, len(names))
    arrays = {field: np.full(shape, np.nan, np.float32) for field in FIELD_TYPES}
    for day_position, (_, _, values) in enumerate(results):
        for name, fields in values.items():
            if name not in column:
                continue
            for field, row in fields.items():
                arrays[field][day_position, :, column[name]] = row
    write_year(
        directory,
        year,
        first_day,
        names,
        [types[name] for name in names],
        arrays["da_lmp"],
        arrays["rt_lmp"],
        arrays["da_mcc"],
    )
    return len(days), len(names)


def build_location_store(
    raw_directory=RAW_DIRECTORY,
    directory=LOCATION_STORE_DIRECTORY,
    worker_count=4,
    years=None,
    progress=print,
):
    """Build every missing year of the store (resumable); returns [(year, days, locations)]."""
    directory = Path(directory)
    store = LocationStore(directory)
    built = []
    all_years = years or range(MARKET_FIRST_DAY.year, EVOLUTION_LAST_DAY.year + 1)
    with Pool(worker_count) as pool:
        for year in all_years:
            if store.has_year(year):
                index = store.index(year)
                built.append((year, index["day_count"], len(index["locations"])))
                continue
            day_count, location_count = build_year(year, raw_directory, directory, pool)
            built.append((year, day_count, location_count))
            progress(f"year {year}: {day_count} days × {location_count} locations")
    return built


class LocationStore:
    """Read access to the yearly all-location files."""

    def __init__(self, directory=LOCATION_STORE_DIRECTORY):
        """Point at a store directory (it may not exist yet)."""
        self.directory = Path(directory)
        self.indexes = {}

    def has_year(self, year):
        """True when the year's files are complete and of this store version."""
        path = self.directory / f"{year}.json"
        if not path.exists():
            return False
        return json.loads(path.read_text(encoding="utf-8")).get("version") == STORE_VERSION

    def years(self):
        """Years with complete files, in order."""
        return sorted(
            int(path.stem) for path in self.directory.glob("*.json") if self.has_year(path.stem)
        )

    def is_built(self):
        """True when every year of the evolution period is present."""
        wanted = range(MARKET_FIRST_DAY.year, EVOLUTION_LAST_DAY.year + 1)
        return all(year in self.years() for year in wanted)

    def index(self, year):
        """The year's index: first day, day count, locations, types."""
        if year not in self.indexes:
            text = (self.directory / f"{year}.json").read_text(encoding="utf-8")
            self.indexes[year] = json.loads(text)
        return self.indexes[year]

    def array(self, year, field):
        """A read-only memory map of one year's field."""
        return np.load(self.directory / f"{year}_{field}.npy", mmap_mode="r")

    def location_types(self, year=None):
        """{name: type} for one year, or over every year (the latest type wins)."""
        types = {}
        for each_year in [year] if year else self.years():
            index = self.index(each_year)
            types.update(zip(index["locations"], index["types"], strict=True))
        return types

    def size_bytes(self):
        """Total size of the store's files on disk."""
        return sum(path.stat().st_size for path in self.directory.glob("*.npy"))

    def daily_spreads(self, first_day, last_day, locations=None):
        """Daily mean DA − RT per location: (days, names, array [day, location], NaN = missing)."""
        market = self.market(first_day, last_day, locations)
        spread = market.day_ahead - market.real_time
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-missing days stay NaN
            daily = np.nanmean(spread, axis=1)
        return market.days, market.hubs, daily

    def market(self, first_day, last_day, locations=None, mask=None, dtype=np.float64):
        """A HubMarket for operating days first_day … last_day.

        Args:
            first_day: first operating day (datetime.date); days outside the store are NaN.
            last_day: last operating day.
            locations: names of the columns (None = every location seen in the period).
            mask: optional callable(year) → set of names that may trade that year; the other
                columns are NaN that year (Stage D uses it for yearly representatives).
            dtype: float64 (the default, as Stage A) or float32 (Stage C over every location,
                half the memory; the store itself is float32).

        Returns:
            A HubMarket (float64 prices) with location types.
        """
        years = [year for year in self.years() if first_day.year <= year <= last_day.year]
        if locations is None:
            seen = {}
            for year in years:
                seen.update(dict.fromkeys(self.index(year)["locations"]))
            locations = sorted(seen)
        locations = tuple(locations)
        day_count = (last_day - first_day).days + 1
        shape = (day_count, HOURS_PER_DAY, len(locations))
        day_ahead = np.full(shape, np.nan, dtype)
        real_time = np.full(shape, np.nan, dtype)
        congestion = np.full(shape, np.nan, dtype)
        types = dict.fromkeys(locations, "Gennode")
        for year in years:
            index = self.index(year)
            year_first = datetime.date.fromisoformat(index["first_day"])
            column_of = {name: position for position, name in enumerate(index["locations"])}
            types.update(
                (name, kind)
                for name, kind in zip(index["locations"], index["types"], strict=True)
                if name in types
            )
            allowed = mask(year) if mask else None
            wanted = [
                (target, column_of[name])
                for target, name in enumerate(locations)
                if name in column_of and (allowed is None or name in allowed)
            ]
            if not wanted:
                continue
            start = max((first_day - year_first).days, 0)
            stop = min((last_day - year_first).days + 1, index["day_count"])
            if stop <= start:
                continue
            offset = (year_first + datetime.timedelta(days=start) - first_day).days
            targets = [target for target, _ in wanted]
            sources = [source for _, source in wanted]
            for field, output in (
                ("da_lmp", day_ahead),
                ("rt_lmp", real_time),
                ("da_mcc", congestion),
            ):
                values = np.asarray(self.array(year, field)[start:stop][:, :, sources], dtype)
                output[offset : offset + stop - start][:, :, targets] = values
        days = tuple(first_day + datetime.timedelta(days=offset) for offset in range(day_count))
        return HubMarket(
            days=days,
            hubs=locations,
            day_ahead=day_ahead,
            real_time=real_time,
            source="MISO",
            day_ahead_congestion=congestion,
            location_types=tuple(types[name] for name in locations),
        )
