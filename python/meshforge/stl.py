"""Binary STL output."""

import trimesh


def write_stl(mesh: trimesh.Trimesh, path: str) -> None:
    # trimesh picks binary STL automatically from the .stl extension.
    mesh.export(path)


def serialize(mesh: trimesh.Trimesh) -> bytes:
    # In-memory binary STL bytes, for callers that need to stream the output
    # (e.g. the Streamlit UI's download button) without touching the disk.
    return mesh.export(file_type="stl")


def summary(mesh: trimesh.Trimesh, path: str) -> str:
    return (
        f"wrote {path}  "
        f"verts={len(mesh.vertices)}  faces={len(mesh.faces)}  "
        f"watertight={mesh.is_watertight}"
    )
