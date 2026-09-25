"""PowerPoint COM render worker.

PowerPoint automation can crash the process hard (``RPC_E_DISCONNECTED``),
so all COM work happens in this subprocess. The parent
(:class:`~deckforge_core.qa.renderers.PowerPointCOMRenderer`) spawns the
module and reads the results back from a manifest JSON file; a crash then
kills only this child.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from deckforge_core.qa.renderers import PowerPointCOMRenderer


def main() -> int:
    pptx_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    dpi = int(sys.argv[3])
    numbers = [int(x) for x in sys.argv[4].split(",") if x]
    manifest_path = Path(sys.argv[5])

    renderer = PowerPointCOMRenderer()
    try:
        results = renderer._render_com_inline(
            pptx_path, out_dir, slides=numbers or None, dpi=dpi
        )
    except Exception as exc:  # pragma: no cover - best-effort last resort
        from deckforge_core.qa.renderers import _error_slides

        results = _error_slides(numbers or [1], f"worker error: {exc}")

    payload = [
        {
            "number": item.number,
            "image_path": item.image_path,
            "error": item.error,
            "width_px": item.width_px,
            "height_px": item.height_px,
        }
        for item in results
    ]
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
