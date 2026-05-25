"""PNG/PDF -> binary STL via simple heightmap extrusion (meshforge Step 1-4)."""

import argparse
import json
import sys

import numpy as np
import trimesh
from PIL import Image

# Defaults for the 3D extrusion. Geometry constants live here so they can be
# overridden via --config JSON (Step 4) without editing the script.
DEFAULTS = {
    "invert": False,
    "threshold": None,
    "dpi": 150.0,
    "pixel_mm": 0.5,        # each input pixel is a pixel_mm × pixel_mm cell in X/Y
    "max_height_mm": 10.0,  # brightness 255 -> this many mm tall
    "base_mm": 1.0,         # solid base thickness
}

SETTINGS_KEYS = ["input", "output", *DEFAULTS]


def heightmap_to_mesh(heights: np.ndarray, pixel_mm: float, base_mm: float) -> trimesh.Trimesh:
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


def rasterize_pdf(path: str, dpi: float) -> Image.Image:
    # PyMuPDF is only required for PDF input; importing lazily keeps PNG-only
    # users (and Step 1/2 environments) from needing it installed.
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PNG/PDF -> binary STL heightmap.")
    # Positionals are optional so they can come from --config instead. argparse
    # SUPPRESS keeps unset flags out of the namespace, so we can tell which
    # values the user actually typed vs. defaults — needed to merge CLI on top
    # of --config without clobbering JSON values with argparse fallbacks.
    p.add_argument("input", nargs="?", default=None)
    p.add_argument("output", nargs="?", default=None)
    p.add_argument(
        "--invert",
        action="store_true",
        default=argparse.SUPPRESS,
        help="invert brightness so dark pixels become tall (e.g. floor-plan walls)",
    )
    p.add_argument(
        "--threshold",
        type=int,
        default=argparse.SUPPRESS,
        metavar="N",
        help="binarize at this 0..255 value (>= N -> max height, else flat)",
    )
    p.add_argument(
        "--dpi",
        type=float,
        default=argparse.SUPPRESS,
        metavar="D",
        help="rasterize PDF input at this DPI (ignored for PNG); default 150",
    )
    p.add_argument(
        "--pixel-mm",
        dest="pixel_mm",
        type=float,
        default=argparse.SUPPRESS,
        metavar="V",
        help="cell size in mm per input pixel; default 0.5",
    )
    p.add_argument(
        "--max-height-mm",
        dest="max_height_mm",
        type=float,
        default=argparse.SUPPRESS,
        metavar="V",
        help="height in mm for brightness 255; default 10.0",
    )
    p.add_argument(
        "--base-mm",
        dest="base_mm",
        type=float,
        default=argparse.SUPPRESS,
        metavar="V",
        help="solid base thickness in mm; default 1.0",
    )
    p.add_argument(
        "--config",
        default=None,
        metavar="FILE",
        help="read settings from JSON (CLI args still win over JSON values)",
    )
    p.add_argument(
        "--save-config",
        dest="save_config",
        default=None,
        metavar="FILE",
        help="write the effective settings to JSON after producing the STL",
    )
    return p.parse_args(argv)


def resolve_settings(args: argparse.Namespace) -> dict:
    # With --config, exactly one positional is ambiguous (argparse always
    # binds the first to `input`, so `script.py out.stl --config c.json`
    # silently overrides input instead of output).
    if args.config and (args.input is None) != (args.output is None):
        raise ValueError("with --config, pass both positional input and output, or neither")
    s: dict = {"input": None, "output": None, **DEFAULTS}
    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError(f"{args.config}: expected a JSON object at top level")
        unknown = sorted(set(cfg) - set(SETTINGS_KEYS))
        if unknown:
            raise ValueError(f"{args.config}: unknown keys {unknown}")
        s.update(cfg)
    a = vars(args)
    # SUPPRESS means absent-from-namespace; positionals (input/output) are
    # always present but None when omitted. Either way, only override when
    # the user actually provided a value on the CLI.
    for k in SETTINGS_KEYS:
        if k in a and a[k] is not None:
            s[k] = a[k]
    return s


def validate(s: dict) -> str | None:
    if not s["input"] or not s["output"]:
        return "input and output are required (positional args or via --config)"
    t = s["threshold"]
    if t is not None and not 0 <= t <= 255:
        return "threshold must be in 0..255"
    if s["input"].lower().endswith(".pdf") and s["dpi"] <= 0:
        return "dpi must be positive"
    if s["pixel_mm"] <= 0:
        return "pixel_mm must be positive"
    if s["max_height_mm"] <= 0:
        return "max_height_mm must be positive"
    if s["base_mm"] <= 0:
        return "base_mm must be positive"
    return None


def save_config(path: str, settings: dict) -> None:
    out = {k: settings[k] for k in SETTINGS_KEYS}
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def main() -> int:
    args = parse_args(sys.argv[1:])
    try:
        settings = resolve_settings(args)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1
    err = validate(settings)
    if err:
        print(err, file=sys.stderr)
        return 1

    arr = np.array(load_grayscale(settings["input"], settings["dpi"]), dtype=np.float32)
    if settings["invert"]:
        arr = 255.0 - arr
    if settings["threshold"] is not None:
        arr = np.where(arr >= settings["threshold"], 255.0, 0.0)
    heights = arr / 255.0 * settings["max_height_mm"]
    mesh = heightmap_to_mesh(heights, settings["pixel_mm"], settings["base_mm"])
    mesh.export(settings["output"])
    print(
        f"wrote {settings['output']}  "
        f"verts={len(mesh.vertices)}  faces={len(mesh.faces)}  "
        f"watertight={mesh.is_watertight}"
    )
    if args.save_config:
        save_config(args.save_config, settings)
        print(f"wrote {args.save_config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
