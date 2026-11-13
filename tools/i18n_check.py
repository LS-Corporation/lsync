from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def literal_calls() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "lsync").rglob("*.py"):
        if path.name == "locales.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
    return found


def data_labels() -> set[str]:
    from lsync.core import ai, downloader, effects, images, media
    from lsync.ui import pages

    out: set[str] = set()
    for d in (effects.RESIZE_MODES, effects.FIT_MODES, effects.COLOR_EFFECTS, effects.EFFECT_SUFFIX,
              media.QUALITY_LABELS, media.RESOLUTION_LABELS, downloader.MODES, downloader.QUALITIES, ai.BG_MODELS,
              pages.ANIMATION_MODES, pages.OUTPUT_KINDS, pages.PREVIEW_VIEWS, pages.DL_MODES, pages.THEMES, effects.CROP_MODES, effects.CROP_RATIOS, pages.PDF_TARGETS, pages.IMAGE_EXTRA, pages.SHEET_TARGETS, pages.DOC_TARGETS, pages.CSV_SEPARATORS, pages.PDF_DPI):
        out |= set(d.values())
    out |= {label for _k, label, *_r in effects.ADJUSTMENTS}
    out |= {label for _k, label in pages.SAME_FORMAT}
    out |= {f.label for f in images._ALL_FORMATS} | {f.label for f in media.FORMATS}
    for cls in pages.PAGES + [pages.SettingsPage]:
        out |= {cls.title, cls.subtitle, getattr(cls, 'nav', ''), getattr(cls, 'run_text', '')}
    return {s for s in out if s}


def main() -> int:
    from lsync.i18n import LANGUAGES
    from lsync.locales import TRANSLATIONS

    texts = literal_calls() | data_labels()
    if "--list" in sys.argv:
        for t in sorted(texts):
            print(repr(t))
    same_everywhere = {t for t in texts if t.isascii() and (t.isupper() or t[:1].isdigit() or t in ("Full HD",))}
    missing_total = 0
    for code in LANGUAGES:
        if code == "pt":
            continue
        table = TRANSLATIONS.get(code, {})
        missing = sorted(t for t in texts - same_everywhere if t not in table)
        unused = sorted(k for k in table if k not in texts)
        bad_fmt = sorted(k for k, v in table.items() if k in texts and _fields(k) != _fields(v))
        print(f"[{code}] {len(texts)} textos, faltando {len(missing)}, sobrando {len(unused)}, placeholders errados {len(bad_fmt)}")
        for t in missing:
            print("   falta:", repr(t))
        for t in bad_fmt:
            print("   {campos} diferentes:", repr(t))
        for t in unused:
            print("   não usado:", repr(t))
        missing_total += len(missing) + len(bad_fmt)
    return 1 if missing_total else 0


def _fields(s: str) -> set[str]:
    import string

    return {f for _lit, f, _spec, _conv in string.Formatter().parse(s) if f is not None}


if __name__ == "__main__":
    raise SystemExit(main())
