from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

from lsync.core.utils import Cancelled, TaskContext, hidden_window_kwargs
from lsync.i18n import _

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_PROGRESS_RE = re.compile(r"^[a-z_0-9]+=\S*$")


@lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    env = os.environ.get("LSYNC_FFMPEG")
    if env and Path(env).is_file():
        return env
    try:
        import imageio_ffmpeg

        bundled = sorted((Path(imageio_ffmpeg.__file__).parent / "binaries").glob("ffmpeg*"))
        if bundled:
            return str(bundled[0])
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError(_("FFmpeg não encontrado. Reinstale o Lsync ou instale o FFmpeg e coloque no PATH."))


def _run_quiet(args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ffmpeg_path(), "-hide_banner", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_window_kwargs(),
    )


@lru_cache(maxsize=1)
def available_encoders() -> frozenset[str]:
    out = _run_quiet(["-encoders"]).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return frozenset(names)


def probe(path: str | Path) -> dict:
    err = _run_quiet(["-i", str(path)]).stderr
    duration = None
    m = _DURATION_RE.search(err)
    if m:
        h, mnt, s = m.groups()
        duration = int(h) * 3600 + int(mnt) * 60 + float(s)
    video_lines = [ln for ln in err.splitlines() if "Stream #" in ln and "Video:" in ln]
    has_video = any("attached pic" not in ln for ln in video_lines)
    has_audio = any("Stream #" in ln and "Audio:" in ln for ln in err.splitlines())
    return {"duration": duration, "has_video": has_video, "has_audio": has_audio}


def run(
    args: Sequence[str],
    ctx: Optional[TaskContext] = None,
    duration: Optional[float] = None,
) -> None:
    cmd = [
        ffmpeg_path(), "-hide_banner", "-y", "-nostdin",
        "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        *args,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **hidden_window_kwargs(),
    )
    errors: list[str] = []
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if ctx is not None and ctx.cancelled:
                proc.kill()
                proc.wait()
                raise Cancelled()
            line = raw.strip()
            if not line:
                continue
            if _PROGRESS_RE.match(line):
                key, _sep, val = line.partition("=")
                if key == "out_time_us" and duration and ctx and val.isdigit():
                    ctx.progress(int(val) / 1e6 / duration)
                continue
            errors.append(line)
    finally:
        if proc.poll() is None:
            proc.wait()
    if proc.returncode != 0:
        detail = "\n".join(errors[-12:]) or f"exit {proc.returncode}"
        raise RuntimeError(_("O FFmpeg não conseguiu processar o arquivo:") + "\n" + detail)
    if ctx is not None:
        ctx.progress(1.0)
