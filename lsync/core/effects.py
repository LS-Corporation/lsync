from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageOps

from lsync.core.utils import TaskContext
from lsync.i18n import _


RESIZE_MODES = {"percent": "Porcentagem", "size": "Largura e altura", "width": "Só largura", "height": "Só altura", "none": "Manter tamanho"}
FIT_MODES = {
    "contain": "Manter proporção (cabe dentro)",
    "cover": "Cortar para preencher",
    "stretch": "Esticar (ignora proporção)",
}


def make_resizer(mode: str, percent: float = 50, width: int = 0, height: int = 0, fit: str = "contain") -> Callable[[Image.Image], Image.Image]:
    def resize(img: Image.Image) -> Image.Image:
        w, h = img.size
        if mode == "none":
            return img
        if mode == "percent":
            f = max(percent, 1) / 100
            return img.resize((max(1, round(w * f)), max(1, round(h * f))), Image.LANCZOS)
        if mode == "width":
            if width <= 0:
                raise ValueError(_("Informe a largura."))
            return img.resize((width, max(1, round(h * width / w))), Image.LANCZOS)
        if mode == "height":
            if height <= 0:
                raise ValueError(_("Informe a altura."))
            return img.resize((max(1, round(w * height / h)), height), Image.LANCZOS)
        if width <= 0 or height <= 0:
            raise ValueError(_("Informe largura e altura."))
        if fit == "stretch":
            return img.resize((width, height), Image.LANCZOS)
        if fit == "cover":
            return ImageOps.fit(img, (width, height), Image.LANCZOS)
        scale = min(width / w, height / h)
        return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)

    return resize


COLOR_EFFECTS = {
    "none": "Nenhum (só os ajustes)",
    "gray": "Preto e branco (tons de cinza)",
    "bw": "Preto e branco puro (alto contraste)",
    "colorize": "Colorir foto P&B com IA",
    "sepia": "Sépia (foto antiga)",
    "invert": "Negativo (inverter cores)",
    "tint": "Tingir com uma cor",
}
EFFECT_SUFFIX = {
    "none": " editada", "gray": " P&B", "bw": " P&B", "colorize": " colorida",
    "sepia": " sépia", "invert": " negativo", "tint": " tingida",
}

ADJUSTMENTS = [
    ("brightness", "Brilho", -100, 100),
    ("contrast", "Contraste", -100, 100),
    ("saturation", "Saturação", -100, 100),
    ("vibrance", "Vibração", -100, 100),
    ("hue", "Matiz", -180, 180),
    ("temperature", "Temperatura", -100, 100),
    ("tint", "Tonalidade", -100, 100),
    ("sharpness", "Nitidez", 0, 100),
]


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def _luma(arr: np.ndarray) -> np.ndarray:
    return (arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114)[..., None]


def apply_adjustments(img: Image.Image, adj: dict) -> Image.Image:
    if not any(adj.get(k) for k, *_rest in ADJUSTMENTS):
        return img
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0

    t = adj.get("temperature", 0) / 100
    if t:
        arr[..., 0] *= 1 + 0.25 * t
        arr[..., 2] *= 1 - 0.25 * t
    tn = adj.get("tint", 0) / 100
    if tn:
        arr[..., 1] *= 1 - 0.2 * tn
    b = adj.get("brightness", 0) / 100
    if b:
        arr = arr * (1 + b) if b < 0 else arr + (1 - arr) * b * 0.8
    c = adj.get("contrast", 0) / 100
    if c:
        arr = (arr - 0.5) * (1 + c) + 0.5
    s = adj.get("saturation", 0) / 100
    if s:
        gray = _luma(arr)
        arr = gray + (arr - gray) * (1 + s)
    v = adj.get("vibrance", 0) / 100
    if v:
        arr = np.clip(arr, 0, 1)
        sat = (arr.max(axis=2) - arr.min(axis=2))[..., None]
        gray = _luma(arr)
        arr = gray + (arr - gray) * (1 + v * (1 - sat))

    out = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")

    hue = adj.get("hue", 0)
    if hue:
        hsv = np.asarray(out.convert("HSV")).copy()
        hsv[..., 0] = (hsv[..., 0].astype(np.int16) + round(hue / 360 * 256)) % 256
        out = Image.fromarray(hsv, "HSV").convert("RGB")
    sh = adj.get("sharpness", 0)
    if sh:
        out = ImageEnhance.Sharpness(out).enhance(1 + sh / 100 * 2)
    return out


