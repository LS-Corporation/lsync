from __future__ import annotations

import sys
import threading
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from lsync import APP_NAME
from lsync.core import updater
from lsync.core.utils import default_output_dir, hide_console_windows, load_settings, save_settings
from lsync.i18n import _, get_language, set_language, system_language
from lsync.ui import theme
from lsync.ui.pages import PAGES, SettingsPage
from lsync.ui.theme import C
from lsync.ui.widgets import LoadingOverlay, ThumbLoader, label



class NavButton(QPushButton):
    def __init__(self, icon_name: str, text: str, badge: str = ""):
        super().__init__()
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self.icon_name = icon_name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(12)
        self.ic = QLabel()
        self.txt = QLabel(text)
        self.txt.setObjectName("NavText")
        for w in (self.ic, self.txt):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(w)
        lay.addStretch(1)
        if badge:
            b = label(badge, "Badge")
            b.setFixedHeight(18)
            b.setAlignment(Qt.AlignCenter)
            b.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(b)
        self.toggled.connect(self._refresh)
        self._refresh(False)

    def _refresh(self, on: bool) -> None:
        self.ic.setPixmap(theme.pixmap(self.icon_name, "#ffffff" if on else C["muted"], 18))
        self.txt.setStyleSheet(f"color: {'#ffffff' if on else C['text']}; background: transparent;")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        set_language(self.settings.get("language") or system_language())
        self.theme_mode = self.settings.get("theme", "Dark")
        self.output_dir = self.settings.get("output_dir") or str(default_output_dir())
        self.open_after = bool(self.settings.get("open_after", False))
        self.current = self.settings.get("page", PAGES[0].key)
        self.thumbs = ThumbLoader()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(theme.asset("icon.ico"))))
        self.resize(1220, 840)
        self.setMinimumSize(1020, 700)
        self.overlay: LoadingOverlay | None = None
        self.tray: QSystemTrayIcon | None = None
        self._build()
        QTimer.singleShot(5000, self._auto_update)

    def _auto_update(self) -> None:
        if not updater.auto_enabled(self.settings) or not updater.due():
            return

        def work() -> None:
            try:
                updater.update()
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _build(self, files: dict | None = None) -> None:
        theme.apply(self.theme_mode)
        QApplication.instance().setStyleSheet(theme.stylesheet())
        root = QWidget()
        root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        self.pages = {}
        for cls in PAGES + [SettingsPage]:
            page = cls(self)
            self.pages[cls.key] = page
            self.stack.addWidget(page)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        for key, paths in (files or {}).items():
            page = self.pages.get(key)
            if page is not None and hasattr(page, "drop"):
                page.drop.add([str(p) for p in paths])
        self.show_page(self.current if self.current in self.pages else PAGES[0].key)
        if self.overlay is None:
            self.overlay = LoadingOverlay(self)
        self.overlay.raise_()

    def _sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(244)
        v = QVBoxLayout(bar)
        v.setContentsMargins(16, 22, 16, 18)
        v.setSpacing(4)

        mark = QLabel()
        mark.setPixmap(theme.logo(30))
        mark.setContentsMargins(10, 0, 0, 0)
        v.addWidget(mark)
        v.addSpacing(24)

        self.nav: dict[str, NavButton] = {}
        group = QButtonGroup(bar)
        group.setExclusive(True)

        def add(key: str, icon_name: str, text: str, badge: str = "") -> None:
            b = NavButton(icon_name, text, badge)
            b.clicked.connect(lambda checked=False, k=key: self.show_page(k))
            group.addButton(b)
            v.addWidget(b)
            self.nav[key] = b

        for cls in PAGES:
            add(cls.key, cls.icon, _(cls.nav or cls.title), _("Em breve") if cls.coming_soon else "")
        v.addStretch(1)
        sep = QFrame()
        sep.setObjectName("Separator")
        v.addWidget(sep)
        v.addSpacing(8)
        add(SettingsPage.key, SettingsPage.icon, _(SettingsPage.title))
        return bar

    def show_page(self, key: str) -> None:
        self.current = key
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        self.nav[key].setChecked(True)
        if hasattr(page, "output"):
            page.output.set(self.output_dir)

    def set_output_dir(self, value: str) -> None:
        self.output_dir = value

    def notify_finished(self, tool: str, done: int, failed: int) -> None:
        if not self.settings.get("notify", True):
            return
        if self.isActiveWindow() and not self.isMinimized():
            return
        QApplication.alert(self)
        if failed:
            text = _("{n} arquivo(s) prontos, {e} com erro.").format(n=done, e=failed)
        else:
            text = _("{n} arquivo(s) prontos. Clique para abrir o Lsync.").format(n=done)
        if self.tray is None:
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip(APP_NAME)
            self.tray.messageClicked.connect(self._restore)
            self.tray.activated.connect(lambda reason: self._restore())
        self.tray.show()
        self.tray.showMessage(f"{APP_NAME} · {tool}", text, self.windowIcon(), 8000)
        QTimer.singleShot(30000, self._hide_tray)

    def _hide_tray(self) -> None:
        if self.tray is not None:
            self.tray.hide()

    def _restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _set_open_after(self, on: bool) -> None:
        self.open_after = bool(on)
        self.save_settings()

    def busy(self) -> bool:
        return any(getattr(p, "busy", False) for p in self.pages.values())

    def _transition(self, text: str, change: Callable[[], None]) -> None:
        self.overlay.start(text)

        def run() -> None:
            change()
            files = {k: list(p.drop.files) for k, p in self.pages.items() if hasattr(p, "drop")}
            self._build(files)
            self.save_settings()
            QTimer.singleShot(280, self.overlay.finish)

        QTimer.singleShot(260, run)

    def change_language(self, code: str, combo: QComboBox) -> None:
        if code == get_language():
            return
        if self.busy():
            QMessageBox.information(self, APP_NAME, _("Espere a tarefa atual terminar para trocar o idioma."))
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(get_language())))
            combo.blockSignals(False)
            return
        set_language(code)
        self._transition(_("Trocando idioma…"), lambda: None)

    def change_theme(self, mode: str) -> None:
        if mode == self.theme_mode:
            return
        self.theme_mode = mode
        self._transition(_("Aplicando tema…"), lambda: None)

    def save_settings(self) -> None:
        self.settings.update({
            "language": get_language(), "theme": self.theme_mode, "output_dir": self.output_dir,
            "open_after": self.open_after, "page": self.current,
        })
        save_settings(self.settings)

    def closeEvent(self, event) -> None:
        if self.busy():
            answer = QMessageBox.question(self, APP_NAME, _("Ainda tem uma tarefa rodando. Fechar mesmo assim?"))
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            for p in self.pages.values():
                if hasattr(p, "_cancel"):
                    p._cancel.set()
        self.save_settings()
        event.accept()


def main() -> None:
    hide_console_windows()
    updater.activate()
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lsync.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(QIcon(str(theme.asset("icon.ico"))))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
