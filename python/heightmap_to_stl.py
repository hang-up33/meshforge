"""PNG -> binary STL via simple heightmap extrusion (meshforge Step 1)."""

import sys

import numpy as np
import trimesh
from PIL import Image

PIXEL_MM = 0.5         # 1 pixel = 0.5 mm in X/Y
MAX_HEIGHT_MM = 10.0   # brightness 255 -> 10 mm tall
BASE_MM = 1.0          # solid base thickness


def heightmap_to_mesh(heights: np.ndarray) -> trimesh.Trimesh:
    h, w = heights.shape
    xs = np.arange(w) * PIXEL_MM
    ys = np.arange(h) * PIXEL_MM
    xx, yy = np.meshgrid(xs, ys)
    z_top = heights + BASE_MM
    z_bot = np.zeros_like(z_top)
    top = np.stack([xx, yy, z_top], axis=-1).reshape(-1, 3)
    bot = np.stack([xx, yy, z_bot], axis=-1).reshape(-1, 3)
    n = h * w
    verts = np.vstack([top, bot])

    ii, jj = np.meshgrid(np.arange(h - 1), np.arange(w - 1), indexing="ij")
    tl = (ii * w + jj).ravel()
    tr = tl + 1
    bl = tl + w
    br = bl + 1
    top_f = np.column_stack([tl, tr, br, tl, br, bl]).reshape(-1, 3)
    bot_f = np.column_stack([n + tl, n + br, n + tr, n + tl, n + bl, n + br]).reshape(-1, 3)

    def wall(top_idx, bot_idx):
        t0, t1 = top_idx[:-1], top_idx[1:]
        b0, b1 = bot_idx[:-1], bot_idx[1:]
        return np.column_stack([t0, t1, b1, t0, b1, b0]).reshape(-1, 3)

    south = wall(np.arange(0, w)[::-1], np.arange(n, n + w)[::-1])
    north = wall(np.arange((h - 1) * w, h * w), np.arange(n + (h - 1) * w, 2 * n))
    west = wall(np.arange(h) * w, n + np.arange(h) * w)
    east = wall((np.arange(h) * w + (w - 1))[::-1], (n + np.arange(h) * w + (w - 1))[::-1])

    faces = np.vstack([top_f, bot_f, south, north, west, east])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: heightmap_to_stl.py input.png output.stl", file=sys.stderr)
        return 1
    arr = np.array(Image.open(sys.argv[1]).convert("L"), dtype=np.float32)
    heights = arr / 255.0 * MAX_HEIGHT_MM
    mesh = heightmap_to_mesh(heights)
    mesh.export(sys.argv[2])
    print(
        f"wrote {sys.argv[2]}  "
        f"verts={len(mesh.vertices)}  faces={len(mesh.faces)}  "
        f"watertight={mesh.is_watertight}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
