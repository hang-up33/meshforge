"""CLI surface: argparse subcommands, --config merging, validation."""

import argparse
import json
import math
import sys

from meshforge.heightmap import load_grayscale, to_heights
from meshforge.mesh import heightmap_to_mesh
from meshforge.stl import summary, write_stl

# Defaults for the 3D extrusion. Geometry constants live here so they can be
# overridden via --config JSON (Step 4) without editing the script.
DEFAULTS = {
    "invert": False,
    "threshold": None,
    "dpi": 150.0,
    "pixel_mm": 0.5,        # each input pixel is a pixel_mm × pixel_mm cell in X/Y
    "max_height_mm": 10.0,  # brightness 255 -> this many mm tall
    "base_mm": 1.0,         # solid base thickness
    # Step 11: 多段階の高さレイヤー。明度バンドごとに固定高を返す形に
    # 拡張可能。None なら従来の threshold / max_height_mm 経路のまま。
    "layers": None,
}

SETTINGS_KEYS = ["input", "output", *DEFAULTS]

# JSON 由来の値はそのまま numeric 比較に流すと "128" のような文字列で
# TypeError になり、利用者から見ると原因不明のトレースバックになる。
# resolve_settings で先に型を弾けば validate() の前で config error として
# 返せる。bool は int の subclass なので、数値型キーに true/false が来た
# 場合と、boolean キーに 0/1 が来た場合の両方を別扱いしたい。
JSON_TYPES = {
    "input": "string",
    "output": "string",
    "invert": "boolean",
    "threshold": "integer or null",
    "dpi": "number",
    "pixel_mm": "number",
    "max_height_mm": "number",
    "base_mm": "number",
    "layers": "layer list or null",
}


