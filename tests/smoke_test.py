from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw

from lsync.core import effects, ffmpeg, images, media

FAILS: list[str] = []


def check(name, fn):
    t = time.time()
    try:
        out = fn()
        print(f"  ok   {name}  ({time.time() - t:.1f}s)  -> {out}")
    except Exception as exc:
        FAILS.append(name)
        print(f"  FAIL {name}: {exc!r}")


def sizes(paths):
    paths = list(paths)
    return ", ".join(f"{Path(p).name} [{Path(p).stat().st_size // 1024} KB]" for p in paths[:3]) + (
        f" … (+{len(paths) - 3})" if len(paths) > 3 else "")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="lsync_test_"))
    out = tmp / "out"
    print("pasta de teste:", tmp)
    print("ffmpeg:", ffmpeg.ffmpeg_path())

    img = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((200, 100, 600, 500), fill=(255, 80, 80, 255))
    d.rectangle((50, 50, 200, 200), fill=(40, 120, 255, 255))
    png = tmp / "amostra.png"
    img.save(png)
    jpg = tmp / "foto.jpg"
    img.convert("RGB").save(jpg, quality=90)
    gif = tmp / "anim.gif"
    frames = [Image.new("RGB", (200, 200), (i * 20, 100, 255 - i * 20)) for i in range(12)]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=80, loop=0)
    mp4 = tmp / "video.mp4"
    ffmpeg.run(["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=3",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mp4)])
    webm = tmp / "clip.webm"
    ffmpeg.run(["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15:duration=2", "-c:v", "libvpx-vp9", "-b:v", "500k", str(webm)])
    same = lambda i: i

    print("\n[Traduções]")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "i18n_check.py")], capture_output=True, text=True, encoding="utf-8")
    print("  " + r.stdout.strip().replace("\n", "\n  "))
    if r.returncode:
        FAILS.append("traduções")

    print("\n[Converter imagem]")
    for f in images.available_formats():
        check(f"PNG -> {f.label}", lambda f=f: sizes(images.process_file(png, out, f, same)))
    check("HEIC -> JPG (ida e volta)", lambda: sizes(images.process_file(
        images.process_file(jpg, out, images.format_by_label("HEIC"), same)[0], out, images.format_by_label("JPG"), same)))
    check("GIF animado -> WEBP animado", lambda: sizes(images.process_file(gif, out, images.format_by_label("WEBP"), same)))
    check("GIF -> PNG todos os quadros", lambda: sizes(images.process_file(gif, out, images.format_by_label("PNG"), same, animation="all")))
    check("WEBM -> PNG (1º quadro)", lambda: sizes(images.process_file(webm, out, images.format_by_label("PNG"), same, animation="first")))
    check("MP4 -> GIF animado (imagem)", lambda: sizes(images.process_file(mp4, out, images.format_by_label("GIF"), same, video_kw={"fps": 10, "max_side": 320})))

    print("\n[Converter áudio/vídeo]")
    avail = media.available_formats()
    print("  formatos disponíveis:", len(avail), "de", len(media.FORMATS))
    for f in avail:
        check(f"MP4 -> {f.label}", lambda f=f: sizes([media.convert(mp4, out, f, height=360)]))
    mp3 = next(out.glob("video.mp3"))
    check("MP3 -> WAV", lambda: sizes([media.convert(mp3, out, media.format_by_label("WAV"))]))

    print("\n[Redimensionar]")
    check("50%", lambda: sizes(images.process_file(jpg, out, None, effects.make_resizer("percent", 50), suffix=" r")))
    check("1080x1080 cortar", lambda: sizes(images.process_file(jpg, out, None, effects.make_resizer("size", 0, 1080, 1080, "cover"), suffix=" r")))
    check("GIF só largura 100", lambda: sizes(images.process_file(gif, out, None, effects.make_resizer("width", width=100), suffix=" r")))

    print("\n[Cores]")
    for e in effects.COLOR_EFFECTS:
        if e != "colorize":
            check(f"efeito {e}", lambda e=e: sizes(images.process_file(png, out, None, effects.make_color_effect(e, {"saturation": 30}), suffix=" c")))
    for key, _label, lo, hi in effects.ADJUSTMENTS:
        check(f"ajuste {key} {hi:+}", lambda key=key, hi=hi: effects.make_color_effect("none", {key: hi})(img).getpixel((400, 300)))
    check("ajuste neutro não muda nada", lambda: _assert(effects.make_color_effect("none", {})(img).tobytes() == img.tobytes()))

    print("\n[Documentos]")
    from openpyxl import Workbook, load_workbook

    from lsync.core import documents

    pages = []
    for i in range(3):
        page = tmp / f"pagina{i}.png"
        Image.new("RGB", (600, 800), (40 * i, 120, 200)).save(page)
        pages.append(page)
    docs = tmp / "docs"
    joined = documents.images_to_pdf(pages, docs)
    check("imagens -> um PDF", lambda: _assert(documents.pdf_page_count(joined) == 3) and joined.name)
    check("PDF -> PNG por página", lambda: _assert(len(documents.pdf_to_images(joined, docs, "png", 72)) == 3) and "3 imagens")
    check("PDF -> JPG", lambda: sizes(documents.pdf_to_images(joined, docs, "jpg", 72)))
    check("juntar PDFs", lambda: _assert(documents.pdf_page_count(documents.merge_pdfs([joined, joined], docs)) == 6) and "6 páginas")
    check("separar PDF", lambda: _assert(len(documents.split_pdf(joined, docs)) == 3) and "3 PDFs")
    check("miniatura de PDF", lambda: documents.pdf_thumbnail(joined).size)
    wb = Workbook()
    ws = wb.active
    ws.append(["Produto", "Preço", "Qtd"])
    ws.append(["Café", 12.5, 3])
    wb.create_sheet("Outra").append(["x"])
    sheet = tmp / "planilha.xlsx"
    wb.save(sheet)
    csvs = []
    check("Excel -> CSV (uma por aba)", lambda: (csvs.extend(documents.sheet_to_csv(sheet, docs, ";")), _assert(len(csvs) == 2), sizes(csvs))[-1])
    check("CSV -> Excel com números", lambda: _assert(list(load_workbook(documents.csv_to_xlsx(csvs[0], docs)).active.iter_rows(values_only=True))[1] == ("Café", 12.5, 3)) and "ok")
    print(f"  --   Word instalado: {documents.word_available()}")

    print("\n[Comprimir vídeo]")
    heavy = tmp / "pesado.mp4"
    ffmpeg.run(["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(heavy)])

    def compress():
        audio_before = _audio_codec(heavy)
        new, before, after = media.compress_video(heavy)
        _assert(after < before and new.exists() and ffmpeg.probe(new)["has_audio"])
        _assert(_audio_codec(new) == audio_before)
        return f"{before // 1024} KB -> {after // 1024} KB, áudio {audio_before} mantido"

    check("comprimir mantendo o áudio", compress)
    check("miniatura de vídeo", lambda: f"{len(media.video_thumbnail(mp4) or b'')} bytes")

    if "--ai" in sys.argv:
        from lsync.core import ai

        print("\n[IA]")
        check("colorir P&B", lambda: ai.colorize(Image.open(jpg).convert("L").convert("RGB")).size)

    if "--net" in sys.argv:
        from lsync.core import downloader

        url = sys.argv[sys.argv.index("--net") + 1]
        print("\n[Download]")
        check(f"informações {url}", lambda: (lambda i: f"{i['title']} · {i['duration']}s · miniatura {len(i['thumbnail'] or b'')} bytes")(downloader.fetch_info(url)))
        check(f"vídeo 360p {url}", lambda: sizes(downloader.download(url, out, "video", 360)))
        check(f"mp3 {url}", lambda: sizes(downloader.download(url, out, "mp3")))

    print("\nRESULTADO:", "tudo certo!" if not FAILS else f"{len(FAILS)} falha(s): {FAILS}")
    return 1 if FAILS else 0


def _audio_codec(path):
    import re

    err = subprocess.run([ffmpeg.ffmpeg_path(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, errors="replace").stderr
    m = re.search(r"Audio: (\w+)", err)
    return m.group(1) if m else None


def _assert(cond):
    if not cond:
        raise AssertionError("falhou")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
