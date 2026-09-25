"""PyInstaller spec for the DeckForge CLI (Workstream J).

Freeze the existing ``[project.scripts]`` console entry point
(``deckforge = deckforge_core.cli.app:main``) into a ``deckforge.exe``
console executable.

Build (from the repository root)::

    pyinstaller --noconfirm --clean packaging/deckforge.spec

Output: ``dist/deckforge/`` (``deckforge.exe`` + ``_internal/``) and the
intermediate ``build/deckforge/`` tree; both are git-ignored. Every path is
derived from ``SPECPATH``, so the spec produces the same build from any working
directory.

One-directory (``COLLECT``) rather than one-file, because DeckForge links numpy,
scikit-learn, Pillow, lxml and XlsxWriter: a one-file build was measured at
~5.4 s per launch (it re-extracts ~640 files to %TEMP% every run) against
~0.7 s for the one-directory build. The Inno Setup script
(``packaging/deckforge.iss``) installs the whole folder.

Scope: the CLI only. The PySide6 GUI is a separate in-flight workstream
(Phase 1I) and is excluded here - add a second, windowed ``EXE`` target once
``deckforge_core.gui.main`` is a real entry point.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ENTRY = ROOT / "deckforge_core" / "cli" / "app.py"

# deckforge_core imports most of its subpackages lazily (inside functions) and
# registers optional providers from bootstrap modules, so the module graph alone
# under-reports: pull the whole library in explicitly.
HIDDEN_IMPORTS = sorted(
    name
    for name in collect_submodules("deckforge_core")
    if not name.startswith("deckforge_core.gui")
)

EXCLUDES = [
    # dev / test tooling
    "pytest",
    "_pytest",
    "coverage",
    "IPython",
    "matplotlib",
    "notebook",
    "setuptools",
    "tkinter",
    # optional extras that are not runtime dependencies; their providers import
    # them lazily and degrade to "provider unavailable"
    "anthropic",
    "openai",
    "google",
    "chromadb",
    # GUI (Phase 1I) - PySide6 is ~400 MB and is not needed by the CLI
    "PySide6",
    "PySide6_Essentials",
    "PySide6_Addons",
    "shiboken6",
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="deckforge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="deckforge",
)
