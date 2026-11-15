from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas = [(str(root / "assets"), "assets")]
binaries = []
hiddenimports = []

for pkg in ("imageio_ffmpeg", "yt_dlp", "yt_dlp_ejs", "deno", "pillow_heif", "pypdfium2", "pypdfium2_raw", "comtypes", "curl_cffi"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:
        print(f"[spec] {pkg}: {exc}")

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter", "customtkinter", "tkinterdnd2", "rembg", "onnxruntime", "torch", "matplotlib", "IPython",
        "pytest", "PyQt5", "PyQt6", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtPdf",
        "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtXml", "PySide6.QtPrintSupport", "PySide6.QtDBus",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Lsync",
    icon=str(root / "assets" / "icon.ico"),
    console=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Lsync", upx=False)
