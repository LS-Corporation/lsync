from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QLayout, QLineEdit, QProgressBar, QPushButton, QSizePolicy, QSlider, QStackedLayout, QVBoxLayout, QWidget,
    QWidgetItem,
)

from lsync.core import formats
from lsync.core.utils import open_in_explorer
from lsync.i18n import _
from lsync.ui import theme
from lsync.ui.theme import C


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def button(text: str, icon_name: str = "", name: str = "", slot: Optional[Callable] = None) -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if icon_name:
        color = "#ffffff" if name == "Primary" else None
        b.setIcon(theme.icon(icon_name, color, 16))
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return ""


def human_time(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def pil_to_qimage(img) -> QImage:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    return QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888).copy()


def rounded(img: QImage, w: int, h: int, radius: float = 7, cover: bool = True) -> QPixmap:
    dpr = 2.0
    target = QPixmap(int(w * dpr), int(h * dpr))
    target.fill(Qt.transparent)
    if img.isNull():
        target.setDevicePixelRatio(dpr)
        return target
    mode = Qt.KeepAspectRatioByExpanding if cover else Qt.KeepAspectRatio
    scaled = img.scaled(int(w * dpr), int(h * dpr), mode, Qt.SmoothTransformation)
    p = QPainter(target)
    p.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w * dpr, h * dpr), radius * dpr, radius * dpr)
    p.setClipPath(path)
    p.drawImage((target.width() - scaled.width()) // 2, (target.height() - scaled.height()) // 2, scaled)
    p.end()
    target.setDevicePixelRatio(dpr)
    return target


class Card(QFrame):
    def __init__(self, title: str = "", icon_name: str = ""):
        super().__init__()
        self.setObjectName("Card")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(18, 16, 18, 16)
        self.box.setSpacing(12)
        if title:
            row = QHBoxLayout()
            row.setSpacing(8)
            if icon_name:
                ic = QLabel()
                ic.setPixmap(theme.pixmap(icon_name, C["accent"], 18))
                row.addWidget(ic)
            row.addWidget(label(title, "CardTitle"))
            row.addStretch(1)
            self.header = row
            self.box.addLayout(row)


class Segmented(QFrame):
    changed = Signal(object)

    def __init__(self, options, value: Any = None):
        super().__init__()
        self.setObjectName("Seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.ids: list[Any] = []
        items = options.items() if isinstance(options, dict) else [(o, o) for o in options]
        for i, (key, text) in enumerate(items):
            b = QPushButton(_(str(text)))
            b.setObjectName("SegBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b, 1)
            self.ids.append(key)
        self.set_value(value if value is not None else self.ids[0])
        self.group.idClicked.connect(lambda i: self.changed.emit(self.ids[i]))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def value(self) -> Any:
        return self.ids[max(0, self.group.checkedId())]

    def set_value(self, key: Any) -> None:
        idx = self.ids.index(key) if key in self.ids else 0
        self.group.button(idx).setChecked(True)


class Combo(QComboBox):
    changed = Signal(object)

    def __init__(self, options, value: Any = None, translate: bool = True):
        super().__init__()
        self.translate = translate
        self.setCursor(Qt.PointingHandCursor)
        self.set_options(options, value)
        self.currentIndexChanged.connect(lambda i: self.changed.emit(self.value()))
        self.setMinimumWidth(220)

    def set_options(self, options, value: Any = None) -> None:
        self.blockSignals(True)
        self.clear()
        if isinstance(options, dict):
            items = list(options.items())
        else:
            items = [o if isinstance(o, tuple) else (o, o) for o in options]
        for key, text in items:
            self.addItem(_(str(text)) if self.translate else str(text), key)
        self.blockSignals(False)
        self.set_value(value if value is not None else items[0][0])

    def value(self) -> Any:
        return self.currentData()

    def set_value(self, key: Any) -> None:
        idx = self.findData(key)
        self.setCurrentIndex(idx if idx >= 0 else 0)


class SliderRow(QWidget):
    changed = Signal(int)

    def __init__(self, lo: int, hi: int, value: int, fmt: Callable[[int], str] = str):
        super().__init__()
        self.fmt = fmt
        self.default = value
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.value_label = label(fmt(value))
        self.value_label.setMinimumWidth(48)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.value_label)
        self.slider.valueChanged.connect(self._moved)

    def _moved(self, v: int) -> None:
        self.value_label.setText(self.fmt(v))
        self.changed.emit(v)

    def value(self) -> int:
        return self.slider.value()

    def set(self, v: int) -> None:
        self.slider.setValue(v)

    def mouseDoubleClickEvent(self, event) -> None:
        self.set(self.default)


class ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self, value: str = "#2f7fff"):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(120)
        self.clicked.connect(self._pick)
        self.set(value)

    def set(self, value: str) -> None:
        self.value = value
        self.setText(value.upper())
        self.setIcon(_swatch(value))

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(self.value), self, _("Escolha a cor"))
        if color.isValid():
            self.set(color.name())
            self.changed.emit(self.value)


