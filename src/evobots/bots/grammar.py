"""The trader language: typed, unit-checked formula trees (`docs/design_spec.md` §9.1–9.3).

A trader's `where`, `when` and `score` slots are trees in this grammar. Evolution edits the
trees, never Python text, so every child is a valid, well-typed program (strongly typed GP,
Montana 1995). The same tree is printed three ways:
- **display form**, with the catalogue's display names, for people (`display`);
- **code form**, the Python expression of the generated trader file (`python_source`), which
  parses back into the same tree (`parse_python`);
- **canonical JSON** (`to_data` / `from_data`), from which the genome id is hashed.

**Grammar** (value types: Number with a unit, or Bool):

- Feature(name): Number, the feature's unit; a number feature of the catalogue
- Constant(value, unit): Number, unit
- Binary(op, left, right): Number; Number, Number; `+ − min max`: equal units; `×`: units multiply;
  `÷` (protected, ÷0 → 0): units divide
- Absolute(child): Number, child's unit; Number
- IfElse(test, then, otherwise): Number, the branches' unit; Bool, Number, Number; equal branch
  units
- Compare(op, left, right): Bool; Number, Number; `>` or `<`, equal units
- Logic(op, left, right): Bool; Bool, Bool; `and`, `or`
- Negate(child): Bool; Bool; `not`
- Member(feature, members): Bool; a category feature in a set (`in {…}`)
- Flag(name): Bool; a boolean feature (`holiday`)
- Truth(value): Bool; always true / false

**Missing values:** a missing input makes every node that depends on it missing, and a
missing condition or score means no bid (`docs/design_spec.md` §8). Bool values are evaluated
as 1.0 / 0.0 / NaN, so `not` of a missing comparison stays missing (never true).

Example:
    >>> tree = Compare(">", Feature("spread_std_28d"), Constant(18.0, USD_PER_MWH))
    >>> display(tree)
    'Spread volatility, last 28 visible days ($/MWh) > 18 $/MWh'
    >>> python_source(tree)
    "gt(x['spread_std_28d'], const(18.0, 'mwh^-1*usd'))"
    >>> parse_python(python_source(tree)) == tree
    True
    >>> unit_of(Binary("*", Constant(0.4, USD_PER_MWH / DEGF_DAY), Feature("cdd_fcst"))).label()
    '$/MWh'
"""

import ast
import dataclasses

import numpy as np

from evobots.features.catalogue import FEATURE_BY_NAME
from evobots.units import DEGF_DAY, FRACTION, USD_PER_MWH, Unit, unit_from_code  # noqa: F401

NUMBER = "number"
BOOL = "bool"
ARITHMETIC_OPERATORS = ("+", "-", "*", "/", "min", "max")
SAME_UNIT_OPERATORS = ("+", "-", "min", "max")
COMPARISON_OPERATORS = (">", "<")
LOGIC_OPERATORS = ("and", "or")
# The code form's function names.
FUNCTION_BY_OPERATOR = {
    "+": "add",
    "-": "sub",
    "*": "mul",
    "/": "div",
    "min": "minimum",
    "max": "maximum",
    ">": "gt",
    "<": "lt",
    "and": "and_",
    "or": "or_",
}
OPERATOR_BY_FUNCTION = {function: operator for operator, function in FUNCTION_BY_OPERATOR.items()}
DISPLAY_SYMBOL = {"+": "+", "-": "−", "*": "×", "/": "÷", ">": ">", "<": "<"}


class GrammarError(ValueError):
    """A tree that breaks the grammar or the unit rules."""


@dataclasses.dataclass(frozen=True)
class Feature:
    """A number feature of the catalogue."""

    name: str


@dataclasses.dataclass(frozen=True)
class Constant:
    """A number with a unit."""

    value: float
    unit: Unit = FRACTION


@dataclasses.dataclass(frozen=True)
class Binary:
    """`+ − × ÷ min max` of two numbers."""

    operator: str
    left: object
    right: object


@dataclasses.dataclass(frozen=True)
class Absolute:
    """|x|."""

    child: object


@dataclasses.dataclass(frozen=True)
class IfElse:
    """`then if test else otherwise`."""

    test: object
    then: object
    otherwise: object


@dataclasses.dataclass(frozen=True)
class Compare:
    """`left > right` or `left < right`."""

    operator: str
    left: object
    right: object


@dataclasses.dataclass(frozen=True)
class Logic:
    """`left and right` or `left or right`."""

    operator: str
    left: object
    right: object


