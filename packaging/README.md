# Packaging (Workstream J)

Windows distribution for DeckForge 0.1.0 (MIT).

- `deckforge.spec` — PyInstaller spec. One console executable `deckforge.exe`
  built from the existing `[project.scripts]` entry
  `deckforge_core.cli.app:main`. `dist/` and `build/` are git-ignored.
- `deckforge.iss` — Inno Setup script. Produces `deckforge-setup.exe`, which
  installs to `%LocalAppData%\Programs\DeckForge` and adds Start Menu shortcuts.

This directory is deliberately **not** a Python package (no `__init__.py`): a
`packaging/` package on the repository root shadows the `packaging`
distribution on `sys.path` and breaks `python -m PyInstaller`, pip build
backends and anything else that imports it.

## Build

```powershell
# 1. freeze the executable (run from the repository root)
.\.venv\Scripts\python.exe -m pip install pyinstaller
pyinstaller --noconfirm --clean packaging\deckforge.spec   # -> dist\deckforge.exe

# 2. build the installer (needs Inno Setup 6 on PATH: iscc.exe)
iscc packaging\deckforge.iss                              # -> dist\deckforge-setup.exe
```

`deckforge-setup.exe` bundles the frozen exe, so the installer is produced from
`dist\deckforge.exe` (step 1) and must be run first.
