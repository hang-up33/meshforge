"""Image loading and heightmap construction (PNG/JPEG/PDF -> float height grid)."""

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
    # Pillow decodes PNG / JPEG (and other raster formats) here; convert("L")
    # collapses anything — including JPEG's YCbCr — down to the grayscale the
    # heightmap path expects.
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


def downsample_heights(
    heights: np.ndarray,
    *,
    pixel_mm: float,
    max_triangles: int,
) -> tuple[np.ndarray, float]:
    """Shrink a height grid so the extruded mesh stays under max_triangles.

    heightmap_to_mesh emits ~4 triangles per input cell (top + bottom, plus a
    lower-order perimeter wall), so an N-cell grid becomes ~4N triangles.
    Slicers like Bambu Studio reject / choke on multi-million-triangle meshes,
    so when the grid would blow the budget we downsample it isotropically and
    scale pixel_mm up by the same factor — the printed model keeps the same
    physical footprint, only fine surface detail is lost. max_triangles <= 0
    disables the cap. Returns (heights, pixel_mm) unchanged when already small
    enough.
    """
    if max_triangles <= 0:
        return heights, pixel_mm
    h, w = heights.shape
    cells = h * w
    budget_cells = max(1, max_triangles // 4)
    if cells <= budget_cells:
        return heights, pixel_mm
    scale = (budget_cells / cells) ** 0.5
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    # BOX (area-average) downsampling, not LANCZOS: no ringing/overshoot, so
    # heights stay within the original [0, max] range (a negative undershoot
    # would push z_top below the base and dent the print). 'F' mode carries the
    # float mm heights through PIL's resampler without quantizing to 8-bit.
    img = Image.fromarray(np.asarray(heights, dtype=np.float32), mode="F")
    img = img.resize((new_w, new_h), Image.BOX)
    out = np.asarray(img, dtype=np.float64)
    # Grow pixel_mm by the realized linear shrink (from the rounded area, so
    # width/height rounding doesn't drift the physical size).
    new_pixel_mm = pixel_mm * (cells / (new_h * new_w)) ** 0.5
    return out, new_pixel_mm
