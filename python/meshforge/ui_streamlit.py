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
通りの手書き / 既存 JSON 直接読み込み、"Extract from image" は PNG/JPEG/PDF を
アップロードして `building.extract.extract_walls` を呼び中間 JSON を生成 →
同じ `build_mesh` フローへ流す。Extract 結果の JSON は別途ダウンロード可能。

Step 12-14 で "Extract from image" の結果を入力画像に重ねて表示する line
overlay を追加。`_render_extract_overlay` が PIL で grayscale 入力を RGB
化し、walls[] の `start`/`end` (px) を結ぶ赤線を描く。パラメータ
(threshold / min_length_mm / merge_*) の試行錯誤を画像で確認できる。

Step 13-1a で "Upload JSON" の walls[] を `st.data_editor` の表で編集してから
`build_mesh` に流せるようにした (パラメトリック編集の最初のスライス)。
walls 以外のトップレベルキー (rooms / openings / roof / furniture) はそのまま
保持する。無編集なら float 正規化を挟んでも幾何は不変で、CLI 出力と md5 一致。
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw

# Downscale target for the dam tab. The mesh is one cell per pixel, so the STL
# size is set purely by pixel count: ~2 Mpx -> ~8M triangles -> ~400 MB STL,
# while ~8 Mpx already hits ~1.6 GB and OOMs the 1 GB Streamlit Cloud instance
# (the mesh arrays and the serialized STL bytes coexist during write). A photo
# turned into a relief needs far less than 8 Mpx anyway, so oversized raster
# input (e.g. a 12 Mpx iPhone JPEG) is downscaled to this via _downscale_to_fit
# rather than rejected.
_MAX_PIXELS = 2_000_000

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
from meshforge.heightmap import downsample_heights, load_grayscale, to_heights
from meshforge.mesh import heightmap_to_mesh
from meshforge.stl import serialize, summary


st.set_page_config(page_title="meshforge", layout="centered")
st.title("meshforge")
st.caption("PNG / JPEG / PDF の高さマップ → 3Dプリント用バイナリ STL")

