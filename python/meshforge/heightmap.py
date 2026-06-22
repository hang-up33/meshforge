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


def _mesh_face_count(h: int, w: int) -> int:
    # Mirror heightmap_to_mesh exactly: 2 triangles per cell on top + 2 on the
    # bottom (4*h*w) plus the perimeter walls (4*w + 4*h). Walls are negligible
    # for square-ish grids but dominate for an extreme aspect ratio, so the
    # budget check must include them — otherwise a long 1px-tall strip stays
    # over budget even after the area-based shrink.
    return 4 * h * w + 4 * w + 4 * h


def downsample_heights(
    heights: np.ndarray,
    *,
    pixel_mm: float,
    max_triangles: int,
) -> tuple[np.ndarray, float]:
    """Shrink a height grid so the extruded mesh stays at/under max_triangles.

    heightmap_to_mesh emits ~4 triangles per input cell (top + bottom) plus a
    perimeter wall, so a high-res grid becomes a multi-million-triangle mesh
    that slicers like Bambu Studio reject / choke on. When the grid would blow
    the budget we downsample it and scale pixel_mm up by the same factor — the
    printed model keeps the same physical footprint, only fine surface detail
    is lost. max_triangles <= 0 disables the cap. Returns (heights, pixel_mm)
    unchanged when already small enough.
    """
    if max_triangles <= 0:
        return heights, pixel_mm
    h, w = heights.shape
    if _mesh_face_count(h, w) <= max_triangles:
        return heights, pixel_mm
    # Isotropic first guess from the dominant top/bottom term (4*h*w).
    scale = (max_triangles / 4 / (h * w)) ** 0.5
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    # The floor + max(1, ...) clamp can leave one side too large when the aspect
    # ratio is extreme (the short side pins at 1px while the wall term, which
    # scales with the long side, blows the budget). Trim the longer side to the
    # largest value that fits the exact face count — solving
    # 4*(short*long + short + long) <= max_triangles for `long`. O(1), and a
    # no-op for square-ish grids where the area guess already fits.
    if _mesh_face_count(new_h, new_w) > max_triangles:
        if new_w >= new_h:
            new_w = max(1, int((max_triangles / 4 - new_h) / (new_h + 1)))
        else:
            new_h = max(1, int((max_triangles / 4 - new_w) / (new_w + 1)))
    # BOX (area-average) downsampling, not LANCZOS: no ringing/overshoot, so
    # heights stay within the original [0, max] range (a negative undershoot
    # would push z_top below the base and dent the print). 'F' mode carries the
    # float mm heights through PIL's resampler without quantizing to 8-bit.
    img = Image.fromarray(np.asarray(heights, dtype=np.float32), mode="F")
    img = img.resize((new_w, new_h), Image.BOX)
    out = np.asarray(img, dtype=np.float64)
    # Grow pixel_mm by the realized linear shrink (from the rounded area, so
    # width/height rounding doesn't drift the physical size). For extreme aspect
    # ratios the trim above is anisotropic, so a single scalar can't preserve
    # both side lengths exactly; the area-based factor keeps the footprint area
    # right, which is all that's meaningful for such a degenerate strip.
    new_pixel_mm = pixel_mm * (h * w / (new_h * new_w)) ** 0.5
    return out, new_pixel_mm
