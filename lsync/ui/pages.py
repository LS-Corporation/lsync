from __future__ import annotations

import io
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QScrollArea,
    QVBoxLayout, QWidget,
)

from lsync import APP_NAME, REPO_URL, __version__
from lsync.core import documents, effects, images, media
from lsync.core.formats import kind_of
from lsync.core.utils import Cancelled, TaskContext, open_in_explorer
from lsync.i18n import LANGUAGES, _, get_language
from lsync.ui import theme
from lsync.ui.theme import C
from lsync.ui.widgets import (
    Card, ColorButton, Combo, CropView, DropZone, OutputBar, RunBar, Segmented, SliderRow, Spinner, button, human_size,
    human_time, label, pil_to_qimage, rounded,
)

ANIMATION_MODES = {"keep": "Manter animação", "first": "Só o 1º quadro", "all": "Todos os quadros"}
OUTPUT_KINDS = {"audio": "Áudio", "video": "Vídeo"}
PREVIEW_VIEWS = {"after": "Depois", "before": "Antes"}
SAME_FORMAT = [("same", "Mesmo formato")]
DL_MODES = {"one": "Um vídeo", "many": "Vários (até 50)"}
LOSSY = ("JPG", "WEBP", "AVIF", "HEIC", "JPEG 2000")
MAX_LINKS = 50


class _Emitter(QObject):
    progress = Signal(float, str)
    done = Signal(list, list, bool)


