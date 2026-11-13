from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from lsync import APP_NAME


class Cancelled(Exception):
    pass


class TaskContext:
    def __init__(
        self,
        on_progress: Optional[Callable[[float, Optional[str]], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ):
        self._on_progress = on_progress
        self.cancel_event = cancel_event or threading.Event()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled()

    def progress(self, fraction: float, text: Optional[str] = None) -> None:
        if self._on_progress:
            self._on_progress(max(0.0, min(1.0, fraction)), text)

    def status(self, text: str) -> None:
        if self._on_progress:
            self._on_progress(-1.0, text)

    def sub(self, base: float, span: float) -> "TaskContext":
        parent = self

        def forward(frac: float, text: Optional[str]) -> None:
            if frac < 0:
                parent.status(text or "")
            else:
                parent.progress(base + span * frac, text)

        return TaskContext(forward, self.cancel_event)


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    path = app_data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_dir() -> Path:
    downloads = Path.home() / "Downloads"
    base = downloads if downloads.is_dir() else Path.home()
    return base / APP_NAME


def unique_path(directory: str | Path, stem: str, ext: str) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ext = ext.lstrip(".")
    candidate = directory / f"{stem}.{ext}"
    i = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({i}).{ext}"
        i += 1
    return candidate


def open_in_explorer(path: str | Path) -> None:
    path = str(path)
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def hidden_window_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


_SETTINGS_FILE = "settings.json"


def load_settings() -> dict:
    try:
        with open(app_data_dir() / _SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        with open(app_data_dir() / _SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass
