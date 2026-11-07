"""Reader for EIA-860M, the monthly US generator inventory: MISO's fleet by month.

One workbook (`tools/fetch_series.py`, newest month) lists every generator in three sheets:
`Operating`, `Retired` and `Planned` (`docs/design_spec.md` §7.8). Each sheet has a title row, a blank
row, then a header row. The capacity history is rebuilt from the operating and retirement
months of the units in `Operating` and `Retired`: a unit counts from its operating month
up to the month before its retirement month.

**What this can and can't say** (`docs/design_spec.md` §7.8):
- Units are selected by today's `Balancing Authority Code` ("MISO"). A unit that joined
  MISO later (MISO South in December 2013, among others) is counted from its operating
  date, so early totals include units that were outside MISO then. Regional features only
  exist while their hub exists (MISO South's hubs from 2013-12-19), which limits the effect.
- Units retired before EIA's inventory began aren't listed, so the earliest months can be
  slightly low. "Estimates will be corrected without specific acknowledgment" (EIA), so a
  newer workbook can change past months a little (measured at M1 from archived files).
- `Planned` is not used for bot inputs: its history only exists from 2016 (reporting only).

Example:
    >>> technology_group("Onshore Wind Turbine"), technology_group("Batteries")
    ('Wind', 'Battery')
    >>> unit = GeneratorUnit(
    ...     plant_id=1,
    ...     generator_id="1",
    ...     technology="Solar Photovoltaic",
    ...     nameplate_mw=50.0,
    ...     first_month=(2020, 6),
    ...     retirement_month=None,
    ...     state="MN",
    ...     latitude_degrees=45.0,
    ...     longitude_degrees=-93.0,
    ... )
    >>> unit.is_operating_in((2020, 5)), unit.is_operating_in((2020, 6))
    (False, True)
"""

import collections
import dataclasses

import openpyxl

from evobots.data.periods import EVOLUTION_LAST_DAY

# The balancing-authority code of units in MISO's footprint today.
MISO_BALANCING_AUTHORITY = "MISO"
# Rows before the header row in every EIA-860M sheet (title row, blank row).
ROWS_BEFORE_HEADER = 2
# The last month whose capacity the evolution period may read: the month of its last
# decision day. Later months fall in the sealed hold-out (`docs/design_spec.md` §7.2).
LAST_EVOLUTION_MONTH = (EVOLUTION_LAST_DAY.year, EVOLUTION_LAST_DAY.month)
# The technology groups the capacity features and reports use (`docs/design_spec.md` §7.8).
TECHNOLOGY_GROUPS = ("Wind", "Solar", "Battery", "Coal", "Natural Gas", "Nuclear", "Other")


def technology_group(technology):
    """Map an EIA technology name to one of the seven groups.

    Wind includes onshore and offshore turbines; Solar includes photovoltaic and thermal;
    Coal includes steam and gasification; Natural Gas covers every technology EIA names
    "Natural Gas …". Everything else (hydro, oil, biomass, other gases …) is Other.

    Args:
        technology: the `Technology` cell, e.g. "Natural Gas Fired Combined Cycle".

    Returns:
        One of TECHNOLOGY_GROUPS.
    """
    text = technology or ""
    if "Wind" in text:
        return "Wind"
    if "Solar" in text:
        return "Solar"
    if "Batter" in text:
        return "Battery"
    if "Coal" in text:
        return "Coal"
    if "Natural Gas" in text:
        return "Natural Gas"
    if "Nuclear" in text:
        return "Nuclear"
    return "Other"


class HoldoutMonthRefusedError(RuntimeError):
    """A capacity month inside the sealed hold-out was asked for without permission."""


@dataclasses.dataclass(frozen=True)
class GeneratorUnit:
    """One generator from EIA-860M.

    Attributes:
        plant_id: EIA plant id.
        generator_id: EIA generator id within the plant.
        technology: EIA technology name.
        nameplate_mw: nameplate capacity, MW.
        first_month: (year, month) it began operating.
        retirement_month: (year, month) it retired, or None if still operating.
        state: two-letter plant state.
        latitude_degrees: plant latitude, or None.
        longitude_degrees: plant longitude (negative west), or None.
    """

    plant_id: int
    generator_id: str
    technology: str
    nameplate_mw: float
    first_month: tuple
    retirement_month: tuple | None
    state: str
    latitude_degrees: float | None
    longitude_degrees: float | None

    def is_operating_in(self, month):
        """True when the unit operated during the (year, month) given."""
        has_started = self.first_month <= month
        has_retired = self.retirement_month is not None and self.retirement_month <= month
        return has_started and not has_retired


