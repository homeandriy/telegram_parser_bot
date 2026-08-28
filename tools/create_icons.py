"""Create a multi-resolution Windows icon from the canonical PNG brand asset."""

from pathlib import Path

from PIL import Image


root = Path(__file__).resolve().parents[1]
source = root / "assets" / "telegram-alert.png"
target = root / "assets" / "telegram-alert.ico"

with Image.open(source) as image:
    rgba = image.convert("RGBA")
    rgba.save(target, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    rgba.resize((55, 55), Image.Resampling.LANCZOS).convert("RGB").save(root / "assets" / "wizard-small.bmp")
    canvas = Image.new("RGB", (164, 314), "#171717")
    logo = rgba.copy(); logo.thumbnail((150, 150), Image.Resampling.LANCZOS)
    canvas.paste(logo, ((164 - logo.width) // 2, 36), logo)
    canvas.save(root / "assets" / "wizard-large.bmp")
