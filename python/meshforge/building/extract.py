"""Image → walls[] auto-extraction (Step 12-11, Step 12-12 axis-aligned merge,
Step 12-15 rooms auto-detection).

The pipeline: grayscale → optional invert → binary threshold → Canny edges →
HoughLinesP → filter by min length → optional axis-aligned line merge →
emit walls[] as a building intermediate JSON (schema_version=1).

Step 12-12 adds the merge pass so 1 stroke の壁線が 2 segments で帰ってくる
Canny の挙動を吸収する。水平 (≈0°/180°) / 垂直 (≈90°) を対象にする。
Step 12-16 で同じ tolerance を任意角度に一般化し、斜め壁の near-collinear
segments も merge するようにした。

Step 12-15 で `with_rooms=True` のとき shapely.snap → unary_union →
polygonize で walls の閉路を検出し rooms[] を JSON に追記する。Hough の
端点不一致 (壁同士が数 px 離れている) は snap_tol_px で吸収する。

スコープ:
- walls[] と (optional) rooms[] のみ抽出 (openings / roof / furniture は将来 Step)
- 壁厚 / 壁高 / 床厚は CLI flag で固定値
- Claude API による意味付け (kind 推定) なし
- rooms の label は room_<index> のシリアル番号 (kind 推定はしない)
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
    merge_gap_mm: float = 2.0,
    with_rooms: bool = False,
    room_floor_thickness_mm: float = 2.0,
    room_snap_tol_px: float = 3.0,
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
        # ときだけ「正の有限数」を要求する。merge_gap_mm のみ 0 も許容する
        # (0 = overlap 必須、gap で分断された壁は別 cluster のまま)。
        for name, value in (
            ("merge_distance_mm", merge_distance_mm),
            ("merge_angle_deg", merge_angle_deg),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number, got {value}")
        if not math.isfinite(merge_gap_mm) or merge_gap_mm < 0:
            raise ValueError(
                f"merge_gap_mm must be a non-negative finite number, got {merge_gap_mm}"
            )
    if with_rooms:
        # with_rooms=False のときは未使用なので未指定値でも通す (merge と同じ方針)。
        if not math.isfinite(room_floor_thickness_mm) or room_floor_thickness_mm <= 0:
            raise ValueError(
                "room_floor_thickness_mm must be a positive finite number, got "
                f"{room_floor_thickness_mm}"
            )
        if not math.isfinite(room_snap_tol_px) or room_snap_tol_px < 0:
            raise ValueError(
                "room_snap_tol_px must be a non-negative finite number, got "
                f"{room_snap_tol_px}"
            )

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
            gap_tol_mm=merge_gap_mm,
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

    result: dict[str, Any] = {
        "schema_version": 1,
        "scale_mm_per_px": float(pixel_mm),
        "walls": walls,
    }
    if with_rooms:
        result["rooms"] = _extract_rooms_from_walls(
            walls,
            snap_tol_px=room_snap_tol_px,
            floor_thickness_mm=room_floor_thickness_mm,
        )
    return result


def _extract_rooms_from_walls(
    walls_px: list[dict[str, Any]],
    *,
    snap_tol_px: float,
    floor_thickness_mm: float,
) -> list[dict[str, Any]]:
    """Return rooms[] entries by polygonizing the wall network (Step 12-15).

    shapely.snap で端点を tol 以内の他線分に吸着 (Hough の端点不一致を吸収) →
    unary_union で交点で分割 → polygonize で閉路を polygon として列挙する。
    各 polygon を rooms[] entry に変換 (`floor_thickness_mm` は共通、label は
    `room_<i>` のシリアル番号)。

    凹形 / 複数 disjoint な閉路もそのまま扱える。閉じていない壁網 (0 件) は
    空 list を返す (assemble.py の rooms validator は `[]` を許容する)。
    """
    try:
        from shapely.geometry import LineString, MultiLineString
        from shapely.ops import polygonize, snap, unary_union
    except ImportError as e:
        raise ImportError(
            "extract-walls --with-rooms requires shapely. "
            "Install with: pip install -e '.[building]'"
        ) from e

    if len(walls_px) < 3:
        # 3 本未満では閉路は作れない (floor plan の最小は三角形だが、現実的には
        # 4 本以上)。早期 return で snap / polygonize のコスト削減。
        return []

    lines = [
        LineString([(w["start"][0], w["start"][1]), (w["end"][0], w["end"][1])])
        for w in walls_px
    ]
    mls = MultiLineString(lines)
    # snap=0 は no-op、その場合は完全一致した端点しか polygonize されない (=
    # Hough 由来の floor plan ではまず 0 件)。tol>0 推奨は CLI default で運用。
    network = snap(mls, mls, tolerance=snap_tol_px) if snap_tol_px > 0 else mls
    merged = unary_union(network)
    polygons = list(polygonize(merged))

    rooms: list[dict[str, Any]] = []
    for i, poly in enumerate(polygons):
        # exterior は最後に始点を重複させて閉じるので、最終点を落として保存する
        # (assemble.py の rooms validator は閉じていない polygon を期待する)。
        coords = list(poly.exterior.coords)[:-1]
        rooms.append(
            {
                "polygon": [[float(x), float(y)] for x, y in coords],
                "floor_thickness_mm": float(floor_thickness_mm),
                "label": f"room_{i}",
            }
        )
    return rooms


def _merge_axis_aligned(
    segments_mm: list[tuple[float, float, float, float]],
    *,
    distance_tol_mm: float,
    angle_tol_deg: float,
    gap_tol_mm: float,
) -> list[tuple[float, float, float, float]]:
    """線分を向きで分類し、各グループを greedy にクラスタリングして merge する。

    水平 (≈0°) の線分は y 中央値が近いものを 1 つに、垂直 (≈90°) は x 中央値が
    近いものを 1 つに統合する (Step 12-12)。斜め線分は `_merge_diagonals` で
    任意角度の near-collinear クラスタとして同じ tolerance で統合する (Step 12-16)。

    クラスタ追加条件は **直交方向の近さ + 軸方向の overlap or gap**:
    軸方向に重なっていれば gap=0、離れていれば離距離が gap_tol_mm 以下なら同じ
    cluster に入れる。これでドア開口で分断された壁や同じ y 上の別部屋の壁が
    一本に統合される事故を防ぐ。

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

    # 斜め線分も near-collinear なら統合する (Step 12-16)。axis-aligned と同じ
    # 「角度近接 + 垂直距離 + 軸方向 overlap/gap」基準を任意角度に一般化する。
    merged: list[tuple[float, float, float, float]] = _merge_diagonals(
        diagonals,
        distance_tol_mm=distance_tol_mm,
        angle_tol=angle_tol,
        gap_tol_mm=gap_tol_mm,
    )
    h_clusters = _cluster_by_perp(
        horizontals, axis="y", distance_tol=distance_tol_mm, gap_tol=gap_tol_mm
    )
    for cluster in h_clusters:
        merged.append(_collapse_cluster(cluster, axis="y"))
    v_clusters = _cluster_by_perp(
        verticals, axis="x", distance_tol=distance_tol_mm, gap_tol=gap_tol_mm
    )
    for cluster in v_clusters:
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
    gap_tol: float,
) -> list[list[tuple[float, float, float, float]]]:
    """Group segments by perpendicular-axis closeness AND axial overlap / gap.

    axis="y" → horizontal segments grouped by y-mid + x range overlap.
    axis="x" → vertical segments grouped by x-mid + y range overlap.

    Greedy: 各 segment を「perpendicular 中心値が distance_tol 以内 + 軸方向に
    overlap or 端点間距離 <= gap_tol」を満たす最初の既存 cluster に入れる。
    軸方向 gap を見ないとドア開口で分断された壁や同じ y 上の別部屋の壁が 1 本
    に結合される (Codex P2 で指摘)。
    """
    if axis not in ("x", "y"):
        raise AssertionError(f"axis must be 'x' or 'y', got {axis!r}")
    clusters: list[dict] = []
    for seg in segs:
        if axis == "y":  # horizontal
            mid = (seg[1] + seg[3]) / 2.0
            axial_min = min(seg[0], seg[2])
            axial_max = max(seg[0], seg[2])
        else:  # vertical
            mid = (seg[0] + seg[2]) / 2.0
            axial_min = min(seg[1], seg[3])
            axial_max = max(seg[1], seg[3])
        placed = False
        for c in clusters:
            existing_mid = c["mid_sum"] / c["count"]
            if abs(mid - existing_mid) > distance_tol:
                continue
            # 軸方向 gap (overlap なら負、隙間ありなら正): max(0, ...) で clamp
            gap = max(0.0, c["axial_min"] - axial_max, axial_min - c["axial_max"])
            if gap > gap_tol:
                continue
            c["segs"].append(seg)
            c["mid_sum"] += mid
            c["count"] += 1
            c["axial_min"] = min(c["axial_min"], axial_min)
            c["axial_max"] = max(c["axial_max"], axial_max)
            placed = True
            break
        if not placed:
            clusters.append(
                {
                    "segs": [seg],
                    "mid_sum": mid,
                    "count": 1,
                    "axial_min": axial_min,
                    "axial_max": axial_max,
                }
            )
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


