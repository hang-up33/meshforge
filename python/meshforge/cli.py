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
    # Step 12: 変換モード。"dam" は従来の明度→高さ押し出し。
    # "building" は平面図を解釈して壁/床/屋根/家具を組み立てる新モード
    # (実装は Step 12-2 以降)。default は dam なので既存 JSON 互換。
    "mode": "dam",
}

MODES = ("dam", "building")

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
    "mode": "string",
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
        "--mode",
        choices=list(MODES),
        default=argparse.SUPPRESS,
        help="conversion mode: 'dam' (default) is the legacy heightmap extrusion; "
             "'building' interprets a floor plan into walls/floors/roof/furniture "
             "(Step 12+, gated until implemented).",
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


def _add_extract_walls_args(c: argparse.ArgumentParser) -> None:
    c.add_argument("input", help="input PNG / PDF floor plan")
    c.add_argument(
        "-o", "--output",
        default=None,
        metavar="FILE",
        help="write the building JSON here (default: stdout)",
    )
    c.add_argument(
        "--dpi", type=float, default=150.0, metavar="D",
        help="rasterize PDF input at this DPI (ignored for PNG); default 150",
    )
    c.add_argument(
        "--pixel-mm", dest="pixel_mm", type=float, default=1.0, metavar="V",
        help="mm per source pixel — emitted as scale_mm_per_px so walls.start/end "
             "remain in image px coords; default 1.0",
    )
    c.add_argument(
        "--threshold", type=int, default=128, metavar="N",
        help="binary threshold 0..255 after grayscale + optional invert; default 128",
    )
    c.add_argument(
        "--no-invert",
        action="store_false",
        dest="invert",
        help="skip the brightness invert step (use when walls are drawn light on dark)",
    )
    c.add_argument(
        "--min-length-mm", dest="min_length_mm", type=float, default=50.0, metavar="V",
        help="discard line segments shorter than this in mm; default 50",
    )
    c.add_argument(
        "--wall-thickness-mm", dest="wall_thickness_mm", type=float, default=150.0,
        metavar="V",
        help="thickness assigned to every emitted wall (mm); default 150",
    )
    c.add_argument(
        "--wall-height-mm", dest="wall_height_mm", type=float, default=2400.0,
        metavar="V",
        help="height assigned to every emitted wall (mm); default 2400",
    )
    # Step 12-12 line merge. デフォルト on で Hough が両 edge を別線として
    # 返す挙動を吸収する。--no-merge で生 Hough 出力に戻せる。
    c.add_argument(
        "--merge", action=argparse.BooleanOptionalAction, default=True,
        help="merge near-collinear axis-aligned segments (Step 12-12). "
             "default on; use --no-merge to keep raw Hough output (1 stroke = 2 walls).",
    )
    c.add_argument(
        "--merge-distance-mm", dest="merge_distance_mm", type=float,
        default=2.0, metavar="V",
        help="perpendicular distance tolerance for line merge (mm); default 2.0",
    )
    c.add_argument(
        "--merge-angle-deg", dest="merge_angle_deg", type=float,
        default=5.0, metavar="V",
        help="angle tolerance for axis-aligned merge in degrees; default 5.0",
    )
    c.add_argument(
        "--merge-gap-mm", dest="merge_gap_mm", type=float,
        default=2.0, metavar="V",
        help="axial gap tolerance (mm) — segments separated by more than this "
             "stay as separate walls, so door openings and adjacent rooms don't "
             "fuse into one wall; default 2.0 (set 0 to require overlap)",
    )
    c.add_argument(
        "--with-rooms", dest="with_rooms",
        action=argparse.BooleanOptionalAction, default=False,
        help="auto-detect rooms[] by polygonizing the wall network (Step 12-15). "
             "default off; needs shapely (in 'building' extra).",
    )
    c.add_argument(
        "--room-floor-thickness-mm", dest="room_floor_thickness_mm",
        type=float, default=2.0, metavar="V",
        help="floor slab thickness for auto-extracted rooms (mm); default 2.0. "
             "ignored without --with-rooms.",
    )
    c.add_argument(
        "--room-snap-tol-px", dest="room_snap_tol_px",
        type=float, default=3.0, metavar="V",
        help="endpoint snap tolerance in px for room polygonization; default 3.0. "
             "shapely.snap は strict `<` 判定なので、floor_plan_simple の "
             "中央壁の 2 px gap には 2.0 では足りず 3.0 が要る。Hough の端点 "
             "不一致を吸収するために必要 (0 にすると壁同士が完全に touch しない "
             "と閉路が見つからない)。ignored without --with-rooms.",
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
    extract = sub.add_parser(
        "extract-walls",
        help="extract walls[] from a PNG/PDF floor plan (Step 12-11; OpenCV)",
    )
    _add_extract_walls_args(extract)
    extract.set_defaults(handler=cmd_extract_walls)
    return p


def resolve_settings(args: argparse.Namespace) -> dict:
    s: dict = {"input": None, "output": None, **DEFAULTS}
    # building_spec は building モード時のみ非 None。SETTINGS_KEYS には含めない
    # ので save_config の出力には混ざらず、legacy roundtrip と独立。
    s["building_spec"] = None
    is_building_config = False
    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError(f"{args.config}: expected a JSON object at top level")
        # Building の中間 JSON は legacy heightmap 設定 JSON と完全に別形状
        # (walls / openings / rooms — docs/building-schema.md)。`schema_version`
        # の有無で二者を判別し、building 側は SETTINGS_KEYS 検証を迂回して
        # そのまま run_building へ渡す。これで --config 用フラグを二系統に
        # 分けずに済む。--mode dam + building JSON の組み合わせは曖昧なので
        # 明示的に拒否する (legacy 検証で謎エラーになるより先に潰す)。
        if "schema_version" in cfg:
            is_building_config = True
            cli_mode = getattr(args, "mode", None)
            if cli_mode is not None and cli_mode != "building":
                raise ValueError(
                    f"{args.config}: looks like a building JSON (has 'schema_version') "
                    f"but --mode {cli_mode} was specified; use --mode building or omit --mode"
                )
            s["mode"] = "building"
            s["building_spec"] = cfg
        else:
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
    if is_building_config:
        # building モードは入力画像を持たないので CLI は positional 1 個 (output) だけ
        # 受け取る。argparse は最初の positional を `input` に束縛するので、ここで
        # 詰め替える。`convert --config bld.json out.stl` → s["output"] = "out.stl"。
        if args.output is not None:
            raise ValueError(
                f"{args.config}: building mode takes only one positional (output STL); "
                f"got input + output"
            )
        if args.input is not None:
            s["output"] = args.input
    else:
        # With --config, exactly one positional is ambiguous (argparse always
        # binds the first to `input`, so `meshforge convert out.stl --config c.json`
        # silently overrides input instead of output).
        if args.config and (args.input is None) != (args.output is None):
            raise ValueError("with --config, pass both positional input and output, or neither")
    a = vars(args)
    # SUPPRESS means absent-from-namespace; positionals (input/output) are
    # always present but None when omitted. Either way, only override when
    # the user actually provided a value on the CLI.
    # building モードでは input/output は既に詰め替え済みなのでスキップ。
    for k in SETTINGS_KEYS:
        if is_building_config and k in ("input", "output"):
            continue
        if k in a and a[k] is not None:
            s[k] = a[k]
    return s


def validate(s: dict) -> str | None:
    if s["mode"] not in MODES:
        return f"mode must be one of {list(MODES)}, got {s['mode']!r}"
    if s["mode"] == "building":
        # building は --config の中間 JSON 駆動。schema_version マーカー検証 +
        # output STL パス必須までを CLI 側で見て、walls 以降のフィールド検証は
        # building/assemble.py 側 (中間 JSON の正本に近い場所) で担当する。
        spec = s.get("building_spec")
        if not spec:
            return "building mode requires --config <building.json> with 'schema_version'"
        v = spec.get("schema_version")
        if v != 1:
            return f"building JSON: schema_version must be 1, got {v!r}"
        if not s["output"]:
            return "building mode requires an output STL path (positional, e.g. 'meshforge convert --config b.json out.stl')"
        return None
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

    if settings["mode"] == "building":
        # Late import: the building pipeline pulls heavier optional deps
        # (opencv, anthropic, manifold3d) added in Step 12-3+. Keeping the
        # import lazy means `--mode dam` runs never touch them.
        from meshforge.building.assemble import run as run_building
        try:
            run_building(settings)
        except (NotImplementedError, ValueError, ImportError) as e:
            print(f"building mode: {e}", file=sys.stderr)
            return 1
        # --save-config roundtrip は legacy SETTINGS_KEYS 用で building schema
        # を書き戻せない。building の永続化は Step 12-3+ の責務として保留。
        return 0

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


def cmd_extract_walls(args: argparse.Namespace) -> int:
    # Lazy import: opencv is in the vision extra, dam-mode users never need it.
    from meshforge.building.extract import extract_walls

    try:
        spec = extract_walls(
            args.input,
            dpi=args.dpi,
            pixel_mm=args.pixel_mm,
            threshold=args.threshold,
            invert=args.invert,
            min_length_mm=args.min_length_mm,
            wall_thickness_mm=args.wall_thickness_mm,
            wall_height_mm=args.wall_height_mm,
            merge=args.merge,
            merge_distance_mm=args.merge_distance_mm,
            merge_angle_deg=args.merge_angle_deg,
            merge_gap_mm=args.merge_gap_mm,
            with_rooms=args.with_rooms,
            room_floor_thickness_mm=args.room_floor_thickness_mm,
            room_snap_tol_px=args.room_snap_tol_px,
        )
    except (OSError, ValueError, ImportError) as e:
        print(f"extract-walls error: {e}", file=sys.stderr)
        return 1

    payload = json.dumps(spec, indent=2) + "\n"
    if args.output:
        with open(args.output, "w") as f:
            f.write(payload)
        print(f"wrote {args.output}  walls={len(spec['walls'])}", file=sys.stderr)
    else:
        sys.stdout.write(payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