def hint(text: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    ic = QLabel()
    ic.setPixmap(theme.pixmap("info", C["muted"], 15))
    ic.setAlignment(Qt.AlignTop)
    lay.addWidget(ic)
    lay.addWidget(label(text, "Small", wrap=True), 1)
    return w


def add_row(form: QFormLayout, text: str, widget: QWidget) -> None:
    lbl = QLabel(text)
    lbl.setTextFormat(Qt.PlainText)
    form.addRow(lbl, widget)


def make_form() -> QFormLayout:
    form = QFormLayout()
    form.setHorizontalSpacing(28)
    form.setVerticalSpacing(12)
    form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
    return form


def options_card(title: str = "", icon_name: str = "sliders") -> tuple[Card, QFormLayout]:
    card = Card(title or _("Opções"), icon_name)
    form = make_form()
    card.box.addLayout(form)
    return card, form


def page_header(icon_name: str, title: str, subtitle: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(16)
    badge = QLabel()
    badge.setObjectName("IconBadge")
    badge.setFixedSize(48, 48)
    badge.setAlignment(Qt.AlignCenter)
    badge.setPixmap(theme.pixmap(icon_name, C["accent"], 24))
    row.addWidget(badge, 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(3)
    col.addWidget(label(title, "Title"))
    col.addWidget(label(subtitle, "Subtitle", wrap=True))
    row.addLayout(col, 1)
    return row


class ToolPage(QWidget):
    key = ""
    icon = "image"
    nav = ""
    title = ""
    subtitle = ""
    kinds: tuple[str, ...] = ("image",)
    run_text = "Converter"
    uses_files = True
    coming_soon = False
    drop_height = 190

    def __init__(self, win):
        super().__init__()
        self.win = win
        self._cancel = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self.notes: list[str] = []
        self.emitter = _Emitter()
        self.emitter.progress.connect(self._on_progress)
        self.emitter.done.connect(self._finish)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 20)
        root.setSpacing(16)
        root.addLayout(self._header())
        if self.coming_soon:
            self._build_coming(root)
            return
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        self.content = QVBoxLayout(host)
        self.content.setContentsMargins(0, 0, 8, 0)
        self.content.setSpacing(14)
        if self.uses_files:
            self.drop = DropZone(self.kinds, win.thumbs, self.drop_height)
            self.drop.changed.connect(self.on_files_changed)
            self.content.addWidget(self.drop)
        self.build(self.content)
        self.content.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        self.output = OutputBar(win.output_dir)
        self.output.changed.connect(win.set_output_dir)
        root.addWidget(self.output)
        self.runbar = RunBar(_(self.run_text), self.start, self.cancel)
        root.addWidget(self.runbar)
        self.on_files_changed()

    def _header(self) -> QHBoxLayout:
        return page_header(self.icon, _(self.title), _(self.subtitle))

    def _build_coming(self, root: QVBoxLayout) -> None:
        card = Card()
        card.box.setContentsMargins(40, 60, 40, 60)
        card.box.setAlignment(Qt.AlignCenter)
        ic = QLabel()
        ic.setFixedHeight(60)
        ic.setPixmap(theme.pixmap("clock", C["accent"], 46))
        ic.setAlignment(Qt.AlignCenter)
        card.box.addWidget(ic)
        t = label(_("Em breve"), "ComingTitle")
        t.setAlignment(Qt.AlignCenter)
        card.box.addWidget(t)
        m = label(_("Essa ferramenta está sendo melhorada e volta numa próxima versão do Lsync."), "Muted", wrap=True)
        m.setAlignment(Qt.AlignCenter)
        card.box.addWidget(m)
        root.addWidget(card)
        root.addStretch(1)

    def build(self, layout: QVBoxLayout) -> None:
        card, form = options_card()
        self.build_options(form)
        layout.addWidget(card)

    def build_options(self, form: QFormLayout) -> None:
        pass

    def collect(self) -> dict:
        return {}

    def process(self, job: Any, out_dir: Path, opts: dict, ctx: TaskContext) -> list[Path]:
        raise NotImplementedError

    def jobs(self, opts: dict) -> list[Any]:
        return list(self.drop.files)

    def job_name(self, job: Any) -> str:
        return Path(job).name

    def on_files_changed(self) -> None:
        pass

    @property
    def busy(self) -> bool:
        return bool(self._worker and self._worker.is_alive())

    def start(self) -> None:
        try:
            opts = self.collect()
            jobs = self.jobs(opts)
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        if not jobs:
            QMessageBox.information(self, APP_NAME, _("Adicione pelo menos um arquivo primeiro.") if self.uses_files else _("Cole pelo menos um link."))
            return
        out_dir = Path(self.output.value() or self.win.output_dir).expanduser()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, _("Não consegui usar a pasta de saída:") + f"\n{exc}")
            return
        self.win.save_settings()
        self.notes = []
        self._cancel.clear()
        self.runbar.busy(True)
        self._worker = threading.Thread(target=self._run, args=(jobs, out_dir, opts), daemon=True)
        self._worker.start()

    def cancel(self) -> None:
        self._cancel.set()
        self.runbar.message(_("Cancelando…"), C["danger"])

    def _on_progress(self, frac: float, text: str) -> None:
        self.runbar.set_progress(frac, text)

    def _run(self, jobs: list, out_dir: Path, opts: dict) -> None:
        n = len(jobs)
        results: list[Path] = []
        errors: list[tuple[str, str]] = []
        cancelled = False
        for i, job in enumerate(jobs):
            name = self.job_name(job)
            prefix = f"[{i + 1}/{n}] " if n > 1 else ""
            last = [_("Processando {name}…").format(name=name)]

            def report(frac: float, text: Optional[str], base=i / n, prefix=prefix, last=last) -> None:
                if text:
                    last[0] = text
                overall = base + frac / n if frac >= 0 else -1.0
                self.emitter.progress.emit(overall, prefix + last[0])

            ctx = TaskContext(report, self._cancel)
            report(0.0, None)
            try:
                results += self.process(job, out_dir, opts, ctx)
            except Cancelled:
                cancelled = True
                break
            except Exception as exc:
                traceback.print_exc()
                errors.append((name, str(exc) or exc.__class__.__name__))
        self.emitter.done.emit(results, errors, cancelled)

    def _finish(self, results: list, errors: list, cancelled: bool) -> None:
        self.runbar.busy(False)
        if cancelled:
            self.runbar.bar.setValue(0)
            self.runbar.message(_("Cancelado. {n} arquivo(s) prontos antes de cancelar.").format(n=len(results)), C["danger"])
            return
        self.runbar.bar.setValue(1000)
        extra = (" · " + " · ".join(self.notes[-3:])) if self.notes else ""
        if errors:
            self.runbar.message(_("Pronto, mas {e} com erro. {n} arquivo(s) gerados.").format(e=len(errors), n=len(results)) + extra, C["danger"])
            detail = "\n\n".join(f"• {name}:\n{err[:500]}" for name, err in errors[:6])
            QMessageBox.critical(self, _("Alguns arquivos falharam"), detail)
        else:
            self.runbar.message(_("Pronto! {n} arquivo(s) salvos em {folder}").format(n=len(results), folder=self.output.value()) + extra, C["success"])
        if results and self.win.open_after:
            try:
                open_in_explorer(Path(results[0]).parent)
            except Exception:
                pass


FILE_KINDS = ("image", "video", "pdf", "sheet", "doc")
PDF_TARGETS = {
    "pdf-png": "Imagens PNG (uma por página)",
    "pdf-jpg": "Imagens JPG (uma por página)",
    "pdf-merge": "Juntar tudo em um PDF",
    "pdf-split": "Separar as páginas (um PDF por página)",
}
IMAGE_EXTRA = {"img-pdf": "PDF com todas as imagens juntas"}
SHEET_TARGETS = {"csv": "CSV", "xlsx": "Excel (XLSX)"}
DOC_TARGETS = {"word-pdf": "PDF"}
CSV_SEPARATORS = {";": "Ponto e vírgula (;)", ",": "Vírgula (,)"}
PDF_DPI = {100: "100 DPI (leve)", 150: "150 DPI", 200: "200 DPI", 300: "300 DPI (impressão)"}
MERGE_TARGETS = ("pdf-merge", "img-pdf")


def file_group(path: Path) -> str:
    kind = kind_of(path)
    return "image" if kind in ("image", "video") else kind


class FileConvertPage(ToolPage):
    key = "img"
    icon = "file"
    nav = "Converter arquivos"
    title = "Converter arquivos"
    subtitle = "Imagens, PDF, planilhas e documentos do Word. Coloque os arquivos e escolha para qual formato converter."
    kinds = FILE_KINDS

    def build_options(self, form):
        self.form = form
        self.group = "image"
        self.notice = hint("")
        self.fmt = Combo(self._targets("image"), "PNG")
        self.fmt.changed.connect(lambda v: self._refresh_rows())
        self.quality = SliderRow(10, 100, 90)
        self.anim = Segmented(ANIMATION_MODES, "keep")
        self.anim_hint = hint(_("“Todos os quadros” salva cada quadro como uma imagem separada numa pasta."))
        self.dpi = Combo(PDF_DPI, 150)
        self.sep = Segmented(CSV_SEPARATORS, ";")
        self.sep.setMaximumWidth(420)
        add_row(form, "", self.notice)
        add_row(form, _("Converter para"), self.fmt)
        add_row(form, _("Qualidade"), self.quality)
        add_row(form, _("Animações e vídeos"), self.anim)
        add_row(form, "", self.anim_hint)
        add_row(form, _("Resolução"), self.dpi)
        add_row(form, _("Separador"), self.sep)
        self._refresh_rows()

    def _targets(self, group: str):
        if group == "pdf":
            return PDF_TARGETS
        if group == "sheet":
            return SHEET_TARGETS
        if group == "doc":
            return DOC_TARGETS
        return [f.label for f in images.available_formats()] + list(IMAGE_EXTRA.items())

    def _groups(self) -> set[str]:
        return {file_group(p) for p in self.drop.files}

    def on_files_changed(self):
        groups = self._groups()
        group = next(iter(groups)) if len(groups) == 1 else ("image" if not groups else "mixed")
        if group != self.group and group != "mixed":
            current = self.fmt.value()
            self.group = group
            self.fmt.set_options(self._targets(group), current)
            if group == "sheet":
                self.fmt.set_value("xlsx" if all(p.suffix.lower() == ".csv" for p in self.drop.files) else "csv")
        self.group = group if group == "mixed" else self.group
        self._refresh_rows()

    def _set_notice(self, text: str) -> None:
        self.notice.findChild(QLabel, "Small").setText(text)
        self.form.setRowVisible(self.notice, bool(text))

    def _refresh_rows(self) -> None:
        target = self.fmt.value()
        group = self.group
        mixed = group == "mixed"
        word_missing = group == "doc" and not documents.word_available()
        if mixed:
            self._set_notice(_("Os arquivos são de tipos diferentes. Converta um tipo de cada vez: imagens, PDFs, planilhas ou documentos do Word."))
        elif word_missing:
            self._set_notice(_("Para converter documentos do Word é preciso ter o Microsoft Word instalado neste computador."))
        elif target in MERGE_TARGETS:
            self._set_notice(_("Todos os arquivos da lista viram um único PDF, na ordem em que aparecem."))
        else:
            self._set_notice("")
        is_image = group == "image" and target not in MERGE_TARGETS
        self.form.setRowVisible(self.fmt, not mixed)
        self.form.setRowVisible(self.quality, is_image)
        self.quality.setEnabled(target in LOSSY)
        self.form.setRowVisible(self.anim, is_image)
        self.form.setRowVisible(self.anim_hint, is_image)
        self.form.setRowVisible(self.dpi, group == "pdf" and target in ("pdf-png", "pdf-jpg"))
        self.form.setRowVisible(self.sep, group == "sheet" and target == "csv")
        if hasattr(self, "runbar"):
            self.runbar.run_btn.setEnabled(not mixed and not word_missing)

    def collect(self):
        if self.group == "mixed":
            raise ValueError(_("Os arquivos são de tipos diferentes. Converta um tipo de cada vez: imagens, PDFs, planilhas ou documentos do Word."))
        target = self.fmt.value()
        opts = {"group": self.group, "target": target, "quality": self.quality.value(), "anim": self.anim.value(),
                "dpi": self.dpi.value(), "sep": self.sep.value()}
        if self.group == "image" and target not in MERGE_TARGETS:
            opts["fmt"] = images.format_by_label(target)
        return opts

    def jobs(self, opts):
        files = list(self.drop.files)
        if not files:
            return []
        if opts["target"] in MERGE_TARGETS or opts["group"] == "doc":
            return [tuple(files)]
        if opts["group"] == "sheet" and opts["target"] == "xlsx":
            files = [p for p in files if p.suffix.lower() == ".csv"]
        if opts["group"] == "sheet" and opts["target"] == "csv":
            files = [p for p in files if p.suffix.lower() != ".csv"]
        if not files:
            raise ValueError(_("Esses arquivos já estão nesse formato."))
        return files

    def job_name(self, job):
        if isinstance(job, tuple):
            return Path(job[0]).name if len(job) == 1 else _("{n} arquivos").format(n=len(job))
        return Path(job).name

    def process(self, job, out_dir, opts, ctx):
        target = opts["target"]
        if target == "img-pdf":
            return [documents.images_to_pdf(list(job), out_dir, ctx)]
        if target == "pdf-merge":
            return [documents.merge_pdfs(list(job), out_dir, ctx)]
        if target in ("pdf-png", "pdf-jpg"):
            return documents.pdf_to_images(job, out_dir, target[-3:], opts["dpi"], ctx)
        if target == "pdf-split":
            return documents.split_pdf(job, out_dir, ctx)
        if target == "csv":
            return documents.sheet_to_csv(job, out_dir, opts["sep"], ctx)
        if target == "xlsx":
            return [documents.csv_to_xlsx(job, out_dir, ctx)]
        if target == "word-pdf":
            return documents.word_to_pdf(list(job), out_dir, ctx)
        fmt, mode = opts["fmt"], opts["anim"]
        video_kw = {}
        if kind_of(job) == "video":
            if mode == "keep" and fmt.ext in ("gif", "webp"):
                video_kw = {"fps": 12, "max_side": 640}
            elif mode == "keep":
                mode = "first"
        return images.process_file(job, out_dir, fmt, lambda im: im, ctx, opts["quality"], animation=mode, video_kw=video_kw)


class MediaConvertPage(ToolPage):
    key = "media"
    icon = "film"
    nav = "Converter áudio/vídeo"
    title = "Converter áudio e vídeo"
    subtitle = "MP4, MKV, WEBM, AVI, MOV, WMV, GIF, MP3, WAV, M4A, FLAC, OGG, OPUS e mais. Para tirar só o som de um vídeo, escolha Áudio e MP3."
    kinds = ("video", "audio")

    def build_options(self, form):
        fmts = media.available_formats()
        self._video = [f.label for f in fmts if f.kind == "video"]
        self._audio = [f.label for f in fmts if f.kind == "audio"]
        self.kind = Segmented(OUTPUT_KINDS, "audio")
        self.kind.changed.connect(self._kind_changed)
        self.fmt = Combo(self._audio, "MP3")
        self.quality = Segmented(media.QUALITY_LABELS, "medium")
        self.res = Combo(media.RESOLUTION_LABELS, 0)
        self.abr = Combo(media.AUDIO_BITRATES, "192k")
        add_row(form, _("Tipo de saída"), self.kind)
        add_row(form, _("Converter para"), self.fmt)
        add_row(form, _("Qualidade do vídeo"), self.quality)
        add_row(form, _("Resolução"), self.res)
        add_row(form, _("Qualidade do áudio"), self.abr)
        self._kind_changed("audio")

    def _kind_changed(self, kind):
        self.fmt.set_options(self._audio if kind == "audio" else self._video)
        self.quality.setEnabled(kind == "video")
        self.res.setEnabled(kind == "video")

    def collect(self):
        return {"fmt": media.format_by_label(self.fmt.value()), "quality": self.quality.value(),
                "height": self.res.value(), "abr": self.abr.value()}

    def process(self, path, out_dir, opts, ctx):
        return [media.convert(path, out_dir, opts["fmt"], ctx, opts["quality"], opts["height"], opts["abr"])]


class _InfoEmitter(QObject):
    ready = Signal(str, object)


class VideoRow(QFrame):
    def __init__(self, url: str, big: bool = False):
        super().__init__()
        self.url = url
        self.setObjectName("VideoCard")
        self.tw, self.th = (240, 135) if big else (112, 63)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 14, 10)
        lay.setSpacing(14)
        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(self.tw, self.th)
        self.thumb.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title = label("", "VideoTitle" if big else "", wrap=big)
        self.meta = label("", "Muted")
        col.addStretch(1)
        col.addWidget(self.title)
        col.addWidget(self.meta)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.spinner = Spinner(22 if big else 18, 2.5)
        lay.addWidget(self.spinner)
        self.loading()

    def loading(self) -> None:
        self.thumb.setPixmap(theme.pixmap("film", C["muted"], 26 if self.tw > 200 else 18))
        self._set_title(_("Buscando vídeo…"))
        self.meta.setText(self._short(self.url))
        self.spinner.start()

    def show_info(self, info: Any) -> None:
        self.spinner.stop()
        if isinstance(info, str):
            self.thumb.setPixmap(theme.pixmap("x", C["danger"], 22))
            self._set_title(_("Não consegui abrir esse link"))
            self.meta.setText(info.splitlines()[0][:140] if info else self._short(self.url))
            return
        if info.get("image") is not None and not info["image"].isNull():
            self.thumb.setPixmap(rounded(info["image"], self.tw, self.th))
        self._set_title(info.get("title") or self.url)
        meta = [m for m in (info.get("uploader"), human_time(info.get("duration"))) if m]
        self.meta.setText(" · ".join(meta))

    def _set_title(self, text: str) -> None:
        if self.tw > 200:
            self.title.setText(text)
        else:
            self.title.setText(self.title.fontMetrics().elidedText(text, Qt.ElideRight, 520))
        self.title.setToolTip(text)

    @staticmethod
    def _short(url: str) -> str:
        return url if len(url) < 70 else url[:67] + "…"


