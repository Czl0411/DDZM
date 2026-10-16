from pathlib import Path

import pytest
from PIL import Image, ImageChops

from dzmm_bot.browser.workstation_image import render_workstation_image


ASSETS = Path(__file__).resolve().parents[2] / "src/dzmm_bot/admin/static/workstation"


def test_empty_scene_preserves_all_base_objects(tmp_path):
    path = tmp_path / "empty.png"
    render_workstation_image({"equipped": []}, path)
    with Image.open(path) as actual, Image.open(ASSETS / "core-base.png") as base:
        assert actual.size == (1536, 1024)
        assert ImageChops.difference(actual.convert("RGB"), base.convert("RGB")).getbbox() is None


def test_equipment_layers_use_the_same_order_as_the_webpage(tmp_path):
    keys = ["monitor-main", "monitor-left", "keyboard", "chair"]
    path = tmp_path / "equipped.png"
    render_workstation_image({"equipped": [{"asset_key": key} for key in keys]}, path)
    with Image.open(ASSETS / "core-base.png") as base:
        expected = base.convert("RGBA")
    for key in ["monitor-left", "monitor-main", "keyboard", "chair"]:
        with Image.open(ASSETS / f"{key}-layer.png") as layer:
            expected.alpha_composite(layer.convert("RGBA"))
    with Image.open(path) as actual:
        assert ImageChops.difference(actual.convert("RGB"), expected.convert("RGB")).getbbox() is None


def test_untrusted_asset_paths_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown"):
        render_workstation_image({"equipped": [{"asset_key": "../../other"}]}, tmp_path / "invalid.png")