def _swatch(value: str):
    from PySide6.QtGui import QIcon

    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(value))
    p.setPen(QPen(QColor(C["border2"]), 2))
    p.drawRoundedRect(2, 2, 28, 28, 7, 7)
    p.end()
    return QIcon(pm)


class Spinner(QWidget):
    def __init__(self, size: int = 28, width: float = 3.0):
        super().__init__()
        self.setFixedSize(size, size)
        self.pen_width = width
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.setInterval(16)

    def start(self) -> None:
        self.timer.start()
        self.show()

    def stop(self) -> None:
        self.timer.stop()
        self.hide()

    def _tick(self) -> None:
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        m = self.pen_width
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setPen(QPen(QColor(C["border"]), self.pen_width, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(C["accent"]), self.pen_width, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, int(-self.angle * 16), int(100 * 16))
        p.end()


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Overlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(14)
        self.spinner = Spinner(40, 3.5)
        self.text = label("", "OverlayText")
        self.text.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.spinner, 0, Qt.AlignCenter)
        lay.addWidget(self.text, 0, Qt.AlignCenter)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(160)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self._then: Optional[Callable] = None
        self.anim.finished.connect(self._anim_finished)
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.parent() and event.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def start(self, text: str) -> None:
        self.text.setText(text)
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self.spinner.start()
        self._fade(0.0, 1.0)

    def finish(self) -> None:
        self.raise_()
        self._fade(1.0, 0.0, self._done)

    def _fade(self, a: float, b: float, then: Optional[Callable] = None) -> None:
        self.anim.stop()
        self._then = then
        self.anim.setStartValue(a)
        self.anim.setEndValue(b)
        self.anim.start()

    def _anim_finished(self) -> None:
        then, self._then = self._then, None
        if then:
            then()

    def _done(self) -> None:
        self.spinner.stop()
        self.hide()


