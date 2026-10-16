from pathlib import Path

from PIL import Image

from dzmm_bot.core.workstation import WORKSTATION_LAYERS


def render_workstation_image(payload, output_path):
    assets = Path(__file__).resolve().parents[1] / "admin" / "static" / "workstation"
    with Image.open(assets / "core-base.png") as base:
        canvas = base.convert("RGBA")
    keys = list(dict.fromkeys(item["asset_key"] for item in payload["equipped"]))
    for key in sorted(keys, key=lambda value: WORKSTATION_LAYERS.get(value, 0)):
        if key not in WORKSTATION_LAYERS:
            raise ValueError("Unknown workstation equipment asset")
        with Image.open(assets / f"{key}-layer.png") as layer:
            if layer.size != canvas.size:
                raise ValueError("Workstation layer dimensions do not match")
            canvas.alpha_composite(layer.convert("RGBA"))
    canvas.convert("RGB").save(output_path, format="PNG")