def normalize_url(text: str) -> Optional[str]:
    t = text.strip()
    if t.lower().startswith("www."):
        t = "https://" + t
    if t.lower().startswith(("http://", "https://")) and " " not in t and len(t) > 10:
        return t
    return None


class DownloadPage(ToolPage):
    key = "download"
    icon = "download"
    nav = "Baixar vídeos"
    title = "Baixar vídeos"
    subtitle = "YouTube, TikTok, Instagram, X, Facebook, Twitch e mais de mil sites. Baixe apenas conteúdo que você tem direito de baixar."
    run_text = "Baixar"
    uses_files = False

    def build(self, layout):
        from lsync.core import downloader

        self.cache: dict[str, Any] = {}
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.info_emitter = _InfoEmitter()
        self.info_emitter.ready.connect(self._info_ready)
        self.rows: dict[str, VideoRow] = {}

        card = Card(_("Link"), "link")
        self.mode = Segmented(DL_MODES, "one")
        self.mode.changed.connect(self._mode_changed)
        self.mode.setMaximumWidth(380)
        card.box.addWidget(self.mode)

        self.single = QWidget()
        sl = QVBoxLayout(self.single)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)
        row = QHBoxLayout()
        self.link = QLineEdit()
        self.link.setPlaceholderText(_("Cole o link do vídeo aqui"))
        self.link.addAction(theme.icon("link", C["muted"], 16), QLineEdit.LeadingPosition)
        self.link.setClearButtonEnabled(True)
        self.link.textChanged.connect(lambda: self.single_timer.start())
        row.addWidget(self.link, 1)
        row.addWidget(button(_("Colar"), "clipboard", "", self._paste))
        sl.addLayout(row)
        self.preview_host = QVBoxLayout()
        sl.addLayout(self.preview_host)
        self.preview: Optional[VideoRow] = None
        card.box.addWidget(self.single)

        self.many = QWidget()
        ml = QVBoxLayout(self.many)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(10)
        self.links = QPlainTextEdit()
        self.links.setPlaceholderText(_("Cole um link por linha (até 50)"))
        self.links.setFixedHeight(120)
        self.links.textChanged.connect(lambda: self.many_timer.start())
        ml.addWidget(self.links)
        self.counter = label("", "Small")
        ml.addWidget(self.counter)
        self.list_host = QVBoxLayout()
        self.list_host.setSpacing(8)
        ml.addLayout(self.list_host)
        card.box.addWidget(self.many)
        self.many.hide()
        layout.addWidget(card)

        self.single_timer = QTimer(self)
        self.single_timer.setSingleShot(True)
        self.single_timer.setInterval(450)
        self.single_timer.timeout.connect(self._lookup_single)
        self.many_timer = QTimer(self)
        self.many_timer.setSingleShot(True)
        self.many_timer.setInterval(700)
        self.many_timer.timeout.connect(self._lookup_many)

        opts, form = options_card()
        self.dl_mode = Segmented(downloader.MODES, "video")
        self.dl_mode.changed.connect(self._dl_mode_changed)
        self.q = Combo(downloader.QUALITIES, 0)
        self.compress = QCheckBox(_("Comprimir o vídeo depois de baixar"))
        self.compress.setCursor(Qt.PointingHandCursor)
        self.compress.setChecked(bool(self.win.settings.get("compress", False)))
        self.compress.toggled.connect(self._compress_toggled)
        add_row(form, _("Baixar como"), self.dl_mode)
        add_row(form, _("Qualidade máxima"), self.q)
        add_row(form, _("Comprimir"), self.compress)
        self.compress_hint = hint(_("Deixa o arquivo bem menor sem perder qualidade visível. O áudio não é alterado. Leva um pouco mais de tempo."))
        add_row(form, "", self.compress_hint)
        layout.addWidget(opts)

    def _compress_toggled(self, on: bool) -> None:
        self.win.settings["compress"] = bool(on)
        self.win.save_settings()

    def _dl_mode_changed(self, mode):
        video = mode == "video"
        self.q.setEnabled(video)
        self.compress.setEnabled(video)

    def _mode_changed(self, mode):
        self.single.setVisible(mode == "one")
        self.many.setVisible(mode == "many")

    def _paste(self):
        text = QGuiApplication.clipboard().text().strip()
        if text:
            self.link.setText(text.splitlines()[0])

    def _fetch(self, url: str) -> None:
        if url in self.cache:
            return
        self.cache[url] = None
        self.pool.submit(self._fetch_work, url)

    def _fetch_work(self, url: str) -> None:
        from lsync.core import downloader

        try:
            info = downloader.fetch_info(url)
            img = QImage()
            if info.get("thumbnail"):
                from PIL import Image

                try:
                    img = pil_to_qimage(Image.open(io.BytesIO(info["thumbnail"])))
                except Exception:
                    img = QImage()
            info["image"] = img
            result: Any = info
        except Exception as exc:
            result = str(exc) or _("Não consegui abrir esse link")
        self.info_emitter.ready.emit(url, result)

    def _info_ready(self, url: str, result: Any) -> None:
        self.cache[url] = result
        if self.preview is not None and self.preview.url == url:
            self.preview.show_info(result)
        row = self.rows.get(url)
        if row is not None:
            row.show_info(result)

    def _lookup_single(self) -> None:
        url = normalize_url(self.link.text())
        if self.preview is not None and (url is None or self.preview.url != url):
            self.preview.setParent(None)
            self.preview.deleteLater()
            self.preview = None
        if url is None or self.preview is not None:
            return
        self.preview = VideoRow(url, big=True)
        self.preview_host.addWidget(self.preview)
        cached = self.cache.get(url)
        if cached is not None:
            self.preview.show_info(cached)
        else:
            self._fetch(url)

    def _urls(self) -> list[str]:
        urls = []
        for line in self.links.toPlainText().splitlines():
            u = normalize_url(line)
            if u and u not in urls:
                urls.append(u)
        return urls

    def _lookup_many(self) -> None:
        urls = self._urls()
        shown = urls[:MAX_LINKS]
        if len(urls) > MAX_LINKS:
            self.counter.setText(_("{n} links. O máximo é {max} por vez; só os primeiros {max} serão baixados.").format(n=len(urls), max=MAX_LINKS))
        else:
            self.counter.setText(_("{n} links").format(n=len(urls)) if urls else "")
        for url in list(self.rows):
            if url not in shown:
                self.rows.pop(url).deleteLater()
        for i, url in enumerate(shown):
            row = self.rows.get(url)
            if row is None:
                row = VideoRow(url)
                self.rows[url] = row
                cached = self.cache.get(url)
                if cached is not None:
                    row.show_info(cached)
                else:
                    self._fetch(url)
            self.list_host.insertWidget(i, row)

    def collect(self):
        return {"mode": self.dl_mode.value(), "height": self.q.value(),
                "compress": self.compress.isChecked() and self.dl_mode.value() == "video"}

    def jobs(self, opts):
        if self.mode.value() == "one":
            text = self.link.text().strip()
            if not text:
                return []
            url = normalize_url(text)
            if url is None:
                raise ValueError(_("Isso não parece um link:") + "\n" + text)
            return [url]
        return self._urls()[:MAX_LINKS]

    def job_name(self, url):
        info = self.cache.get(url)
        if isinstance(info, dict) and info.get("title"):
            return info["title"]
        return url if len(url) < 60 else url[:57] + "…"

    def process(self, url, out_dir, opts, ctx):
        from lsync.core import downloader

        compress = opts["compress"]
        paths = downloader.download(url, out_dir, opts["mode"], opts["height"], ctx.sub(0, 0.6 if compress else 1.0))
        if not compress:
            return paths
        result = []
        for p in paths:
            cctx = ctx.sub(0.6, 0.4)
            cctx.status(_("Comprimindo o vídeo…"))
            new, before, after = media.compress_video(p, cctx)
            if after < before:
                self.notes.append(_("comprimido de {a} para {b}").format(a=human_size(before), b=human_size(after)))
            else:
                self.notes.append(_("o vídeo já estava leve, mantive o original"))
            result.append(new)
        return result


