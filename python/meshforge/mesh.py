"""Heightmap -> trimesh.Trimesh extrusion."""

import numpy as np
import trimesh


def heightmap_to_mesh(
    heights: np.ndarray,
    *,
    pixel_mm: float,
    base_mm: float,
) -> trimesh.Trimesh:
    # Treat each pixel as a pixel_mm × pixel_mm cell. Vertices sit at cell
    # corners, so a W×H pixel image becomes a mesh spanning exactly
    # W*pixel_mm × H*pixel_mm (e.g. 64 px @ 0.5 mm/px -> 32.0 mm, not 31.5).
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
    xs = np.arange(w) * pixel_mm
    ys = np.arange(h) * pixel_mm
    xx, yy = np.meshgrid(xs, ys)
    z_top = corners + base_mm
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
