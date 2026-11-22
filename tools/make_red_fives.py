"""生成日麻的赤五牌面: 把 frontend/public/tiles/ 里 5 万、5 筒、5 条的彩色笔画和圆点改成红色。

    python tools/make_red_fives.py

输出 man0.png、pin0.png、sou0.png(0 在牌的写法里表示赤 5)。牌面底色和边框饱和度低,不受影响。
需要 Pillow(只有这个一次性工具用,不在项目依赖里)。
"""
from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image

TILES = Path(__file__).resolve().parent.parent / "frontend" / "public" / "tiles"
RED_HUE = 0.99


def redden(src: Path, dst: Path) -> None:
    im = Image.open(src).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s > 0.45 and v > 0.2:  # 有颜色的笔画、圆点、竹节
                rr, gg, bb = colorsys.hsv_to_rgb(RED_HUE, max(s, 0.85), min(1.0, max(v, 0.75)))
                px[x, y] = (round(rr * 255), round(gg * 255), round(bb * 255), a)
    im.save(dst, optimize=True)


def main() -> None:
    for suit in ("man", "pin", "sou"):
        redden(TILES / f"{suit}5.png", TILES / f"{suit}0.png")
        print(f"写好了 {suit}0.png")


if __name__ == "__main__":
    main()
