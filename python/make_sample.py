"""Generate a tiny sample PNG so heightmap_to_stl.py has something to chew on."""

import sys

import numpy as np
from PIL import Image


def dome(size: int = 64) -> np.ndarray:
    y, x = np.ogrid[:size, :size]
    cx = cy = size // 2
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    return np.clip(255 * (1 - r / (size * 0.4)), 0, 255).astype(np.uint8)


def floorplan(size: int = 64) -> np.ndarray:
    # Black walls on a white floor, mimicking the input shape of a real
    # architectural plan. Use heightmap_to_stl.py with --invert --threshold
    # to extrude the walls.
    img = np.full((size, size), 255, dtype=np.uint8)
    t = max(1, size // 32)
    img[:t, :] = 0
    img[-t:, :] = 0
    img[:, :t] = 0
    img[:, -t:] = 0
    mid = size // 2
    img[mid:mid + t, :] = 0
    door_x = size // 4
    door_w = size // 8
    img[mid:mid + t, door_x:door_x + door_w] = 255
    return img


KINDS = {"dome": dome, "floorplan": floorplan}


def main(path: str, kind: str = "dome") -> None:
    if kind not in KINDS:
        raise SystemExit(f"unknown kind: {kind!r} (choose from {sorted(KINDS)})")
    size = 64
    arr = KINDS[kind](size)
    Image.fromarray(arr, mode="L").save(path)
    print(f"wrote {path}  ({size}x{size}, {kind})")


if __name__ == "__main__":
    argv = sys.argv[1:]
    path = argv[0] if argv else "samples/dome.png"
    kind = argv[1] if len(argv) > 1 else "dome"
    main(path, kind)
