"""Generate windows/jarvis.ico — the Start Menu shortcut icon — from
src/Assets/logo.png.

Uses Pillow rather than reimplementing an ICO writer: unlike FreeClaw's own
windows/make_icon.py (which draws its mark procedurally and deliberately
stays stdlib-only), Jarvis already depends on Pillow at runtime for the MCP
server's screenshot tool, so reaching for it here costs nothing extra. Run
from the repo root:

    python windows/make_icon.py
"""

import os

from PIL import Image

SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def build():
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "..", "src", "Assets", "logo.png")
    out = os.path.join(here, "jarvis.ico")

    with Image.open(src) as img:
        img = img.convert("RGBA")
        # Square source, but crop to the visible mark first if it isn't
        # already tight — a logo with a lot of transparent padding shrinks to
        # a speck at 16x16 otherwise. logo.png's bounding box is used as-is;
        # get_bbox() finds it without assuming anything about the padding.
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        img.save(out, format="ICO", sizes=SIZES)

    size_bytes = os.path.getsize(out)
    print(f"wrote {out} ({size_bytes:,} bytes, {len(SIZES)} sizes)")


if __name__ == "__main__":
    build()