def _matches_json_type(value, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer or null":
        return value is None or (isinstance(value, int) and not isinstance(value, bool))
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "layer list or null":
        return value is None or isinstance(value, list)
    raise AssertionError(f"unknown json type kind: {kind!r}")


def _validate_layers(layers: list) -> str | None:
    # bands は {"max": 0..255 int, "height_mm": positive finite number} の
    # 列で、max は昇順かつ各バンドが空でないこと（max が等しいと幅 0 で
    # 該当バンドが選ばれない）。最後のバンドが 255 を覆う必要は無い（
    # to_heights 側で clip するので最終バンドが上限超を吸収する）。
    if not layers:
        return "layers must be a non-empty list"
    prev_max: int | None = None
    for i, layer in enumerate(layers):
        if not isinstance(layer, dict):
            return f"layers[{i}] must be an object"
        keys = set(layer)
        if keys != {"max", "height_mm"}:
            return f"layers[{i}] must have exactly keys 'max' and 'height_mm', got {sorted(keys)}"
        m = layer["max"]
        h = layer["height_mm"]
        if not (isinstance(m, int) and not isinstance(m, bool)) or not 0 <= m <= 255:
            return f"layers[{i}].max must be an integer in 0..255"
        if not (isinstance(h, (int, float)) and not isinstance(h, bool)):
            return f"layers[{i}].height_mm must be a number"
        if not math.isfinite(h) or h < 0:
            return f"layers[{i}].height_mm must be finite and >= 0"
        if prev_max is not None and m <= prev_max:
            return f"layers[{i}].max ({m}) must be strictly greater than layers[{i-1}].max ({prev_max})"
        prev_max = m
    return None


def _add_convert_args(c: argparse.ArgumentParser) -> None:
    # Positionals are optional so they can come from --config instead. argparse
    # SUPPRESS keeps unset flags out of the namespace, so we can tell which
    # values the user actually typed vs. defaults — needed to merge CLI on top
    # of --config without clobbering JSON values with argparse fallbacks.
    c.add_argument("input", nargs="?", default=None)
    c.add_argument("output", nargs="?", default=None)
    # BooleanOptionalAction で --no-invert を生やしておかないと、JSON で
    # "invert": true を入れた利用者が CLI 一発で無効化する手段がなくなり、
    # --config と --invert の優先順位ルール（CLI 勝ち）が片方向にしか
    # 機能しなくなる。
    c.add_argument(
        "--invert",
        action=argparse.BooleanOptionalAction,
        default=argparse.SUPPRESS,
        help="invert brightness so dark pixels become tall (e.g. floor-plan walls); "
             "use --no-invert to override a JSON config that enabled it",
    )
    c.add_argument(
        "--threshold",
        type=int,
        default=argparse.SUPPRESS,
        metavar="N",
        help="binarize at this 0..255 value (>= N -> max height, else flat)",
    )
    c.add_argument(
        "--dpi",
        type=float,
        default=argparse.SUPPRESS,
        metavar="D",
        help="rasterize PDF input at this DPI (ignored for PNG); default 150",
    )
    c.add_argument(
        "--pixel-mm",
        dest="pixel_mm",
        type=float,
        default=argparse.SUPPRESS,
        metavar="V",
        help="cell size in mm per input pixel; default 0.5",
    )
    c.add_argument(
        "--max-height-mm",
        dest="max_height_mm",
        type=float,
        default=argparse.SUPPRESS,
        metavar="V",
        help="height in mm for brightness 255; default 10.0",
    )
    c.add_argument(
        "--base-mm",
        dest="base_mm",
        type=float,
        default=argparse.SUPPRESS,
        metavar="V",
        help="solid base thickness in mm; default 1.0",
    )
    c.add_argument(
        "--config",
        default=None,
        metavar="FILE",
        help="read settings from JSON (CLI args still win over JSON values)",
    )
    c.add_argument(
        "--save-config",
        dest="save_config",
        default=None,
        metavar="FILE",
        help="write the effective settings to JSON after producing the STL",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="meshforge",
        description="PNG/PDF -> binary STL heightmap.",
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    convert = sub.add_parser("convert", help="convert a PNG/PDF heightmap to binary STL")
    _add_convert_args(convert)
    convert.set_defaults(handler=cmd_convert)
    return p


def resolve_settings(args: argparse.Namespace) -> dict:
    # With --config, exactly one positional is ambiguous (argparse always
    # binds the first to `input`, so `meshforge convert out.stl --config c.json`
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
        for k, v in cfg.items():
            kind = JSON_TYPES[k]
            if not _matches_json_type(v, kind):
                raise ValueError(
                    f"{args.config}: {k!r} must be {kind}, got {type(v).__name__}"
                )
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
    # NaN / inf すり抜け防止: `nan > 0` も `nan <= 0` も False になるので
    # 単純な ">0" だけだと validate を素通りして NaN 座標のメッシュが
    # できる。json.load や float() は NaN/Infinity を受理するため
    # 数値キーは isfinite で先に弾く。
    pdf_input = s["input"].lower().endswith(".pdf")
    finite_positive = ["pixel_mm", "max_height_mm", "base_mm"] + (["dpi"] if pdf_input else [])
    for k in finite_positive:
        v = s[k]
        if not math.isfinite(v) or v <= 0:
            return f"{k} must be a positive finite number"
    layers = s["layers"]
    if layers is not None:
        # layers 指定時は threshold / max_height_mm を併用しても解釈が
        # 曖昧 (どちらの高さに従うか) なので、threshold は排他。
        # max_height_mm は default 値があり常に存在するため、CLI/JSON で
        # 明示指定されたかを区別できないので排他にはしない (layers 側が
        # 単純に勝つ)。
        if s["threshold"] is not None:
            return "layers と threshold は同時指定できません (どちらか片方にしてください)"
        err = _validate_layers(layers)
        if err:
            return err
    return None


def save_config(path: str, settings: dict) -> None:
    out = {k: settings[k] for k in SETTINGS_KEYS}
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def cmd_convert(args: argparse.Namespace) -> int:
    try:
        settings = resolve_settings(args)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1
    err = validate(settings)
    if err:
        print(err, file=sys.stderr)
        return 1

    image = load_grayscale(settings["input"], settings["dpi"])
    heights = to_heights(
        image,
        invert=settings["invert"],
        threshold=settings["threshold"],
        max_height_mm=settings["max_height_mm"],
        layers=settings["layers"],
    )
    mesh = heightmap_to_mesh(
        heights,
        pixel_mm=settings["pixel_mm"],
        base_mm=settings["base_mm"],
    )
    write_stl(mesh, settings["output"])
    print(summary(mesh, settings["output"]))
    if args.save_config:
        save_config(args.save_config, settings)
        print(f"wrote {args.save_config}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
