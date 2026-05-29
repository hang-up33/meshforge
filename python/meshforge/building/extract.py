"""Image → walls[] auto-extraction (Step 12-11, Step 12-12 axis-aligned merge).

The pipeline: grayscale → optional invert → binary threshold → Canny edges →
HoughLinesP → filter by min length → optional axis-aligned line merge →
emit walls[] as a building intermediate JSON (schema_version=1).

Step 12-12 adds the merge pass so 1 stroke の壁線が 2 segments で帰ってくる
Canny の挙動を吸収する。水平 (≈0°/180°) / 垂直 (≈90°) のみを対象にし、
任意角度・斜めの merge は Step 12-13+ に残す。

スコープ:
- walls[] のみ抽出 (rooms / openings / roof / furniture は将来 Step)
- 壁厚 / 壁高は CLI flag で固定値
- Claude API による意味付け (kind 推定) なし
- Streamlit UI 露出なし
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
    merge: bool = True,
    merge_distance_mm: float = 2.0,
    merge_angle_deg: float = 5.0,
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
    if merge:
        # merge=False のときは未使用なので未指定値 (任意) でも通す。merge=True の
        # ときだけ「正の有限数」を要求する。
        for name, value in (
            ("merge_distance_mm", merge_distance_mm),
            ("merge_angle_deg", merge_angle_deg),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number, got {value}")

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

    # pixel_mm > 0 はこの関数の冒頭 (line 45-58) で既に validate 済なので
    # この除算は ZeroDivisionError を起こさない。convert 側の数値検証パターンと
    # 同じ「正の有限数」要求を再掲しないように上に集約してある。
    min_length_px = max(1, int(round(min_length_mm / pixel_mm)))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=hough_threshold,
        minLineLength=min_length_px,
        maxLineGap=hough_max_gap_px,
    )

    # 検出された px 線分を mm に正規化してから merge する (角度・距離の判定は
    # mm 単位の方が直感的)。最後にもう一度 px に戻して JSON に書き出す。
    segments_mm: list[tuple[float, float, float, float]] = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = (float(v) for v in line[0])
            segments_mm.append((x1 * pixel_mm, y1 * pixel_mm, x2 * pixel_mm, y2 * pixel_mm))

    if merge and segments_mm:
        segments_mm = _merge_axis_aligned(
            segments_mm,
            distance_tol_mm=merge_distance_mm,
            angle_tol_deg=merge_angle_deg,
        )

    walls: list[dict[str, Any]] = []
    for x1_mm, y1_mm, x2_mm, y2_mm in segments_mm:
        walls.append(
            {
                "start": [x1_mm / pixel_mm, y1_mm / pixel_mm],
                "end": [x2_mm / pixel_mm, y2_mm / pixel_mm],
                "thickness_mm": float(wall_thickness_mm),
                "height_mm": float(wall_height_mm),
            }
        )

    # 0 件は building 側で walls 必須エラーになり、書き出した JSON が convert で
    # 即失敗する。extract-walls の時点で error にして「使えない JSON」を残さない。
    if not walls:
        raise ValueError(
            "no wall segments detected — try lowering --min-length-mm, "
            "raising --threshold, or toggling --no-invert (current invert="
            f"{invert}, threshold={threshold}, min_length_mm={min_length_mm})"
        )

    return {
        "schema_version": 1,
        "scale_mm_per_px": float(pixel_mm),
        "walls": walls,
    }


def _merge_axis_aligned(
    segments_mm: list[tuple[float, float, float, float]],
    *,
    distance_tol_mm: float,
    angle_tol_deg: float,
) -> list[tuple[float, float, float, float]]:
    """軸方向の線分のみを greedy にクラスタリングして merge する (Step 12-12)。

    水平 (≈0°) の線分は y 中央値が近いものを 1 つに、垂直 (≈90°) は x 中央値が
    近いものを 1 つに統合する。任意角度・斜め線の merge は Step 12-13+ に残す
    (axis-aligned floor plan の大半はこれで十分)。

    1 cluster 内の最終線分は: 軸方向の min/max を新しい端点に取り、直交方向は
    cluster 全 segment の端点座標の平均にする (Canny の両 edge を中央へ寄せる)。
    """
    angle_tol = math.radians(angle_tol_deg)
    horizontals: list[tuple[float, float, float, float]] = []
    verticals: list[tuple[float, float, float, float]] = []
    diagonals: list[tuple[float, float, float, float]] = []
    for seg in segments_mm:
        a = _angle_normalized(seg)
        if a < angle_tol or a > math.pi - angle_tol:
            horizontals.append(seg)
        elif abs(a - math.pi / 2) < angle_tol:
            verticals.append(seg)
        else:
            diagonals.append(seg)

    merged: list[tuple[float, float, float, float]] = list(diagonals)
    for cluster in _cluster_by_perp(horizontals, axis="y", distance_tol=distance_tol_mm):
        merged.append(_collapse_cluster(cluster, axis="y"))
    for cluster in _cluster_by_perp(verticals, axis="x", distance_tol=distance_tol_mm):
        merged.append(_collapse_cluster(cluster, axis="x"))
    return merged


def _angle_normalized(seg: tuple[float, float, float, float]) -> float:
    """Return atan2 angle in [0, π) — direction-agnostic (start↔end swap = same)."""
    x1, y1, x2, y2 = seg
    a = math.atan2(y2 - y1, x2 - x1)
    if a < 0:
        a += math.pi
    return a


def _cluster_by_perp(
    segs: list[tuple[float, float, float, float]],
    *,
    axis: str,
    distance_tol: float,
) -> list[list[tuple[float, float, float, float]]]:
    """Group segments where the perpendicular-axis mean is within distance_tol.

    axis="y" → horizontal segments grouped by y-mid. axis="x" → vertical
    segments grouped by x-mid. Greedy: 各 segment を「中心値が tolerance 内の
    最初の既存 cluster」に入れる。代表値は累積平均で更新する。
    """
    if axis not in ("x", "y"):
        raise AssertionError(f"axis must be 'x' or 'y', got {axis!r}")
    clusters: list[dict] = []  # {"segs": [...], "mid_sum": float, "count": int}
    for seg in segs:
        mid = (seg[1] + seg[3]) / 2.0 if axis == "y" else (seg[0] + seg[2]) / 2.0
        placed = False
        for c in clusters:
            existing = c["mid_sum"] / c["count"]
            if abs(mid - existing) <= distance_tol:
                c["segs"].append(seg)
                c["mid_sum"] += mid
                c["count"] += 1
                placed = True
                break
        if not placed:
            clusters.append({"segs": [seg], "mid_sum": mid, "count": 1})
    return [c["segs"] for c in clusters]


def _collapse_cluster(
    cluster: list[tuple[float, float, float, float]],
    *,
    axis: str,
) -> tuple[float, float, float, float]:
    """Collapse a horizontal (axis='y') or vertical (axis='x') cluster to one segment.

    軸方向は端点座標の min/max、直交方向は全端点座標の平均にする。これで Canny
    が拾った両 edge (上下 / 左右) の真ん中に統合線分が来る。
    """
    if axis == "y":  # horizontal: extend along x, average y
        xs = [c for seg in cluster for c in (seg[0], seg[2])]
        ys = [c for seg in cluster for c in (seg[1], seg[3])]
        return (min(xs), sum(ys) / len(ys), max(xs), sum(ys) / len(ys))
    if axis == "x":  # vertical: extend along y, average x
        xs = [c for seg in cluster for c in (seg[0], seg[2])]
        ys = [c for seg in cluster for c in (seg[1], seg[3])]
        return (sum(xs) / len(xs), min(ys), sum(xs) / len(xs), max(ys))
    raise AssertionError(f"axis must be 'x' or 'y', got {axis!r}")
