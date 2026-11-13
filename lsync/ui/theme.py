from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPainterPath, QPixmap, QPolygonF
from PySide6.QtSvg import QSvgRenderer

from lsync.core.utils import app_data_dir

DARK = {
    "bg": "#0e1014", "side": "#121419", "card": "#16191f", "card2": "#1b1f26", "border": "#262b33",
    "border2": "#323843", "text": "#e8eaed", "muted": "#8b929c", "accent": "#3b82f6", "accent_hover": "#5a95f8",
    "accent_soft": "#18263d", "danger": "#ef4444", "success": "#22c55e", "hover": "#1b1f26", "input": "#111318",
}
LIGHT = {
    "bg": "#f4f5f7", "side": "#ffffff", "card": "#ffffff", "card2": "#f7f8fa", "border": "#e3e6eb",
    "border2": "#d3d8df", "text": "#15171b", "muted": "#68707c", "accent": "#2563eb", "accent_hover": "#1d4ed8",
    "accent_soft": "#e7efff", "danger": "#dc2626", "success": "#16a34a", "hover": "#f1f3f6", "input": "#ffffff",
}
C: dict[str, str] = dict(DARK)
_state = {"dark": True}

ICONS = {
    "image": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/>',
    "film": '<rect x="2.5" y="4" width="19" height="16" rx="3"/><path d="M10 9l5 3-5 3z"/>',
    "download": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 20h16"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9"/><path d="M14.5 14.5L20 20"/><path d="M8.1 8.1L12 12"/>',
    "resize": '<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.3A4.7 4.7 0 0 0 21 9.7C21 5.9 17 3 12 3z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10.5" cy="7" r="1"/><circle cx="15.5" cy="7.5" r="1"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "play": '<path d="M7 4.5l12 7.5-12 7.5z" fill="currentColor"/>',
    "upload": '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "music": '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "chevron": '<path d="M6 9l6 6 6-6"/>',
    "clipboard": '<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 3h6v3H9z"/>',
    "sliders": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    "gear": '<circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="2.5"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "crop": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>',
    "zip": '<path d="M4 14l4-4 4 4 4-4 4 4"/><path d="M4 20h16"/><path d="M12 3v7"/>',
}


def resolve(mode: str) -> bool:
    if mode == "Light":
        return False
    if mode == "Dark":
        return True
    try:
        return QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
    except Exception:
        return True


def apply(mode: str) -> None:
    dark = resolve(mode)
    _state["dark"] = dark
    C.clear()
    C.update(DARK if dark else LIGHT)


def is_dark() -> bool:
    return _state["dark"]


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / name


def _dpr() -> float:
    screen = QGuiApplication.primaryScreen()
    return max(2.0, screen.devicePixelRatio() if screen else 1.0)


def pixmap(name: str, color: str | None = None, size: int = 20) -> QPixmap:
    color = color or C["text"]
    body = ICONS[name].replace("currentColor", color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    dpr = _dpr()
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    return QIcon(pixmap(name, color, size))


def flag(code: str, w: int = 22, h: int = 15) -> QIcon:
    dpr = _dpr()
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpr, dpr)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w, h), 2.5, 2.5)
    p.setClipPath(clip)
    p.setPen(Qt.NoPen)
    if code == "pt":
        p.fillRect(QRectF(0, 0, w, h), QColor("#009c3b"))
        p.setBrush(QColor("#ffdf00"))
        p.drawPolygon(QPolygonF([QPointF(w / 2, 1.8), QPointF(w - 2, h / 2), QPointF(w / 2, h - 1.8), QPointF(2, h / 2)]))
        p.setBrush(QColor("#002776"))
        p.drawEllipse(QPointF(w / 2, h / 2), h * 0.26, h * 0.26)
    elif code == "es":
        p.fillRect(QRectF(0, 0, w, h), QColor("#aa151b"))
        p.fillRect(QRectF(0, h / 4, w, h / 2), QColor("#f1bf00"))
    else:
        stripe = h / 13
        for i in range(13):
            p.fillRect(QRectF(0, i * stripe, w, stripe + 0.05), QColor("#b22234" if i % 2 == 0 else "#ffffff"))
        p.fillRect(QRectF(0, 0, w * 0.42, stripe * 7), QColor("#3c3b6e"))
        p.setBrush(QColor("#ffffff"))
        for row in range(3):
            for col in range(3):
                p.drawEllipse(QPointF(1.6 + col * 3.0, 1.6 + row * 2.6), 0.55, 0.55)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


def logo(height: int = 26) -> QPixmap:
    img = QImage(str(asset("logo.png")))
    if img.isNull():
        return QPixmap()
    if not is_dark():
        img = img.convertToFormat(QImage.Format_ARGB32)
        p = QPainter(img)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(img.rect(), QColor(C["text"]))
        p.end()
    dpr = _dpr()
    pm = QPixmap.fromImage(img.scaledToHeight(int(height * dpr), Qt.SmoothTransformation))
    pm.setDevicePixelRatio(dpr)
    return pm