@dataclasses.dataclass(frozen=True)
class Negate:
    """`not child`."""

    child: object


@dataclasses.dataclass(frozen=True)
class Member:
    """A category feature's value is one of `members` (sorted names)."""

    feature: str
    members: tuple


@dataclasses.dataclass(frozen=True)
class Flag:
    """A boolean feature (e.g. `holiday`)."""

    name: str


@dataclasses.dataclass(frozen=True)
class Truth:
    """A constant condition (an empty `where` or `when` is Truth(True))."""

    value: bool


NUMBER_NODES = (Feature, Constant, Binary, Absolute, IfElse)
BOOL_NODES = (Compare, Logic, Negate, Member, Flag, Truth)


def kind_of(node):
    """NUMBER or BOOL."""
    if isinstance(node, NUMBER_NODES):
        return NUMBER
    if isinstance(node, BOOL_NODES):
        return BOOL
    raise GrammarError(f"not a node: {node!r}")


def children(node):
    """The node's child nodes, in order."""
    if isinstance(node, (Binary, Compare, Logic)):
        return (node.left, node.right)
    if isinstance(node, (Absolute, Negate)):
        return (node.child,)
    if isinstance(node, IfElse):
        return (node.test, node.then, node.otherwise)
    return ()


def with_children(node, new_children):
    """A copy of the node with its children replaced (same order as `children`)."""
    if isinstance(node, (Binary, Compare, Logic)):
        return dataclasses.replace(node, left=new_children[0], right=new_children[1])
    if isinstance(node, (Absolute, Negate)):
        return dataclasses.replace(node, child=new_children[0])
    if isinstance(node, IfElse):
        return IfElse(*new_children)
    return node


def unit_of(node):
    """The unit of a Number node (raises GrammarError on a unit error)."""
    if isinstance(node, Feature):
        feature = FEATURE_BY_NAME.get(node.name)
        if feature is None or feature.kind != "number":
            raise GrammarError(f"{node.name!r} is not a number feature")
        return feature.unit
    if isinstance(node, Constant):
        return node.unit
    if isinstance(node, Binary):
        left, right = unit_of(node.left), unit_of(node.right)
        if node.operator in SAME_UNIT_OPERATORS:
            if left != right:
                raise GrammarError(
                    f"{node.operator} needs equal units: {left.label()} vs {right.label()}"
                )
            return left
        if node.operator == "*":
            return left * right
        if node.operator == "/":
            return left / right
        raise GrammarError(f"unknown operator {node.operator!r}")
    if isinstance(node, Absolute):
        return unit_of(node.child)
    if isinstance(node, IfElse):
        check(node.test)
        then, otherwise = unit_of(node.then), unit_of(node.otherwise)
        if then != otherwise:
            raise GrammarError("if-branches need equal units")
        return then
    raise GrammarError(f"not a number node: {node!r}")


def check(node):
    """Raise GrammarError unless the tree is well typed and unit-consistent."""
    if kind_of(node) == NUMBER:
        unit_of(node)
        return
    if isinstance(node, Compare):
        if node.operator not in COMPARISON_OPERATORS:
            raise GrammarError(f"unknown comparison {node.operator!r}")
        if unit_of(node.left) != unit_of(node.right):
            raise GrammarError("a comparison needs equal units")
    elif isinstance(node, Logic):
        if node.operator not in LOGIC_OPERATORS:
            raise GrammarError(f"unknown logic {node.operator!r}")
        if kind_of(node.left) != BOOL or kind_of(node.right) != BOOL:
            raise GrammarError("and/or need conditions")
        check(node.left)
        check(node.right)
    elif isinstance(node, Negate):
        if kind_of(node.child) != BOOL:
            raise GrammarError("not needs a condition")
        check(node.child)
    elif isinstance(node, Member):
        feature = FEATURE_BY_NAME.get(node.feature)
        if feature is None or feature.kind != "category":
            raise GrammarError(f"{node.feature!r} is not a category feature")
        if not node.members or tuple(sorted(set(node.members))) != node.members:
            raise GrammarError("members must be a sorted, non-empty set")
        if not set(node.members) <= set(feature.categories):
            raise GrammarError(f"unknown members of {node.feature}")
    elif isinstance(node, Flag):
        feature = FEATURE_BY_NAME.get(node.name)
        if feature is None or feature.kind != "boolean":
            raise GrammarError(f"{node.name!r} is not a boolean feature")


def size(node):
    """Number of nodes in the tree."""
    return 1 + sum(size(child) for child in children(node))


