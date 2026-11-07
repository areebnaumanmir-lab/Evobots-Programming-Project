"""A trader's source code: the standalone Python file generated from its genome (§9.1).

`trader_source(genome, record)` prints the genome as a standard-library module
`trader_<id>.py`. Run it as `python trader_R12-184213.py --inputs day.csv` to print that day's
bids. The file is the reference form of the organism: an equivalence test checks that, on
many random days, it bids exactly what the vectorised engine (`trader.trader_decisions`)
bids.

The slot functions are written in the trader dialect (`grammar.python_source`), so
`genome_from_source(text)` parses an edited or hand-written file back into a genome. If it
passes the grammar and unit checks, it can join a Refine run as a `founder:human` (§9.1).

**Input file** (one CSV row per location-hour): `location`, `hour`, `cap_mw` (the location's
hard MW cap), then one column per feature the trader reads. Category features hold names
(e.g. `Hub`), `holiday` holds 0 or 1, and an empty cell means missing.

Example:
    >>> from evobots.bots.founders import FOUNDERS
    >>> text = trader_source(FOUNDERS["heat_dec"], {"trader_id": "R1-7"})
    >>> genome_from_source(text) == FOUNDERS["heat_dec"]
    True
"""

import ast
import csv
import io

from evobots.bots.grammar import GrammarError, parse_python, python_source
from evobots.bots.trader import GENE_NAMES, SLOT_NAMES, Genome, describe, genome_id, trader_name
from evobots.features.catalogue import FEATURE_BY_NAME

GENE_CONSTANT_BY_NAME = {name: name.upper() for name in GENE_NAMES}
VERSION = "0.2"

RUNTIME = '''
# ----- the trader language: every helper returns None for a missing value -----


def known(value):
    """None for a missing value (None or NaN), else the value."""
    return None if value is None or value != value else value


def const(value, unit):
    """A constant; the unit is documentation (checked when the file is parsed)."""
    return value


def add(left, right):
    return None if known(left) is None or known(right) is None else known(left + right)


def sub(left, right):
    return None if known(left) is None or known(right) is None else known(left - right)


def mul(left, right):
    return None if known(left) is None or known(right) is None else known(left * right)


def div(left, right):
    """Protected division: ÷ 0 gives 0."""
    if known(left) is None or known(right) is None:
        return None
    return 0.0 if right == 0 else known(left / right)


def minimum(left, right):
    return None if known(left) is None or known(right) is None else min(left, right)


def maximum(left, right):
    return None if known(left) is None or known(right) is None else max(left, right)


def absolute(value):
    return None if known(value) is None else abs(value)


def if_else(test, then, otherwise):
    if test is None:
        return None
    return known(then) if test else known(otherwise)


def gt(left, right):
    return None if known(left) is None or known(right) is None else left > right


def lt(left, right):
    return None if known(left) is None or known(right) is None else left < right


def and_(left, right):
    return None if left is None or right is None else (left and right)


def or_(left, right):
    return None if left is None or right is None else (left or right)


def not_(value):
    return None if value is None else (not value)


def member(value, members):
    return None if value is None else (value in members)


def flag(value):
    return None if known(value) is None else bool(value)


def truth(value):
    return value
'''

DECIDE = '''

def decide(x, cap_mw):
    """Full-size bid for one location-hour: (side, limit $/MWh, MW), or None for no bid."""
    is_where = where(x)
    is_when = when(x)
    value = score(x)
    day_ahead_last = known(x.get("da_last"))
    if is_where is not True or is_when is not True or value is None or day_ahead_last is None:
        return None
    if value > DEC_THRESHOLD_USD_PER_MWH:
        side = 1
    elif value < -INC_THRESHOLD_USD_PER_MWH:
        side = -1
    else:
        return None
    limit = day_ahead_last + side * PRICE_OFFSET_USD_PER_MWH
    strength = min(1.0, abs(value) / SIZE_SCORE_SCALE_USD_PER_MWH)
    return side, limit, cap_mw * SIZE_FRACTION * strength


def round_down_to_step(power_mw):
    """MISO's 0.1 MW bid step (same formula as the engine)."""
    return math.floor(power_mw / 0.1 + 1e-9) * 0.1


def read_rows(path):
    """Input rows as dicts with numbers parsed and empty cells as None."""
    with open(path, newline="", encoding="utf-8") as table:
        for row in csv.DictReader(table):
            parsed = {}
            for name, text in row.items():
                if text == "":
                    parsed[name] = None
                elif name in CATEGORY_FEATURES or name == "location":
                    parsed[name] = text
                else:
                    parsed[name] = float(text)
            yield parsed


def main():
    parser = argparse.ArgumentParser(description="Print this trader's bids for one day.")
    parser.add_argument("--inputs", required=True, help="CSV of inputs, one row per location-hour")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="position scale from the account (1 = full size)")
    arguments = parser.parse_args()
    writer = csv.writer(sys.stdout, lineterminator="\\n")
    writer.writerow(["location", "hour", "side", "limit_usd_per_mwh", "mw"])
    for row in read_rows(arguments.inputs):
        bid = decide(row, row["cap_mw"])
        if bid is None:
            continue
        side, limit, power = bid
        power = round_down_to_step(arguments.scale * power)
        if power < 0.1 - 1e-12:
            continue
        writer.writerow([row["location"], int(row["hour"]), "DEC" if side > 0 else "INC",
                         repr(limit), repr(power)])


if __name__ == "__main__":
    main()
'''