class RemoveBgPage(ToolPage):
    key = "bg"
    icon = "scissors"
    nav = "Remover fundo"
    title = "Remover fundo"
    subtitle = "Tira o fundo das fotos automaticamente."
    coming_soon = True


class IntEdit(QLineEdit):
    def __init__(self, value: int):
        super().__init__(str(value))
        self.setValidator(QIntValidator(1, 20000, self))
        self.setFixedWidth(90)
        self.setAlignment(Qt.AlignCenter)

    def value(self) -> int:
        return int(self.text()) if self.text().isdigit() and int(self.text()) > 0 else 1

    def setValue(self, v: int) -> None:
        self.setText(str(v))


class _BoxEmitter(QObject):
    ready = Signal(str, object)


class ResizePage(ToolPage):
    key = "resize"
    icon = "resize"
    nav = "Redimensionar e cortar"
    title = "Redimensionar e cortar"
    subtitle = "Mude o tamanho de várias imagens de uma vez ou corte bordas e partes que você não quer. GIFs animados continuam animados."
    run_text = "Aplicar"

    def build(self, layout):
        self.drop.caption_fn = self._caption
        self.boxes: dict[str, Any] = {}
        self.box_pool = ThreadPoolExecutor(max_workers=2)
        self.box_emitter = _BoxEmitter()
        self.box_emitter.ready.connect(self._box_ready)
        self._crop_src: Optional[Path] = None
        self._crop_size: Optional[tuple[int, int]] = None
        self.box_timer = QTimer(self)
        self.box_timer.setSingleShot(True)
        self.box_timer.setInterval(250)
        self.box_timer.timeout.connect(self._recompute_boxes)

        crop = Card(_("Cortar"), "crop")
        self.crop_mode = Segmented(effects.CROP_MODES, "off")
        self.crop_mode.changed.connect(self._crop_mode_changed)
        crop.box.addWidget(self.crop_mode)

        self.auto_panel = QWidget()
        af = make_form()
        self.auto_panel.setLayout(af)
        af.setContentsMargins(0, 4, 0, 0)
        self.tolerance = SliderRow(0, 100, 20)
        self.tolerance.changed.connect(lambda v: self.box_timer.start())
        add_row(af, _("Sensibilidade"), self.tolerance)
        add_row(af, "", hint(_("Tira as bordas da mesma cor em volta da foto, como faixas pretas, fundo branco ou transparente. Se sobrar um pouco de borda, aumente a sensibilidade.")))
        crop.box.addWidget(self.auto_panel)

        self.manual_panel = QWidget()
        ml = QVBoxLayout(self.manual_panel)
        ml.setContentsMargins(0, 4, 0, 0)
        ml.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(label(_("Proporção")))
        self.ratio = Segmented(effects.CROP_RATIOS, "free")
        self.ratio.changed.connect(self._ratio_changed)
        top.addWidget(self.ratio, 1)
        top.addWidget(button(_("Desfazer recorte"), "x", "", lambda: self.cropper.reset()))
        ml.addLayout(top)
        self.cropper = CropView()
        self.cropper.changed.connect(self._crop_changed)
        ml.addWidget(self.cropper)
        self.crop_info = label("", "Small")
        ml.addWidget(self.crop_info)
        ml.addWidget(hint(_("Arraste na imagem para marcar a área. Puxe os cantos para ajustar e clique duas vezes para desfazer. O mesmo recorte vale para todas as imagens da lista.")))
        crop.box.addWidget(self.manual_panel)
        layout.addWidget(crop)

        size_card, form = options_card(_("Tamanho"), "resize")
        self.build_options(form)
        layout.addWidget(size_card)
        self._crop_mode_changed("off")

    def build_options(self, form):
        self.mode = Segmented(effects.RESIZE_MODES, "percent")
        self.mode.changed.connect(self._mode_changed)
        self.percent = SliderRow(5, 400, 50, lambda v: f"{v}%")
        self.percent.changed.connect(lambda v: self.drop.refresh_captions())
        size = QWidget()
        sl = QHBoxLayout(size)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        self.w = self._spin(1920)
        self.h = self._spin(1080)
        sl.addWidget(self.w)
        sl.addWidget(label("×", "Muted"))
        sl.addWidget(self.h)
        sl.addSpacing(10)
        for text, (pw, ph) in {"HD": (1280, 720), "Full HD": (1920, 1080), "Insta": (1080, 1080), "Story": (1080, 1920)}.items():
            b = button(text, "", "", lambda checked=False, pw=pw, ph=ph: self._preset(pw, ph))
            b.setStyleSheet("padding: 5px 10px;")
            sl.addWidget(b)
        sl.addStretch(1)
        self.fit = Combo(effects.FIT_MODES)
        self.fit.changed.connect(lambda v: self.drop.refresh_captions())
        self.fmt = Combo(SAME_FORMAT + [f.label for f in images.available_formats()], "same")
        add_row(form, _("Como"), self.mode)
        add_row(form, _("Porcentagem"), self.percent)
        add_row(form, _("Tamanho (px)"), size)
        add_row(form, _("Proporção"), self.fit)
        add_row(form, _("Salvar como"), self.fmt)
        self._mode_changed("percent")

    def _spin(self, value: int) -> "IntEdit":
        s = IntEdit(value)
        s.textChanged.connect(lambda t: self.drop.refresh_captions())
        return s

    def _preset(self, w: int, h: int) -> None:
        self.mode.set_value("size")
        self._mode_changed("size")
        self.w.setValue(w)
        self.h.setValue(h)

    def _mode_changed(self, mode):
        self.percent.setEnabled(mode == "percent")
        self.w.setEnabled(mode in ("size", "width"))
        self.h.setEnabled(mode in ("size", "height"))
        self.fit.setEnabled(mode == "size")
        self.drop.refresh_captions()

    def _crop_mode_changed(self, mode):
        self.auto_panel.setVisible(mode == "auto")
        self.manual_panel.setVisible(mode == "manual")
        if mode == "manual":
            self._load_crop_image()
        if mode == "auto":
            self._recompute_boxes()
        self.drop.refresh_captions()

    def on_files_changed(self):
        mode = self.crop_mode.value()
        if mode == "manual":
            self._load_crop_image()
        elif mode == "auto":
            self._recompute_boxes()

    def _load_crop_image(self) -> None:
        first = self.drop.files[0] if self.drop.files else None
        if first == self._crop_src:
            return
        self._crop_src = first
        self._crop_size = None
        img = QImage()
        if first is not None:
            try:
                pil = images.open_image(first)
                self._crop_size = pil.size
                pil.thumbnail((1400, 1400))
                img = pil_to_qimage(pil)
            except Exception:
                img = QImage()
        self.cropper.set_image(img)

    def _ratio_changed(self, key):
        if key == "free":
            self.cropper.set_ratio(None)
        else:
            a, b = key.split(":")
            self.cropper.set_ratio(int(a) / int(b))

    def _crop_changed(self):
        if self._crop_size:
            w, h = self.cropper.pixel_size(*self._crop_size)
            self.crop_info.setText(_("Área recortada: {w} × {h} px").format(w=w, h=h))
        else:
            self.crop_info.setText("")
        self.drop.refresh_captions()

    def _recompute_boxes(self) -> None:
        tol = self.tolerance.value()
        for p in self.drop.files:
            key = f"{p}|{tol}"
            if key not in self.boxes:
                self.boxes[key] = "pending"
                self.box_pool.submit(self._box_work, p, tol, key)
        self.drop.refresh_captions()

    def _box_work(self, path: Path, tol: int, key: str) -> None:
        try:
            img = images.open_image(path)
            full = img.size
            scale = min(1.0, 4000 / max(full))
            small = img.resize((max(1, round(full[0] * scale)), max(1, round(full[1] * scale)))) if scale < 1 else img
            box = effects.trim_box(small, tol)
            if box and scale < 1:
                box = tuple(round(v / scale) for v in box)
            result: Any = (box, full)
        except Exception:
            result = (None, None)
        self.box_emitter.ready.emit(key, result)

    def _box_ready(self, key: str, result: Any) -> None:
        self.boxes[key] = result
        self.drop.refresh_captions()

    def _cropped(self, path: Path, w: int, h: int) -> Optional[tuple[int, int]]:
        mode = self.crop_mode.value()
        if mode == "manual":
            return self.cropper.pixel_size(w, h)
        if mode == "auto":
            result = self.boxes.get(f"{path}|{self.tolerance.value()}")
            if result is None or result == "pending":
                return None
            box = result[0]
            return (box[2] - box[0], box[3] - box[1]) if box else (w, h)
        return w, h

    def _new_size(self, w: int, h: int) -> tuple[int, int]:
        mode = self.mode.value()
        tw, th = self.w.value(), self.h.value()
        if mode == "none":
            return w, h
        if mode == "percent":
            f = self.percent.value() / 100
            return max(1, round(w * f)), max(1, round(h * f))
        if mode == "width":
            return tw, max(1, round(h * tw / w))
        if mode == "height":
            return max(1, round(w * th / h)), th
        if self.fit.value() == "contain":
            s = min(tw / w, th / h)
            return max(1, round(w * s)), max(1, round(h * s))
        return tw, th

    def _caption(self, path: Path, info: dict) -> str:
        size = info.get("size")
        if not size:
            return ""
        w, h = size
        cropped = self._cropped(path, w, h)
        if cropped is None:
            return f"{w}×{h}  →  …"
        nw, nh = self._new_size(*cropped)
        if (nw, nh) == (w, h):
            if self.crop_mode.value() == "auto":
                return f"{w}×{h} · " + _("sem bordas")
            return f"{w}×{h}"
        return f"{w}×{h}  →  {nw}×{nh}"

    def collect(self):
        crop = self.crop_mode.value()
        mode = self.mode.value()
        if crop == "off" and mode == "none":
            raise ValueError(_("Escolha um corte ou um tamanho novo, senão a imagem fica igual."))
        resizer = effects.make_resizer(mode, self.percent.value(), self.w.value(), self.h.value(), self.fit.value())
        fmt_id = self.fmt.value()
        return {"crop": crop, "tol": self.tolerance.value(), "frac": self.cropper.fractions(), "fn": resizer,
                "fmt": None if fmt_id == "same" else images.format_by_label(fmt_id),
                "suffix": _(" cortada") if mode == "none" else _(" redimensionado")}

    def process(self, path, out_dir, opts, ctx):
        fn = effects.chain(effects.make_cropper(opts["crop"], opts["tol"], opts["frac"]), opts["fn"])
        return images.process_file(path, out_dir, opts["fmt"], fn, ctx, 92, suffix=opts["suffix"])