class FlowLayout(QLayout):
    def __init__(self, spacing: int = 10):
        super().__init__()
        self.items: list = []
        self.space = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self.items.append(item)

    def count(self) -> int:
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for it in self.items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _layout(self, rect, test: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for it in self.items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x = rect.x()
                y += line + self.space
                line = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.space
            line = max(line, hint.height())
        return y + line - rect.y()

    def add(self, widget: QWidget) -> None:
        self.addChildWidget(widget)
        self.addItem(QWidgetItem(widget))
        self.invalidate()

    def clear(self) -> None:
        while self.items:
            it = self.items.pop()
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.invalidate()


class ThumbLoader(QObject):
    loaded = Signal(str, QImage, dict)

    def __init__(self):
        super().__init__()
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.cache: dict[str, tuple[QImage, dict]] = {}

    def request(self, path: Path) -> None:
        key = str(path)
        if key in self.cache:
            img, info = self.cache[key]
            QTimer.singleShot(0, lambda: self.loaded.emit(key, img, info))
            return
        self.pool.submit(self._work, path)

    def _work(self, path: Path) -> None:
        key = str(path)
        info: dict = {}
        img = QImage()
        kind = formats.kind_of(path)
        try:
            from PIL import Image

            if kind == "image":
                with Image.open(path) as im:
                    info["size"] = im.size
                    info["frames"] = getattr(im, "n_frames", 1)
                    im.seek(0)
                    frame = im.copy()
                frame.thumbnail((320, 320))
                img = pil_to_qimage(frame)
            elif kind == "pdf":
                from lsync.core import documents

                info["pages"] = documents.pdf_page_count(path)
                thumb = documents.pdf_thumbnail(path, 320)
                if thumb is not None:
                    img = pil_to_qimage(thumb)
            elif kind in ("video", "audio"):
                from lsync.core import ffmpeg, media

                info.update(ffmpeg.probe(path))
                if kind == "video":
                    data = media.video_thumbnail(path, 320)
                    if data:
                        img = pil_to_qimage(Image.open(io.BytesIO(data)))
        except Exception:
            pass
        self.cache[key] = (img, info)
        self.loaded.emit(key, img, info)


class FileCard(QFrame):
    removed = Signal(object)
    clicked = Signal(object)
    W, H = 148, 96

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.info: dict = {}
        self.setObjectName("FileCard")
        self.setFixedWidth(self.W + 16)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(self.W, self.H)
        self.thumb.setAlignment(Qt.AlignCenter)
        kind = formats.kind_of(path)
        self.thumb.setPixmap(theme.pixmap({"audio": "music", "video": "film", "image": "image"}.get(kind, "file"), C["muted"], 28))
        lay.addWidget(self.thumb)
        name = label("", "")
        name.setText(name.fontMetrics().elidedText(path.name, Qt.ElideMiddle, self.W))
        name.setToolTip(path.name)
        lay.addWidget(name)
        self.caption = label("", "Small")
        lay.addWidget(self.caption)
        self.close_btn = QPushButton(self)
        self.close_btn.setObjectName("IconButton")
        self.close_btn.setIcon(theme.icon("x", "#ffffff", 14))
        self.close_btn.setStyleSheet("QPushButton { background: rgba(0,0,0,150); border-radius: 11px; padding: 3px; }")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.move(self.W - 12, 12)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(lambda: self.removed.emit(self.path))
        self.close_btn.hide()

    def set_thumb(self, img: QImage, info: dict) -> None:
        self.info = info
        if not img.isNull():
            self.thumb.setPixmap(rounded(img, self.W, self.H))

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.path)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def enterEvent(self, event) -> None:
        self.close_btn.show()
        self.close_btn.raise_()

    def leaveEvent(self, event) -> None:
        self.close_btn.hide()


class AddCard(QPushButton):
    def __init__(self, slot: Callable):
        super().__init__()
        self.setObjectName("AddCard")
        self.setFixedSize(FileCard.W + 16, FileCard.H + 58)
        self.setIcon(theme.icon("plus", C["muted"], 22))
        self.setIconSize(QSize(22, 22))
        self.setText(_("Adicionar"))
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(slot)


