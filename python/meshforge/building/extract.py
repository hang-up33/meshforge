"""Image → walls[] auto-extraction (Step 12-11).

The pipeline: grayscale → optional invert → binary threshold → Canny edges →
HoughLinesP → filter by min length → emit walls[] as a building intermediate
JSON (schema_version=1).

Step 12-11 is intentionally the smallest useful slice: only `walls[]` are
extracted. rooms / openings / roof are left for the user to add manually or
for future Steps. Line merging, wall-thickness measurement, and Claude
semantic labeling are out of scope here — the goal is just to prove the
PNG/PDF → JSON path with one CLI invocation.
"""

import math
from typing import Any

import numpy as np


def extract_walls(
    image_path: str,
    *,
    dpi: float = 150.0,
    threshold: int = 128,
    invert: bool = True,
    min_length_mm: float = 50.0,
    pixel_mm: float = 1.0,
    wall_thickness_mm: float = 150.0,
    wall_height_mm: float = 2400.0,
    canny_low: int = 50,
    canny_high: int = 150,
    hough_threshold: int = 50,
    hough_max_gap_px: int = 10,
) -> dict[str, Any]:
    """Return a building intermediate JSON (`schema_version: 1`) with `walls[]` only.

    `start` / `end` の座標は **画像の px** で出力し、`scale_mm_per_px = pixel_mm`
    として一緒に返す (assemble 側で start/end × scale_mm_per_px = mm)。事前換算
    して mm 直接入りにすると、ユーザーが手動でレビュー / 編集するときに元画像と
    座標が対応しなくなるためこの形にしている。

    `invert=True` (デフォルト) は「黒い壁線・白い床」の建築図向け。Canny は明るい
    縁を検出するので、壁を高く=白くするためにまず反転する。
    """
    # 入力検証。convert subcommand と同じく「正の有限数」を要求する。
    # 特に pixel_mm <= 0 は min_length_px の除算で ZeroDivisionError になり
    # cmd_extract_walls の except では拾えないトレースバックになる。
    for name, value in (
        ("dpi", dpi),
        ("pixel_mm", pixel_mm),
        ("min_length_mm", min_length_mm),
        ("wall_thickness_mm", wall_thickness_mm),
        ("wall_height_mm", wall_height_mm),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite number, got {value}")
    if not 0 <= threshold <= 255:
        raise ValueError(f"threshold must be in 0..255, got {threshold}")

    try:
        import cv2
    except ImportError as e:
        raise ImportError(
            "extract-walls requires opencv-python-headless. "
            "Install with: pip install -e '.[vision]'"
        ) from e

    # PNG / PDF のロードは既存 dam パイプラインの load_grayscale を流用する
    # (PDF は PyMuPDF で 1 ページ目をラスタライズ、PNG はそのまま読み込み)。
    from meshforge.heightmap import load_grayscale

    pil_image = load_grayscale(image_path, dpi)
    arr = np.array(pil_image, dtype=np.uint8)  # 2D grayscale, H×W
    if invert:
        arr = 255 - arr
    _, binary = cv2.threshold(arr, threshold, 255, cv2.THRESH_BINARY)
    edges = cv2.Canny(binary, canny_low, canny_high)

    min_length_px = max(1, int(round(min_length_mm / pixel_mm)))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=hough_threshold,
        minLineLength=min_length_px,
        maxLineGap=hough_max_gap_px,
    )

    walls: list[dict[str, Any]] = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = (float(v) for v in line[0])
            walls.append(
                {
                    "start": [x1, y1],
                    "end": [x2, y2],
                    "thickness_mm": float(wall_thickness_mm),
                    "height_mm": float(wall_height_mm),
                }
            )

    return {
        "schema_version": 1,
        "scale_mm_per_px": float(pixel_mm),
        "walls": walls,
    }
