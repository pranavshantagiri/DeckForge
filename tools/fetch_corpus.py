"""Fetch a small set of permissively licensed real .pptx decks (Workstream J).

Complements the deterministic generator (``deckforge_core.tools.generate_corpus``,
DECISION D004): the test suite and CI always use the *generated* corpus, which
means these downloads are never on a test path. A developer can opt in to a
handful of real-world decks to sanity-check the learner against layouts the
generator does not produce.

Source: the Apache POI regression fixtures under ``test-data/slideshow`` -
Apache License 2.0, part of the POI project itself, a few hundred kilobytes in
total. Provenance and licence are written next to the decks
(``ATTRIBUTION.md``, ``_sources.json``) so a downloaded corpus is always
traceable. URLs track POI's ``trunk`` branch; if POI ever moves them, run with
``--only``/edit :data:`DEFAULT_FILES` - nothing else in the repo depends on them.

    python tools/fetch_corpus.py --list
    python tools/fetch_corpus.py
    python tools/fetch_corpus.py --only sample.pptx themes.pptx --force

Exits 0 when every requested deck landed, 1 when any download failed (which is
also what a machine with no network gets), 2 on bad usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - the repo depends on requests
    requests = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "corpus" / "external"

_BASE_URL = "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow"
_LICENSE = "Apache-2.0"
_LICENSE_URL = "https://github.com/apache/poi/blob/trunk/LICENSE"
_REPOSITORY = "https://github.com/apache/poi"
_MAX_BYTES = 64 * 1024 * 1024
_USER_AGENT = "DeckForge-fetch-corpus/0.1 (+https://github.com/pranavshantagiri/DeckForge)"

EXIT_OK = 0
EXIT_DOWNLOAD_FAILED = 1
EXIT_USAGE = 2


class FetchError(RuntimeError):
    """A single deck could not be fetched, verified or written."""


@dataclass(frozen=True)
class CorpusFile:
    id: str
    filename: str
    url: str
    note: str


# Kept deliberately small and stable: mixed layouts (shapes, tables, charts,
# SmartArt, slide masters, layouts) so the learner sees more than one geometry.
DEFAULT_FILES: tuple[CorpusFile, ...] = (
    CorpusFile("sample", "sample.pptx", f"{_BASE_URL}/sample.pptx",
               "general-purpose deck with mixed text and pictures"),
    CorpusFile("sampleshow", "SampleShow.pptx", f"{_BASE_URL}/SampleShow.pptx",
               "multi-slide show deck, one slide per layout"),
    CorpusFile("shapes", "shapes.pptx", f"{_BASE_URL}/shapes.pptx",
               "dense autoshape geometry"),
    CorpusFile("table_test", "table_test.pptx", f"{_BASE_URL}/table_test.pptx",
               "native tables with merged and multi-line cells"),
    CorpusFile("bar_chart", "bar-chart.pptx", f"{_BASE_URL}/bar-chart.pptx",
               "native chart with an embedded workbook"),
    CorpusFile("smartart", "SmartArt.pptx", f"{_BASE_URL}/SmartArt.pptx",
               "SmartArt diagrams and grouped shapes"),
    CorpusFile("layouts", "layouts.pptx", f"{_BASE_URL}/layouts.pptx",
               "slide layouts and placeholder inheritance"),
    CorpusFile("themes", "themes.pptx", f"{_BASE_URL}/themes.pptx",
               "theme-heavy deck, useful for style-profile learning"),
)


@dataclass
class Fetched:
    item: CorpusFile
    path: Path
    bytes_: int
    sha256: str
    from_cache: bool


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pptx(path: Path) -> None:
    """Raise :class:`FetchError` unless ``path`` is a real Open XML package."""
    if not zipfile.is_zipfile(path):
        raise FetchError(f"{path.name} is not a zip archive (bad download?)")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            broken = archive.testzip()
    except zipfile.BadZipFile as exc:
        raise FetchError(f"{path.name} is a corrupt zip archive: {exc}") from exc
    if "ppt/presentation.xml" not in names:
        raise FetchError(f"{path.name} has no ppt/presentation.xml (not a .pptx)")
    if broken is not None:
        raise FetchError(f"{path.name} has a corrupt entry: {broken}")


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def _fetch_bytes(item: CorpusFile, *, timeout: float, retries: int) -> bytes:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(
                item.url,
                timeout=timeout,
                stream=True,
                headers={"User-Agent": _USER_AGENT},
            ) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    total += len(chunk)
                    if total > _MAX_BYTES:
                        raise FetchError(f"{item.id}: download exceeds {_MAX_BYTES} bytes")
                    chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                raise FetchError(f"{item.id}: empty response body")
            return data
        except FetchError:
            raise
        except requests.RequestException as exc:
            last = exc
            if attempt < retries:
                time.sleep(min(2.0 * attempt, 5.0))
    raise FetchError(f"{item.id}: {type(last).__name__}: {last}")


def download(
    items: tuple[CorpusFile, ...],
    out_dir: Path,
    *,
    timeout: float = 30.0,
    retries: int = 2,
    force: bool = False,
) -> list[Fetched]:
    """Download every item into ``out_dir``; raises :class:`FetchError` on the
    first failure. Already-present, still-valid decks are kept unless ``force``."""
    if requests is None:  # pragma: no cover - guarded in main()
        raise FetchError("the 'requests' package is required; pip install -e .")

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Fetched] = []
    for item in items:
        target = out_dir / item.filename
        if target.is_file() and not force:
            try:
                verify_pptx(target)
            except FetchError:
                target.unlink()
            else:
                results.append(
                    Fetched(item, target, target.stat().st_size, _sha256(target), True)
                )
                print(f"  cached    {item.filename}")
                continue

        partial = target.with_name(target.name + ".part")
        try:
            data = _fetch_bytes(item, timeout=timeout, retries=retries)
            partial.write_bytes(data)
            verify_pptx(partial)
            partial.replace(target)
        except (FetchError, OSError) as exc:
            partial.unlink(missing_ok=True)
            raise FetchError(f"{item.id} ({item.url}): {exc}") from exc
        results.append(
            Fetched(item, target, target.stat().st_size, _sha256(target), False)
        )
        print(f"  fetched  {item.filename}  {target.stat().st_size:,} bytes")
    return results


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def write_manifest(out_dir: Path, results: list[Fetched]) -> Path:
    manifest = out_dir / "_sources.json"
    decks = []
    for fetched in results:
        item = fetched.item
        decks.append(
            {
                "id": item.id,
                "file": fetched.path.name,
                "url": item.url,
                "license": _LICENSE,
                "note": item.note,
                "bytes": fetched.bytes_,
                "sha256": fetched.sha256,
            }
        )
    payload = {
        "generator": "tools/fetch_corpus.py",
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": _REPOSITORY,
        "license": _LICENSE,
        "license_url": _LICENSE_URL,
        "decks": decks,
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_attribution(out_dir: Path, results: list[Fetched]) -> Path:
    path = out_dir / "ATTRIBUTION.md"
    lines = [
        "# External sample decks",
        "",
        "Fetched by `tools/fetch_corpus.py` (DECISION D004). The generated corpus",
        "in `corpus/raw/` is what the test suite uses; these real-world decks are",
        "an optional, manually fetched extra for learn-quality spot checks.",
        "",
        f"Source repository: {_REPOSITORY} (`test-data/slideshow`)",
        f"Licence: {_LICENSE} - {_LICENSE_URL}",
        "",
        "| file | sha256 | bytes | what it exercises |",
        "| --- | --- | --- | --- |",
    ]
    for fetched in results:
        item = fetched.item
        lines.append(
            f"| `{fetched.path.name}` | `{fetched.sha256[:16]}` | "
            f"{fetched.bytes_:,} | {item.note} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_table() -> None:
    print(f"{'id':<12} {'file':<20} {'license':<12} url")
    for item in DEFAULT_FILES:
        print(f"{item.id:<12} {item.filename:<20} {_LICENSE:<12} {item.url}")


def _select(ids: list[str]) -> tuple[CorpusFile, ...]:
    by_id = {item.id: item for item in DEFAULT_FILES}
    by_file = {item.filename: item for item in DEFAULT_FILES}
    chosen: list[CorpusFile] = []
    for token in ids:
        item = by_id.get(token) or by_file.get(token)
        if item is None:
            raise ValueError(
                f"unknown deck {token!r}; known ids: {', '.join(sorted(by_id))}"
            )
        if item not in chosen:
            chosen.append(item)
    return tuple(chosen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch_corpus.py",
        description=(
            "Download a small set of Apache-2.0 .pptx decks from the Apache POI "
            "regression fixtures into corpus/external/."
        ),
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT_DIR,
        help="output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--only", nargs="+", metavar="ID", default=None,
        help="fetch only these deck ids or file names (default: all)",
    )
    parser.add_argument(
        "--force", action="store_true", help="re-download decks already present"
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, metavar="SECONDS",
        help="per-request timeout (default: %(default)s)",
    )
    parser.add_argument(
        "--retries", type=int, default=2, metavar="N",
        help="attempts per deck (default: %(default)s)",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_only",
        help="print the deck table and exit without downloading",
    )
    args = parser.parse_args(argv)

    if args.list_only:
        _print_table()
        return EXIT_OK
    if requests is None:
        print(
            "error: the 'requests' package is missing; run "
            "'pip install -e .' in the project venv",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.retries < 1:
        print("error: --retries must be >= 1", file=sys.stderr)
        return EXIT_USAGE

    try:
        items = _select(args.only) if args.only else DEFAULT_FILES
    except ValueError as exc:
        print(f"error: {exc} (use --list)", file=sys.stderr)
        return EXIT_USAGE
    out_dir = args.out.resolve()
    print(f"fetching {len(items)} deck(s) into {out_dir}")
    try:
        results = download(
            items, out_dir,
            timeout=args.timeout, retries=args.retries, force=args.force,
        )
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "hint: this machine may have no network access; DeckForge's own "
            "corpus is generated offline with "
            "'python -m deckforge_core.tools.generate_corpus'",
            file=sys.stderr,
        )
        return EXIT_DOWNLOAD_FAILED

    manifest = write_manifest(out_dir, results)
    attribution = write_attribution(out_dir, results)
    fresh = sum(1 for r in results if not r.from_cache)
    print(
        f"ok: {len(results)} deck(s) ready ({fresh} downloaded, "
        f"{len(results) - fresh} already present)"
    )
    print(f"    manifest:     {manifest}")
    print(f"    attribution:  {attribution}")
    print(f"    licence:      {_LICENSE} - {_LICENSE_URL}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
