"""Entry point for `--mode building` (Step 12-1 stub).

The CLI calls `run(settings)` after merging --config + CLI args. Later
steps will:
  - Step 12-2: load a hand-written JSON spec and emit wall boxes
  - Step 12-6+: pipe an image through OpenCV + Claude API to build that spec
  - Step 12-7+: assemble openings / floors / roof / furniture

For now we only raise NotImplementedError so the new mode is visibly
gated without breaking the dam pipeline.
"""


def run(settings: dict) -> None:
    raise NotImplementedError(
        "Step 12-2 以降で実装します (現状は --mode building の骨格のみ)"
    )
