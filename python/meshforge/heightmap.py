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
) -> np.ndarray:
    # Keep this arithmetic identical to the pre-Step-5 single-file script so
    # the same input produces a byte-identical binary STL after refactor.
    arr = np.array(image, dtype=np.float32)
    if invert:
        arr = 255.0 - arr
    if threshold is not None:
        arr = np.where(arr >= threshold, 255.0, 0.0)
    return arr / 255.0 * max_height_mm