# Presets nudge the four most input-dependent parameters (invert, threshold
# usage + value, max_height_mm, base_mm). pixel_mm / dpi vary much less by
# input type so they stay on the form's current value.
_CUSTOM = "カスタム (手動)"
PRESETS: dict[str, dict[str, object]] = {
    _CUSTOM: {},
    "間取り図（明るい背景に暗い壁）": {
        "invert": True,
        "use_threshold": True,
        "threshold": 128,
        "max_height_mm": 10.0,
        "base_mm": 1.0,
    },
    "ロゴ / 文字（暗い背景に明るい図）": {
        "invert": False,
        "use_threshold": True,
        "threshold": 128,
        "max_height_mm": 5.0,
        "base_mm": 2.0,
    },
    "地形 / 深度マップ（グレースケール階調）": {
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
    st.subheader("3Dプレビュー")
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
        "STL をダウンロード",
        data=stl_bytes,
        file_name=download_name,
        mime="model/stl",
        key=f"{preview_key}-download",
    )


def _downscale_to_fit(image: Image.Image, max_pixels: int) -> tuple[Image.Image, float]:
    """Shrink `image` isotropically so width*height <= max_pixels.

    Returns (image, scale) where scale is the linear shrink factor (<= 1.0);
    callers divide pixel_mm by it to keep the physical mesh size unchanged. The
    resize is isotropic, so the aspect ratio is preserved and that single scale
    restores both side lengths (to within sub-pixel rounding).

    iPhone photos are ~12 Mpx — over the cap — so without this the dam tab
    dead-ends on a "too large" error with no in-app way to recover.

    Raises ValueError when the input is too elongated to fit the cap without
    breaking the aspect ratio — i.e. its ratio exceeds ~max_pixels:1, so the
    short side would round below 1px. Distorting such a strip anisotropically
    would silently throw off the printed dimensions, so we reject it instead.
    No real photo or floor plan reaches a >2,000,000:1 ratio.
    """
    pixels = image.width * image.height
    if pixels <= max_pixels:
        return image, 1.0
    scale = (max_pixels / pixels) ** 0.5
    new_w = max(1, int(image.width * scale))
    new_h = max(1, int(image.height * scale))
    # int() only truncates down, so new_w*new_h exceeds the cap only when the
    # max(1, ...) above raised a side that rounded to 0 — meaning an isotropic
    # shrink can't fit the cap at all. Reject rather than distort.
    if new_w * new_h > max_pixels:
        raise ValueError(
            "アスペクト比が極端すぎて "
            f"{max_pixels / 1_000_000:.0f} Mpx 以内に縮小できません "
            f"({image.width}×{image.height})。"
        )
    resized = image.resize((new_w, new_h), Image.LANCZOS)
    # Derive the returned scale from the rounded *area* (geometric mean of the
    # two per-axis scales). With an isotropic shrink the two axis scales match,
    # so this equals either one; using the area keeps it exact under sub-pixel
    # rounding without favoring width over height.
    return resized, (new_w * new_h / pixels) ** 0.5


def _render_dam_tab() -> None:
    st.caption(
        "白黒画像（PNG / JPEG / PDF）の明るさを高さに変換して立体にします。"
        "ロゴ・地形・平面図の凹凸モデル向け。"
    )
    uploaded = st.file_uploader(
        "入力ファイル（PNG / JPEG / PDF）",
        type=["png", "jpg", "jpeg", "pdf"],
        help="PDF は PyMuPDF で1ページ目をラスタライズします（`pip install -e '.[pdf]'` で導入）。",
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
        "プリセット",
        list(PRESETS.keys()),
        key="preset",
        help="プリセットを選ぶと下のパラメータが埋まります。選んだ後の微調整も可能。「カスタム (手動)」は今の値を保持します。",
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
        st.subheader("パラメータ")
        col_left, col_right = st.columns(2)
        with col_left:
            invert = st.checkbox(
                "明暗を反転（暗いピクセルが高くなる）",
                key="invert",
                help="明るい背景に暗く描かれた壁の間取り図などで使います。",
            )
            use_threshold = st.checkbox(
                "しきい値で二値化",
                key="use_threshold",
                help="各ピクセルを最大高さか平坦のどちらかに振り分けます。グレースケールのアンチエイリアスを消して、垂直な壁にできます。",
            )
            threshold = st.slider(
                "しきい値 (0〜255)",
                min_value=0,
                max_value=255,
                key="threshold",
                disabled=not use_threshold,
            )
            dpi = st.number_input(
                "PDF DPI（PDF入力時のみ）",
                min_value=1.0,
                max_value=_MAX_DPI,
                value=DEFAULTS["dpi"],
                step=10.0,
                format="%.1f",
                help=f"DPI が高いほど精細ですがメモリを多く使います。Streamlit Cloud のOOM回避のため {_MAX_DPI:.0f} DPI が上限です。",
            )
        with col_right:
            pixel_mm = st.number_input(
                "ピクセルサイズ (mm/px)",
                min_value=0.001,
                value=DEFAULTS["pixel_mm"],
                step=0.1,
                format="%.3f",
            )
            max_height_mm = st.number_input(
                "最大高さ（mm・明度255のとき）",
                min_value=0.01,
                key="max_height_mm",
                step=0.5,
                format="%.2f",
            )
            base_mm = st.number_input(
                "土台の厚み (mm)",
                min_value=0.01,
                key="base_mm",
                step=0.1,
                format="%.2f",
            )
            max_triangles = st.number_input(
                "最大三角形数（スライサー対策）",
                min_value=0,
                value=DEFAULTS["max_triangles"],
                step=100_000,
                help="この数を超えるとハイトマップを自動で縮小し、物理サイズは保ったまま"
                     "三角形を減らします。Bambu Studio などが「三角形が多すぎる」と"
                     "拒否する場合に有効。0 で無制限。",
            )

        submitted = st.form_submit_button(
            "変換",
            type="primary",
            disabled=uploaded is None or (_pdf_uploaded and not _pymupdf_available),
        )

    if not (submitted and uploaded is not None):
        return

    # A positive budget below the 12-face minimum of a 1x1 mesh can't be honored
    # (downsample_heights raises on it), so bail early with a friendly message.
    if 0 < int(max_triangles) < 12:
        st.error("最大三角形数は 0（無制限）または 12 以上を指定してください。")
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
        with st.spinner("変換中..."):
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
                    f"({type(e).__name__}: {e})。サポート形式は PNG / JPEG / PDF です。"
                )
            else:
                # iPhone JPEGs (~12 Mpx) blow past _MAX_PIXELS. Rather than
                # dead-end, downscale to fit and bump pixel_mm by 1/scale so the
                # printed model keeps the same physical size — only surface
                # detail drops, which is unavoidable under the RAM cap anyway.
                orig_w, orig_h = image.width, image.height
                try:
                    image, scale = _downscale_to_fit(image, _MAX_PIXELS)
                except ValueError as e:
                    # Degenerate strip that can't fit the cap without distorting.
                    st.error(str(e))
                else:
                    effective_pixel_mm = pixel_mm / scale
                    if scale < 1.0:
                        st.info(
                            "メモリ節約のため入力を自動で縮小しました "
                            f"({orig_w}×{orig_h} = {orig_w * orig_h / 1_000_000:.1f} Mpx → "
                            f"{image.width}×{image.height} ≈ {_MAX_PIXELS / 1_000_000:.0f} Mpx)。"
                            " 物理サイズを保つため pixel_mm を "
                            f"{pixel_mm:.3f} → {effective_pixel_mm:.3f} に自動調整しています。"
                        )
                    heights = to_heights(
                        image,
                        invert=invert,
                        threshold=threshold if use_threshold else None,
                        max_height_mm=max_height_mm,
                    )
                    # Cap the triangle count so slicers (Bambu Studio etc.) don't
                    # reject the STL for being too dense. Downsampling here bumps
                    # the X/Y pixel sizes to keep the printed footprint unchanged.
                    pre_h, pre_w = heights.shape
                    heights, pixel_mm_x, pixel_mm_y = downsample_heights(
                        heights, pixel_mm=effective_pixel_mm, max_triangles=int(max_triangles)
                    )
                    if heights.shape != (pre_h, pre_w):
                        st.info(
                            "三角形数の上限のためハイトマップを縮小しました "
                            f"({pre_w}×{pre_h} → {heights.shape[1]}×{heights.shape[0]} px、"
                            f"約 {heights.shape[0] * heights.shape[1] * 4 / 1_000_000:.1f}M 三角形)。"
                            " 物理サイズは維持しています。上限は「最大三角形数」で調整できます。"
                        )
                    mesh = heightmap_to_mesh(
                        heights, pixel_mm=pixel_mm_x, base_mm=base_mm, pixel_mm_y=pixel_mm_y
                    )
                    stl_bytes = serialize(mesh)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if stl_bytes is None or mesh is None:
        return

    download_name = Path(uploaded.name).with_suffix(".stl").name
    st.success(summary(mesh, download_name))
    _render_stl_result(stl_bytes, download_name, preview_key="stl-preview")


def _render_building_tab() -> None:
    st.caption(
        "壁・部屋・開口部を持つ「編集できる建物モデル」から立体にします。"
        "間取り図の画像から壁を自動抽出することも可能。"
    )
    source = st.radio(
        "入力ソース",
        ["JSON をアップロード", "画像から抽出"],
        horizontal=True,
        key="building-source",
        help="「JSON をアップロード」は手書き / 既存の building 中間 JSON を直接読む。"
             "「画像から抽出」は PNG/JPEG/PDF 平面図から walls[] を自動生成する。",
    )

    if source == "JSON をアップロード":
        result = _building_spec_from_json_upload()
    else:
        result = _building_spec_from_image_extract()
    if result is None:
        return
    spec, source_basename = result

    mesh = None
    try:
        with st.spinner("メッシュを生成中..."):
            mesh = build_mesh(spec)
    except ValueError as e:
        # _validate_* / shapely is_valid 由来。CLI と同じメッセージを返す。
        st.error(f"建物モード: {e}")
        return
    except ImportError as e:
        # shapely + mapbox_earcut (rooms / flat roof) や manifold3d (openings) 未導入。
        st.error(f"建物モード: {e}")
        return

    download_name = Path(source_basename).with_suffix(".stl").name
    st.success(summary(mesh, download_name))
    stl_bytes = serialize(mesh)
    _render_stl_result(stl_bytes, download_name, preview_key="building-stl-preview")


# Step 13-1a: flatten the nested `start`/`end` points into scalar columns so
# `st.data_editor` can show one wall per row. build_mesh only reads start / end
# / thickness_mm / height_mm (+ optional label), so these columns round-trip the
# whole mesh-relevant payload.
_WALL_COLUMNS = [
    "label",
    "start_x",
    "start_y",
    "end_x",
    "end_y",
    "thickness_mm",
    "height_mm",
]
_WALL_NUMERIC_COLUMNS = _WALL_COLUMNS[1:]


def _walls_to_df(walls: list[dict]) -> pd.DataFrame:
    rows = []
    for w in walls:
        start = w.get("start", [0.0, 0.0])
        end = w.get("end", [0.0, 0.0])
        rows.append(
            {
                "label": w.get("label", ""),
                "start_x": float(start[0]),
                "start_y": float(start[1]),
                "end_x": float(end[0]),
                "end_y": float(end[1]),
                "thickness_mm": float(w.get("thickness_mm", 0.0)),
                "height_mm": float(w.get("height_mm", 0.0)),
            }
        )
    return pd.DataFrame(rows, columns=_WALL_COLUMNS)


def _df_to_walls(df: pd.DataFrame) -> list[dict]:
    # num_rows="dynamic" leaves a trailing all-blank row when the user clicks
    # "add" without filling it; drop rows where every numeric cell is missing.
    df = df.dropna(how="all", subset=_WALL_NUMERIC_COLUMNS)
    walls: list[dict] = []
    for _, r in df.iterrows():
        wall: dict = {
            "start": [float(r["start_x"]), float(r["start_y"])],
            "end": [float(r["end_x"]), float(r["end_y"])],
            "thickness_mm": float(r["thickness_mm"]),
            "height_mm": float(r["height_mm"]),
        }
        label = r["label"]
        if isinstance(label, str) and label.strip():
            wall["label"] = label
        walls.append(wall)
    return walls


def _building_spec_from_json_upload() -> tuple[dict, str] | None:
    st.markdown(
        "中間 JSON (`schema_version: 1`、`walls[]` 必須) をアップロードして"
        " STL を生成します。スキーマは "
        "[`docs/building-schema.md`](https://github.com/hang-up33/meshforge/blob/main/docs/building-schema.md)"
        " 参照。`samples/building_*.json` をそのままドロップすれば動きます。"
        " アップロード後は walls[] を下の表で編集してから「生成」できます"
        " (rooms / openings / roof / furniture はそのまま保持)。"
    )
    uploaded = st.file_uploader(
        "建物の中間 JSON",
        type=["json"],
        key="building-uploader",
        help="walls / rooms / openings / roof / furniture を含む中間 JSON。",
    )
    if uploaded is None:
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

    walls = spec.get("walls")
    if not isinstance(walls, list) or not walls:
        st.error(
            "building JSON: walls[] が非空のリストである必要があります"
            f" (got {type(walls).__name__})"
        )
        return None

    st.markdown(
        "**壁 (walls)** — 値の編集 / 行の追加・削除ができます。編集して「生成」を"
        " 押すと反映された STL が出ます。"
    )
    with st.form("building-json-edit"):
        edited = st.data_editor(
            _walls_to_df(walls),
            num_rows="dynamic",
            use_container_width=True,
            key="building-walls-editor",
            column_config={
                "label": st.column_config.TextColumn("label", help="任意のラベル (メッシュには焼かない)"),
                "start_x": st.column_config.NumberColumn("start_x"),
                "start_y": st.column_config.NumberColumn("start_y"),
                "end_x": st.column_config.NumberColumn("end_x"),
                "end_y": st.column_config.NumberColumn("end_y"),
                "thickness_mm": st.column_config.NumberColumn("thickness_mm", min_value=0.0),
                "height_mm": st.column_config.NumberColumn("height_mm", min_value=0.0),
            },
        )
        submitted = st.form_submit_button("生成", type="primary")
    if not submitted:
        return None

    spec = dict(spec)
    spec["walls"] = _df_to_walls(edited)
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
    する。dam タブには自動縮小ガードがあるが extract 側にはない (Codex R2 P2)。
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
        "PNG / JPEG / PDF 平面図から `walls[]` を自動抽出して STL を生成します。"
        " CLI の `meshforge extract-walls` と同じパラメータが使えます。"
        " rooms / openings / roof / furniture は出さないので、必要なら抽出 JSON を"
        " ダウンロードして手で追記してください。"
    )
    uploaded = st.file_uploader(
        "間取り図の画像（PNG / JPEG / PDF）",
        type=["png", "jpg", "jpeg", "pdf"],
        key="building-extract-uploader",
        help="PDF 入力時は `pip install -e '.[vision,pdf]'` が必要。",
    )

    with st.form("building-extract-form"):
        st.subheader("抽出パラメータ")
        col_left, col_right = st.columns(2)
        with col_left:
            pixel_mm = st.number_input(
                "pixel_mm（元画像1ピクセルあたりのmm）",
                min_value=0.001, value=0.5, step=0.1, format="%.3f",
                key="extract-pixel-mm",
            )
            invert = st.checkbox(
                "明暗を反転（既定: 明るい背景に暗い壁）",
                value=True,
                key="extract-invert",
            )
            threshold = st.slider(
                "二値化しきい値 (0〜255)",
                min_value=0, max_value=255, value=128,
                key="extract-threshold",
            )
            min_length_mm = st.number_input(
                "壁の最小長さ (mm)",
                min_value=0.001, value=30.0, step=5.0, format="%.2f",
                key="extract-min-length",
            )
            dpi = st.number_input(
                "PDF DPI（PDF入力時のみ）",
                min_value=1.0, max_value=600.0, value=150.0, step=10.0, format="%.1f",
                key="extract-dpi",
            )
        with col_right:
            wall_thickness_mm = st.number_input(
                "壁の厚み (mm)",
                min_value=0.001, value=4.0, step=1.0, format="%.2f",
                key="extract-wall-thickness",
            )
            wall_height_mm = st.number_input(
                "壁の高さ (mm)",
                min_value=0.001, value=24.0, step=2.0, format="%.2f",
                key="extract-wall-height",
            )
            merge = st.checkbox(
                "ほぼ一直線の線分を統合 (Step 12-12 / 12-16)",
                value=True,
                key="extract-merge",
            )
            merge_distance_mm = st.number_input(
                "統合: 垂直方向の距離 (mm)",
                min_value=0.001, value=2.0, step=0.5, format="%.2f",
                key="extract-merge-distance",
                disabled=not merge,
            )
            merge_angle_deg = st.number_input(
                "統合: 角度の許容差 (度)",
                min_value=0.001, value=5.0, step=1.0, format="%.2f",
                key="extract-merge-angle",
                disabled=not merge,
            )
            merge_gap_mm = st.number_input(
                "統合: 軸方向のギャップ許容差 (mm)",
                min_value=0.0, value=2.0, step=0.5, format="%.2f",
                key="extract-merge-gap",
                disabled=not merge,
            )
            with_rooms = st.checkbox(
                "部屋を自動抽出 (Step 12-15)",
                value=False,
                key="extract-with-rooms",
                help="walls の閉路を shapely.polygonize で検出して rooms[] に "
                     "追加する。建てたあと床スラブが出る。",
            )
            room_floor_thickness_mm = st.number_input(
                "床スラブの厚み (mm)",
                min_value=0.001, value=2.0, step=0.5, format="%.2f",
                key="extract-room-floor",
                disabled=not with_rooms,
            )
            room_snap_tol_px = st.number_input(
                "部屋スナップの許容差 (px)",
                min_value=0.0, value=3.0, step=0.5, format="%.2f",
                key="extract-room-snap",
                disabled=not with_rooms,
                help="shapely.snap の strict `<` 判定なので、2 px gap には "
                     "3.0 が要る。Hough の端点不一致を吸収する。",
            )
        submitted = st.form_submit_button(
            "抽出して生成",
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
        with st.spinner("壁を抽出中..."):
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
                st.error(f"壁抽出エラー: {e}")
                return None
            except ImportError as e:
                # opencv-python-headless 未導入時の lazy import 失敗。
                st.error(f"壁抽出エラー: {e}")
                return None
            except FileNotFoundError as e:
                st.error(f"入力ファイルが見つかりません: {e}")
                return None
            except Exception as e:
                # PIL.UnidentifiedImageError, 壊れた PDF, パスワード付き PDF など。
                # dam タブと同じく型名を添えて UI を継続させる。
                st.error(
                    f"入力ファイルを読み込めませんでした "
                    f"({type(e).__name__}: {e})。サポート形式は PNG / JPEG / PDF です。"
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
    summary_msg = f"壁 {n_walls} 本を抽出"
    if with_rooms:
        summary_msg += f"、部屋 {n_rooms} 室"
    st.success(summary_msg)
    if overlay_image is not None:
        caption = f"検出した壁 ({n_walls} 本)"
        if with_rooms:
            caption += f" ＋ 部屋 ({n_rooms} 室)"
        caption += " を入力画像に重ねて表示"
        st.image(overlay_image, caption=caption, use_container_width=True)
    json_basename = Path(uploaded.name).with_suffix(".json").name
    st.download_button(
        "壁 JSON をダウンロード",
        data=json.dumps(spec, indent=2) + "\n",
        file_name=json_basename,
        mime="application/json",
        key="extract-json-download",
    )
    return spec, uploaded.name


tab_dam, tab_building = st.tabs(["画像から立体化 (Heightmap)", "間取り図から建物 (Building)"])
with tab_dam:
    _render_dam_tab()
with tab_building:
    _render_building_tab()
