"""Concrete slide renderers for QA previews.

PowerPoint COM gives the truest rendering on Windows when PowerPoint and the
full ``pywin32`` package are installed; LibreOffice headless is the fallback.
Both backends degrade gracefully: per-slide failures are captured in
:attr:`RenderedSlide.error` and a missing renderer simply returns error entries
so downstream QA never crashes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from deckforge_core.logging_util import get_logger
from deckforge_core.providers.render import (
    RenderBackend,
    RenderedSlide,
    SlideRenderer,
    libreoffice_available,
    powerpoint_com_available,
)

log = get_logger("deckforge.qa.renderers")


def _resolve_slide_numbers(pptx_path, slides: Optional[list[int]]) -> list[int]:
    """1-based slide numbers to render (all, or the requested subset)."""
    path = Path(pptx_path)
    if not path.exists():
        return [1]
    from pptx import Presentation

    try:
        presentation = Presentation(str(path))
    except Exception:
        return [1]
    count = len(presentation.slides) or 1
    numbers = list(range(1, count + 1))
    if slides:
        wanted = set(slides)
        numbers = [n for n in numbers if n in wanted]
    return numbers or [1]


def _error_slides(numbers: list[int], message: str) -> list[RenderedSlide]:
    return [
        RenderedSlide(number=n, image_path="", error=message) for n in numbers
    ]


def _find_soffice() -> Optional[Path]:
    """Locate LibreOffice's ``soffice`` executable (PATH + known Windows dirs)."""
    for candidate in shutil.which("soffice"), shutil.which("libreoffice"):
        if candidate:
            return Path(candidate)
    for candidate in (
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
        Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    ):
        if candidate.exists():
            return candidate
    return None


class PowerPointCOMRenderer(SlideRenderer):
    """Render slides to PNG via PowerPoint's COM Automation API.

    COM automation can hard-crash the process (``RPC_E_DISCONNECTED``), so the
    work is always delegated to a subprocess worker
    (:mod:`deckforge_core.qa._com_worker`). A crash then takes down only the
    child; the host receives error entries via the manifest file.
    """

    name = "powerpoint-com"
    backend = RenderBackend.POWERPOINT_COM

    @staticmethod
    def available() -> bool:
        return powerpoint_com_available()

    def render(self, pptx_path, out_dir, *, slides=None, dpi=96):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        numbers = _resolve_slide_numbers(pptx_path, slides)
        if not self.available():
            return _error_slides(numbers, "PowerPoint COM renderer unavailable")

        try:
            import win32com.client  # noqa: F401
        except Exception as exc:
            return _error_slides(numbers, f"pywin32 not installed: {exc}")

        manifest_path = out_dir / "_com_manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()
        command = [
            sys.executable,
            "-m",
            "deckforge_core.qa._com_worker",
            str(pptx_path),
            str(out_dir),
            str(dpi),
            ",".join(str(n) for n in numbers),
            str(manifest_path),
        ]
        try:
            proc = subprocess.run(
                command, capture_output=True, timeout=300, cwd=os.getcwd()
            )
        except subprocess.TimeoutExpired:
            return _error_slides(numbers, "PowerPoint COM render timed out")
        if not manifest_path.exists():
            message = f"PowerPoint COM render crashed (exit {proc.returncode})"
            if proc.stderr:
                message += f": {proc.stderr.decode('utf-8', 'replace')[-400:]}"
            return _error_slides(numbers, message)
        try:
            payload = json.loads(manifest_path.read_bytes().decode("utf-8"))
            results = [RenderedSlide.model_validate(item) for item in payload]
        except Exception as exc:
            return _error_slides(numbers, f"bad render manifest: {exc}")
        for result in results:
            image = Path(result.image_path)
            if result.image_path and not image.exists():
                result.image_path = ""
                result.error = "worker produced no PNG on disk"
        return results

    def _render_com_inline(self, pptx_path, out_dir, *, slides=None, dpi=96):
        """COM work, run inside the worker subprocess. Returns ``RenderedSlide``s."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        numbers = _resolve_slide_numbers(pptx_path, slides)
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except Exception as exc:
            return _error_slides(numbers, f"pywin32 not installed: {exc}")

        app = None
        presentation = None
        co_initialized = False
        try:
            import pythoncom
            import win32com.client

            try:
                pythoncom.CoInitialize()
                co_initialized = True
            except Exception:
                co_initialized = False
            app = win32com.client.Dispatch("PowerPoint.Application")
            app.Visible = True
        except Exception as exc:
            return _error_slides(numbers, f"could not start PowerPoint COM: {exc}")

        try:
            try:
                presentation = app.Presentations.Open(str(pptx_path), ReadOnly=True)
            except Exception:
                presentation = _matching_open_presentation(app, pptx_path)
            if presentation is None:
                return _error_slides(
                    numbers,
                    f"could not open {Path(pptx_path).name} (file in use by PowerPoint?)",
                )

            width_px, height_px = self._export_size(presentation, dpi)
            results: list[RenderedSlide] = []
            for number in numbers:
                png_path = out_dir / f"slide_{number:03d}.png"
                try:
                    presentation.Slides(number).Export(
                        str(png_path), "PNG", width_px, height_px
                    )
                except Exception as exc:
                    results.append(
                        RenderedSlide(number=number, image_path="", error=str(exc))
                    )
                    continue
                results.append(
                    RenderedSlide(
                        number=number,
                        image_path=str(png_path),
                        width_px=width_px,
                        height_px=height_px,
                    )
                )
            return results
        finally:
            try:
                if presentation is not None:
                    presentation.Close()
            except Exception:
                pass
            try:
                if app is not None:
                    app.Quit()
            except Exception:
                pass
            if co_initialized:
                try:
                    import pythoncom

                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    @staticmethod
    def _export_size(presentation, dpi: int) -> tuple[int, int]:
        """Pixel size for ``dpi`` from the slide's point dimensions."""
        try:
            width_pt = float(presentation.PageSetup.SlideWidth)
            height_pt = float(presentation.PageSetup.SlideHeight)
        except Exception:
            width_pt, height_pt = 13.333, 7.5  # 16:9 fallback
        return (
            max(1, int(round(width_pt / 72.0 * dpi))),
            max(1, int(round(height_pt / 72.0 * dpi))),
        )