class DropZone(QFrame):
    changed = Signal()
    selected = Signal(object)

    def __init__(self, kinds: Iterable[str], loader: ThumbLoader, empty_height: int = 190):
        super().__init__()
        self.kinds = tuple(kinds)
        self.loader = loader
        self.files: list[Path] = []
        self.cards: dict[str, FileCard] = {}
        self.caption_fn: Optional[Callable[[Path, dict], str]] = None
        self.setAcceptDrops(True)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(theme.pixmap("file", C["accent"], 18))
        head.addWidget(ic)
        head.addWidget(label(_("Arquivos"), "CardTitle"))
        self.count = label("", "Muted")
        head.addWidget(self.count)
        head.addStretch(1)
        self.add_btn = button(_("Adicionar arquivos"), "plus", "", self.browse)
        self.folder_btn = button(_("Pasta…"), "folder", "", self.add_folder)
        self.clear_btn = button(_("Limpar"), "trash", "", self.clear)
        for b in (self.add_btn, self.folder_btn, self.clear_btn):
            head.addWidget(b)
        outer.addLayout(head)

        self.stack = QStackedLayout()
        outer.addLayout(self.stack)
        self.empty = QFrame()
        self.empty.setObjectName("DropZone")
        self.empty.setMinimumHeight(empty_height)
        self.empty.setCursor(Qt.PointingHandCursor)
        el = QVBoxLayout(self.empty)
        el.setAlignment(Qt.AlignCenter)
        el.setSpacing(6)
        up = QLabel()
        up.setPixmap(theme.pixmap("upload", C["accent"], 34))
        up.setAlignment(Qt.AlignCenter)
        el.addWidget(up)
        el.addWidget(self._center(label(_("Arraste e solte seus arquivos aqui"), "DropTitle")))
        el.addWidget(self._center(label(_("ou clique para escolher"), "Muted")))
        self.grid_host = QWidget()
        self.flow = FlowLayout(10)
        self.grid_host.setLayout(self.flow)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.grid_host)
        loader.loaded.connect(self._thumb_ready)
        self._render()

    @staticmethod
    def _center(w: QLabel) -> QLabel:
        w.setAlignment(Qt.AlignCenter)
        return w

    def _exts(self) -> set[str]:
        out: set[str] = set()
        for k in self.kinds:
            out |= formats.EXTS_BY_KIND[k]
        return out

    def _filter(self) -> str:
        return ";;".join(f"{label_} ({pattern})" for label_, pattern in formats.dialog_patterns(*self.kinds))

    def browse(self) -> None:
        paths, _sel = QFileDialog.getOpenFileNames(self, _("Escolha os arquivos"), "", self._filter())
        self.add(paths)

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, _("Escolha uma pasta"))
        if folder:
            self.add([str(p) for p in sorted(Path(folder).iterdir()) if p.is_file()])

    def add(self, paths: Iterable[str]) -> None:
        exts = self._exts()
        added = False
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                self.add([str(c) for c in sorted(p.iterdir()) if c.is_file()])
                continue
            if p.is_file() and p not in self.files and p.suffix.lower().lstrip(".") in exts:
                self.files.append(p)
                added = True
        if added:
            self._render()
            self.changed.emit()

    def remove(self, path: Path) -> None:
        self.files = [f for f in self.files if f != path]
        self._render()
        self.changed.emit()

    def clear(self) -> None:
        if self.files:
            self.files.clear()
            self._render()
            self.changed.emit()

    def mark(self, path) -> None:
        self._marked = path
        for key, card in self.cards.items():
            card.set_selected(path is not None and Path(key) == Path(path))

    def info(self, path: Path) -> dict:
        card = self.cards.get(str(path))
        return card.info if card else {}

    def refresh_captions(self) -> None:
        for card in self.cards.values():
            card.set_caption(self._caption(card.path, card.info))

    def _caption(self, path: Path, info: dict) -> str:
        if self.caption_fn:
            return self.caption_fn(path, info)
        parts = []
        if info.get("size"):
            parts.append(f"{info['size'][0]}×{info['size'][1]}")
        if info.get("duration"):
            parts.append(human_time(info["duration"]))
        if info.get("pages"):
            parts.append(_("1 página") if info["pages"] == 1 else _("{n} páginas").format(n=info["pages"]))
        try:
            parts.append(human_size(path.stat().st_size))
        except OSError:
            pass
        return " · ".join(parts)

    def _render(self) -> None:
        has = bool(self.files)
        self.stack.setCurrentIndex(1 if has else 0)
        self.folder_btn.setVisible(True)
        self.clear_btn.setVisible(has)
        n = len(self.files)
        self.count.setText(("· " + (_("1 arquivo") if n == 1 else _("{n} arquivos").format(n=n))) if n else "")
        self.flow.clear()
        self.cards = {}
        for p in self.files:
            card = FileCard(p)
            card.removed.connect(self.remove)
            card.clicked.connect(self.selected.emit)
            card.set_selected(p == getattr(self, "_marked", None))
            card.set_caption(self._caption(p, {}))
            self.cards[str(p)] = card
            self.flow.add(card)
            self.loader.request(p)
        if has:
            self.flow.add(AddCard(self.browse))
        self.grid_host.updateGeometry()

    def _thumb_ready(self, key: str, img: QImage, info: dict) -> None:
        card = self.cards.get(key)
        if card is not None:
            card.set_thumb(img, info)
            card.set_caption(self._caption(card.path, info))

    def mousePressEvent(self, event) -> None:
        if not self.files and self.empty.geometry().contains(event.position().toPoint()):
            self.browse()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._hot(True)

    def dragLeaveEvent(self, event) -> None:
        self._hot(False)

    def dropEvent(self, event) -> None:
        self._hot(False)
        self.add([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])

    def _hot(self, on: bool) -> None:
        self.empty.setProperty("hot", "true" if on else "false")
        self.empty.style().unpolish(self.empty)
        self.empty.style().polish(self.empty)


