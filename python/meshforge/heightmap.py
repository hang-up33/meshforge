"""Image loading and heightmap construction (PNG/PDF -> float height grid)."""

import numpy as np
from PIL import Image


def rasterize_pdf(path: str, dpi: float) -> Image.Image:
    # PyMuPDF is only required for PDF input; importing lazily keeps PNG-only
    # users from needing it installed.
    import fitz  # PyMuPDF
    with fitz.open(path) as doc:
        if doc.page_count == 0:
            raise ValueError(f"{path} has no pages")
        page = doc.load_page(0)
        zoom = dpi / 72.0  # PyMuPDF's base resolution is 72 DPI
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csGRAY)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def load_grayscale(path: str, dpi: float) -> Image.Image:
    if path.lower().endswith(".pdf"):
        return rasterize_pdf(path, dpi)
    return Image.open(path).convert("L")


def to_heights(
    image: Image.Image,
    *,
    invert: bool,
    threshold: int | None,
    max_height_mm: float,
    layers: list[dict] | None = None,
) -> np.ndarray:
    # Keep this arithmetic identical to the pre-Step-5 single-file script so
    # the same input produces a byte-identical binary STL after refactor.
    arr = np.array(image, dtype=np.float32)
    if invert:
        arr = 255.0 - arr
    if layers is not None:
        # Step 11: 多段階の高さレイヤー。 `max` の昇順に並んだ閾値で
        # 明度をバンド分けし、バンドごとに固定高を返す。`right=True` で
        # 「明度 <= max」のピクセルがそのバンドに入る（README の説明と
        # 一致 — 例: max=64 のバンドは明度 64 を含む）。最終バンドの
        # max を超える明度（ありえないが安全のため）は最後のバンドに
        # 寄せるため index を clip する。
        bins = np.asarray([L["max"] for L in layers], dtype=np.float32)
        band_h = np.asarray([L["height_mm"] for L in layers], dtype=np.float32)
        idx = np.clip(np.digitize(arr, bins, right=True), 0, len(layers) - 1)
        return band_h[idx]
    if threshold is not None:
        arr = np.where(arr >= threshold, 255.0, 0.0)
    return arr / 255.0 * max_height_mm
