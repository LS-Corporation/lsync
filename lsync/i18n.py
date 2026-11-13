from __future__ import annotations

import locale
import os

LANGUAGES = {"pt": "Português", "en": "English", "es": "Español"}
_current = "pt"


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGES else "en"


def get_language() -> str:
    return _current


def _(text: str) -> str:
    if _current == "pt":
        return text
    from lsync.locales import TRANSLATIONS

    return TRANSLATIONS.get(_current, {}).get(text, text)


def system_language() -> str:
    name = ""
    try:
        if os.name == "nt":
            import ctypes

            name = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        if not name:
            name = locale.getlocale()[0] or os.environ.get("LANG", "")
    except Exception:
        pass
    name = name.lower()
    for code in ("pt", "es", "en"):
        if name.startswith(code):
            return code
    return "en"
