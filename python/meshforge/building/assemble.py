"""Entry point for `--mode building` (Step 12-2: walls, Step 12-3: floor slabs,
Step 12-4: openings, Step 12-5: flat roof).

The CLI calls `run(settings)` after merging --config + CLI args. This Step
turns each entry of the hand-written `walls[]` into a rotated box and
concatenates them into one STL. `rooms[]` (Step 12-3, optional) adds an
extruded floor slab per polygon. `openings[]` (Step 12-4, optional) carves
door / window holes out of the referenced wall via boolean difference
(manifold3d). `roof` (Step 12-5, optional) extrudes a flat slab from an
explicit polygon and lifts it to sit on top of the tallest wall. Later steps
will widen the scope:
  - Step 12-7: drive walls from an image (OpenCV + Claude API)
  - Step 12-8+: gable / hip roof, eaves overhang, furniture

Coordinate convention (kept simple for hand-written JSON):
  - `start` / `end` are 2D points in the source coordinate system. The
    default `scale_mm_per_px = 1.0` makes them mm directly, which is the
    natural choice for hand-written specs.
  - `thickness_mm` / `height_mm` are always in mm — `scale_mm_per_px`
    never touches them, even when start/end come from pixel coords.
  - Z = up. Walls extrude from z=0 to z=height_mm. Floor slabs also occupy
    z=0..floor_thickness_mm, sitting *inside* the wall footprint at the
    base. Internal duplicate faces (slab top vs. wall bottom) are left in,
    same as wall-wall corners — slicers fill them as solid.
  - The schema's origin-at-top-left is preserved as-is; the X-Y plane is
    just a 2D layout and slicers don't care about that orientation.
"""

import math

import numpy as np
import trimesh

from meshforge.stl import summary, write_stl


def run(settings: dict) -> None:
    spec = settings["building_spec"]
    output_path = settings["output"]

    scale = spec.get("scale_mm_per_px", 1.0)
    err = _validate_scale(scale)
    if err:
        raise ValueError(err)

    walls_spec = spec.get("walls")
    err = _validate_walls(walls_spec)
    if err:
        raise ValueError(err)

    rooms_spec = spec.get("rooms")
    err = _validate_rooms(rooms_spec)
    if err:
        raise ValueError(err)

    openings_spec = spec.get("openings")
    err = _validate_openings(openings_spec, walls_spec, scale)
    if err:
        raise ValueError(err)

    roof_spec = spec.get("roof")
    err = _validate_roof(roof_spec)
    if err:
        raise ValueError(err)

    parts = [_assemble_walls(walls_spec, openings_spec, scale)]
    if rooms_spec:
        parts.append(_assemble_rooms(rooms_spec, scale))
    if roof_spec:
        parts.append(_assemble_roof(roof_spec, walls_spec, scale))
    mesh = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
    write_stl(mesh, output_path)
    print(summary(mesh, output_path))


def _validate_scale(scale) -> str | None:
    if not (isinstance(scale, (int, float)) and not isinstance(scale, bool)):
        return f"scale_mm_per_px must be a number, got {type(scale).__name__}"
    if not math.isfinite(scale) or scale <= 0:
        return "scale_mm_per_px must be a positive finite number"
    return None


def _validate_walls(walls) -> str | None:
    if walls is None:
        return "building JSON must have 'walls' (Step 12-2 で必須)"
    if not isinstance(walls, list):
        return f"walls must be a list, got {type(walls).__name__}"
    if not walls:
        return "walls must be a non-empty list"
    required = {"start", "end", "thickness_mm", "height_mm"}
    for i, w in enumerate(walls):
        if not isinstance(w, dict):
            return f"walls[{i}] must be an object"
        keys = set(w)
        missing = required - keys
        if missing:
            return f"walls[{i}] is missing keys: {sorted(missing)}"
        unknown = keys - required
        if unknown:
            return f"walls[{i}] has unknown keys: {sorted(unknown)}"
        for k in ("start", "end"):
            pt = w[k]
            if not isinstance(pt, list) or len(pt) != 2:
                return f"walls[{i}].{k} must be a [x, y] list of two numbers"
            for c in pt:
                if not (isinstance(c, (int, float)) and not isinstance(c, bool)):
                    return f"walls[{i}].{k} must contain numbers, got {type(c).__name__}"
                if not math.isfinite(c):
                    return f"walls[{i}].{k} must contain finite numbers"
        if w["start"] == w["end"]:
            return f"walls[{i}] start equals end (zero-length wall)"
        for k in ("thickness_mm", "height_mm"):
            v = w[k]
            if not (isinstance(v, (int, float)) and not isinstance(v, bool)):
                return f"walls[{i}].{k} must be a number, got {type(v).__name__}"
            if not math.isfinite(v) or v <= 0:
                return f"walls[{i}].{k} must be a positive finite number"
    return None