def nodes_with_paths(node, path=()):
    """Every (path, node) in pre-order; a path is a tuple of child positions."""
    yield path, node
    for position, child in enumerate(children(node)):
        yield from nodes_with_paths(child, path + (position,))


def node_at(node, path):
    """The node at a path."""
    for position in path:
        node = children(node)[position]
    return node


def replace_at(node, path, replacement):
    """A copy of the tree with the node at `path` replaced."""
    if not path:
        return replacement
    child_nodes = list(children(node))
    child_nodes[path[0]] = replace_at(child_nodes[path[0]], path[1:], replacement)
    return with_children(node, child_nodes)


def features_used(node):
    """Sorted names of every feature the tree reads."""
    names = set()
    for _, part in nodes_with_paths(node):
        if isinstance(part, Feature):
            names.add(part.name)
        elif isinstance(part, Member):
            names.add(part.feature)
        elif isinstance(part, Flag):
            names.add(part.name)
    return sorted(names)


# ----- canonical data (JSON) -----


def to_data(node):
    """A JSON-ready, canonical description of the tree."""
    if isinstance(node, Feature):
        return {"node": "feature", "name": node.name}
    if isinstance(node, Constant):
        return {"node": "constant", "value": node.value, "unit": node.unit.code()}
    if isinstance(node, Binary):
        return {
            "node": "binary",
            "operator": node.operator,
            "left": to_data(node.left),
            "right": to_data(node.right),
        }
    if isinstance(node, Absolute):
        return {"node": "absolute", "child": to_data(node.child)}
    if isinstance(node, IfElse):
        return {
            "node": "if",
            "test": to_data(node.test),
            "then": to_data(node.then),
            "otherwise": to_data(node.otherwise),
        }
    if isinstance(node, Compare):
        return {
            "node": "compare",
            "operator": node.operator,
            "left": to_data(node.left),
            "right": to_data(node.right),
        }
    if isinstance(node, Logic):
        return {
            "node": "logic",
            "operator": node.operator,
            "left": to_data(node.left),
            "right": to_data(node.right),
        }
    if isinstance(node, Negate):
        return {"node": "not", "child": to_data(node.child)}
    if isinstance(node, Member):
        return {"node": "member", "feature": node.feature, "members": list(node.members)}
    if isinstance(node, Flag):
        return {"node": "flag", "name": node.name}
    if isinstance(node, Truth):
        return {"node": "truth", "value": node.value}
    raise GrammarError(f"not a node: {node!r}")


def from_data(data):
    """The tree a `to_data` description gives (exact round trip)."""
    kind = data["node"]
    if kind == "feature":
        return Feature(data["name"])
    if kind == "constant":
        return Constant(float(data["value"]), unit_from_code(data["unit"]))
    if kind == "binary":
        return Binary(data["operator"], from_data(data["left"]), from_data(data["right"]))
    if kind == "absolute":
        return Absolute(from_data(data["child"]))
    if kind == "if":
        return IfElse(
            from_data(data["test"]), from_data(data["then"]), from_data(data["otherwise"])
        )
    if kind == "compare":
        return Compare(data["operator"], from_data(data["left"]), from_data(data["right"]))
    if kind == "logic":
        return Logic(data["operator"], from_data(data["left"]), from_data(data["right"]))
    if kind == "not":
        return Negate(from_data(data["child"]))
    if kind == "member":
        return Member(data["feature"], tuple(data["members"]))
    if kind == "flag":
        return Flag(data["name"])
    if kind == "truth":
        return Truth(bool(data["value"]))
    raise GrammarError(f"unknown node {kind!r}")


# ----- display form -----


def format_number(value):
    """Short, readable number text (the JSON keeps full precision)."""
    return f"{value:.4g}"