THEMES = {"System": "Sistema", "Light": "Claro", "Dark": "Escuro"}


class SettingsPage(QWidget):
    key = "settings"
    icon = "gear"
    title = "Configurações"
    subtitle = "Idioma, pasta onde os arquivos são salvos, aparência e informações do Lsync."

    def __init__(self, win):
        super().__init__()
        self.win = win
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 20)
        root.setSpacing(16)
        root.addLayout(page_header(self.icon, _(self.title), _(self.subtitle)))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(14)

        general = Card(_("Geral"), "globe")
        gf = make_form()
        general.box.addLayout(gf)
        self.lang = QComboBox()
        self.lang.setCursor(Qt.PointingHandCursor)
        self.lang.setMinimumWidth(240)
        for code, name in LANGUAGES.items():
            self.lang.addItem(theme.flag(code), name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(get_language())))
        self.lang.currentIndexChanged.connect(lambda i: win.change_language(self.lang.itemData(i), self.lang))
        add_row(gf, _("Idioma"), self.lang)
        opener = QCheckBox(_("Abrir a pasta ao terminar"))
        opener.setCursor(Qt.PointingHandCursor)
        opener.setChecked(win.open_after)
        opener.toggled.connect(win._set_open_after)
        add_row(gf, _("Ao terminar"), opener)
        lay.addWidget(general)

        folders = Card(_("Pastas"), "folder")
        folders.box.addWidget(label(_("Pasta padrão onde os arquivos prontos são salvos."), "Muted", wrap=True))
        self.output = OutputBar(win.output_dir)
        self.output.changed.connect(win.set_output_dir)
        folders.box.addWidget(self.output)
        lay.addWidget(folders)

        look = Card(_("Aparência"), "sun")
        lf = make_form()
        look.box.addLayout(lf)
        seg = Segmented(THEMES, win.theme_mode)
        seg.setMaximumWidth(360)
        seg.changed.connect(win.change_theme)
        add_row(lf, _("Tema"), seg)
        lay.addWidget(look)

        about = Card(_("Sobre"), "info")
        row = QHBoxLayout()
        row.setSpacing(16)
        mark = QLabel()
        mark.setPixmap(theme.logo(30))
        row.addWidget(mark, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(f"Lsync {__version__}", "CardTitle"))
        col.addWidget(label(_("Gratuito e de código aberto, sob a licença MIT."), "Muted"))
        row.addLayout(col, 1)
        row.addWidget(button(_("Ver no GitHub"), "external", "", lambda: QDesktopServices.openUrl(QUrl(REPO_URL))))
        row.addWidget(button(_("Reportar um problema"), "info", "", lambda: QDesktopServices.openUrl(QUrl(REPO_URL + "/issues"))))
        about.box.addLayout(row)
        lay.addWidget(about)
        lay.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    @property
    def busy(self) -> bool:
        return False


