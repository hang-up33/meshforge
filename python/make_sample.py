"""Generate a tiny sample PNG/PDF so heightmap_to_stl.py has something to chew on."""

import io
import sys

import numpy as np
from PIL import Image


def dome(size: int = 64) -> np.ndarray:
    y, x = np.ogrid[:size, :size]
    cx = cy = size // 2
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    return np.clip(255 * (1 - r / (size * 0.4)), 0, 255).astype(np.uint8)


def floorplan(size: int = 64) -> np.ndarray:
    # Black walls on a white floor, mimicking the input shape of a real
    # architectural plan. Use heightmap_to_stl.py with --invert --threshold
    # to extrude the walls.
    img = np.full((size, size), 255, dtype=np.uint8)
    t = max(1, size // 32)
    img[:t, :] = 0
    img[-t:, :] = 0
    img[:, :t] = 0
    img[:, -t:] = 0
    mid = size // 2
    img[mid:mid + t, :] = 0
    door_x = size // 4
    door_w = size // 8
    img[mid:mid + t, door_x:door_x + door_w] = 255
    return img


def floorplan_lines(_unused_size: int = 256) -> np.ndarray:
    # Step 12-11 extract-walls 用のクリーンなテスト入力。1 px stroke の
    # 線で外周 4 本 + 内壁 1 本を白背景に描く。HoughLinesP がほぼ生のまま
    # 5 本の wall に対応する線分を返せるよう細い線にしてある (太い線は壁の
    # 両 edge が別線として検出されて 2 倍になる)。
    from PIL import Image, ImageDraw
    W, H = 200, 150
    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)
    # 外周長方形 (20,20)-(180,130) → 内寸 160×110 px
    draw.rectangle([(20, 20), (180, 130)], outline=0, width=1)
    # 内壁: 中央を縦に貫く
    draw.line([(100, 20), (100, 130)], fill=0, width=1)
    return np.array(img, dtype=np.uint8)


KINDS = {"dome": dome, "floorplan": floorplan, "floorplan_lines": floorplan_lines}


def _save_pdf(img: Image.Image, path: str) -> None:
    # Pillow's PDF writer needs libjpeg for L/RGB-mode images, which isn't
    # always available; PyMuPDF (already a Step 3 dependency) embeds the
    # rasterized PNG bytes directly instead.
    import fitz  # PyMuPDF
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    with fitz.open() as pdf:
        page = pdf.new_page(width=img.width, height=img.height)
        page.insert_image(page.rect, stream=buf.getvalue())
        pdf.save(path)


def main(path: str, kind: str = "dome") -> None:
    if kind not in KINDS:
        raise SystemExit(f"unknown kind: {kind!r} (choose from {sorted(KINDS)})")
    arr = KINDS[kind](64)
    img = Image.fromarray(arr, mode="L")
    if path.lower().endswith(".pdf"):
        _save_pdf(img, path)
    else:
        img.save(path)
    print(f"wrote {path}  ({img.width}x{img.height}, {kind})")


if __name__ == "__main__":
    argv = sys.argv[1:]
    path = argv[0] if argv else "samples/dome.png"
    kind = argv[1] if len(argv) > 1 else "dome"
    main(path, kind)
