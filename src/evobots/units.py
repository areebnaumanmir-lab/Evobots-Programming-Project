"""Physical units for features and formulas: products and quotients of base units.

Every feature carries a unit (`docs/design_spec.md` §8: "raw units, each feature tagged with
its unit"), and trader formulas are unit-checked (§9.3): `+ − > <`, `min` and `max` need equal
units, `× ÷` combine them. So `spread + temperature` cannot be built, while
`0.4 $/MWh/(°F·day) × cdd_fcst` is a $/MWh quantity.

A unit is a sorted tuple of (base, exponent) pairs; the dimensionless unit (a fraction) is
the empty tuple. Base units:

| Base | Meaning |
|---|---|
| usd | US dollars |
| mwh | megawatt-hours |
| mw | megawatts |
| degf | degrees Fahrenheit |
| day | one day (degree-days, %/day) |
| mph | miles per hour |
| mmbtu | million British thermal units |
| point | index points (EPU) |
| hour | hour ending, 1–24 |

Example:
    >>> USD_PER_MWH.label()
    '$/MWh'
    >>> (USD_PER_MWH / DEGF_DAY).label()
    '$/MWh/(°F·day)'
    >>> (USD_PER_MWH / DEGF_DAY) * DEGF_DAY == USD_PER_MWH
    True
    >>> unit_from_label("°F·day") == DEGF_DAY
    True
"""

import dataclasses

BASE_UNITS = ("usd", "mwh", "mw", "degf", "day", "mph", "mmbtu", "point", "hour")
BASE_SYMBOLS = {
    "usd": "$",
    "mwh": "MWh",
    "mw": "MW",
    "degf": "°F",
    "day": "day",
    "mph": "mph",
    "mmbtu": "MMBtu",
    "point": "index points",
    "hour": "hour",
}


@dataclasses.dataclass(frozen=True)
class Unit:
    """A product of base units with integer exponents.

    Attributes:
        exponents: sorted ((base, exponent), …) with non-zero exponents; () = fraction.
    """

    exponents: tuple = ()

    @classmethod
    def of(cls, **exponent_by_base):
        """The unit with these exponents, e.g. Unit.of(usd=1, mwh=-1)."""
        for base in exponent_by_base:
            if base not in BASE_UNITS:
                raise ValueError(f"unknown base unit {base!r}")
        return cls(
            tuple(
                sorted((base, exponent) for base, exponent in exponent_by_base.items() if exponent)
            )
        )

    def exponent_by_base(self):
        """The exponents as a dict."""
        return dict(self.exponents)

    def __mul__(self, other):
        """The product unit (exponents add)."""
        combined = self.exponent_by_base()
        for base, exponent in other.exponents:
            combined[base] = combined.get(base, 0) + exponent
        return Unit.of(**combined)

    def __truediv__(self, other):
        """The quotient unit (exponents subtract)."""
        combined = self.exponent_by_base()
        for base, exponent in other.exponents:
            combined[base] = combined.get(base, 0) - exponent
        return Unit.of(**combined)

    def is_dimensionless(self):
        """True for a pure number (a fraction)."""
        return not self.exponents

    def label(self):
        """A readable label: the named label when the unit has one, else a built one."""
        for label, unit in UNIT_BY_LABEL.items():
            if unit == self:
                return label
        # A ratio or product of two named units reads best in their own labels.
        for top_label, top in UNIT_BY_LABEL.items():
            for bottom_label, bottom in UNIT_BY_LABEL.items():
                if top.is_dimensionless() or bottom.is_dimensionless():
                    continue
                if top / bottom == self:
                    wrapped = (
                        f"({bottom_label})"
                        if "·" in bottom_label or "/" in bottom_label
                        else bottom_label
                    )
                    return f"{top_label}/{wrapped}"
                if top * bottom == self and top_label <= bottom_label:
                    return f"{top_label}·{bottom_label}"
        numerator = [(base, exponent) for base, exponent in self.exponents if exponent > 0]
        denominator = [(base, -exponent) for base, exponent in self.exponents if exponent < 0]

        def product(pairs):
            parts = []
            for base, exponent in pairs:
                symbol = BASE_SYMBOLS[base]
                parts.append(symbol if exponent == 1 else f"{symbol}^{exponent}")
            return "·".join(parts)

        top = product(numerator) or "1"
        if not denominator:
            return top
        bottom = product(denominator)
        if len(denominator) > 1:
            bottom = f"({bottom})"
        return f"{top}/{bottom}"

    def code(self):
        """A compact, parseable text form, e.g. 'usd*mwh^-1' ('1' for a fraction)."""
        if not self.exponents:
            return "1"
        return "*".join(
            base if exponent == 1 else f"{base}^{exponent}" for base, exponent in self.exponents
        )


def unit_from_code(text):
    """The unit a `Unit.code()` text names.

    Example:
        >>> unit_from_code("usd*mwh^-1") == USD_PER_MWH
        True
    """
    if text == "1":
        return FRACTION
    exponents = {}
    for part in text.split("*"):
        base, _, power = part.partition("^")
        exponents[base] = exponents.get(base, 0) + (int(power) if power else 1)
    return Unit.of(**exponents)


FRACTION = Unit()
USD_PER_MWH = Unit.of(usd=1, mwh=-1)
DEGF = Unit.of(degf=1)
DEGF_DAY = Unit.of(degf=1, day=1)
MPH = Unit.of(mph=1)
MW = Unit.of(mw=1)
USD_PER_MMBTU = Unit.of(usd=1, mmbtu=-1)
FRACTION_PER_DAY = Unit.of(day=-1)
INDEX_POINTS = Unit.of(point=1)
HOUR = Unit.of(hour=1)

# The labels used in the feature catalogue and the docs.
UNIT_BY_LABEL = {
    "$/MWh": USD_PER_MWH,
    "fraction": FRACTION,
    "°F": DEGF,
    "°F·day": DEGF_DAY,
    "mph": MPH,
    "MW": MW,
    "$/MMBtu": USD_PER_MMBTU,
    "fraction/day": FRACTION_PER_DAY,
    "index points": INDEX_POINTS,
    "hour": HOUR,
}


def unit_from_label(label):
    """The unit with a catalogue label, e.g. '$/MWh'."""
    return UNIT_BY_LABEL[label]
