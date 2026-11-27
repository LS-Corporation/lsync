from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / "assets"
SIZE = 1024
SUPER = 4
INSET = 3


def load_source() -> Image.Image:
    path = ROOT / "icon-source.webp"
    try:
        img = Image.open(path)
        img.load()
        return img.convert("RGBA")
    except OSError:
        import cv2

        bgra = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if bgra.shape[2] == 3:
            bgra = cv2.cvtColor(bgra, cv2.COLOR_BGR2BGRA)
        return Image.fromarray(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA), "RGBA")


def subject_box(rgba: np.ndarray) -> tuple[int, int, int, int, int]:
    alpha = rgba[..., 3]
    if (alpha < 16).mean() > 0.05:
        card = alpha > 128
    else:
        a = rgba[..., :3].astype(np.float32) / 255.0
        hi, lo = a.max(axis=2), a.min(axis=2)
        sat = (hi - lo) / np.maximum(hi, 1e-6)
        card = (sat > 0.35) | (hi < 0.3)
    rows = np.nonzero(card.mean(axis=1) > 0.5)[0]
    cols = np.nonzero(card.mean(axis=0) > 0.5)[0]
    y0, y1, x0, x1 = int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1
    steps = []
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1 - 1, y0, -1, 1), (x0, y1 - 1, 1, -1), (x1 - 1, y1 - 1, -1, -1)):
        for t in range(min(x1 - x0, y1 - y0) // 2):
            if card[cy + dy * t, cx + dx * t]:
                steps.append(t)
                break
    t = float(np.median(steps)) if steps else 0.0
    radius = max(8, round(t / (1 - 1 / np.sqrt(2))))
    return x0, y0, x1, y1, radius


def rounded_mask(w: int, h: int, radius: int) -> Image.Image:
    big = Image.new("L", (w * SUPER, h * SUPER), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * SUPER - 1, h * SUPER - 1), radius=radius * SUPER, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def build() -> Image.Image:
    src = load_source()
    x0, y0, x1, y1, radius = subject_box(np.asarray(src))
    x0, y0, x1, y1 = x0 + INSET, y0 + INSET, x1 - INSET, y1 - INSET
    radius = max(4, radius - INSET)
    card = src.crop((x0, y0, x1, y1))
    mask = rounded_mask(card.width, card.height, radius)
    card = card.convert("RGB").convert("RGBA")
    card.putalpha(mask)
    side = max(card.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(card, ((side - card.width) // 2, (side - card.height) // 2))
    margin = round(SIZE * 0.02)
    inner = SIZE - 2 * margin
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.alpha_composite(square.resize((inner, inner), Image.LANCZOS), (margin, margin))
    print("recorte:", (x0, y0, x1, y1), "raio:", radius)
    return out


icon = build()
icon.save(ROOT / "icon.png")
icon.save(ROOT / "icon.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
print("ok")
