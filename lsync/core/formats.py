from __future__ import annotations

from pathlib import Path

from lsync.i18n import _

VIDEO_EXTS = {
    "mp4", "mkv", "webm", "avi", "mov", "flv", "wmv", "mpeg", "mpg", "m4v",
    "3gp", "3g2", "ts", "mts", "m2ts", "ogv", "vob", "f4v", "asf", "divx", "rm", "rmvb",
}
AUDIO_EXTS = {
    "mp3", "wav", "aac", "m4a", "flac", "ogg", "oga", "opus", "wma", "aiff", "aif",
    "ac3", "amr", "mka", "alac", "ape", "wv", "mp2", "caf", "au", "m4b", "dts",
}
IMAGE_EXTS = {
    "png", "jpg", "jpeg", "jfif", "jpe", "webp", "bmp", "dib", "gif", "tif", "tiff",
    "ico", "icns", "tga", "ppm", "pgm", "pbm", "pnm", "pcx", "dds", "psd", "heic",
    "heif", "avif", "jp2", "j2k", "jpx", "xbm", "sgi", "rgb", "eps", "im", "msp", "qoi",
}
PDF_EXTS = {"pdf"}
SHEET_EXTS = {"xlsx", "xlsm", "csv"}
DOC_EXTS = {"docx", "doc", "docm", "rtf", "odt", "dotx"}
EXTS_BY_KIND = {
    "image": IMAGE_EXTS, "video": VIDEO_EXTS, "audio": AUDIO_EXTS,
    "pdf": PDF_EXTS, "sheet": SHEET_EXTS, "doc": DOC_EXTS,
}


def kind_of(path: str | Path) -> str:
    ext = Path(path).suffix.lower().lstrip(".")
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in SHEET_EXTS:
        return "sheet"
    if ext in DOC_EXTS:
        return "doc"
    return "unknown"


def dialog_patterns(*kinds: str) -> list[tuple[str, str]]:
    groups = {
        "image": (_("Imagens"), IMAGE_EXTS),
        "video": (_("Vídeos"), VIDEO_EXTS),
        "audio": (_("Áudios"), AUDIO_EXTS),
        "pdf": (_("Documentos PDF"), PDF_EXTS),
        "sheet": (_("Planilhas"), SHEET_EXTS),
        "doc": (_("Documentos do Word"), DOC_EXTS),
    }
    result = []
    all_exts: set[str] = set()
    for k in kinds:
        label, exts = groups[k]
        all_exts |= exts
        result.append((label, " ".join(f"*.{e}" for e in sorted(exts))))
    if len(kinds) > 1:
        result.insert(0, (_("Todos suportados"), " ".join(f"*.{e}" for e in sorted(all_exts))))
    result.append((_("Todos os arquivos"), "*.*"))
    return result
