import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union
from urllib.request import Request, urlopen

from timeline import (
    PACKAGE_LIKE_RE,
    _canonical_package,
    _clean_text,
    _TimelineTableParser,
)


DEFAULT_ACTIVITIES_LIFECYCLE_URL = (
    "https://docs.uipath.com/overview/other/latest/overview/activities-lifecycle"
)

# A release-train column header, for example "2024.10 LTS" or "2021.4 FTS".
_RELEASE_HEADER_RE = re.compile(r"\b(\d{4}\.\d+)\b")
# An activity-package version cell, for example "2.24.4" or "25.10.5".
_VERSION_CELL_RE = re.compile(r"^\d+(?:\.\d+)+$")


def fetch_activities_lifecycle(
    source_url: str = DEFAULT_ACTIVITIES_LIFECYCLE_URL,
    cache_path: Optional[Union[Path, str]] = None,
    refresh: bool = False,
    use_cache_only: bool = False,
) -> list[dict[str, Any]]:
    """Fetch and normalize the UiPath activities lifecycle matrix, with cache fallback."""
    cache = Path(cache_path) if cache_path else None
    if use_cache_only and cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["entries"]
    if use_cache_only:
        raise FileNotFoundError(f"Activities lifecycle cache does not exist: {cache}")

    request = Request(source_url, headers={"User-Agent": "uipath-deprecation-analyzer/1.0"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - official docs URL
            content = response.read().decode("utf-8", errors="ignore")
    except Exception:
        if cache and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))["entries"]
        raise

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entries = normalize_activities_lifecycle_from_html(content, source_url, fetched_at)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {"source_url": source_url, "fetched_at": fetched_at, "entries": entries},
                indent=2,
            ),
            encoding="utf-8",
        )
    return entries


def normalize_activities_lifecycle_from_html(
    content: str,
    source_url: str,
    fetched_at: str,
) -> list[dict[str, Any]]:
    """Normalize the activity package x release-train matrix.

    Each data row maps an activity package to the version shipped in each release-train
    column. The page carries no per-cell support status; the support floor is derived at
    match time from the out-of-support versions dates (see
    ``references/activities_lifecycle_schema.md``).
    """
    parser = _TimelineTableParser()
    parser.feed(content)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    columns: list[dict[str, str]] = []

    for row in parser.rows:
        cells = [cell.strip() for cell in row["cells"]]
        if not cells:
            continue
        if _is_matrix_header(cells):
            columns = _parse_columns(cells)
            continue
        if not columns:
            continue

        package_name = _package_from_cell(cells[0])
        if not package_name:
            continue
        versions_by_release: list[dict[str, str]] = []
        for index, column in enumerate(columns, start=1):
            if index >= len(cells):
                break
            version = _version_from_cell(cells[index])
            if not version:
                continue
            versions_by_release.append(
                {
                    "release_train": column["release_train"],
                    "release_label": column["release_label"],
                    "version": version,
                }
            )
        if not versions_by_release:
            continue
        key = package_name.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "package_name": package_name,
                "versions_by_release": versions_by_release,
                "source_url": source_url,
                "source_section_title": row.get("section_title", ""),
                "source_text": _clean_text(" | ".join(cells)),
                "confidence": "high",
                "fetched_at": fetched_at,
                "normalization_warnings": [],
            }
        )
    return entries


def _is_matrix_header(cells: list[str]) -> bool:
    first = cells[0].lower()
    if "activity pack" not in first:
        return False
    return any(_RELEASE_HEADER_RE.search(cell) for cell in cells[1:])


def _parse_columns(cells: list[str]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for cell in cells[1:]:
        match = _RELEASE_HEADER_RE.search(cell)
        columns.append(
            {
                "release_label": _clean_text(cell),
                "release_train": match.group(1) if match else "",
            }
        )
    return columns


def _package_from_cell(cell: str) -> str:
    text = _clean_text(cell)
    match = PACKAGE_LIKE_RE.search(text)
    if not match:
        return ""
    return _canonical_package(match.group(0))


def _version_from_cell(cell: str) -> str:
    text = _clean_text(cell)
    return text if _VERSION_CELL_RE.match(text) else ""