def _wall_box(start, end, thickness_mm: float, height_mm: float, scale: float) -> trimesh.Trimesh:
    s = np.asarray(start, dtype=np.float64) * scale
    e = np.asarray(end, dtype=np.float64) * scale
    direction = e - s
    length = float(np.linalg.norm(direction))
    # trimesh.creation.box centers on the origin; build with the wall's local
    # axes (X = length, Y = thickness, Z = height), rotate around Z to align
    # with the start→end direction, then translate so the wall sits with its
    # base at z=0 centered on the midpoint.
    box = trimesh.creation.box(extents=[length, thickness_mm, height_mm])
    angle = math.atan2(direction[1], direction[0])
    box.apply_transform(trimesh.transformations.rotation_matrix(angle, [0.0, 0.0, 1.0]))
    midpoint = (s + e) / 2.0
    box.apply_translation([midpoint[0], midpoint[1], height_mm / 2.0])
    return box


def _assemble_walls(walls, openings, scale: float) -> trimesh.Trimesh:
    # 開口を壁ごとにグルーピング。openings が無ければ boolean を一切呼ばないので
    # 既存サンプル (building_minimal / building_with_floor) は Step 12-3 とバイト
    # 一致のままになる。
    by_wall: dict[int, list[dict]] = {}
    for op in openings or ():
        by_wall.setdefault(op["wall_index"], []).append(op)
    boxes = []
    for i, w in enumerate(walls):
        wall_box = _wall_box(w["start"], w["end"], w["thickness_mm"], w["height_mm"], scale)
        if i in by_wall:
            wall_box = _carve_openings(wall_box, w, by_wall[i], scale)
        boxes.append(wall_box)
    if len(boxes) == 1:
        return boxes[0]
    # 単純結合 — 角で隣接する壁は内部に重複面が残るが、FDM スライサは問題なく
    # 処理できる。boolean union による厳密な watertight 化は将来検討。
    return trimesh.util.concatenate(boxes)


# rooms[] validation. label は任意の文字列で、メッシュには焼かない純粋メタデータ
# (Step 12-9 の家具配置で room_index 参照する時の目印として残す)。polygon は
# 単純多角形を要求するが自己交差は shapely 側の triangulate で死ぬのでこちらでは
# 「3 点以上 + 各点 [x,y] 有限数」までで済ませる (Codex から指摘が来たら厳密化)。
_ROOM_REQUIRED = {"polygon", "floor_thickness_mm"}
_ROOM_OPTIONAL = {"label"}