PREVIEW_W, PREVIEW_H = 380, 300


class ColorPage(ToolPage):
    key = "color"
    icon = "palette"
    nav = "Cores"
    title = "Cores e ajustes"
    subtitle = "Brilho, contraste, saturação, matiz, temperatura e mais, com prévia ao vivo. Também deixa em preto e branco, sépia ou negativo e colore fotos preto e branco."
    run_text = "Aplicar"
    drop_height = 130

    def build(self, layout):
        self._thumb = None
        self._thumb_src: Optional[Path] = None
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(30)
        self.preview_timer.timeout.connect(self._render)

        card = Card(_("Opções"), "sliders")
        cols = QHBoxLayout()
        cols.setSpacing(28)
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.effect = Combo(effects.COLOR_EFFECTS, "none")
        self.effect.changed.connect(self._effect_changed)
        self.threshold = SliderRow(1, 254, 128)
        self.threshold.changed.connect(self._schedule)
        self.tint = ColorButton("#2f7fff")
        self.tint.changed.connect(self._schedule)
        add_row(form, _("Efeito"), self.effect)
        add_row(form, _("Limite P&B puro"), self.threshold)
        add_row(form, _("Cor para tingir"), self.tint)
        self.adj: dict[str, SliderRow] = {}
        for key, text, lo, hi in effects.ADJUSTMENTS:
            fmt = (lambda v: f"{v:+d}°" if v else "0°") if key == "hue" else (lambda v: f"{v:+d}" if v else "0")
            s = SliderRow(lo, hi, 0, fmt)
            s.changed.connect(self._schedule)
            self.adj[key] = s
            add_row(form, _(text), s)
        reset = button(_("Zerar ajustes"), "x", "", self._reset)
        add_row(form, "", reset)
        self.fmt = Combo(SAME_FORMAT + [f.label for f in images.available_formats()], "same")
        add_row(form, _("Salvar como"), self.fmt)
        cols.addLayout(form, 1)

        right = QVBoxLayout()
        right.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(label(_("Prévia"), "CardTitle"))
        top.addStretch(1)
        self.view = Segmented(PREVIEW_VIEWS, "after")
        self.view.changed.connect(lambda v: self._render())
        top.addWidget(self.view)
        right.addLayout(top)
        self.preview = QLabel(_("Adicione uma imagem para ver a prévia"))
        self.preview.setObjectName("PreviewBox")
        self.preview.setFixedSize(PREVIEW_W, PREVIEW_H)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        right.addWidget(self.preview)
        self.note = label("", "Small", wrap=True)
        self.note.setFixedWidth(PREVIEW_W)
        right.addWidget(self.note)
        right.addStretch(1)
        cols.addLayout(right)
        card.box.addLayout(cols)
        layout.addWidget(card)
        self._effect_changed("none")

    def _effect_changed(self, effect):
        self.threshold.setEnabled(effect == "bw")
        self.tint.setEnabled(effect == "tint")
        self.note.setText(_("A prévia não mostra a colorização por IA; ela é aplicada ao salvar.") if effect == "colorize" else "")
        self._schedule()

    def _reset(self):
        for s in self.adj.values():
            s.slider.blockSignals(True)
            s.set(0)
            s.value_label.setText(s.fmt(0))
            s.slider.blockSignals(False)
        self._schedule()

    def on_files_changed(self):
        first = self.drop.files[0] if self.drop.files else None
        if first == self._thumb_src:
            return
        self._thumb_src = first
        self._thumb = None
        if first is not None:
            try:
                img = images.open_image(first)
                img.thumbnail((PREVIEW_W * 2, PREVIEW_H * 2))
                self._thumb = img
            except Exception:
                self._thumb = None
        self._schedule()

    def _schedule(self, *args):
        self.preview_timer.start()

    def _render(self):
        if self._thumb is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(_("Adicione uma imagem para ver a prévia"))
            return
        img = self._thumb
        if self.view.value() == "after":
            o = self.collect()
            img = effects.make_color_effect(o["effect"], o["adj"], o["threshold"], o["tint"], preview=True)(img)
        self.preview.setPixmap(rounded(pil_to_qimage(img), PREVIEW_W - 2, PREVIEW_H - 2, 9, cover=False))

    def collect(self):
        fmt_id = self.fmt.value()
        return {
            "effect": self.effect.value(),
            "fmt": None if fmt_id == "same" else images.format_by_label(fmt_id),
            "adj": {k: s.value() for k, s in self.adj.items()},
            "threshold": self.threshold.value(),
            "tint": self.tint.value,
        }

    def process(self, path, out_dir, opts, ctx):
        fn = effects.make_color_effect(opts["effect"], opts["adj"], opts["threshold"], opts["tint"], ctx)
        suffix = _(effects.EFFECT_SUFFIX.get(opts["effect"], " editada"))
        return images.process_file(path, out_dir, opts["fmt"], fn, ctx, 92, suffix=suffix)


PAGES = [FileConvertPage, MediaConvertPage, DownloadPage, ResizePage, ColorPage, RemoveBgPage]
