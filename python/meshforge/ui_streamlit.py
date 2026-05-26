"""Streamlit UI for meshforge (Step 6).

Run:
    .venv/bin/streamlit run python/meshforge/ui_streamlit.py

The UI is intentionally a thin wrapper around the same core pipeline that the
`python -m meshforge convert` CLI uses, so swapping the front end later (e.g.
to Avalonia / C# via subprocess) does not require touching heightmap/mesh/stl.
"""

import sys
import tempfile
from pathlib import Path

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

from meshforge.cli import DEFAULTS
from meshforge.heightmap import load_grayscale, to_heights
from meshforge.mesh import heightmap_to_mesh
from meshforge.stl import serialize, summary


st.set_page_config(page_title="meshforge", layout="centered")
st.title("meshforge")
st.caption("PNG / PDF heightmap → 3D printable binary STL")

uploaded = st.file_uploader(
    "Input file (PNG or PDF)",
    type=["png", "pdf"],
    help="PDF input rasterizes the first page via PyMuPDF (install with `pip install -e '.[pdf]'`).",
)

with st.form("convert"):
    st.subheader("Parameters")
    col_left, col_right = st.columns(2)
    with col_left:
        invert = st.checkbox(
            "Invert brightness (dark pixels become tall)",
            value=DEFAULTS["invert"],
            help="Use for floor plans where walls are drawn dark on a light background.",
        )
        use_threshold = st.checkbox(
            "Binarize with threshold",
            value=False,
            help="Snap each pixel to either max height or flat. Kills grayscale anti-aliasing for clean vertical walls.",
        )
        threshold = st.slider(
            "Threshold (0..255)",
            min_value=0,
            max_value=255,
            value=128,
            disabled=not use_threshold,
        )
        dpi = st.number_input(
            "PDF DPI (PDF input only)",
            min_value=1.0,
            value=DEFAULTS["dpi"],
            step=10.0,
            format="%.1f",
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
            value=DEFAULTS["max_height_mm"],
            step=0.5,
            format="%.2f",
        )
        base_mm = st.number_input(
            "Base thickness (mm)",
            min_value=0.01,
            value=DEFAULTS["base_mm"],
            step=0.1,
            format="%.2f",
        )

    submitted = st.form_submit_button(
        "Convert",
        type="primary",
        disabled=uploaded is None,
    )

if submitted and uploaded is not None:
    # load_grayscale dispatches on the path suffix to decide PNG vs PDF, so we
    # round-trip through a tempfile that preserves the original extension
    # instead of refactoring the core API.
    suffix = Path(uploaded.name).suffix.lower() or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    try:
        with st.spinner("Converting..."):
            image = load_grayscale(tmp_path, dpi)
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

    download_name = Path(uploaded.name).with_suffix(".stl").name
    st.success(summary(mesh, download_name))

    st.subheader("3D preview")
    stl_from_text(
        text=stl_bytes,
        color="#bfbfbf",
        material="material",
        auto_rotate=False,
        opacity=1.0,
        height=500,
        key="stl-preview",
    )

    st.download_button(
        "Download STL",
        data=stl_bytes,
        file_name=download_name,
        mime="model/stl",
    )