class OutputBar(QWidget):
    changed = Signal(str)

    def __init__(self, value: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(label(_("Salvar em:")))
        self.edit = QLineEdit(value)
        self.edit.addAction(theme.icon("folder", C["muted"], 16), QLineEdit.LeadingPosition)
        self.edit.textChanged.connect(self.changed.emit)
        lay.addWidget(self.edit, 1)
        lay.addWidget(button(_("Escolher…"), "folder", "", self.choose))
        lay.addWidget(button(_("Abrir pasta"), "external", "", self.open))

    def value(self) -> str:
        return self.edit.text().strip()

    def set(self, value: str) -> None:
        if value != self.edit.text():
            self.edit.blockSignals(True)
            self.edit.setText(value)
            self.edit.blockSignals(False)

    def choose(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, _("Onde salvar os arquivos?"), self.value())
        if folder:
            self.edit.setText(folder)

    def open(self) -> None:
        path = Path(self.value())
        path.mkdir(parents=True, exist_ok=True)
        open_in_explorer(path)


class RunBar(QWidget):
    def __init__(self, run_text: str, on_run: Callable, on_cancel: Callable):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(6)
        self.status = label("", "Small")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        left.addWidget(self.status)
        left.addWidget(self.bar)
        lay.addLayout(left, 1)
        self.cancel_btn = button(_("Cancelar"), "x", "Danger", on_cancel)
        self.cancel_btn.hide()
        self.run_btn = button(run_text, "play", "Primary", on_run)
        self.run_btn.setMinimumWidth(170)
        lay.addWidget(self.cancel_btn)
        lay.addWidget(self.run_btn)

    def busy(self, value: bool) -> None:
        self.run_btn.setEnabled(not value)
        self.cancel_btn.setVisible(value)
        if value:
            self.bar.setValue(0)

    def set_progress(self, frac: float, text: Optional[str]) -> None:
        if frac >= 0:
            self.bar.setValue(int(frac * 1000))
        if text is not None:
            self.message(text)

    def message(self, text: str, color: Optional[str] = None) -> None:
        self.status.setStyleSheet(f"color: {color};" if color else "")
        metrics = self.status.fontMetrics()
        self.status.setText(metrics.elidedText(text, Qt.ElideMiddle, max(200, self.status.width())))
        self.status.setToolTip(text)


class CropView(QWidget):
    changed = Signal()
    HANDLE = 10
    MIN = 0.03

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(340)
        self.setMouseTracking(True)
        self.img = QImage()
        self.ratio: Optional[float] = None
        self.frac = QRectF(0, 0, 1, 1)
        self._drag: Optional[tuple] = None

    def set_image(self, img: QImage) -> None:
        self.img = img
        self.frac = QRectF(0, 0, 1, 1)
        self._apply_ratio()
        self.update()
        self.changed.emit()

    def set_ratio(self, ratio: Optional[float]) -> None:
        self.ratio = ratio
        self.frac = QRectF(0, 0, 1, 1)
        self._apply_ratio()
        self.update()
        self.changed.emit()

    def reset(self) -> None:
        self.set_ratio(self.ratio)

    def fractions(self) -> tuple[float, float, float, float]:
        f = self.frac
        return f.left(), f.top(), f.right(), f.bottom()

    def pixel_size(self, w: int, h: int) -> tuple[int, int]:
        from lsync.core.effects import manual_box

        x0, y0, x1, y1 = manual_box((w, h), self.fractions())
        return x1 - x0, y1 - y0

    def _image_rect(self) -> QRectF:
        if self.img.isNull():
            return QRectF()
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        s = min(area.width() / self.img.width(), area.height() / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def _crop_rect(self) -> QRectF:
        r = self._image_rect()
        f = self.frac
        return QRectF(r.x() + f.x() * r.width(), r.y() + f.y() * r.height(), f.width() * r.width(), f.height() * r.height())

    def _target(self) -> float:
        return self.ratio / (self.img.width() / self.img.height())

    def _apply_ratio(self) -> None:
        if not self.ratio or self.img.isNull():
            return
        target = self._target()
        f = self.frac
        w, h = f.width(), f.height()
        if w / h > target:
            w = h * target
        else:
            h = w / target
        cx, cy = f.center().x(), f.center().y()
        self.frac = self._clamp(QRectF(cx - w / 2, cy - h / 2, w, h))

    @staticmethod
    def _clamp(r: QRectF) -> QRectF:
        w, h = min(r.width(), 1.0), min(r.height(), 1.0)
        x = min(max(r.x(), 0.0), 1.0 - w)
        y = min(max(r.y(), 0.0), 1.0 - h)
        return QRectF(x, y, w, h)

    def _hit(self, pos) -> str:
        c = self._crop_rect()
        if c.isNull():
            return ""
        x, y, m = pos.x(), pos.y(), self.HANDLE
        in_x = c.left() - m <= x <= c.right() + m
        in_y = c.top() - m <= y <= c.bottom() + m
        edge = ""
        if in_x and abs(y - c.top()) <= m:
            edge += "t"
        if in_x and abs(y - c.bottom()) <= m:
            edge += "b"
        if in_y and abs(x - c.left()) <= m:
            edge += "l"
        if in_y and abs(x - c.right()) <= m:
            edge += "r"
        if edge:
            return edge
        return "move" if c.contains(pos) else ""

    def _cursor(self, hit: str):
        mapping = {"t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor, "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                   "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
                   "move": Qt.SizeAllCursor}
        return mapping.get(hit, Qt.CrossCursor if not self.img.isNull() else Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        if self.img.isNull():
            return
        pos = event.position()
        self._drag = (self._hit(pos) or "new", pos, QRectF(self.frac))

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if not self._drag:
            self.setCursor(self._cursor(self._hit(pos)))
            return
        hit, start, orig = self._drag
        r = self._image_rect()
        if r.isNull():
            return
        dx, dy = (pos.x() - start.x()) / r.width(), (pos.y() - start.y()) / r.height()
        if hit == "move":
            self.frac = self._clamp(QRectF(orig.x() + dx, orig.y() + dy, orig.width(), orig.height()))
            self.update()
            self.changed.emit()
            return
        if hit == "new":
            sx, sy = (start.x() - r.x()) / r.width(), (start.y() - r.y()) / r.height()
            px, py = (pos.x() - r.x()) / r.width(), (pos.y() - r.y()) / r.height()
            left, right = sorted((min(max(sx, 0.0), 1.0), min(max(px, 0.0), 1.0)))
            top, bottom = sorted((min(max(sy, 0.0), 1.0), min(max(py, 0.0), 1.0)))
        else:
            left, top, right, bottom = orig.left(), orig.top(), orig.right(), orig.bottom()
            if "l" in hit:
                left = min(max(orig.left() + dx, 0.0), right - self.MIN)
            if "r" in hit:
                right = max(min(orig.right() + dx, 1.0), left + self.MIN)
            if "t" in hit:
                top = min(max(orig.top() + dy, 0.0), bottom - self.MIN)
            if "b" in hit:
                bottom = max(min(orig.bottom() + dy, 1.0), top + self.MIN)
        rect = QRectF(left, top, max(right - left, self.MIN), max(bottom - top, self.MIN))
        if self.ratio:
            target = self._target()
            vertical_only = hit in ("t", "b")
            if vertical_only:
                rect = QRectF(rect.x(), rect.y(), rect.height() * target, rect.height())
            else:
                h = rect.width() / target
                y = rect.bottom() - h if "t" in hit else rect.y()
                rect = QRectF(rect.x(), y, rect.width(), h)
            if rect.x() < -1e-6 or rect.y() < -1e-6 or rect.right() > 1 + 1e-6 or rect.bottom() > 1 + 1e-6:
                return
        self.frac = self._clamp(rect)
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None

    def mouseDoubleClickEvent(self, event) -> None:
        self.reset()

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QPainterPath

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.fillPath(bg, QColor(C["card2"]))
        if self.img.isNull():
            p.setPen(QColor(C["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, _("Adicione uma imagem para escolher o recorte"))
            p.end()
            return
        r = self._image_rect()
        p.drawImage(r, self.img)
        c = self._crop_rect()
        shade = QPainterPath()
        shade.addRect(r)
        hole = QPainterPath()
        hole.addRect(c)
        p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 150))
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for i in (1, 2):
            x = c.left() + c.width() * i / 3
            y = c.top() + c.height() * i / 3
            p.drawLine(QPoint(int(x), int(c.top())), QPoint(int(x), int(c.bottom())))
            p.drawLine(QPoint(int(c.left()), int(y)), QPoint(int(c.right()), int(y)))
        p.setPen(QPen(QColor("#ffffff"), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawRect(c)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        s = 9
        for x, y in ((c.left(), c.top()), (c.right(), c.top()), (c.left(), c.bottom()), (c.right(), c.bottom())):
            p.drawRoundedRect(QRectF(x - s / 2, y - s / 2, s, s), 2, 2)
        p.end()
