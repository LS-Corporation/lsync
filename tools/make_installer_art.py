from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / "assets"
OUT = ROOT / "installer"
SCALES = (100, 125, 150, 175, 200, 250)
TOP = (14, 16, 20)
BOTTOM = (20, 30, 52)
ACCENT = (59, 130, 246)


def gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        draw.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    return img


def glow(img: Image.Image, center: tuple[float, float], radius: float, strength: int) -> Image.Image:
    layer = Image.new("RGB", img.size, (0, 0, 0))
    cx, cy = center
    ImageDraw.Draw(layer).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=tuple(c * strength // 100 for c in ACCENT))
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.6))
    return ImageChops.add(img, layer)


def logo(width: int) -> Image.Image:
    mark = Image.open(ROOT / "logo.png").convert("RGBA")
    return mark.resize((width, round(mark.height * width / mark.width)), Image.LANCZOS)


def wizard(scale: int) -> Image.Image:
    w, h = round(164 * scale / 100), round(314 * scale / 100)
    img = glow(gradient(w, h), (w * 0.5, h * 0.36), w * 0.55, 45)
    mark = logo(round(w * 0.56))
    canvas = img.convert("RGBA")
    canvas.alpha_composite(mark, ((w - mark.width) // 2, round(h * 0.36 - mark.height / 2)))
    bar_h = max(2, round(3 * scale / 100))
    ImageDraw.Draw(canvas).rectangle((0, h - bar_h, w, h), fill=ACCENT + (255,))
    return canvas.convert("RGB")


def small(scale: int) -> Image.Image:
    s = round(55 * scale / 100)
    icon = Image.open(ROOT / "icon.png").convert("RGBA").resize((s, s), Image.LANCZOS)
    return icon


OUT.mkdir(parents=True, exist_ok=True)
for sc in SCALES:
    wizard(sc).save(OUT / f"wizard-{sc}.bmp")
    small(sc).save(OUT / f"small-{sc}.bmp")
print("ok", sorted(p.name for p in OUT.iterdir()))
