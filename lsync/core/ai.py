from __future__ import annotations

import hashlib
import threading
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image

from lsync.core.utils import Cancelled, TaskContext, models_dir
from lsync.i18n import _

_lock = threading.Lock()


_COLOR_FILES = {
    "colorization_deploy_v2.prototxt": {
        "urls": ["https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/models/colorization_deploy_v2.prototxt"],
        "sha256": "d16418cef8df4ccd703a55ae0ef3960861d5010418f77c90d0a47689998a7169",
    },
    "pts_in_hull.npy": {
        "urls": ["https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/resources/pts_in_hull.npy"],
        "sha256": "b5dec01315c34f43f1c8c089e84c45ae35d1838d8e77ed0e7ca930f79ffa450e",
    },
    "colorization_release_v2.caffemodel": {
        "urls": [
            "https://www.dropbox.com/s/dx0qvhhp5hbcx7z/colorization_release_v2.caffemodel?dl=1",
            "https://huggingface.co/spaces/BilalSardar/Black-N-White-To-Color/resolve/main/colorization_release_v2.caffemodel",
        ],
        "sha256": "f5af1e602646328c792e1094f9876fe9cd4c09ac46fa886e5708a1abc89137b1",
    },
}
_color_net = None


def _download(name: str, spec: dict, ctx: Optional[TaskContext]) -> Path:
    folder = models_dir() / "colorization"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    last_err: Exception | None = None
    for url in spec["urls"]:
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Lsync"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                digest = hashlib.sha256()
                while True:
                    if ctx is not None and ctx.cancelled:
                        raise Cancelled()
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if ctx is not None and total > 5_000_000:
                        ctx.status(_("Baixando modelo de IA (só na 1ª vez): {done} de {total} MB").format(done=done >> 20, total=total >> 20))
            if spec["sha256"] and digest.hexdigest() != spec["sha256"]:
                raise RuntimeError(_("O arquivo {name} veio corrompido.").format(name=name))
            tmp.replace(dest)
            return dest
        except Cancelled:
            tmp.unlink(missing_ok=True)
            raise
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            last_err = exc
    raise RuntimeError(_("Não consegui baixar o modelo de IA ({name}):").format(name=name) + f" {last_err}")


def _load_color_net(ctx: Optional[TaskContext]):
    global _color_net
    with _lock:
        if _color_net is not None:
            return _color_net
        import cv2
        import numpy as np

        paths = {n: _download(n, s, ctx) for n, s in _COLOR_FILES.items()}
        net = cv2.dnn.readNetFromCaffe(
            str(paths["colorization_deploy_v2.prototxt"]),
            str(paths["colorization_release_v2.caffemodel"]),
        )
        pts = np.load(str(paths["pts_in_hull.npy"])).transpose().reshape(2, 313, 1, 1)
        net.getLayer(net.getLayerId("class8_ab")).blobs = [pts.astype(np.float32)]
        net.getLayer(net.getLayerId("conv8_313_rh")).blobs = [np.full((1, 313), 2.606, dtype=np.float32)]
        _color_net = net
        return net


def colorize(img: Image.Image, ctx: Optional[TaskContext] = None) -> Image.Image:
    import cv2
    import numpy as np

    net = _load_color_net(ctx)
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    rgb = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    small = cv2.resize(lab, (224, 224))
    net.setInput(cv2.dnn.blobFromImage(small[:, :, 0] - 50))
    ab = cv2.resize(net.forward()[0].transpose((1, 2, 0)), (rgb.shape[1], rgb.shape[0]))
    out = np.clip(cv2.cvtColor(np.concatenate((lab[:, :, :1], ab), axis=2), cv2.COLOR_LAB2RGB), 0, 1)
    result = Image.fromarray((out * 255).astype("uint8"), "RGB")
    if alpha is not None:
        result.putalpha(alpha)
    return result