def _validate_rooms(rooms) -> str | None:
    if rooms is None:
        return None
    if not isinstance(rooms, list):
        return f"rooms must be a list, got {type(rooms).__name__}"
    # 空配列 [] は「キー省略」と同じく床なしとして扱う。スキーマ雛形や JSON
    # 生成ツールが rooms を空で残すケースを壊さないため (Codex P2 対応)。
    allowed = _ROOM_REQUIRED | _ROOM_OPTIONAL
    for i, r in enumerate(rooms):
        if not isinstance(r, dict):
            return f"rooms[{i}] must be an object"
        keys = set(r)
        missing = _ROOM_REQUIRED - keys
        if missing:
            return f"rooms[{i}] is missing keys: {sorted(missing)}"
        unknown = keys - allowed
        if unknown:
            return f"rooms[{i}] has unknown keys: {sorted(unknown)}"
        poly = r["polygon"]
        if not isinstance(poly, list):
            return f"rooms[{i}].polygon must be a list of [x, y] points"
        if len(poly) < 3:
            return f"rooms[{i}].polygon must have at least 3 points"
        for j, pt in enumerate(poly):
            if not isinstance(pt, list) or len(pt) != 2:
                return f"rooms[{i}].polygon[{j}] must be a [x, y] list of two numbers"
            for c in pt:
                if not (isinstance(c, (int, float)) and not isinstance(c, bool)):
                    return f"rooms[{i}].polygon[{j}] must contain numbers, got {type(c).__name__}"
                if not math.isfinite(c):
                    return f"rooms[{i}].polygon[{j}] must contain finite numbers"
        t = r["floor_thickness_mm"]
        if not (isinstance(t, (int, float)) and not isinstance(t, bool)):
            return f"rooms[{i}].floor_thickness_mm must be a number, got {type(t).__name__}"
        if not math.isfinite(t) or t <= 0:
            return f"rooms[{i}].floor_thickness_mm must be a positive finite number"
        if "label" in r and not isinstance(r["label"], str):
            return f"rooms[{i}].label must be a string, got {type(r['label']).__name__}"
    return None


def _room_slab(polygon, floor_thickness_mm: float, scale: float) -> trimesh.Trimesh:
    # shapely / mapbox_earcut は building extra でのみ要求する (`pip install -e
    # '.[building]'`)。dam モードしか使わないユーザに重い依存を背負わせない。
    try:
        from shapely.geometry import Polygon
        from trimesh.creation import extrude_polygon
    except ImportError as e:
        raise ImportError(
            "building mode with rooms[] requires shapely + mapbox_earcut. "
            "Install with: pip install -e '.[building]'"
        ) from e
    coords = [(float(x) * scale, float(y) * scale) for x, y in polygon]
    shape = Polygon(coords)
    if not shape.is_valid:
        # shapely は self-intersecting や zero-area を invalid と判定する。
        # explain_validity でユーザ向けの文字列を返してくれる。
        from shapely.validation import explain_validity
        raise ValueError(f"invalid room polygon: {explain_validity(shape)}")
    return extrude_polygon(shape, height=floor_thickness_mm)


def _assemble_rooms(rooms, scale: float) -> trimesh.Trimesh:
    slabs = [_room_slab(r["polygon"], r["floor_thickness_mm"], scale) for r in rooms]
    if len(slabs) == 1:
        return slabs[0]
    return trimesh.util.concatenate(slabs)


# openings[] validation. 各エントリは {wall_index, offset_mm, width_mm,
# height_mm, sill_mm?, kind} で、sill_mm は省略可 (door は常に 0、window は
# 0 以上の任意値)。kind=door かつ sill_mm > 0 は意味的に衝突するので reject。
# 開口同士の重なりは validate しない (Codex から指摘が来たら強化) — 重なって
# も boolean 差は問題なく取れる。
_OPENING_REQUIRED = {"wall_index", "offset_mm", "width_mm", "height_mm", "kind"}
_OPENING_OPTIONAL = {"sill_mm"}
_OPENING_KINDS = ("door", "window")


_OPENING_EPS_MM = 1e-6


def _wall_length_mm(wall: dict, scale: float) -> float:
    s = np.asarray(wall["start"], dtype=np.float64) * scale
    e = np.asarray(wall["end"], dtype=np.float64) * scale
    return float(np.linalg.norm(e - s))


