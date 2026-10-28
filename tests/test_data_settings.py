"""Tests for the `[data]` settings and the MISO redistribution switch (round 25)."""

import pytest

from evobots.config import load_data_settings
from evobots.config.data import DataSettings, shareable_sources


def test_default_leaves_miso_out():
    settings = load_data_settings("configs/10_miso_hubs.toml")
    assert settings.is_miso_redistribution_allowed is False
    assert "miso" not in shareable_sources(settings)


def test_switch_on_from_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[data]\nis_miso_redistribution_allowed = true\n", encoding="utf-8")
    assert "miso" in shareable_sources(load_data_settings(path))


@pytest.mark.parametrize("text", ['is_miso_redistribution_allowed = "false"', "bundle_miso = 1"])
def test_bad_values_and_unknown_keys_rejected(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(f"[data]\n{text}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_data_settings(path)


def test_no_file_gives_defaults():
    assert load_data_settings() == DataSettings()
