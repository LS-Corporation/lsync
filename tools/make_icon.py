from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1] / "assets"
SIZE = 1024


def letters() -> Image.Image:
    gray = ImageOps.grayscale(Image.open(ROOT / "logo-source.png"))
    alpha = gray.point(lambda v: 0 if v < 40 else (255 if v > 215 else int((v - 40) * 255 / 175)))
    box = alpha.getbbox()
    alpha = alpha.crop(box)
    out = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def app_icon(mark: Image.Image) -> Image.Image:
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bg = Image.new("L", (SIZE * 4, SIZE * 4), 0)
    ImageDraw.Draw(bg).rounded_rectangle((0, 0, SIZE * 4 - 1, SIZE * 4 - 1), radius=SIZE * 4 * 0.22, fill=255)
    icon.paste((10, 10, 12, 255), (0, 0), bg.resize((SIZE, SIZE), Image.LANCZOS))
    width = int(SIZE * 0.74)
    mark = mark.resize((width, round(mark.height * width / mark.width)), Image.LANCZOS)
    icon.alpha_composite(mark, ((SIZE - mark.width) // 2, (SIZE - mark.height) // 2))
    return icon


mark = letters()
mark.save(ROOT / "logo.png")
icon = app_icon(mark)
icon.save(ROOT / "icon.png")
icon.save(ROOT / "icon.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
print("ok", mark.size)