def _validate_openings(openings, walls, scale: float) -> str | None:
    if openings is None:
        return None
    if not isinstance(openings, list):
        return f"openings must be a list, got {type(openings).__name__}"
    # 空配列 [] は rooms と同じく「無し」扱い。スキーマ雛形互換用 (Codex P2 と
    # 同じ理由)。
    allowed = _OPENING_REQUIRED | _OPENING_OPTIONAL
    n_walls = len(walls)
    for i, op in enumerate(openings):
        if not isinstance(op, dict):
            return f"openings[{i}] must be an object"
        keys = set(op)
        missing = _OPENING_REQUIRED - keys
        if missing:
            return f"openings[{i}] is missing keys: {sorted(missing)}"
        unknown = keys - allowed
        if unknown:
            return f"openings[{i}] has unknown keys: {sorted(unknown)}"
        wi = op["wall_index"]
        if not (isinstance(wi, int) and not isinstance(wi, bool)):
            return f"openings[{i}].wall_index must be an integer, got {type(wi).__name__}"
        if not 0 <= wi < n_walls:
            return f"openings[{i}].wall_index {wi} out of range (walls has {n_walls} entries)"
        for k in ("offset_mm", "width_mm", "height_mm"):
            v = op[k]
            if not (isinstance(v, (int, float)) and not isinstance(v, bool)):
                return f"openings[{i}].{k} must be a number, got {type(v).__name__}"
            if not math.isfinite(v) or v <= 0:
                return f"openings[{i}].{k} must be a positive finite number"
        sill = op.get("sill_mm", 0.0)
        if not (isinstance(sill, (int, float)) and not isinstance(sill, bool)):
            return f"openings[{i}].sill_mm must be a number, got {type(sill).__name__}"
        if not math.isfinite(sill) or sill < 0:
            return f"openings[{i}].sill_mm must be a non-negative finite number"
        kind = op["kind"]
        if kind not in _OPENING_KINDS:
            return f"openings[{i}].kind must be one of {list(_OPENING_KINDS)}, got {kind!r}"
        if kind == "door" and sill > 0:
            return f"openings[{i}] is kind=door but sill_mm={sill} > 0 (door must start from floor)"
        # 壁本体に収まるか確認。offset_mm / width_mm は常に mm なので壁長も mm に
        # 換算して比較する (scale_mm_per_px は start/end のみに掛かる)。
        w = walls[wi]
        wall_len = _wall_length_mm(w, scale)
        if op["offset_mm"] + op["width_mm"] > wall_len + _OPENING_EPS_MM:
            return (
                f"openings[{i}] offset_mm+width_mm ({op['offset_mm']}+{op['width_mm']}) "
                f"exceeds wall length ({wall_len:.3f} mm) on wall {wi}"
            )
        if sill + op["height_mm"] > w["height_mm"] + _OPENING_EPS_MM:
            return (
                f"openings[{i}] sill_mm+height_mm ({sill}+{op['height_mm']}) "
                f"exceeds wall height ({w['height_mm']} mm) on wall {wi}"
            )
    return None


def _carve_openings(wall_box: trimesh.Trimesh, wall_spec: dict, openings: list[dict],
                    scale: float) -> trimesh.Trimesh:
    # manifold3d は openings がある壁でのみ要求する。dam モードや openings 無しの
    # building JSON には影響しない。trimesh 4.x は manifold3d が import 可能なら
    # 自動的にエンジンとして使う。
    try:
        import manifold3d  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "building mode with openings[] requires manifold3d. "
            "Install with: pip install -e '.[building]'"
        ) from e
    cutouts = [_opening_cutout_box(wall_spec, op, scale) for op in openings]
    if len(cutouts) == 1:
        cutout = cutouts[0]
    else:
        cutout = trimesh.boolean.union(cutouts)
    return wall_box.difference(cutout)


# roof は当面 flat のみ。polygon は明示指定で、rooms / walls からの自動推定は
# しない (壁の少し外側に屋根を出したいケースを別フィールドではなく polygon の
# 書き換えで吸収できる)。gable / hip / eaves_overhang は Step 12-6+。
_ROOF_REQUIRED = {"kind", "polygon", "thickness_mm"}
_ROOF_KINDS = ("flat",)


