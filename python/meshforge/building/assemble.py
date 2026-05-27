"""Entry point for `--mode building` (Step 12-2: walls only).

The CLI calls `run(settings)` after merging --config + CLI args. This Step
turns each entry of the hand-written `walls[]` into a rotated box and
concatenates them into one STL. Later steps will widen the scope:
  - Step 12-3: openings (door / window holes)
  - Step 12-4: rooms (floor slabs from polygons)
  - Step 12-7: drive walls from an image (OpenCV + Claude API)
  - Step 12-8+: roof / furniture

Coordinate convention (kept simple for hand-written JSON):
  - `start` / `end` are 2D points in the source coordinate system. The
    default `scale_mm_per_px = 1.0` makes them mm directly, which is the
    natural choice for hand-written specs.
  - `thickness_mm` / `height_mm` are always in mm — `scale_mm_per_px`
    never touches them, even when start/end come from pixel coords.
  - Z = up (walls extrude from z=0 to z=height_mm).
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

    mesh = _assemble_walls(walls_spec, scale)
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


def _assemble_walls(walls, scale: float) -> trimesh.Trimesh:
    boxes = [
        _wall_box(w["start"], w["end"], w["thickness_mm"], w["height_mm"], scale)
        for w in walls
    ]
    if len(boxes) == 1:
        return boxes[0]
    # 単純結合 — 角で隣接する壁は内部に重複面が残るが、FDM スライサは問題なく
    # 処理できる。boolean union による厳密な watertight 化は Step 12-3
    # (開口くり抜き) で manifold3d を入れる時にまとめて検討する。
    return trimesh.util.concatenate(boxes)
