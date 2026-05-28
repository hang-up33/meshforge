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
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

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
        return

    raw = uploaded.getvalue()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as e:
        st.error(f"JSON のパースに失敗しました: {e}")
        return
    if not isinstance(spec, dict):
        st.error(f"JSON のトップレベルはオブジェクトである必要があります (got {type(spec).__name__})")
        return
    if spec.get("schema_version") != 1:
        st.error(
            f"building JSON: schema_version must be 1, got {spec.get('schema_version')!r}"
        )
        return

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

    download_name = Path(uploaded.name).with_suffix(".stl").name
    st.success(summary(mesh, download_name))
    stl_bytes = serialize(mesh)
    _render_stl_result(stl_bytes, download_name, preview_key="building-stl-preview")


tab_dam, tab_building = st.tabs(["Heightmap (dam)", "Building"])
with tab_dam:
    _render_dam_tab()
with tab_building:
    _render_building_tab()