def trader_source(genome, record):
    """The trader's standalone Python file.

    Args:
        genome: a Genome.
        record: birth-record fields shown in the header: trader_id (required), and optionally
            parent_ids, operator, evaluation, run_id.
    """
    trader_id = record["trader_id"]
    features = genome.features()
    rules = "\n".join(f"  {line}" for line in describe(genome))
    inputs = "\n".join(f"  {name}: {FEATURE_BY_NAME[name].display_name}" for name in features)
    parents = ", ".join(record.get("parent_ids", ())) or "none"
    header = (
        f'"""Trader {trader_id} "{trader_name(trader_id)}". Generated by evobots {VERSION} '
        f"from genome {genome_id(genome)[:16]}….\n"
        f"Parents: {parents}. Made by: {record.get('operator', 'unknown')}. "
        f"Born at evaluation {record.get('evaluation', '?')} "
        f"of run {record.get('run_id', '?')}.\n\n"
        f"Rules in plain English:\n{rules}\n\n"
        "Inputs (one CSV row per location-hour: location, hour, cap_mw, then these; empty = "
        f"missing):\n{inputs}\n\n"
        f"Run: python trader_{trader_id}.py --inputs day.csv [--scale 0.5]\n"
        "Standard library only. Edit the slot functions and this file parses back into a "
        'genome.\n"""\n\n'
        "import argparse\nimport csv\nimport math\nimport sys\n\n"
    )
    genes = "".join(
        f"{GENE_CONSTANT_BY_NAME[name]} = {getattr(genome, name)!r}\n" for name in GENE_NAMES
    )
    categories = sorted(name for name in features if FEATURE_BY_NAME[name].kind == "category")
    slots = "".join(
        f"\n\ndef {name}(x):\n    return {python_source(getattr(genome, name))}\n"
        for name in SLOT_NAMES
    )
    return (
        header
        + "# ----- numeric genes -----\n"
        + genes
        + f"CATEGORY_FEATURES = {tuple(categories)!r}\n"
        + RUNTIME
        + "\n# ----- the trader's slots -----"
        + slots
        + DECIDE
    )


def genome_from_source(text):
    """Parse a generated (or hand-edited) trader file back into a Genome.

    Raises:
        GrammarError: when a slot leaves the trader dialect or breaks a type or unit rule.
        ValueError: when a gene is missing or out of range.
    """
    module = ast.parse(text)
    genes = {}
    slots = {}
    constant_names = {constant: name for name, constant in GENE_CONSTANT_BY_NAME.items()}
    for statement in module.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id in constant_names:
                genes[constant_names[target.id]] = ast.literal_eval(statement.value)
        if isinstance(statement, ast.FunctionDef) and statement.name in SLOT_NAMES:
            body = statement.body
            if len(body) != 1 or not isinstance(body[0], ast.Return):
                raise GrammarError(f"{statement.name} must be a single return statement")
            slots[statement.name] = parse_python(ast.unparse(body[0].value))
    missing = set(SLOT_NAMES) - set(slots) | set(GENE_NAMES) - set(genes)
    if missing:
        raise GrammarError(f"missing from the file: {sorted(missing)}")
    genes["pause_days"] = int(genes["pause_days"])
    return Genome(**slots, **genes)


def input_rows(store, day_index, caps_mw, feature_names):
    """The input rows a trader file reads for one operating day of a FeatureStore.

    Returns a list of dicts (location, hour, cap_mw, features), with category codes turned
    into names and missing values as None. Used by the equivalence test, the
    "What did it see?" panel and `evobots export-bot`.
    """
    rows = []
    arrays = {name: store.window(name, day_index, day_index + 1)[0] for name in feature_names}
    for location_index, location in enumerate(store.locations):
        for hour_index in range(24):
            row = {
                "location": location,
                "hour": float(hour_index + 1),
                "cap_mw": float(caps_mw[location_index]),
            }
            for name in feature_names:
                value = float(arrays[name][hour_index, location_index])
                feature = FEATURE_BY_NAME[name]
                if value != value:
                    row[name] = None
                elif feature.kind == "category":
                    row[name] = feature.categories[int(value)]
                else:
                    row[name] = value
            rows.append(row)
    return rows


def rows_to_csv(rows, feature_names):
    """Input rows as CSV text (repr floats, so values round-trip exactly)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    columns = ["location", "hour", "cap_mw", *feature_names]
    writer.writerow(columns)
    for row in rows:
        writer.writerow(
            [
                ""
                if row[name] is None
                else (row[name] if isinstance(row[name], str) else repr(row[name]))
                for name in columns
            ]
        )
    return buffer.getvalue()
