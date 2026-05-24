"""PNG -> binary STL via simple heightmap extrusion (meshforge Step 1-2)."""

import argparse
import sys

import numpy as np
import trimesh
from PIL import Image

PIXEL_MM = 0.5         # each input pixel is a PIXEL_MM × PIXEL_MM cell in X/Y
MAX_HEIGHT_MM = 10.0   # brightness 255 -> 10 mm tall
BASE_MM = 1.0          # solid base thickness


def heightmap_to_mesh(heights: np.ndarray) -> trimesh.Trimesh:
    # Treat each pixel as a PIXEL_MM × PIXEL_MM cell. Vertices sit at cell
    # corners, so a W×H pixel image becomes a mesh spanning exactly
    # W*PIXEL_MM × H*PIXEL_MM (e.g. 64 px @ 0.5 mm/px -> 32.0 mm, not 31.5).
    # Corner heights are the 2x2 average of the (edge-padded) pixel grid,
    # which also makes a 1×1 input a single valid cell instead of a
    # degenerate wall-only mesh.
    if heights.ndim != 2 or heights.size == 0:
        raise ValueError(f"heights must be a non-empty 2D array, got shape={heights.shape}")
    # Promote before the 2x2 sum so a uint8 input (e.g. raw PIL array passed
    # straight to this function) doesn't overflow into garbage heights.
    heights = np.asarray(heights, dtype=np.float64)
    padded = np.pad(heights, 1, mode="edge")
    corners = (padded[:-1, :-1] + padded[:-1, 1:] + padded[1:, :-1] + padded[1:, 1:]) / 4.0
    h, w = corners.shape  # (H+1, W+1)
    xs = np.arange(w) * PIXEL_MM
    ys = np.arange(h) * PIXEL_MM
    xx, yy = np.meshgrid(xs, ys)
    z_top = corners + BASE_MM
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
    parser = argparse.ArgumentParser(
        description="PNG -> binary STL via simple heightmap extrusion",
    )
    parser.add_argument("input", help="input PNG path")
    parser.add_argument("output", help="output STL path")
    parser.add_argument(
        "--invert",
        action="store_true",
        help="invert brightness (use for black-wall / white-floor floorplans)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        metavar="N",
        help="binarise heights: pixels < N -> floor, pixels >= N -> full height (0-255)",
    )
    args = parser.parse_args()

    if args.threshold is not None and not 0 <= args.threshold <= 255:
        parser.error(f"--threshold must be in 0..255 (got {args.threshold})")

    arr = np.array(Image.open(args.input).convert("L"), dtype=np.float32)
    # Invert first so --threshold compares against the post-invert brightness;
    # for a black-wall floorplan the user expects "threshold = wall darkness",
    # not "threshold = floor brightness".
    if args.invert:
        arr = 255.0 - arr
    if args.threshold is not None:
        arr = np.where(arr >= args.threshold, 255.0, 0.0)
    heights = arr / 255.0 * MAX_HEIGHT_MM
    mesh = heightmap_to_mesh(heights)
    mesh.export(args.output)
    print(
        f"wrote {args.output}  "
        f"verts={len(mesh.vertices)}  faces={len(mesh.faces)}  "
        f"watertight={mesh.is_watertight}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