def display(node, is_code_names=False):
    """The tree in words, with display names (or code names) and units."""

    def name(feature_name):
        return feature_name if is_code_names else FEATURE_BY_NAME[feature_name].display_name

    def wrap(child):
        text = display(child, is_code_names)
        return f"({text})" if isinstance(child, (Binary, Logic, Compare, IfElse)) else text

    if isinstance(node, Feature):
        return name(node.name)
    if isinstance(node, Constant):
        unit = "" if node.unit.is_dimensionless() else " " + node.unit.label()
        return format_number(node.value) + unit
    if isinstance(node, Binary):
        if node.operator in ("min", "max"):
            left = display(node.left, is_code_names)
            return f"{node.operator}({left}, {display(node.right, is_code_names)})"
        return f"{wrap(node.left)} {DISPLAY_SYMBOL[node.operator]} {wrap(node.right)}"
    if isinstance(node, Absolute):
        return f"|{display(node.child, is_code_names)}|"
    if isinstance(node, IfElse):
        test = display(node.test, is_code_names)
        return f"if {test} then {wrap(node.then)} else {wrap(node.otherwise)}"
    if isinstance(node, Compare):
        left = display(node.left, is_code_names)
        return f"{left} {node.operator} {display(node.right, is_code_names)}"
    if isinstance(node, Logic):
        return f"{wrap(node.left)} {node.operator} {wrap(node.right)}"
    if isinstance(node, Negate):
        return f"not {wrap(node.child)}"
    if isinstance(node, Member):
        return f"{name(node.feature)} in {{{', '.join(node.members)}}}"
    if isinstance(node, Flag):
        return name(node.name)
    if isinstance(node, Truth):
        return "always" if node.value else "never"
    raise GrammarError(f"not a node: {node!r}")


# ----- code form and its parser -----


def python_source(node):
    """The tree as a Python expression over helper functions and the row `x`."""
    if isinstance(node, Feature):
        return f"x[{node.name!r}]"
    if isinstance(node, Constant):
        return f"const({node.value!r}, {node.unit.code()!r})"
    if isinstance(node, (Binary, Compare, Logic)):
        function = FUNCTION_BY_OPERATOR[node.operator]
        return f"{function}({python_source(node.left)}, {python_source(node.right)})"
    if isinstance(node, Absolute):
        return f"absolute({python_source(node.child)})"
    if isinstance(node, IfElse):
        return (
            f"if_else({python_source(node.test)}, {python_source(node.then)}, "
            f"{python_source(node.otherwise)})"
        )
    if isinstance(node, Negate):
        return f"not_({python_source(node.child)})"
    if isinstance(node, Member):
        return f"member(x[{node.feature!r}], {node.members!r})"
    if isinstance(node, Flag):
        return f"flag(x[{node.name!r}])"
    if isinstance(node, Truth):
        return f"truth({node.value!r})"
    raise GrammarError(f"not a node: {node!r}")


def parse_python(text):
    """The tree a `python_source` expression describes; GrammarError if outside the dialect."""
    return tree_from_ast(ast.parse(text, mode="eval").body)


def literal(expression):
    """A Python literal (number, string, bool or tuple of strings), else GrammarError."""
    try:
        return ast.literal_eval(expression)
    except ValueError as error:
        raise GrammarError(f"expected a literal, got {ast.unparse(expression)}") from error


def row_key(expression):
    """The feature name of an `x['name']` expression."""
    if (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.value, ast.Name)
        and expression.value.id == "x"
    ):
        return literal(expression.slice)
    raise GrammarError(f"expected x['feature'], got {ast.unparse(expression)}")


def tree_from_ast(expression):
    """Convert one parsed expression of the dialect into a node, checking it."""
    if isinstance(expression, ast.Subscript):
        node = Feature(row_key(expression))
    elif isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name):
        function = expression.func.id
        arguments = expression.args
        if function == "const":
            node = Constant(float(literal(arguments[0])), unit_from_code(literal(arguments[1])))
        elif function in ("add", "sub", "mul", "div", "minimum", "maximum"):
            node = Binary(
                OPERATOR_BY_FUNCTION[function],
                tree_from_ast(arguments[0]),
                tree_from_ast(arguments[1]),
            )
        elif function in ("gt", "lt"):
            node = Compare(
                OPERATOR_BY_FUNCTION[function],
                tree_from_ast(arguments[0]),
                tree_from_ast(arguments[1]),
            )
        elif function in ("and_", "or_"):
            node = Logic(
                OPERATOR_BY_FUNCTION[function],
                tree_from_ast(arguments[0]),
                tree_from_ast(arguments[1]),
            )
        elif function == "absolute":
            node = Absolute(tree_from_ast(arguments[0]))
        elif function == "not_":
            node = Negate(tree_from_ast(arguments[0]))
        elif function == "if_else":
            node = IfElse(*(tree_from_ast(argument) for argument in arguments))
        elif function == "member":
            node = Member(row_key(arguments[0]), tuple(literal(arguments[1])))
        elif function == "flag":
            node = Flag(row_key(arguments[0]))
        elif function == "truth":
            node = Truth(bool(literal(arguments[0])))
        else:
            raise GrammarError(f"unknown function {function!r}")
    else:
        raise GrammarError(f"outside the trader dialect: {ast.unparse(expression)}")
    check(node)
    return node


