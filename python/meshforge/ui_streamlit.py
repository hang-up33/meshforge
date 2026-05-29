"""Streamlit UI for meshforge.

Run:
    .venv/bin/streamlit run python/meshforge/ui_streamlit.py

The UI is intentionally a thin wrapper around the same core pipeline that the
`python -m meshforge convert` CLI uses, so swapping the front end later (e.g.
to Avalonia / C# via subprocess) does not require touching heightmap/mesh/stl.

Step 12-10 で building モード用のタブを追加。dam (Heightmap) タブは Step 6〜9
の挙動を維持。building タブは中間 JSON をアップロードして
`building.assemble.build_mesh` を呼ぶだけの薄いラッパで、CLI と同じメッシュ
を返す (md5 一致)。

Step 12-13 で Building タブに「Source」radio を追加。"Upload JSON" は従来
通りの手書き / 既存 JSON 直接読み込み、"Extract from image" は PNG/PDF を
アップロードして `building.extract.extract_walls` を呼び中間 JSON を生成 →
同じ `build_mesh` フローへ流す。Extract 結果の JSON は別途ダウンロード可能。

Step 12-14 で "Extract from image" の結果を入力画像に重ねて表示する line
overlay を追加。`_render_extract_overlay` が PIL で grayscale 入力を RGB
化し、walls[] の `start`/`end` (px) を結ぶ赤線を描く。パラメータ
(threshold / min_length_mm / merge_*) の試行錯誤を画像で確認できる。
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

# 8 megapixel cap. A4 @ 300 DPI is ~8.7 Mpx, so anything beyond this is
# almost certainly too large for the 1 GB RAM limit on Streamlit Cloud
# (heightmap_to_mesh allocates ~30x the image bytes for verts + faces).
_MAX_PIXELS = 8_000_000

# Cap DPI at 600. PyMuPDF will happily rasterize at multi-thousand DPI and
# instantly OOM, so we clamp before the request reaches load_grayscale.
_MAX_DPI = 600.0

# Streamlit Community Cloud installs deps from requirements.txt but does not
# pip-install the meshforge package itself (Poetry can't see our src layout
# under `python/`). Add `python/` to sys.path so `import meshforge` resolves.
# Local `pip install -e .` keeps working — this insert is a no-op when the
# package is already importable from site-packages.
_PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

import streamlit as st
from streamlit_stl import stl_from_text

from meshforge.building.assemble import build_mesh
from meshforge.building.extract import extract_walls
from meshforge.cli import DEFAULTS
from meshforge.heightmap import load_grayscale, to_heights
from meshforge.mesh import heightmap_to_mesh
from meshforge.stl import serialize, summary


st.set_page_config(page_title="meshforge", layout="centered")
st.title("meshforge")
st.caption("PNG / PDF heightmap → 3D printable binary STL")

# Presets nudge the four most input-dependent parameters (invert, threshold
# usage + value, max_height_mm, base_mm). pixel_mm / dpi vary much less by
# input type so they stay on the form's current value.
_CUSTOM = "Custom (manual)"
PRESETS: dict[str, dict[str, object]] = {
    _CUSTOM: {},
    "Floor plan (dark walls on light background)": {
        "invert": True,
        "use_threshold": True,
        "threshold": 128,
        "max_height_mm": 10.0,
        "base_mm": 1.0,
    },
    "Logo / Text (light on dark)": {
        "invert": False,
        "use_threshold": True,
        "threshold": 128,
        "max_height_mm": 5.0,
        "base_mm": 2.0,
    },
    "Terrain / Depth map (grayscale gradient)": {
        "invert": False,
        "use_threshold": False,
        "threshold": 128,
        "max_height_mm": 15.0,
        "base_mm": 1.0,
    },
}

# Seed session_state once so the form widgets below can bind via `key=` and
# preset changes can overwrite these entries directly.
for k, v in {
    "invert": DEFAULTS["invert"],
    "use_threshold": False,
    "threshold": 128,
    "max_height_mm": DEFAULTS["max_height_mm"],
    "base_mm": DEFAULTS["base_mm"],
}.items():
    st.session_state.setdefault(k, v)


def _render_stl_result(stl_bytes: bytes, download_name: str, preview_key: str) -> None:
    """3D プレビュー + ダウンロードボタンの共通描画。dam / building の両タブで使う。"""
    st.subheader("3D preview")
    stl_from_text(
        text=stl_bytes,
        color="#bfbfbf",
        material="material",
        auto_rotate=False,
        opacity=1.0,
        height=500,
        key=preview_key,
    )
    st.download_button(
        "Download STL",
        data=stl_bytes,
        file_name=download_name,
        mime="model/stl",
        key=f"{preview_key}-download",
    )


def _render_dam_tab() -> None:
    uploaded = st.file_uploader(
        "Input file (PNG or PDF)",
        type=["png", "pdf"],
        help="PDF input rasterizes the first page via PyMuPDF (install with `pip install -e '.[pdf]'`).",
        key="dam-uploader",
    )

    # Detect PDF input + missing optional dep early, so the form below can stay
    # enabled for PNG re-uploads without the user having to clear the error.
    _pdf_uploaded = uploaded is not None and uploaded.name.lower().endswith(".pdf")
    _pymupdf_available = importlib.util.find_spec("fitz") is not None
    if _pdf_uploaded and not _pymupdf_available:
        st.error(
            "PDF 入力には PyMuPDF が必要です。"
            "リポジトリ直下で `pip install -e '.[pdf]'` を実行してください。"
        )

    preset = st.selectbox(
        "Preset",
        list(PRESETS.keys()),
        key="preset",
        help="Pick a preset to fill the parameters below, then fine-tune as needed. 'Custom (manual)' keeps your current values.",
    )

    # When the user switches preset, overwrite session_state for the affected
    # widgets. Tracking `_applied_preset` prevents us from clobbering manual
    # tweaks on every rerun. Selecting Custom clears the tracker so picking the
    # *same* preset again after tweaks re-applies its values (otherwise the
    # tracker would still match and skip the overwrite).
    if preset == _CUSTOM:
        st.session_state["_applied_preset"] = None
    elif st.session_state.get("_applied_preset") != preset:
        for k, v in PRESETS[preset].items():
            st.session_state[k] = v
        st.session_state["_applied_preset"] = preset

    with st.form("convert"):
        st.subheader("Parameters")
        col_left, col_right = st.columns(2)
        with col_left:
            invert = st.checkbox(
                "Invert brightness (dark pixels become tall)",
                key="invert",
                help="Use for floor plans where walls are drawn dark on a light background.",
            )
            use_threshold = st.checkbox(
                "Binarize with threshold",
                key="use_threshold",
                help="Snap each pixel to either max height or flat. Kills grayscale anti-aliasing for clean vertical walls.",
            )
            threshold = st.slider(
                "Threshold (0..255)",
                min_value=0,
                max_value=255,
                key="threshold",
                disabled=not use_threshold,
            )
            dpi = st.number_input(
                "PDF DPI (PDF input only)",
                min_value=1.0,
                max_value=_MAX_DPI,
                value=DEFAULTS["dpi"],
                step=10.0,
                format="%.1f",
                help=f"Higher DPI = more detail but more memory. Capped at {_MAX_DPI:.0f} DPI to avoid OOM on Streamlit Cloud.",
            )
        with col_right:
            pixel_mm = st.number_input(
                "Pixel size (mm/px)",
                min_value=0.001,
                value=DEFAULTS["pixel_mm"],
                step=0.1,
                format="%.3f",
            )
            max_height_mm = st.number_input(
                "Max height (mm @ brightness 255)",
                min_value=0.01,
                key="max_height_mm",
                step=0.5,
                format="%.2f",
            )
            base_mm = st.number_input(
                "Base thickness (mm)",
                min_value=0.01,
                key="base_mm",
                step=0.1,
                format="%.2f",
            )

        submitted = st.form_submit_button(
            "Convert",
            type="primary",
            disabled=uploaded is None or (_pdf_uploaded and not _pymupdf_available),
        )

    if not (submitted and uploaded is not None):
        return

    # load_grayscale dispatches on the path suffix to decide PNG vs PDF, so we
    # round-trip through a tempfile that preserves the original extension
    # instead of refactoring the core API.
    suffix = Path(uploaded.name).suffix.lower() or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    # Sentinel: if any step below sets this to a value, render preview /
    # download. Using a name binding instead of nesting lets the cleanup in
    # `finally` run even when we bail early with a friendly error.
    stl_bytes: bytes | None = None
    mesh = None

    try:
        with st.spinner("Converting..."):
            try:
                image = load_grayscale(tmp_path, dpi)
            except ImportError:
                # Belt-and-suspenders: the form-level guard above should have
                # caught this, but if a user somehow bypasses it (e.g. PNG
                # with .pdf extension) we still want a clean message.
                st.error(
                    "PDF 入力には PyMuPDF が必要です。"
                    "`pip install -e '.[pdf]'` を実行してください。"
                )
            except FileNotFoundError as e:
                st.error(f"入力ファイルが見つかりません: {e}")
            except ValueError as e:
                # e.g. PDF with no pages (raised by rasterize_pdf).
                st.error(f"入力ファイルが処理できません: {e}")
            except Exception as e:
                # PIL.UnidentifiedImageError, corrupt PDF, password-protected
                # PDF, etc. Show the exception type so debugging is possible
                # without dumping a full traceback to the user.
                st.error(
                    f"入力ファイルを読み込めませんでした "
                    f"({type(e).__name__}: {e})。サポート形式は PNG / PDF です。"
                )
            else:
                pixels = image.width * image.height
                if pixels > _MAX_PIXELS:
                    st.error(
                        f"入力サイズが大きすぎます "
                        f"({image.width}×{image.height} = {pixels / 1_000_000:.1f} Mpx)。"
                        f"上限は {_MAX_PIXELS / 1_000_000:.0f} Mpx です。"
                        " DPI を下げるか、より小さい画像を使ってください。"
                    )
                else:
                    heights = to_heights(
                        image,
                        invert=invert,
                        threshold=threshold if use_threshold else None,
                        max_height_mm=max_height_mm,
                    )
                    mesh = heightmap_to_mesh(heights, pixel_mm=pixel_mm, base_mm=base_mm)
                    stl_bytes = serialize(mesh)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if stl_bytes is None or mesh is None:
        return

    download_name = Path(uploaded.name).with_suffix(".stl").name
    st.success(summary(mesh, download_name))
    _render_stl_result(stl_bytes, download_name, preview_key="stl-preview")


def _render_building_tab() -> None:
    source = st.radio(
        "Source",
        ["Upload JSON", "Extract from image"],
        horizontal=True,
        key="building-source",
        help="Upload JSON は手書き / 既存の building 中間 JSON を直接読む。"
             "Extract from image は PNG/PDF 平面図から walls[] を自動生成する。",
    )

    if source == "Upload JSON":
        result = _building_spec_from_json_upload()
    else:
        result = _building_spec_from_image_extract()
    if result is None:
        return
    spec, source_basename = result

    mesh = None
    try:
        with st.spinner("Building mesh..."):
            mesh = build_mesh(spec)
    except ValueError as e:
        # _validate_* / shapely is_valid 由来。CLI と同じメッセージを返す。
        st.error(f"building mode: {e}")
        return
    except ImportError as e:
        # shapely + mapbox_earcut (rooms / flat roof) や manifold3d (openings) 未導入。
        st.error(f"building mode: {e}")
        return

    download_name = Path(source_basename).with_suffix(".stl").name
    st.success(summary(mesh, download_name))
    stl_bytes = serialize(mesh)
    _render_stl_result(stl_bytes, download_name, preview_key="building-stl-preview")


def _building_spec_from_json_upload() -> tuple[dict, str] | None:
    st.markdown(
        "中間 JSON (`schema_version: 1`、`walls[]` 必須) をアップロードして"
        " STL を生成します。スキーマは "
        "[`docs/building-schema.md`](https://github.com/hang-up33/meshforge/blob/main/docs/building-schema.md)"
        " 参照。`samples/building_*.json` をそのままドロップすれば動きます。"
    )
    uploaded = st.file_uploader(
        "Building intermediate JSON",
        type=["json"],
        key="building-uploader",
        help="walls / rooms / openings / roof / furniture を含む中間 JSON。",
    )
    submitted = st.button(
        "Convert",
        type="primary",
        disabled=uploaded is None,
        key="building-convert",
    )
    if not (submitted and uploaded is not None):
        return None

    raw = uploaded.getvalue()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as e:
        st.error(f"JSON のパースに失敗しました: {e}")
        return None
    if not isinstance(spec, dict):
        st.error(f"JSON のトップレベルはオブジェクトである必要があります (got {type(spec).__name__})")
        return None
    if spec.get("schema_version") != 1:
        st.error(
            f"building JSON: schema_version must be 1, got {spec.get('schema_version')!r}"
        )
        return None
    return spec, uploaded.name


_OVERLAY_MAX_SIDE_PX = 1600


def _render_extract_overlay(
    image_path: str, spec: dict, *, dpi: float
) -> Image.Image:
    """Draw walls[] center lines on the input image, return an RGB PIL Image.

    Reloads the input through `load_grayscale` so the overlay sits on exactly
    the same px grid that `extract_walls` operated on (same DPI rasterization
    for PDFs). walls[] の `start`/`end` は px なので、`scale_mm_per_px` を
    通さずそのまま PIL の coordinate system に渡せる。

    extract form は `--dpi` を 600 まで許可しており、A4 PDF を 600 DPI で
    入れると ~35 Mpx (RGB で 100 MB+) になる。`st.image` は PNG エンコードし
    てブラウザに送るので、Streamlit Cloud の 1 GB RAM 上限でフリーズ / OOM
    する。dam タブには 8 Mpx ガードがあるが extract 側にはない (Codex R2 P2)。
    overlay は全体把握が目的で精細さは要らないので、長辺 `_OVERLAY_MAX_SIDE_PX`
    px までに thumbnail してから線を描く。線座標も同じ scale で縮める。
    """
    gray = load_grayscale(image_path, dpi)
    longest = max(gray.size)
    scale = 1.0 if longest <= _OVERLAY_MAX_SIDE_PX else _OVERLAY_MAX_SIDE_PX / longest
    if scale < 1.0:
        gray = gray.resize(
            (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
            Image.LANCZOS,
        )
    rgb = gray.convert("RGB")
    draw = ImageDraw.Draw(rgb)
    # rooms[] を先に描く (青の細線で polygon outline) ので、後で重ねる赤い
    # walls 線が前景になる。Step 12-15 で `with_rooms=True` のとき walls の
    # 中心線と room polygon の辺がだいたい一致するため、walls が前景の方が
    # 自然 (青はちらっと見える程度で、検出された rooms 数が分かれば十分)。
    for room in spec.get("rooms", []):
        coords = [
            (float(x) * scale, float(y) * scale) for x, y in room["polygon"]
        ]
        if len(coords) >= 2:
            coords.append(coords[0])
            draw.line(coords, fill=(60, 140, 220), width=1)
    for wall in spec.get("walls", []):
        x1, y1 = wall["start"]
        x2, y2 = wall["end"]
        draw.line(
            [
                (float(x1) * scale, float(y1) * scale),
                (float(x2) * scale, float(y2) * scale),
            ],
            fill=(220, 50, 50),
            width=2,
        )
    return rgb


def _building_spec_from_image_extract() -> tuple[dict, str] | None:
    st.markdown(
        "PNG / PDF 平面図から `walls[]` を自動抽出して STL を生成します。"
        " CLI の `meshforge extract-walls` と同じパラメータが使えます。"
        " rooms / openings / roof / furniture は出さないので、必要なら抽出 JSON を"
        " ダウンロードして手で追記してください。"
    )
    uploaded = st.file_uploader(
        "Floor plan image (PNG or PDF)",
        type=["png", "pdf"],
        key="building-extract-uploader",
        help="PDF 入力時は `pip install -e '.[vision,pdf]'` が必要。",
    )

    with st.form("building-extract-form"):
        st.subheader("Extract parameters")
        col_left, col_right = st.columns(2)
        with col_left:
            pixel_mm = st.number_input(
                "pixel_mm (mm per source pixel)",
                min_value=0.001, value=0.5, step=0.1, format="%.3f",
                key="extract-pixel-mm",
            )
            invert = st.checkbox(
                "Invert brightness (default: dark walls on light bg)",
                value=True,
                key="extract-invert",
            )
            threshold = st.slider(
                "Binary threshold (0..255)",
                min_value=0, max_value=255, value=128,
                key="extract-threshold",
            )
            min_length_mm = st.number_input(
                "Min wall length (mm)",
                min_value=0.001, value=30.0, step=5.0, format="%.2f",
                key="extract-min-length",
            )
            dpi = st.number_input(
                "PDF DPI (PDF input only)",
                min_value=1.0, max_value=600.0, value=150.0, step=10.0, format="%.1f",
                key="extract-dpi",
            )
        with col_right:
            wall_thickness_mm = st.number_input(
                "Wall thickness (mm)",
                min_value=0.001, value=4.0, step=1.0, format="%.2f",
                key="extract-wall-thickness",
            )
            wall_height_mm = st.number_input(
                "Wall height (mm)",
                min_value=0.001, value=24.0, step=2.0, format="%.2f",
                key="extract-wall-height",
            )
            merge = st.checkbox(
                "Merge axis-aligned segments (Step 12-12)",
                value=True,
                key="extract-merge",
            )
            merge_distance_mm = st.number_input(
                "Merge: perpendicular distance (mm)",
                min_value=0.001, value=2.0, step=0.5, format="%.2f",
                key="extract-merge-distance",
                disabled=not merge,
            )
            merge_angle_deg = st.number_input(
                "Merge: angle tolerance (deg)",
                min_value=0.001, value=5.0, step=1.0, format="%.2f",
                key="extract-merge-angle",
                disabled=not merge,
            )
            merge_gap_mm = st.number_input(
                "Merge: axial gap tolerance (mm)",
                min_value=0.0, value=2.0, step=0.5, format="%.2f",
                key="extract-merge-gap",
                disabled=not merge,
            )
            with_rooms = st.checkbox(
                "Auto-extract rooms (Step 12-15)",
                value=False,
                key="extract-with-rooms",
                help="walls の閉路を shapely.polygonize で検出して rooms[] に "
                     "追加する。建てたあと床スラブが出る。",
            )
            room_floor_thickness_mm = st.number_input(
                "Room floor thickness (mm)",
                min_value=0.001, value=2.0, step=0.5, format="%.2f",
                key="extract-room-floor",
                disabled=not with_rooms,
            )
            room_snap_tol_px = st.number_input(
                "Room snap tolerance (px)",
                min_value=0.0, value=3.0, step=0.5, format="%.2f",
                key="extract-room-snap",
                disabled=not with_rooms,
                help="shapely.snap の strict `<` 判定なので、2 px gap には "
                     "3.0 が要る。Hough の端点不一致を吸収する。",
            )
        submitted = st.form_submit_button(
            "Extract & Build",
            type="primary",
            disabled=uploaded is None,
        )

    if not (submitted and uploaded is not None):
        return None

    # extract-walls は CLI と同じく load_grayscale を呼ぶので、拡張子を保持した
    # tempfile に書き出してから渡す。
    suffix = Path(uploaded.name).suffix.lower() or ".png"
    tmp_path: str | None = None
    spec: dict | None = None
    overlay_image: Image.Image | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        with st.spinner("Extracting walls..."):
            try:
                spec = extract_walls(
                    tmp_path,
                    dpi=dpi,
                    pixel_mm=pixel_mm,
                    threshold=threshold,
                    invert=invert,
                    min_length_mm=min_length_mm,
                    wall_thickness_mm=wall_thickness_mm,
                    wall_height_mm=wall_height_mm,
                    with_rooms=with_rooms,
                    room_floor_thickness_mm=room_floor_thickness_mm,
                    room_snap_tol_px=room_snap_tol_px,
                    merge=merge,
                    merge_distance_mm=merge_distance_mm,
                    merge_angle_deg=merge_angle_deg,
                    merge_gap_mm=merge_gap_mm,
                )
            except ValueError as e:
                # _validate_* / no segments detected / 検証エラー。
                st.error(f"extract-walls error: {e}")
                return None
            except ImportError as e:
                # opencv-python-headless 未導入時の lazy import 失敗。
                st.error(f"extract-walls error: {e}")
                return None
            except FileNotFoundError as e:
                st.error(f"入力ファイルが見つかりません: {e}")
                return None
            except Exception as e:
                # PIL.UnidentifiedImageError, 壊れた PDF, パスワード付き PDF など。
                # dam タブと同じく型名を添えて UI を継続させる。
                st.error(
                    f"入力ファイルを読み込めませんでした "
                    f"({type(e).__name__}: {e})。サポート形式は PNG / PDF です。"
                )
                return None
        # Step 12-14: render overlay while tmp_path is still alive.
        # load_grayscale を再呼び出ししても extract_walls 内と同じラスタライズ
        # 結果になる (DPI が同じため決定的) ので、px 座標も完全に一致する。
        overlay_image = _render_extract_overlay(tmp_path, spec, dpi=dpi)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    n_walls = len(spec.get("walls", []))
    n_rooms = len(spec.get("rooms", [])) if with_rooms else 0
    summary_msg = f"extracted walls={n_walls}"
    if with_rooms:
        summary_msg += f", rooms={n_rooms}"
    st.success(summary_msg)
    if overlay_image is not None:
        caption = f"Detected walls ({n_walls} segments)"
        if with_rooms:
            caption += f" + rooms ({n_rooms})"
        caption += " overlaid on input image"
        st.image(overlay_image, caption=caption, use_container_width=True)
    json_basename = Path(uploaded.name).with_suffix(".json").name
    st.download_button(
        "Download walls JSON",
        data=json.dumps(spec, indent=2) + "\n",
        file_name=json_basename,
        mime="application/json",
        key="extract-json-download",
    )
    return spec, uploaded.name


tab_dam, tab_building = st.tabs(["Heightmap (dam)", "Building"])
with tab_dam:
    _render_dam_tab()
with tab_building:
    _render_building_tab()