def make_color_effect(
    effect: str,
    adjustments: Optional[dict] = None,
    threshold: int = 128,
    tint_color: str = "#2f7fff",
    ctx: Optional[TaskContext] = None,
    preview: bool = False,
) -> Callable[[Image.Image], Image.Image]:
    adjustments = adjustments or {}

    def base(img: Image.Image) -> Image.Image:
        if effect == "gray":
            return ImageOps.grayscale(img)
        if effect == "bw":
            return ImageOps.grayscale(img).point(lambda v: 255 if v >= threshold else 0)
        if effect == "colorize" and not preview:
            from lsync.core import ai

            return ai.colorize(img, ctx)
        if effect == "sepia":
            return ImageOps.colorize(ImageOps.grayscale(img), black="#1e1408", white="#fff3dc", mid="#a0784c")
        if effect == "invert":
            return ImageOps.invert(img)
        if effect == "tint":
            gray = ImageOps.autocontrast(ImageOps.grayscale(img))
            return ImageOps.colorize(gray, black="#000000", white="#ffffff", mid=_hex_to_rgb(tint_color))
        return img

    def apply(img: Image.Image) -> Image.Image:
        alpha = img.getchannel("A") if img.mode == "RGBA" else None
        out = apply_adjustments(base(img.convert("RGB")).convert("RGB"), adjustments)
        if alpha is not None:
            out.putalpha(alpha)
        return out

    return apply


CROP_MODES = {"off": "Não cortar", "auto": "Tirar bordas automaticamente", "manual": "Cortar manualmente"}
CROP_RATIOS = {"free": "Livre", "1:1": "1:1", "16:9": "16:9", "9:16": "9:16", "4:3": "4:3", "3:4": "3:4"}


def trim_box(img: Image.Image, tolerance: int = 20) -> Optional[tuple[int, int, int, int]]:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    if w < 3 or h < 3:
        return None
    corners = [rgba.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if sum(1 for c in corners if c[3] < 16) >= 3:
        box = rgba.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
    else:
        bg = tuple(sorted(c[i] for c in corners)[1:3][0] // 2 + sorted(c[i] for c in corners)[1:3][1] // 2 for i in range(3))
        diff = ImageChops.difference(rgba.convert("RGB"), Image.new("RGB", (w, h), bg)).convert("L")
        limit = max(6, int(tolerance * 2.55))
        box = diff.point(lambda v: 255 if v > limit else 0).getbbox()
    if not box or box == (0, 0, w, h) or box[2] - box[0] < 4 or box[3] - box[1] < 4:
        return None
    return box


def manual_box(size: tuple[int, int], fractions: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    w, h = size
    left, top, right, bottom = fractions
    x0, y0 = round(left * w), round(top * h)
    return x0, y0, max(x0 + 1, round(right * w)), max(y0 + 1, round(bottom * h))


def make_cropper(mode: str, tolerance: int = 20, fractions: tuple[float, float, float, float] = (0, 0, 1, 1)) -> Callable[[Image.Image], Image.Image]:
    state: dict = {}

    def crop(img: Image.Image) -> Image.Image:
        if mode == "off":
            return img
        if "box" not in state:
            state["box"] = trim_box(img, tolerance) if mode == "auto" else manual_box(img.size, fractions)
        box = state["box"]
        return img.crop(box) if box else img

    return crop


def chain(*fns: Callable[[Image.Image], Image.Image]) -> Callable[[Image.Image], Image.Image]:
    def run(img: Image.Image) -> Image.Image:
        for fn in fns:
            img = fn(img)
        return img

    return run
