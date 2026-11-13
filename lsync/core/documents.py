from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from typing import Optional

from PIL import Image

from lsync.core import images
from lsync.core.utils import TaskContext, unique_path
from lsync.i18n import _


def _folder(out_dir: str | Path, stem: str) -> Path:
    base = Path(out_dir)
    folder = base / stem
    i = 1
    while folder.exists():
        folder = base / f"{stem} ({i})"
        i += 1
    folder.mkdir(parents=True)
    return folder


def pdf_page_count(path: str | Path) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def pdf_thumbnail(path: str | Path, width: int = 320) -> Optional[Image.Image]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[0]
        scale = width / max(1.0, page.get_width())
        return page.render(scale=scale).to_pil()
    finally:
        pdf.close()


def pdf_to_images(src: str | Path, out_dir: str | Path, ext: str = "png", dpi: int = 150,
                  ctx: Optional[TaskContext] = None) -> list[Path]:
    import pypdfium2 as pdfium

    src = Path(src)
    pdf = pdfium.PdfDocument(str(src))
    try:
        n = len(pdf)
        target = _folder(out_dir, src.stem) if n > 1 else Path(out_dir)
        fmt = images.format_by_label("JPG" if ext == "jpg" else "PNG")
        out = []
        for i in range(n):
            if ctx:
                ctx.check()
                ctx.progress(i / n, _("Página {i} de {n}…").format(i=i + 1, n=n))
            pil = pdf[i].render(scale=dpi / 72).to_pil()
            name = f"{src.stem} - {i + 1:03d}" if n > 1 else src.stem
            dest = unique_path(target, name, fmt.ext)
            images.save_image(pil, dest, fmt, 92)
            out.append(dest)
        return out
    finally:
        pdf.close()


def images_to_pdf(paths: list[Path], out_dir: str | Path, ctx: Optional[TaskContext] = None) -> Path:
    pages = []
    for i, p in enumerate(paths):
        if ctx:
            ctx.check()
            ctx.progress(i / len(paths) * 0.8, _("Adicionando {name}…").format(name=Path(p).name))
        pages.append(images.flatten(images.open_image(p)))
    if not pages:
        raise RuntimeError(_("Nenhuma imagem para juntar."))
    dest = unique_path(out_dir, _merged_name(paths), "pdf")
    pages[0].save(dest, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    return dest


def merge_pdfs(paths: list[Path], out_dir: str | Path, ctx: Optional[TaskContext] = None) -> Path:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for i, p in enumerate(paths):
        if ctx:
            ctx.check()
            ctx.progress(i / len(paths) * 0.9, _("Adicionando {name}…").format(name=Path(p).name))
        writer.append(str(p))
    dest = unique_path(out_dir, _merged_name(paths), "pdf")
    with open(dest, "wb") as fh:
        writer.write(fh)
    writer.close()
    return dest


def split_pdf(src: str | Path, out_dir: str | Path, ctx: Optional[TaskContext] = None) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    src = Path(src)
    reader = PdfReader(str(src))
    n = len(reader.pages)
    folder = _folder(out_dir, src.stem)
    out = []
    for i, page in enumerate(reader.pages):
        if ctx:
            ctx.check()
            ctx.progress(i / n, _("Página {i} de {n}…").format(i=i + 1, n=n))
        writer = PdfWriter()
        writer.add_page(page)
        dest = unique_path(folder, f"{src.stem} - {i + 1:03d}", "pdf")
        with open(dest, "wb") as fh:
            writer.write(fh)
        out.append(dest)
    return out


def _merged_name(paths: list[Path]) -> str:
    first = Path(paths[0]).stem
    return first if len(paths) == 1 else _("{name} e mais {n}").format(name=first, n=len(paths) - 1)


def sheet_to_csv(src: str | Path, out_dir: str | Path, sep: str = ";", ctx: Optional[TaskContext] = None) -> list[Path]:
    from openpyxl import load_workbook

    src = Path(src)
    wb = load_workbook(str(src), read_only=True, data_only=True)
    try:
        sheets = wb.worksheets
        out = []
        for i, ws in enumerate(sheets):
            if ctx:
                ctx.check()
                ctx.progress(i / len(sheets))
            name = src.stem if len(sheets) == 1 else f"{src.stem} - {ws.title}"
            dest = unique_path(out_dir, name, "csv")
            with open(dest, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh, delimiter=sep)
                for row in ws.iter_rows(values_only=True):
                    writer.writerow(["" if v is None else _cell_text(v, sep) for v in row])
            out.append(dest)
        return out
    finally:
        wb.close()


def _cell_text(value, sep: str) -> str:
    if isinstance(value, float):
        text = repr(value) if value != int(value) else str(int(value))
        return text.replace(".", ",") if sep == ";" else text
    return str(value)


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _number(text: str, decimal_comma: bool):
    t = text.strip()
    if not t:
        return t
    candidate = t.replace(".", "").replace(",", ".") if decimal_comma and "," in t else t
    try:
        if candidate.lstrip("-").isdigit() and not (len(candidate.lstrip("-")) > 1 and candidate.lstrip("-").startswith("0")):
            return int(candidate)
        if any(c.isdigit() for c in candidate):
            return float(candidate)
    except ValueError:
        pass
    return text


def csv_to_xlsx(src: str | Path, out_dir: str | Path, ctx: Optional[TaskContext] = None) -> Path:
    from openpyxl import Workbook

    src = Path(src)
    text = _read_text(src)
    try:
        dialect = csv.Sniffer().sniff(text[:20000], delimiters=";,\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ";" if text.count(";") > text.count(",") else ","
    wb = Workbook()
    ws = wb.active
    ws.title = src.stem[:31] or "Planilha"
    for row in csv.reader(io.StringIO(text), delimiter=sep):
        ws.append([_number(v, sep == ";") for v in row])
    dest = unique_path(out_dir, src.stem, "xlsx")
    wb.save(dest)
    return dest


def word_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"))
        return True
    except OSError:
        return False


def word_to_pdf(paths: list[Path], out_dir: str | Path, ctx: Optional[TaskContext] = None) -> list[Path]:
    if not word_available():
        raise RuntimeError(_("Para converter documentos do Word é preciso ter o Microsoft Word instalado neste computador."))
    import comtypes
    import comtypes.client

    comtypes.CoInitialize()
    word = None
    out = []
    try:
        word = comtypes.client.CreateObject("Word.Application", dynamic=True)
        word.Visible = False
        word.DisplayAlerts = 0
        for i, p in enumerate(paths):
            if ctx:
                ctx.check()
                ctx.progress(i / len(paths), _("Abrindo {name} no Word…").format(name=Path(p).name))
            dest = unique_path(out_dir, Path(p).stem, "pdf")
            doc = word.Documents.Open(str(Path(p).resolve()), False, True)
            try:
                doc.SaveAs2(str(dest.resolve()), 17)
            finally:
                doc.Close(False)
            out.append(dest)
        return out
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        comtypes.CoUninitialize()
