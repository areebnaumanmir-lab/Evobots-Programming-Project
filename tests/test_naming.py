"""Names are full words (docs/design_spec.md §14.1), checked on every identifier in src/, tools/,
tests/,
benchmarks/.

Every identifier a module defines (functions, classes, arguments, variables, attributes) is
split into words at underscores and case changes. A word of one or two letters, or one on
COMMON_ABBREVIATIONS, must be in naming_allowlist.txt. Names may not say "percent" (use
`_fraction`), and an argument or constant whose default is True or False must start with
is_, has_ or can_.
"""

import ast
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKED_DIRECTORIES = ("src", "tools", "tests", "benchmarks")
ALLOWLIST_PATH = REPOSITORY_ROOT / "naming_allowlist.txt"
# Abbreviations that are long enough to pass the length rule but still unclear.
COMMON_ABBREVIATIONS = {
    "arr",
    "avg",
    "buf",
    "calc",
    "cfg",
    "cnt",
    "col",
    "cols",
    "ctx",
    "cur",
    "df",
    "dir",
    "dt",
    "elem",
    "err",
    "fn",
    "func",
    "idx",
    "info",
    "lst",
    "msg",
    "num",
    "obj",
    "pct",
    "pos",
    "prev",
    "pts",
    "res",
    "ret",
    "sec",
    "src",
    "std",
    "str",
    "tmp",
    "val",
    "vals",
    "var",
    "vec",
}
BOOLEAN_PREFIXES = ("is_", "has_", "can_")
# Names Python or a library chooses for us.
EXTERNAL_NAMES = {"self", "cls", "argv", "main", "tmp_path", "tmp_path_factory", "should_exit"}


def allowed_words():
    words = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return words


def words_of(identifier):
    """'trailing_p99DailyLoss' → ['trailing', 'p99', 'daily', 'loss']."""
    words = []
    for part in identifier.strip("_").split("_"):
        # Split camelCase at lower→upper changes; keep letter-digit runs like p99 whole.
        words += re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", part).lower().split("_")
    # Words starting with a digit are numbers or section labels (840, 4b, 05m).
    return [word for word in words if word and not word[0].isdigit()]


def assigned_elements(target):
    """The names an assignment target defines: unpack tuples, skip subscripts' contents."""
    if isinstance(target, (ast.Tuple, ast.List)):
        return [element for item in target.elts for element in assigned_elements(item)]
    if isinstance(target, ast.Starred):
        return assigned_elements(target.value)
    if isinstance(target, (ast.Name, ast.Attribute)):
        return [target]
    return []


def defined_names(tree):
    """(name, line, is_boolean_default) for every name the module defines."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append((node.name, node.lineno, False))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            arguments = node.args
            positional = arguments.posonlyargs + arguments.args
            defaults = [None] * (len(positional) - len(arguments.defaults)) + arguments.defaults
            pairs = list(zip(positional, defaults)) + list(
                zip(arguments.kwonlyargs, arguments.kw_defaults)
            )
            for argument, default in pairs:
                is_boolean = isinstance(default, ast.Constant) and isinstance(default.value, bool)
                names.append((argument.arg, argument.lineno, is_boolean))
            for argument in (arguments.vararg, arguments.kwarg):
                if argument is not None:
                    names.append((argument.arg, argument.lineno, False))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            is_boolean = isinstance(value, ast.Constant) and isinstance(value.value, bool)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for element in assigned_elements(target):
                    if isinstance(element, ast.Name):
                        names.append((element.id, element.lineno, is_boolean))
                    elif isinstance(element, ast.Attribute):
                        names.append((element.attr, element.lineno, is_boolean))
        if isinstance(node, (ast.For, ast.comprehension, ast.With)):
            targets = (
                [item.optional_vars for item in node.items if item.optional_vars]
                if isinstance(node, ast.With)
                else [node.target]
            )
            for target in targets:
                for element in ast.walk(target):
                    if isinstance(element, ast.Name):
                        names.append((element.id, getattr(element, "lineno", 0), False))
        if isinstance(node, ast.ExceptHandler) and node.name:
            names.append((node.name, node.lineno, False))
    return names


def naming_problems(path, allowed):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems = []
    for name, line, is_boolean_default in defined_names(tree):
        if name in EXTERNAL_NAMES or (name.startswith("__") and name.endswith("__")):
            continue
        if name == "_":
            continue
        where = f"{path.relative_to(REPOSITORY_ROOT)}:{line} {name}"
        for word in words_of(name):
            if (len(word) <= 2 or word in COMMON_ABBREVIATIONS) and word not in allowed:
                problems.append(f"{where}: '{word}' is not a full word")
            if word in ("percent", "pct"):
                problems.append(f"{where}: use _fraction, not percent")
        bare_name = name.lstrip("_").lower()
        if is_boolean_default and not bare_name.startswith(BOOLEAN_PREFIXES):
            problems.append(f"{where}: a boolean name starts with is_, has_ or can_")
    return problems


def checked_files():
    for directory in CHECKED_DIRECTORIES:
        yield from sorted((REPOSITORY_ROOT / directory).rglob("*.py"))


def test_words_of_splits_identifiers():
    assert words_of("trailing_p99_daily_loss") == ["trailing", "p99", "daily", "loss"]
    assert words_of("CapitalSettings") == ["capital", "settings"]
    assert words_of("test_section_4b_table") == ["test", "section", "table"]
    assert words_of("HUB_MEDIAN_CLEARED_MW") == ["hub", "median", "cleared", "mw"]


def test_names_are_full_words():
    allowed = allowed_words()
    problems = [problem for path in checked_files() for problem in naming_problems(path, allowed)]
    assert problems == [], "\n" + "\n".join(problems)
