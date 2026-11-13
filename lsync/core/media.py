from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lsync.core import ffmpeg
from lsync.core.utils import TaskContext, unique_path
from lsync.i18n import _


@dataclass(frozen=True)
class MediaFormat:
    label: str
    ext: str
    kind: str
    video: tuple = ()
    audio: tuple = ()
    audio_bitrate: bool = True
    extra: tuple = ()
    needs: tuple = ()


H264 = ("-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p")
AAC = ("-c:a", "aac")

FORMATS = [
    MediaFormat("MP4 (H.264)", "mp4", "video", H264, AAC, extra=("-movflags", "+faststart"), needs=("libx264",)),
    MediaFormat("MP4 (H.265/HEVC)", "mp4", "video", ("-c:v", "libx265", "-preset", "medium", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"), AAC, extra=("-movflags", "+faststart"), needs=("libx265",)),
    MediaFormat("MKV", "mkv", "video", H264, AAC, needs=("libx264",)),
    MediaFormat("WEBM (VP9)", "webm", "video", ("-c:v", "libvpx-vp9", "-b:v", "0", "-deadline", "good", "-cpu-used", "4", "-row-mt", "1"), ("-c:a", "libopus"), needs=("libvpx-vp9", "libopus")),
    MediaFormat("AVI", "avi", "video", ("-c:v", "mpeg4", "-vtag", "xvid"), ("-c:a", "libmp3lame"), needs=("libmp3lame",)),
    MediaFormat("MOV", "mov", "video", H264, AAC, needs=("libx264",)),
    MediaFormat("FLV", "flv", "video", H264, AAC, needs=("libx264",)),
    MediaFormat("WMV", "wmv", "video", ("-c:v", "wmv2"), ("-c:a", "wmav2")),
    MediaFormat("MPEG", "mpg", "video", ("-c:v", "mpeg2video"), ("-c:a", "mp2")),
    MediaFormat("M4V", "m4v", "video", H264, AAC, needs=("libx264",)),
    MediaFormat("3GP (celular antigo)", "3gp", "video", ("-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-profile:v", "baseline"), ("-c:a", "aac", "-ac", "1", "-ar", "22050"), needs=("libx264",)),
    MediaFormat("TS", "ts", "video", H264, AAC, needs=("libx264",)),
    MediaFormat("OGV", "ogv", "video", ("-c:v", "libtheora"), ("-c:a", "libvorbis"), needs=("libtheora", "libvorbis")),
    MediaFormat("GIF animado", "gif", "video"),
    MediaFormat("MP3", "mp3", "audio", (), ("-c:a", "libmp3lame"), needs=("libmp3lame",)),
    MediaFormat("WAV", "wav", "audio", (), ("-c:a", "pcm_s16le"), audio_bitrate=False),
    MediaFormat("M4A (AAC)", "m4a", "audio", (), AAC),
    MediaFormat("AAC", "aac", "audio", (), AAC),
    MediaFormat("FLAC (sem perdas)", "flac", "audio", (), ("-c:a", "flac"), audio_bitrate=False),
    MediaFormat("OGG (Vorbis)", "ogg", "audio", (), ("-c:a", "libvorbis"), needs=("libvorbis",)),
    MediaFormat("OPUS", "opus", "audio", (), ("-c:a", "libopus"), needs=("libopus",)),
    MediaFormat("WMA", "wma", "audio", (), ("-c:a", "wmav2")),
    MediaFormat("AIFF", "aiff", "audio", (), ("-c:a", "pcm_s16be"), audio_bitrate=False),
    MediaFormat("AC3 (Dolby)", "ac3", "audio", (), ("-c:a", "ac3")),
    MediaFormat("ALAC (Apple sem perdas)", "m4a", "audio", (), ("-c:a", "alac"), audio_bitrate=False),
    MediaFormat("MKA", "mka", "audio", (), ("-c:a", "libopus"), needs=("libopus",)),
]

QUALITY_LABELS = {"high": "Alta", "medium": "Média", "low": "Baixa (arquivo menor)"}
QUALITIES = {
    "high": {"crf264": 18, "crf265": 22, "crfvp9": 28, "q": 2},
    "medium": {"crf264": 23, "crf265": 28, "crfvp9": 33, "q": 4},
    "low": {"crf264": 28, "crf265": 32, "crfvp9": 40, "q": 8},
}
RESOLUTION_LABELS = {
    0: "Original",
    2160: "2160p (4K)",
    1440: "1440p",
    1080: "1080p (Full HD)",
    720: "720p (HD)",
    480: "480p",
    360: "360p",
}
AUDIO_BITRATES = ["320k", "256k", "192k", "160k", "128k", "96k", "64k"]


def available_formats() -> list[MediaFormat]:
    enc = ffmpeg.available_encoders()
    return [f for f in FORMATS if all(n in enc for n in f.needs)]


def format_by_label(label: str) -> MediaFormat:
    for f in FORMATS:
        if f.label == label:
            return f
    raise ValueError(label)


def _quality_args(fmt: MediaFormat, quality: str) -> list[str]:
    q = QUALITIES.get(quality, QUALITIES["medium"])
    codec = fmt.video[1] if len(fmt.video) > 1 else ""
    if codec == "libx264":
        return ["-crf", str(q["crf264"])]
    if codec == "libx265":
        return ["-crf", str(q["crf265"])]
    if codec == "libvpx-vp9":
        return ["-crf", str(q["crfvp9"])]
    if codec in ("mpeg4", "mpeg2video"):
        return ["-q:v", str(q["q"])]
    if codec == "libtheora":
        return ["-q:v", str(10 - q["q"])]
    if codec == "wmv2":
        return ["-b:v", {2: "6M", 4: "3M", 8: "1M"}[q["q"]]]
    return []


def convert(
    src: str | Path,
    out_dir: str | Path,
    fmt: MediaFormat,
    ctx: Optional[TaskContext] = None,
    quality: str = "medium",
    height: int = 0,
    audio_bitrate: str = "192k",
    gif_fps: int = 12,
    gif_width: int = 480,
) -> Path:
    src = Path(src)
    info = ffmpeg.probe(src)
    dest = unique_path(out_dir, src.stem, fmt.ext)
    args: list[str] = ["-i", str(src)]

    if fmt.kind == "audio":
        if not info["has_audio"]:
            raise RuntimeError(_("Esse arquivo não tem áudio."))
        args += ["-vn", "-map", "0:a:0", *fmt.audio]
        if fmt.audio_bitrate:
            args += ["-b:a", audio_bitrate]
        if fmt.ext == "mp3":
            args += ["-id3v2_version", "3"]
    elif fmt.ext == "gif":
        if not info["has_video"]:
            raise RuntimeError(_("Para gerar GIF o arquivo precisa ter vídeo."))
        scale = f"scale=-2:'min({height},ih)':flags=lanczos" if height else f"scale='min({gif_width},iw)':-1:flags=lanczos"
        args += [
            "-vf", f"fps={gif_fps},{scale},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5",
            "-loop", "0", "-an",
        ]
    else:
        if not info["has_video"] and not info["has_audio"]:
            raise RuntimeError(_("Não encontrei áudio nem vídeo nesse arquivo."))
        if info["has_video"]:
            args += ["-map", "0:v:0", *fmt.video, *_quality_args(fmt, quality)]
            if height:
                args += ["-vf", f"scale=-2:'min({height},ih)'"]
        if info["has_audio"]:
            args += ["-map", "0:a:0?", *fmt.audio]
            if fmt.audio_bitrate:
                args += ["-b:a", audio_bitrate]
        args += list(fmt.extra)

    args.append(str(dest))
    try:
        ffmpeg.run(args, ctx, info["duration"])
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return dest


def compress_video(src: str | Path, ctx: Optional[TaskContext] = None, crf: int = 26) -> tuple[Path, int, int]:
    src = Path(src)
    info = ffmpeg.probe(src)
    before = src.stat().st_size
    if not info["has_video"]:
        return src, before, before
    tmp = src.with_name(src.stem + ".lsync-tmp.mp4")
    base = ["-i", str(src), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium",
            "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    try:
        try:
            ffmpeg.run(base + ["-c:a", "copy", str(tmp)], ctx, info["duration"])
        except RuntimeError:
            ffmpeg.run(base + ["-c:a", "aac", "-b:a", "192k", str(tmp)], ctx, info["duration"])
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    after = tmp.stat().st_size
    if after >= before * 0.95:
        tmp.unlink(missing_ok=True)
        return src, before, before
    dest = src.with_suffix(".mp4")
    src.unlink()
    tmp.replace(dest)
    return dest, before, after


def video_thumbnail(src: str | Path, width: int = 320) -> Optional[bytes]:
    import subprocess

    from lsync.core.utils import hidden_window_kwargs

    for seek in ("1", "0"):
        try:
            r = subprocess.run(
                [ffmpeg.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-ss", seek, "-i", str(src),
                 "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                capture_output=True, timeout=20, **hidden_window_kwargs(),
            )
        except Exception:
            return None
        if r.returncode == 0 and r.stdout:
            return r.stdout
    return None