def _validate_roof(roof) -> str | None:
    if roof is None:
        return None
    if not isinstance(roof, dict):
        return f"roof must be an object, got {type(roof).__name__}"
    keys = set(roof)
    missing = _ROOF_REQUIRED - keys
    if missing:
        return f"roof is missing keys: {sorted(missing)}"
    unknown = keys - _ROOF_REQUIRED
    if unknown:
        return f"roof has unknown keys: {sorted(unknown)}"
    kind = roof["kind"]
    if kind not in _ROOF_KINDS:
        return (
            f"roof.kind must be one of {list(_ROOF_KINDS)} (gable/hip は Step 12-6+ 予定), "
            f"got {kind!r}"
        )
    poly = roof["polygon"]
    if not isinstance(poly, list):
        return "roof.polygon must be a list of [x, y] points"
    if len(poly) < 3:
        return "roof.polygon must have at least 3 points"
    for j, pt in enumerate(poly):
        if not isinstance(pt, list) or len(pt) != 2:
            return f"roof.polygon[{j}] must be a [x, y] list of two numbers"
        for c in pt:
            if not (isinstance(c, (int, float)) and not isinstance(c, bool)):
                return f"roof.polygon[{j}] must contain numbers, got {type(c).__name__}"
            if not math.isfinite(c):
                return f"roof.polygon[{j}] must contain finite numbers"
    t = roof["thickness_mm"]
    if not (isinstance(t, (int, float)) and not isinstance(t, bool)):
        return f"roof.thickness_mm must be a number, got {type(t).__name__}"
    if not math.isfinite(t) or t <= 0:
        return "roof.thickness_mm must be a positive finite number"
    return None


def _assemble_roof(roof, walls, scale: float) -> trimesh.Trimesh:
    # shapely / mapbox_earcut は rooms と同じ building extra に乗っている。
    # rooms 無し + roof 有りの JSON でも extra が必要なので、ここで同じ案内を
    # 出す (rooms の _room_slab と同じ ImportError メッセージ)。
    try:
        from shapely.geometry import Polygon
        from trimesh.creation import extrude_polygon
    except ImportError as e:
        raise ImportError(
            "building mode with roof requires shapely + mapbox_earcut. "
            "Install with: pip install -e '.[building]'"
        ) from e
    coords = [(float(x) * scale, float(y) * scale) for x, y in roof["polygon"]]
    shape = Polygon(coords)
    if not shape.is_valid:
        from shapely.validation import explain_validity
        raise ValueError(f"invalid roof polygon: {explain_validity(shape)}")
    slab = extrude_polygon(shape, height=roof["thickness_mm"])
    # 屋根は最も高い壁の天端に乗せる。壁ごとに高さが違うと低い壁の上に空気層が
    # できるが、Step 12-5 では「flat な天井板を 1 枚」までで止める (勾配は Step
    # 12-6+ の gable/hip と一緒に扱う)。
    elevation = max(float(w["height_mm"]) for w in walls)
    slab.apply_translation([0.0, 0.0, elevation])
    return slab


def _opening_cutout_box(wall_spec: dict, opening: dict, scale: float) -> trimesh.Trimesh:
    s = np.asarray(wall_spec["start"], dtype=np.float64) * scale
    e = np.asarray(wall_spec["end"], dtype=np.float64) * scale
    direction = e - s
    length = float(np.linalg.norm(direction))
    thickness = wall_spec["thickness_mm"]
    wall_h = wall_spec["height_mm"]
    w_op = opening["width_mm"]
    h_op = opening["height_mm"]
    sill = opening.get("sill_mm", 0.0)
    # 壁厚を 2mm 超えた厚みで作って boolean の coplanar 面が残らないようにする
    # (manifold3d は coplanar に強いが、安全側で逃がす)。
    box = trimesh.creation.box(extents=[w_op, thickness + 2.0, h_op])
    # wall-local: 壁中心を原点とし x が壁方向。
    local_x = opening["offset_mm"] + w_op / 2.0 - length / 2.0
    local_z = sill + h_op / 2.0 - wall_h / 2.0
    box.apply_translation([local_x, 0.0, local_z])
    angle = math.atan2(direction[1], direction[0])
    box.apply_transform(trimesh.transformations.rotation_matrix(angle, [0.0, 0.0, 1.0]))
    midpoint = (s + e) / 2.0
    box.apply_translation([midpoint[0], midpoint[1], wall_h / 2.0])
    return box
