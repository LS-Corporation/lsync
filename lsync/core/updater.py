from __future__ import annotations

import hashlib
import io
import importlib
import importlib.machinery
import json
import re
import shutil
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from lsync.core.utils import app_data_dir
from lsync.i18n import _

MODULES = ("yt_dlp", "yt_dlp_ejs")
CHECK_INTERVAL = 24 * 3600
_lock = threading.Lock()


def _root() -> Path:
    path = app_data_dir() / "downloader"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state() -> dict:
    try:
        return json.loads((_root() / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    (_root() / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def _active_dir() -> Optional[Path]:
    name = _state().get("folder")
    if not name:
        return None
    folder = _root() / name
    return folder if (folder / "yt_dlp" / "__init__.py").exists() else None


class _Finder:
    def __init__(self, folder: Path):
        self.folder = str(folder)

    def find_spec(self, name, path=None, target=None):
        top = name.split(".")[0]
        if top not in MODULES:
            return None
        search = path if "." in name else [self.folder]
        return importlib.machinery.PathFinder.find_spec(name, search)


def activate() -> None:
    sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, _Finder)]
    folder = _active_dir()
    if folder is not None:
        sys.meta_path.insert(0, _Finder(folder))


def _unpatch_urllib3() -> None:
    try:
        import urllib3.util.url as url_mod
    except Exception:
        return
    pattern = getattr(url_mod, "_PERCENT_RE", None)
    while pattern is not None and type(pattern).__name__ == "Urllib3PercentREOverride":
        pattern = pattern.re
    if pattern is not None:
        url_mod._PERCENT_RE = pattern


def reload() -> None:
    _unpatch_urllib3()
    activate()
    for key in [k for k in sys.modules if k.split(".")[0] in MODULES]:
        del sys.modules[key]
    importlib.invalidate_caches()


def _key(version: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", version))


def current_version() -> str:
    try:
        from yt_dlp.version import __version__

        return __version__
    except Exception:
        return "?"


def _pypi(package: str, version: str = "") -> dict:
    url = f"https://pypi.org/pypi/{package}/{version + '/' if version else ''}json"
    req = urllib.request.Request(url, headers={"User-Agent": "Lsync"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def _wheel(meta: dict) -> dict:
    for item in meta["urls"]:
        if item["packagetype"] == "bdist_wheel" and item["filename"].endswith("py3-none-any.whl"):
            return item
    raise RuntimeError(_("Não encontrei o pacote do baixador para baixar."))


def _download_wheel(item: dict, dest: Path) -> None:
    req = urllib.request.Request(item["url"], headers={"User-Agent": "Lsync"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if hashlib.sha256(data).hexdigest() != item["digests"]["sha256"]:
        raise RuntimeError(_("O arquivo baixado veio corrompido. Tente de novo mais tarde."))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.namelist():
            top = member.split("/")[0]
            if top in MODULES:
                zf.extract(member, dest)


def latest_version() -> str:
    return _pypi("yt-dlp")["info"]["version"]


def update(force: bool = False) -> tuple[str, str, bool]:
    with _lock:
        old = current_version()
        meta = _pypi("yt-dlp")
        new = meta["info"]["version"]
        state = _state()
        state["checked"] = time.time()
        if not force and old != "?" and _key(new) <= _key(old):
            _save_state(state)
            return old, old, False
        ejs = None
        for req in meta["info"].get("requires_dist") or []:
            m = re.match(r"yt-dlp-ejs\s*==\s*([\w.]+)", req)
            if m:
                ejs = m.group(1)
        folder_name = f"yt-dlp-{new}"
        tmp = _root() / (folder_name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        try:
            _download_wheel(_wheel(meta), tmp)
            if ejs:
                _download_wheel(_wheel(_pypi("yt-dlp-ejs", ejs)), tmp)
            final = _root() / folder_name
            shutil.rmtree(final, ignore_errors=True)
            tmp.rename(final)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        previous = state.get("folder")
        state.update({"folder": folder_name, "version": new})
        _save_state(state)
        reload()
        try:
            import yt_dlp

            yt_dlp.YoutubeDL({"quiet": True}).close()
        except Exception as exc:
            state["folder"] = previous if previous != folder_name else None
            _save_state(state)
            shutil.rmtree(_root() / folder_name, ignore_errors=True)
            reload()
            raise RuntimeError(_("A versão nova do baixador não funcionou, então mantive a anterior.")) from exc
        if previous and previous != folder_name:
            shutil.rmtree(_root() / previous, ignore_errors=True)
        return old, new, True


def auto_enabled(settings: dict) -> bool:
    return bool(settings.get("auto_update_downloader", True))


def due() -> bool:
    return time.time() - float(_state().get("checked", 0)) > CHECK_INTERVAL


def looks_outdated(message: str) -> bool:
    low = message.lower()
    hints = ("please report this issue", "unable to extract", "unexpected response", "update to the latest",
             "yt-dlp -u", "nsig extraction failed", "signature extraction failed", "unable to download api page")
    return any(h in low for h in hints)


DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
_deno_lock = threading.Lock()


def deno_exe() -> Path:
    return _root() / "deno" / "deno.exe"


def ensure_deno(ctx=None) -> Optional[str]:
    exe = deno_exe()
    if exe.exists():
        return str(exe)
    if sys.platform != "win32":
        return None
    with _deno_lock:
        if exe.exists():
            return str(exe)
        req = urllib.request.Request(DENO_URL + ".sha256sum", headers={"User-Agent": "Lsync"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
        text = raw.decode("utf-16") if raw[:2] in (bytes([255, 254]), bytes([254, 255])) else raw.decode("utf-8", "replace")
        match = re.search("[0-9a-fA-F]{64}", text)
        if not match:
            raise RuntimeError(_("Não consegui conferir o arquivo do suporte ao YouTube."))
        expected = match.group(0).lower()
        req = urllib.request.Request(DENO_URL, headers={"User-Agent": "Lsync"})
        digest = hashlib.sha256()
        buf = io.BytesIO()
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                buf.write(chunk)
                digest.update(chunk)
                if ctx is not None and total:
                    ctx.status(_("Preparando o suporte ao YouTube (só na 1ª vez): {done} de {total} MB").format(done=buf.tell() >> 20, total=total >> 20))
        if digest.hexdigest() != expected:
            raise RuntimeError(_("O arquivo baixado veio corrompido. Tente de novo mais tarde."))
        exe.parent.mkdir(parents=True, exist_ok=True)
        tmp = exe.with_suffix(".part")
        with zipfile.ZipFile(buf) as zf, open(tmp, "wb") as fh:
            fh.write(zf.read("deno.exe"))
        tmp.replace(exe)
        return str(exe)
