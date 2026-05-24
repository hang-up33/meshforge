"""Generate a tiny sample PNG so heightmap_to_stl.py has something to chew on."""

import sys

import numpy as np
from PIL import Image


def main(path: str) -> None:
    size = 64
    y, x = np.ogrid[:size, :size]
    cx = cy = size // 2
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    bump = np.clip(255 * (1 - r / (size * 0.4)), 0, 255).astype(np.uint8)
    Image.fromarray(bump, mode="L").save(path)
    print(f"wrote {path}  ({size}x{size}, dome)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "samples/dome.png")