def _matching_open_presentation(app, pptx_path: Path):
    """Point at an already-open presentation instead of failing on the Open call."""
    target = Path(pptx_path).resolve()
    try:
        for item in app.Presentations:
            try:
                if Path(item.FullName).resolve() == target:
                    return item
            except Exception:
                continue
    except Exception:
        pass
    return None


class LibreOfficeRenderer(SlideRenderer):
    """Render slides to PNG via headless LibreOffice ``soffice``.

    ``soffice --convert-to png`` emits one PNG per slide named
    ``<deck>-<N>.png``; when it collapses to a single image (or fails) every
    slide reports an error entry instead.
    """

    name = "libreoffice"
    backend = RenderBackend.LIBREOFFICE

    @staticmethod
    def available() -> bool:
        return libreoffice_available()

    def render(self, pptx_path, out_dir, *, slides=None, dpi=96):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pptx_path = Path(pptx_path)
        numbers = _resolve_slide_numbers(pptx_path, slides)

        soffice = _find_soffice()
        if soffice is None:
            return _error_slides(numbers, "LibreOffice not installed (soffice not found)")

        work = out_dir / "_soffice_png"
        work.mkdir(parents=True, exist_ok=True)
        command = [
            str(soffice),
            "--headless",
            "--convert-to",
            "png",
            "--outdir",
            str(work),
            str(pptx_path),
        ]
        try:
            proc = subprocess.run(command, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            return _error_slides(numbers, "soffice conversion timed out")
        if proc.returncode != 0:
            return _error_slides(numbers, f"soffice exited with code {proc.returncode}")

        by_index: dict[int, Path] = {}
        for png_file in work.glob("*.png"):
            index = _png_index(png_file)
            if index:
                by_index[index] = png_file

        if len(by_index) == 1 and len(numbers) > 1:
            return _error_slides(
                numbers,
                "LibreOffice exported a single PNG; per-slide export is not "
                "available without a PDF rasteriser",
            )

        results: list[RenderedSlide] = []
        for number in numbers:
            source = by_index.get(number)
            if source is None and len(by_index) == 1:
                source = next(iter(by_index.values()))
            if source is None:
                results.append(
                    RenderedSlide(
                        number=number, image_path="", error="no PNG produced for this slide"
                    )
                )
                continue
            target = out_dir / f"slide_{number:03d}.png"
            target.write_bytes(source.read_bytes())
            results.append(RenderedSlide(number=number, image_path=str(target)))
        return results


def _png_index(path: Path) -> Optional[int]:
    """Trailing ``-N`` of ``<deck>-N.png`` -> slide number N (1-based)."""
    match = re.search(r"-(\d+)$", path.stem)
    return int(match.group(1)) if match else None