def number_or_none(cell):
    """A cell's number, or None for blanks and EIA's single-space placeholders.

    Example:
        >>> number_or_none(" "), number_or_none(12), number_or_none("3.5")
        (None, 12.0, 3.5)
    """
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).strip()
    return float(text) if text else None


def units_from_rows(rows, is_retired_sheet, balancing_authority=MISO_BALANCING_AUTHORITY):
    """Turn one sheet's rows (header first) into GeneratorUnits of one balancing authority.

    Args:
        rows: the header row then data rows, each a sequence of cell values.
        is_retired_sheet: True for `Retired` (reads the retirement month).
        balancing_authority: the code to keep.

    Returns:
        A list of GeneratorUnit. Rows without an operating month or capacity are skipped.
    """
    header = list(rows[0])
    column = {name: index for index, name in enumerate(header)}
    units = []
    for row in rows[1:]:
        if not row or row[column["Balancing Authority Code"]] != balancing_authority:
            continue
        operating_year = number_or_none(row[column["Operating Year"]])
        operating_month = number_or_none(row[column["Operating Month"]])
        nameplate = number_or_none(row[column["Nameplate Capacity (MW)"]])
        if operating_year is None or operating_month is None or nameplate is None:
            continue
        retirement_month = None
        if is_retired_sheet:
            retired_year = number_or_none(row[column["Retirement Year"]])
            retired_month = number_or_none(row[column["Retirement Month"]])
            if retired_year is not None and retired_month is not None:
                retirement_month = (int(retired_year), int(retired_month))
        units.append(
            GeneratorUnit(
                plant_id=int(row[column["Plant ID"]]),
                generator_id=str(row[column["Generator ID"]]),
                technology=str(row[column["Technology"]]),
                nameplate_mw=nameplate,
                first_month=(int(operating_year), int(operating_month)),
                retirement_month=retirement_month,
                state=str(row[column["Plant State"]]),
                latitude_degrees=number_or_none(row[column["Latitude"]]),
                longitude_degrees=number_or_none(row[column["Longitude"]]),
            )
        )
    return units


def read_units(path, balancing_authority=MISO_BALANCING_AUTHORITY):
    """Read the operating and retired units of one balancing authority from a workbook.

    Args:
        path: an EIA-860M workbook, e.g. `september_generator2026.xlsx`.
        balancing_authority: the code to keep.

    Returns:
        A list of GeneratorUnit from the `Operating` and `Retired` sheets.
    """
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    units = []
    for sheet_name, is_retired_sheet in (("Operating", False), ("Retired", True)):
        rows = list(workbook[sheet_name].iter_rows(values_only=True))[ROWS_BEFORE_HEADER:]
        units.extend(units_from_rows(rows, is_retired_sheet, balancing_authority))
    workbook.close()
    return units


def nameplate_mw_by_group(units, month, area_by_unit=None, holdout_permission=None):
    """Operating nameplate capacity in one month, by technology group (and area).

    Args:
        units: GeneratorUnits.
        month: (year, month).
        area_by_unit: optional mapping from unit to an area name; when given, the result is
            keyed by (area, group).
        holdout_permission: required for months after LAST_EVOLUTION_MONTH; only the
            hold-out accessor creates it.

    Returns:
        A dict from group (or (area, group)) to MW.

    Raises:
        HoldoutMonthRefusedError: for a hold-out month without permission.

    Example:
        >>> unit = GeneratorUnit(1, "1", "Batteries", 10.0, (2020, 1), (2021, 1), "MN", None, None)
        >>> nameplate_mw_by_group([unit], (2020, 7))
        {'Battery': 10.0}
        >>> nameplate_mw_by_group([unit], (2021, 1))
        {}
    """
    if month > LAST_EVOLUTION_MONTH and holdout_permission is None:
        raise HoldoutMonthRefusedError(f"{month} is after the evolution period")
    total = collections.defaultdict(float)
    for unit in units:
        if unit.is_operating_in(month):
            group = technology_group(unit.technology)
            key = group if area_by_unit is None else (area_by_unit[unit], group)
            total[key] += unit.nameplate_mw
    return dict(total)