def _merge_diagonals(
    segments_mm: list[tuple[float, float, float, float]],
    *,
    distance_tol_mm: float,
    angle_tol: float,
    gap_tol_mm: float,
) -> list[tuple[float, float, float, float]]:
    """任意角度の near-collinear 線分を greedy にクラスタリングして merge する (Step 12-16).

    axis-aligned 版 (`_cluster_by_perp`) の「直交方向の近さ + 軸方向 overlap/gap」を
    任意角度に一般化する。各線分を自身の向き θ で
    - perpendicular offset d = -x·sinθ + y·cosθ (原点から線までの符号付き距離)
    - axial position t = x·cosθ + y·sinθ (線方向への射影)
    に分解し、cluster へは「角度差 <= angle_tol かつ |d - d_mean| <= distance_tol
    かつ 軸方向 gap <= gap_tol」のとき追加する。

    diagonals は分類段階で [angle_tol, π-angle_tol] の安全域 (0/π の wrap を跨が
    ない) に限定済みなので、角度の平均は単純な算術平均で足りる。collapse は
    cluster 平均角の線上に全端点を射影し、軸方向 min/max を端点・直交方向は平均
    offset に寄せる (`_collapse_diagonal`)。
    """
    clusters: list[dict] = []
    for seg in segments_mm:
        theta = _angle_normalized(seg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        # 両端点の perpendicular offset / axial position。線上なので d は両端ほぼ
        # 一致するが、Hough 由来の微小ブレを均すため平均を取る。
        d1 = -seg[0] * sin_t + seg[1] * cos_t
        d2 = -seg[2] * sin_t + seg[3] * cos_t
        d = (d1 + d2) / 2.0
        t1 = seg[0] * cos_t + seg[1] * sin_t
        t2 = seg[2] * cos_t + seg[3] * sin_t
        axial_min, axial_max = min(t1, t2), max(t1, t2)
        placed = False
        for c in clusters:
            mean_angle = c["angle_sum"] / c["count"]
            dtheta = abs(theta - mean_angle)
            dtheta = min(dtheta, math.pi - dtheta)  # 0/π wrap 安全側
            if dtheta > angle_tol:
                continue
            mean_d = c["d_sum"] / c["count"]
            if abs(d - mean_d) > distance_tol_mm:
                continue
            gap = max(0.0, c["axial_min"] - axial_max, axial_min - c["axial_max"])
            if gap > gap_tol_mm:
                continue
            c["segs"].append(seg)
            c["angle_sum"] += theta
            c["d_sum"] += d
            c["count"] += 1
            c["axial_min"] = min(c["axial_min"], axial_min)
            c["axial_max"] = max(c["axial_max"], axial_max)
            placed = True
            break
        if not placed:
            clusters.append(
                {
                    "segs": [seg],
                    "angle_sum": theta,
                    "d_sum": d,
                    "count": 1,
                    "axial_min": axial_min,
                    "axial_max": axial_max,
                }
            )
    return [_collapse_diagonal(c["segs"]) for c in clusters]


def _collapse_diagonal(
    cluster: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Collapse an arbitrary-angle cluster to one segment along the mean direction.

    cluster 平均角 θ の線上に全端点を射影し、軸方向 (t) の min/max を端点に、
    直交方向 (perpendicular offset d) は全端点の平均にして 1 本へまとめる。
    θ=0 / π/2 では `_collapse_cluster` の axis-aligned 版と一致する。
    """
    thetas = [_angle_normalized(seg) for seg in cluster]
    theta = sum(thetas) / len(thetas)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    ds: list[float] = []
    ts: list[float] = []
    for seg in cluster:
        for x, y in ((seg[0], seg[1]), (seg[2], seg[3])):
            ds.append(-x * sin_t + y * cos_t)
            ts.append(x * cos_t + y * sin_t)
    d = sum(ds) / len(ds)
    t_min, t_max = min(ts), max(ts)
    # 線上の点 p0 = d·n (n=(-sinθ, cosθ)) を基準に t で両端を取る。
    px0, py0 = -d * sin_t, d * cos_t
    return (
        px0 + t_min * cos_t,
        py0 + t_min * sin_t,
        px0 + t_max * cos_t,
        py0 + t_max * sin_t,
    )