# ----- vectorised evaluation -----


class EvaluationCache:
    """Sub-expression results shared across a population, keyed by (tree, window).

    Holds at most `capacity_bytes` of arrays; the oldest entries leave first.
    """

    def __init__(self, capacity_bytes=512 * 2**20):
        """Start empty, holding at most capacity_bytes of arrays."""
        self.capacity_bytes = capacity_bytes
        self.entries = {}
        self.used_bytes = 0

    def get(self, key):
        """The cached array, or None."""
        return self.entries.get(key)

    def put(self, key, value):
        """Remember an array, evicting the oldest entries when full."""
        if value.nbytes > self.capacity_bytes:
            return
        while self.used_bytes + value.nbytes > self.capacity_bytes and self.entries:
            oldest = next(iter(self.entries))
            self.used_bytes -= self.entries.pop(oldest).nbytes
        self.entries[key] = value
        self.used_bytes += value.nbytes


def category_codes(feature_name, members):
    """Category codes (floats) of member names."""
    categories = FEATURE_BY_NAME[feature_name].categories
    return np.array([float(categories.index(member)) for member in members])


def evaluate(node, store, start, end, cache=None):
    """The tree's values over store days start … end−1.

    Returns a float array broadcastable to (days, 24, locations); NaN = missing; Bool nodes
    give 1.0 / 0.0 / NaN.
    """
    is_cacheable = cache is not None and not isinstance(node, (Feature, Constant, Truth, Flag))
    key = None
    if is_cacheable:
        key = (python_source(node), id(store), start, end)
        cached = cache.get(key)
        if cached is not None:
            return cached
    value = evaluate_uncached(node, store, start, end, cache)
    if is_cacheable:
        cache.put(key, value)
    return value


def strict_bool(condition, *operands):
    """1.0/0.0 from a boolean array, NaN where any operand is NaN."""
    is_missing = np.zeros(np.broadcast_shapes(*(operand.shape for operand in operands)), dtype=bool)
    for operand in operands:
        is_missing = is_missing | np.isnan(operand)
    return np.where(is_missing, np.nan, condition.astype(float))


def evaluate_uncached(node, store, start, end, cache):
    """Evaluate one node (children through the cache)."""
    if isinstance(node, Feature):
        array = store.arrays[node.name]
        return array[start:end] if array.shape[0] > 1 else array
    if isinstance(node, Constant):
        return np.array(node.value).reshape(1, 1, 1)
    if isinstance(node, Truth):
        return np.array(1.0 if node.value else 0.0).reshape(1, 1, 1)
    if isinstance(node, Flag):
        array = store.arrays[node.name]
        return array[start:end] if array.shape[0] > 1 else array
    if isinstance(node, Member):
        array = store.arrays[node.feature]
        array = array[start:end] if array.shape[0] > 1 else array
        is_member = np.isin(array, category_codes(node.feature, node.members))
        return np.where(np.isnan(array), np.nan, is_member.astype(float))
    values = [evaluate(child, store, start, end, cache) for child in children(node)]
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        if isinstance(node, Binary):
            left, right = values
            if node.operator == "+":
                return left + right
            if node.operator == "-":
                return left - right
            if node.operator == "*":
                return left * right
            if node.operator == "/":
                quotient = np.where(right == 0, 0.0, left / np.where(right == 0, 1.0, right))
                return np.where(np.isnan(left) | np.isnan(right), np.nan, quotient)
            if node.operator == "min":
                return np.minimum(left, right)
            if node.operator == "max":
                return np.maximum(left, right)
        if isinstance(node, Absolute):
            return np.abs(values[0])
        if isinstance(node, IfElse):
            test, then, otherwise = values
            chosen = np.where(test == 1.0, then, otherwise)
            return np.where(np.isnan(test), np.nan, chosen)
        if isinstance(node, Compare):
            left, right = values
            condition = left > right if node.operator == ">" else left < right
            return strict_bool(condition, left, right)
        if isinstance(node, Logic):
            left, right = values
            condition = (
                (left == 1.0) & (right == 1.0)
                if node.operator == "and"
                else (left == 1.0) | (right == 1.0)
            )
            return strict_bool(condition, left, right)
        if isinstance(node, Negate):
            child = values[0]
            return np.where(np.isnan(child), np.nan, 1.0 - child)
    raise GrammarError(f"not a node: {node!r}")
