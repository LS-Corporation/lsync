from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageOps, ImageSequence

from lsync.core import ffmpeg
from lsync.core.formats import kind_of
from lsync.core.utils import TaskContext, unique_path
from lsync.i18n import _

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pillow_heif = None

Image.init()


@dataclass(frozen=True)
class ImageFormat:
    label: str
    pil: str
    ext: str
    alpha: bool
    animated: bool


_ALL_FORMATS = [
    ImageFormat("PNG", "PNG", "png", True, True),
    ImageFormat("JPG", "JPEG", "jpg", False, False),
    ImageFormat("WEBP", "WEBP", "webp", True, True),
    ImageFormat("GIF", "GIF", "gif", True, True),
    ImageFormat("BMP", "BMP", "bmp", False, False),
    ImageFormat("TIFF", "TIFF", "tiff", True, True),
    ImageFormat("ICO (ícone)", "ICO", "ico", True, False),
    ImageFormat("AVIF", "AVIF", "avif", True, True),
    ImageFormat("HEIC", "HEIF", "heic", True, False),
    ImageFormat("PDF", "PDF", "pdf", False, True),
    ImageFormat("JPEG 2000", "JPEG2000", "jp2", True, False),
    ImageFormat("TGA", "TGA", "tga", True, False),
    ImageFormat("DDS", "DDS", "dds", True, False),
    ImageFormat("ICNS (ícone Mac)", "ICNS", "icns", True, False),
    ImageFormat("QOI", "QOI", "qoi", True, False),
    ImageFormat("PCX", "PCX", "pcx", False, False),
    ImageFormat("PPM", "PPM", "ppm", False, False),
]


def available_formats() -> list[ImageFormat]:
    return [f for f in _ALL_FORMATS if f.pil in Image.SAVE]


def format_by_label(label: str) -> ImageFormat:
    for f in _ALL_FORMATS:
        if f.label == label:
            return f
    raise ValueError(label)


def format_for_ext(ext: str) -> Optional[ImageFormat]:
    ext = ext.lower().lstrip(".")
    aliases = {"jpeg": "jpg", "jfif": "jpg", "jpe": "jpg", "tif": "tiff", "heif": "heic"}
    ext = aliases.get(ext, ext)
    for f in available_formats():
        if f.ext == ext:
            return f
    return None


@dataclass
class Frames:
    images: list[Image.Image]
    durations: list[int]
    loop: int = 0

    @property
    def animated(self) -> bool:
        return len(self.images) > 1


def _normalize(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "RGB"):
        return img
    if img.mode in ("P", "PA", "LA", "La") or "transparency" in img.info:
        return img.convert("RGBA")
    if img.mode in ("I", "I;16", "F"):
        return ImageOps.autocontrast(img.convert("I").point(lambda v: v / 256)).convert("RGB")
    return img.convert("RGB") if img.mode in ("CMYK", "YCbCr", "LAB", "HSV", "L", "1") else img.convert("RGBA")


def open_image(path: str | Path) -> Image.Image:
    with Image.open(path) as im:
        im.seek(0)
        img = ImageOps.exif_transpose(im) or im
        return _normalize(img.copy())


def video_frames(
    path: str | Path,
    ctx: Optional[TaskContext] = None,
    fps: Optional[float] = None,
    max_seconds: Optional[float] = None,
    first_only: bool = False,
    max_side: Optional[int] = None,
) -> Frames:
    info = ffmpeg.probe(path)
    if not info["has_video"]:
        raise RuntimeError(_("Esse arquivo não tem imagem de vídeo."))
    with tempfile.TemporaryDirectory(prefix="lsync_") as tmp:
        filters = []
        if fps:
            filters.append(f"fps={fps}")
        if max_side:
            filters.append(f"scale='min({max_side},iw)':'min({max_side},ih)':force_original_aspect_ratio=decrease")
        args = []
        if Path(path).suffix.lower() == ".webm" and "libvpx-vp9" in ffmpeg.available_encoders():
            args += ["-c:v", "libvpx-vp9"]
        args += ["-i", str(path)]
        if max_seconds:
            args += ["-t", str(max_seconds)]
        if filters:
            args += ["-vf", ",".join(filters)]
        if first_only:
            args += ["-frames:v", "1"]
        args += ["-an", "-pix_fmt", "rgba", str(Path(tmp) / "f_%06d.png")]
        duration = info["duration"]
        if max_seconds and duration:
            duration = min(duration, max_seconds)
        try:
            ffmpeg.run(args, ctx, duration)
        except RuntimeError:
            if args[:1] == ["-c:v"]:
                ffmpeg.run(args[2:], ctx, duration)
            else:
                raise
        files = sorted(Path(tmp).glob("f_*.png"))
        if not files:
            raise RuntimeError(_("Não consegui extrair quadros desse vídeo."))
        images = []
        for f in files:
            with Image.open(f) as im:
                images.append(_normalize(im.copy()))
    frame_ms = int(round(1000 / fps)) if fps else 40
    return Frames(images, [frame_ms] * len(images))


