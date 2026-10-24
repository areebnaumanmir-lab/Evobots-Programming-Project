"""Configuration loading: code defaults < TOML file < command-line overrides."""

import tomllib
from dataclasses import fields
from pathlib import Path

from evobots.config.capital import CapitalSettings

CAPITAL_TABLE = "capital"


def load_capital(config_path=None, overrides=None):
    """Build CapitalSettings from the code defaults, a TOML `[capital]` table, then overrides.

    Args:
        config_path: a TOML file (e.g. configs/10_miso_hubs.toml) or None.
        overrides: {setting name: value} from the command line; None values are ignored.

    Returns:
        A validated CapitalSettings.

    Raises:
        ValueError: for an unknown key or a value outside its bounds.
    """
    known_names = {setting.name for setting in fields(CapitalSettings)}
    values = {}
    if config_path is not None:
        with Path(config_path).open("rb") as config_file:
            table = tomllib.load(config_file).get(CAPITAL_TABLE, {})
        unknown = set(table) - known_names
        if unknown:
            raise ValueError(f"unknown [capital] keys: {', '.join(sorted(unknown))}")
        values.update(table)
    for name, value in (overrides or {}).items():
        if name not in known_names:
            raise ValueError(f"unknown capital setting: {name}")
        if value is not None:
            values[name] = value
    return CapitalSettings(**values)
