from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from lsync.core import ffmpeg
from lsync.core.utils import Cancelled, TaskContext
from lsync.i18n import _

MODES = {"video": "Vídeo (MP4)", "mp3": "Só áudio (MP3)", "m4a": "Só áudio (M4A, original)"}
QUALITIES = {0: "Melhor disponível", 1080: "1080p", 720: "720p", 480: "480p", 360: "360p"}


def _deno_path() -> Optional[str]:
    try:
        import deno

        path = deno.find_deno_bin()
        if path and Path(path).is_file():
            return str(path)
    except Exception:
        pass
    return shutil.which("deno")


def _format_selector(mode: str, height: int) -> str:
    if mode != "video":
        return "bestaudio[ext=m4a]/bestaudio/best"
    h = f"[height<={height}]" if height else ""
    return f"bv*{h}[vcodec^=avc1]+ba[ext=m4a]/bv*{h}[ext=mp4]+ba[ext=m4a]/bv*{h}+ba/b{h}/bv*+ba/b"


def download(
    url: str,
    out_dir: str | Path,
    mode: str = "video",
    height: int = 0,
    ctx: Optional[TaskContext] = None,
    playlist: bool = False,
) -> list[Path]:
    import yt_dlp

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    finished: list[Path] = []

    def hook(d: dict) -> None:
        if ctx is not None and ctx.cancelled:
            raise Cancelled()
        if d.get("status") == "downloading" and ctx is not None:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = (d.get("downloaded_bytes") or 0) / 1_048_576
            speed = d.get("speed")
            speed_txt = f" — {speed / 1_048_576:.1f} MB/s" if speed else ""
            if total:
                mb = total / 1_048_576
                ctx.progress(min(done / mb, 1.0) * 0.95, _("Baixando… {done} de {total} MB").format(done=f"{done:.1f}", total=f"{mb:.1f}") + speed_txt)
            else:
                ctx.status(_("Baixando… {done} MB").format(done=f"{done:.1f}") + speed_txt)
        elif d.get("status") == "finished" and ctx is not None:
            ctx.status(_("Finalizando (juntando áudio e vídeo)…"))

    def post_hook(d: dict) -> None:
        if d.get("status") == "finished":
            info = d.get("info_dict") or {}
            fp = info.get("filepath") or info.get("_filename")
            if fp:
                finished.append(Path(fp))

    opts: dict = {
        "outtmpl": str(out_dir / "%(title).150B [%(id)s].%(ext)s"),
        "format": _format_selector(mode, height),
        "ffmpeg_location": ffmpeg.ffmpeg_path(),
        "noplaylist": not playlist,
        "progress_hooks": [hook],
        "postprocessor_hooks": [post_hook],
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "overwrites": False,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
    }
    deno = _deno_path()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    if mode == "video":
        opts["merge_output_format"] = "mp4"
    elif mode == "mp3":
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata"},
        ]
    else:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]

    if ctx is not None:
        ctx.status(_("Buscando informações do link…"))
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc).replace("ERROR: ", "")
        if (ctx is not None and ctx.cancelled) or "Cancelled" in msg:
            raise Cancelled() from exc
        raise RuntimeError(_friendly_error(msg)) from exc

    unique = list(dict.fromkeys(p for p in finished if p.exists()))
    if ctx is not None:
        ctx.progress(1.0)
    return unique


def _friendly_error(msg: str) -> str:
    low = msg.lower()
    if any(w in low for w in ("private", "login", "sign in", "cookies")):
        return _("Esse conteúdo é privado ou exige login, então não dá para baixar.") + "\n\n" + msg
    if "unsupported url" in low:
        return _("Esse link não é suportado. Confira se copiou o endereço certo.") + "\n\n" + msg
    if any(w in low for w in ("unable to download", "network", "timed out")):
        return _("Problema de conexão. Verifique sua internet e tente de novo.") + "\n\n" + msg
    return msg


def fetch_info(url: str) -> dict:
    import urllib.request

    import yt_dlp

    opts: dict = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
                  "extract_flat": "in_playlist", "socket_timeout": 15}
    deno = _deno_path()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(_friendly_error(str(exc).replace("ERROR: ", ""))) from exc
    info = info or {}
    thumb_url = info.get("thumbnail")
    if not thumb_url and info.get("thumbnails"):
        thumb_url = info["thumbnails"][-1].get("url")
    thumb = None
    if thumb_url:
        try:
            req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                thumb = resp.read()
        except Exception:
            thumb = None
    return {
        "title": info.get("title") or url,
        "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key") or "",
        "duration": info.get("duration"),
        "thumbnail": thumb,
        "is_playlist": info.get("_type") == "playlist",
    }