def load_frames(path: str | Path, ctx: Optional[TaskContext] = None, **video_kw) -> Frames:
    if kind_of(path) == "video":
        return video_frames(path, ctx, **video_kw)
    with Image.open(path) as im:
        n = getattr(im, "n_frames", 1)
        if n <= 1:
            img = ImageOps.exif_transpose(im) or im
            return Frames([_normalize(img.copy())], [100])
        images, durations = [], []
        for frame in ImageSequence.Iterator(im):
            images.append(_normalize(frame.copy()).convert("RGBA"))
            durations.append(int(frame.info.get("duration", im.info.get("duration", 100)) or 100))
        return Frames(images, durations, int(im.info.get("loop", 0) or 0))


def flatten(img: Image.Image, background=(255, 255, 255)) -> Image.Image:
    if img.mode != "RGBA":
        return img.convert("RGB")
    bg = Image.new("RGB", img.size, background)
    bg.paste(img, mask=img.getchannel("A"))
    return bg


def _prepare(img: Image.Image, fmt: ImageFormat) -> Image.Image:
    img = _normalize(img)
    if not fmt.alpha:
        return flatten(img)
    if fmt.pil == "ICO":
        img = img.convert("RGBA")
        if max(img.size) > 256:
            img.thumbnail((256, 256), Image.LANCZOS)
    if fmt.pil == "ICNS":
        img = img.convert("RGBA")
        side = max(img.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        img = canvas.resize((1024, 1024), Image.LANCZOS)
    return img


def _save_kwargs(fmt: ImageFormat, quality: int) -> dict:
    if fmt.pil == "JPEG":
        return {"quality": quality, "optimize": True, "subsampling": 0 if quality >= 90 else 2}
    if fmt.pil == "WEBP":
        return {"quality": quality, "method": 6}
    if fmt.pil in ("AVIF", "HEIF"):
        return {"quality": quality}
    if fmt.pil == "PNG":
        return {"optimize": True}
    if fmt.pil == "TIFF":
        return {"compression": "tiff_lzw"}
    if fmt.pil == "ICO":
        return {"sizes": [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]}
    if fmt.pil == "PDF":
        return {"resolution": 150.0}
    if fmt.pil == "JPEG2000":
        return {"quality_mode": "dB", "quality_layers": [30 + quality * 0.2]}
    return {}


def save_image(img: Image.Image, path: Path, fmt: ImageFormat, quality: int = 92) -> Path:
    _prepare(img, fmt).save(path, fmt.pil, **_save_kwargs(fmt, quality))
    return path


def save_frames(frames: Frames, path: Path, fmt: ImageFormat, quality: int = 92) -> Path:
    if not frames.animated or not fmt.animated:
        return save_image(frames.images[0], path, fmt, quality)
    imgs = [_prepare(im, fmt) for im in frames.images]
    kw = _save_kwargs(fmt, quality)
    if fmt.pil == "PNG":
        kw.pop("optimize", None)
    if fmt.pil in ("GIF", "WEBP", "PNG", "AVIF"):
        kw.update(duration=frames.durations, loop=frames.loop)
    if fmt.pil == "GIF":
        kw.update(disposal=2, optimize=False)
    imgs[0].save(path, fmt.pil, save_all=True, append_images=imgs[1:], **kw)
    return path


def process_file(
    src: str | Path,
    out_dir: str | Path,
    fmt: Optional[ImageFormat],
    transform: Callable[[Image.Image], Image.Image],
    ctx: Optional[TaskContext] = None,
    quality: int = 92,
    suffix: str = "",
    animation: str = "keep",
    video_kw: Optional[dict] = None,
) -> list[Path]:
    src = Path(src)
    if fmt is None:
        fmt = format_for_ext(src.suffix) or format_by_label("PNG")
    stem = src.stem + suffix
    is_video = kind_of(src) == "video"

    if animation == "first" or (animation == "keep" and not fmt.animated):
        if is_video:
            frames = video_frames(src, ctx, first_only=True)
        else:
            frames = Frames([open_image(src)], [100])
    else:
        frames = load_frames(src, ctx.sub(0, 0.5) if ctx else None, **(video_kw or {}))

    total = len(frames.images)
    out: list[Image.Image] = []
    for i, im in enumerate(frames.images):
        if ctx:
            ctx.check()
            ctx.progress(0.5 + 0.45 * i / total if total > 1 else 0.5)
        out.append(transform(im))
    frames.images = out

    if animation == "all" and frames.animated:
        folder = unique_path(out_dir, stem, "frames").with_suffix("")
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, im in enumerate(frames.images, 1):
            if ctx:
                ctx.check()
            paths.append(save_image(im, folder / f"{stem}_{i:05d}.{fmt.ext}", fmt, quality))
        return paths

    dest = unique_path(out_dir, stem, fmt.ext)
    save_frames(frames, dest, fmt, quality)
    if ctx:
        ctx.progress(1.0)
    return [dest]