def _cached_png(name: str, color: str, size: int) -> str:
    folder = app_data_dir() / "ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}-{size}.png"
    if not path.exists():
        pixmap(name, color, size).save(str(path))
    return path.as_posix()


def stylesheet() -> str:
    c = C
    chevron = _cached_png("chevron", c["muted"], 16)
    check = _cached_png("check", "#ffffff", 14)
    return f"""
    QWidget {{ color: {c['text']}; font-family: "Segoe UI"; font-size: 13px; }}
    #Root, QMainWindow {{ background: {c['bg']}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    #Sidebar {{ background: {c['side']}; border-right: 1px solid {c['border']}; }}
    #Brand {{ font-size: 19px; font-weight: 600; }}
    #NavButton {{ background: transparent; border: none; border-radius: 8px; padding: 0; text-align: left; }}
    #NavButton:hover {{ background: {c['hover']}; }}
    #NavButton:checked {{ background: {c['accent']}; }}
    #NavText {{ font-size: 13px; background: transparent; }}
    #Badge {{ background: {c['card2']}; color: {c['muted']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 0px 7px; font-size: 10px; }}
    #SideLabel {{ color: {c['muted']}; font-size: 12px; }}
    #Separator {{ background: {c['border']}; max-height: 1px; min-height: 1px; }}
    #Title {{ font-size: 22px; font-weight: 600; }}
    #Subtitle, #Muted {{ color: {c['muted']}; }}
    #Small {{ color: {c['muted']}; font-size: 12px; }}
    #IconBadge {{ background: {c['accent_soft']}; border-radius: 12px; }}
    #Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    #CardTitle {{ font-size: 14px; font-weight: 600; }}
    #DropZone {{ background: {c['card2']}; border: 1.5px dashed {c['border2']}; border-radius: 10px; }}
    #DropZone[hot="true"] {{ border-color: {c['accent']}; background: {c['accent_soft']}; }}
    #DropTitle {{ font-size: 15px; font-weight: 600; }}
    #FileCard {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    #FileCard:hover {{ border-color: {c['border2']}; }}
    #Thumb {{ background: {c['card2']}; border-radius: 7px; }}
    #AddCard {{ background: transparent; border: 1.5px dashed {c['border2']}; border-radius: 10px; color: {c['muted']}; }}
    #AddCard:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
    QPushButton {{ background: {c['card2']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 7px 14px; }}
    QPushButton:hover {{ border-color: {c['border2']}; background: {c['hover']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton#Primary {{ background: {c['accent']}; border: none; color: #ffffff; font-weight: 600; font-size: 14px; padding: 10px 26px; }}
    QPushButton#Primary:hover {{ background: {c['accent_hover']}; }}
    QPushButton#Primary:disabled {{ background: {c['border']}; color: {c['muted']}; }}
    QPushButton#Danger {{ color: {c['danger']}; }}
    QPushButton#IconButton {{ background: transparent; border: none; padding: 4px; border-radius: 6px; }}
    QPushButton#IconButton:hover {{ background: {c['hover']}; }}
    #Seg {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 9px; }}
    #SegBtn {{ background: transparent; border: none; border-radius: 7px; padding: 6px 14px; color: {c['muted']}; }}
    #SegBtn:hover {{ color: {c['text']}; }}
    #SegBtn:checked {{ background: {c['accent']}; color: #ffffff; }}
    #SegBtn:disabled {{ color: {c['border2']}; }}
    QComboBox, QLineEdit, QSpinBox, QPlainTextEdit {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 10px; selection-background-color: {c['accent']}; }}
    QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QPlainTextEdit:hover {{ border-color: {c['border2']}; }}
    QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
    QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled {{ color: {c['muted']}; background: {c['card2']}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 4px; outline: 0; selection-background-color: {c['accent']}; selection-color: #ffffff; }}
    QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: #ffffff; border: 2px solid {c['accent']}; width: 12px; height: 12px; margin: -6px 0; border-radius: 8px; }}
    QSlider::groove:horizontal:disabled {{ background: {c['border']}; }}
    QSlider::sub-page:horizontal:disabled {{ background: {c['border2']}; }}
    QSlider::handle:horizontal:disabled {{ border-color: {c['border2']}; background: {c['card2']}; }}
    QProgressBar {{ background: {c['border']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
    QCheckBox {{ spacing: 9px; background: transparent; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px; border: 1.5px solid {c['border2']}; background: {c['input']}; }}
    QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url("{check}"); }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border2']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
    QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px 8px; }}
    QMessageBox {{ background: {c['card']}; }}
    #Overlay {{ background: {'rgba(14, 16, 20, 225)' if is_dark() else 'rgba(244, 245, 247, 225)'}; }}
    #OverlayText {{ font-size: 14px; color: {c['muted']}; background: transparent; }}
    #PreviewBox {{ background: {c['card2']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    #VideoCard {{ background: {c['card2']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    #VideoTitle {{ font-size: 15px; font-weight: 600; }}
    #ComingTitle {{ font-size: 20px; font-weight: 600; }}
    """
