import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional, Union
from urllib.request import Request, urlopen


DEFAULT_TIMELINE_URL = (
    "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline"
)
PACKAGE_RE = re.compile(r"\bUiPath\.[A-Za-z0-9_.]+(?:\.Activities|\.ML)\b", re.I)
SHORT_PACKAGE_MAP = {
    "IntelligentOCR.Activities": "UiPath.IntelligentOCR.Activities",
    "PDF.Activities": "UiPath.PDF.Activities",
    "DocumentUnderstanding.ML": "UiPath.DocumentUnderstanding.ML",
    "OCR.Activities": "UiPath.OCR.Activities",
    "CommunicationsMining.Activities": "UiPath.CommunicationsMining.Activities",
    "OmniPage": "UiPath.OmniPage.Activities",
}
MODEL_PACKAGE_RE = re.compile(r"\bpython37duv[34]\b", re.I)
PACKAGE_LIKE_RE = re.compile(
    r"\bUiPath\.[A-Za-z0-9_.]+(?:\.Activities|\.ML)\b"
    r"|\b(?:IntelligentOCR\.Activities|PDF\.Activities|DocumentUnderstanding\.ML|OCR\.Activities|CommunicationsMining\.Activities|OmniPage)\b"
    r"|\bpython37duv[34]\b",
    re.I,
)
NON_PACKAGE_TERMS = (
    "automation suite",
    "backup",
    "docker",
    "kubernetes",
    "ai center",
    "apps",
    "orchestrator",
    "platform",
    "infrastructure",
)


class _TimelineTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.heading = ""
        self._heading_tag = ""
        self._in_cell = False
        self._in_row = False
        self._current_cell: list[str] = []
        self._current_row: list[str] = []
        self.rows: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._current_cell = []
        elif tag == "tr":
            self._in_row = True
            self._current_row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading_tag:
            self.heading = _clean_text(" ".join(self._current_cell))
            self._heading_tag = ""
            self._current_cell = []
        elif tag in {"td", "th"} and self._in_cell:
            self._current_row.append(_clean_text(" ".join(self._current_cell)))
            self._current_cell = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self.rows.append({"section_title": self.heading, "cells": self._current_row})
            self._current_row = []
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._heading_tag or self._in_cell:
            self._current_cell.append(data)


def fetch_timeline(
    source_url: str = DEFAULT_TIMELINE_URL,
    cache_path: Optional[Union[Path, str]] = None,
    refresh: bool = False,
    use_cache_only: bool = False,
) -> list[dict[str, Any]]:
    """Fetch and normalize the live UiPath timeline, with cache fallback."""
    cache = Path(cache_path) if cache_path else None
    if use_cache_only and cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["entries"]
    if use_cache_only:
        raise FileNotFoundError(f"Timeline cache does not exist: {cache}")

    request = Request(source_url, headers={"User-Agent": "uipath-deprecation-analyzer/1.0"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - official docs URL
            content = response.read().decode("utf-8", errors="ignore")
    except Exception:
        if cache and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))["entries"]
        raise

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entries = normalize_timeline_from_html(content, source_url, fetched_at)
    warnings = _normalization_warnings(entries)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "source_url": source_url,
                    "fetched_at": fetched_at,
                    "normalization_warnings": warnings,
                    "entries": entries,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return entries


def normalize_timeline_from_html(
    content: str,
    source_url: str,
    fetched_at: str,
) -> list[dict[str, Any]]:
    """Normalize package-only timeline entries from the UiPath docs HTML."""
    parser = _TimelineTableParser()
    parser.feed(content)
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for row in parser.rows:
        cells = row["cells"]
        if _looks_like_header(cells):
            continue
        combined = _clean_text(" | ".join(cells))
        candidate_text = cells[0] if cells else combined
        candidates = _extract_package_candidates(candidate_text)
        if not candidates or not _is_package_timeline_entry(combined):
            continue
        deprecation_date, removal_date = _extract_dates(cells, combined)
        scope = _compatibility_scope(combined)
        for candidate in candidates:
            package_name = candidate["package_name"]
            replacement = _extract_replacement_package(combined, package_name, len(candidates))
            affected_version = _extract_version_hint_near_candidate(combined, candidate["span"])
            confidence = _entry_confidence(candidate, removal_date, deprecation_date)
            key = (
                package_name.lower(),
                removal_date or "",
                deprecation_date or "",
                affected_version or "",
            )
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "package_name": package_name,
                    "affected_version": affected_version,
                    "deprecation_date": deprecation_date,
                    "removal_date": removal_date,
                    "replacement_package": replacement,
                    "compatibility_scope": scope,
                    "project_compatibility_impact": _compatibility_impact(scope),
                    "source_url": source_url,
                    "source_section_title": row.get("section_title", ""),
                    "source_text": combined,
                    "confidence": confidence,
                    "fetched_at": fetched_at,
                    "canonicalized_from": candidate["canonicalized_from"],
                    "normalization_warnings": candidate["warnings"],
                }
            )
    return entries


def _is_package_timeline_entry(text: str) -> bool:
    lower = text.lower()
    if not PACKAGE_LIKE_RE.search(text):
        return False
    if any(term in lower for term in NON_PACKAGE_TERMS) and not any(
        token in lower for token in ("activities", ".ml", "ml package", "python37duv")
    ):
        return False
    return True


def _extract_package_candidates(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for match in PACKAGE_LIKE_RE.finditer(text):
        raw = match.group(0).strip()
        package_name = _canonical_package(raw)
        key = (package_name.lower(), match.start())
        if key in seen:
            continue
        seen.add(key)
        canonicalized_from = "" if raw.lower() == package_name.lower() else raw
        candidates.append(
            {
                "raw": raw,
                "package_name": package_name,
                "canonicalized_from": canonicalized_from,
                "span": match.span(),
                "warnings": [],
            }
        )
    return candidates


def _extract_replacement_package(text: str, package_name: str, package_count: int) -> str:
    package_pattern = r"(?P<pkg>UiPath\.[A-Za-z0-9_.]+(?:\.Activities|\.ML))"
    escaped_name = re.escape(package_name)
    specific_patterns = [
        rf"alternative\s+(?:to|for)\s+{escaped_name}\s+is(?:\s+to\s+replace\s+it\s+with)?\s+{package_pattern}",
        rf"{escaped_name}.*?(?:replace(?:d)?\s+with|replacement(?: package)?|move to|use)\s+{package_pattern}",
    ]
    for pattern in specific_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = _canonical_package(match.group("pkg"))
            if candidate.lower() != package_name.lower():
                return candidate
    if package_count == 1:
        for match in re.finditer(
            rf"(?:replace(?:d)?\s+with|replacement(?: package)?|move to|use)\s+{package_pattern}",
            text,
            re.I,
        ):
            candidate = _canonical_package(match.group("pkg"))
            if candidate.lower() != package_name.lower():
                return candidate
    return ""


def _extract_dates(cells: list[str], text: str) -> tuple[str, str]:
    dates = [_normalize_date(match) for match in _date_candidates(text)]
    dates = [item for item in dates if item]
    deprecation_date = ""
    removal_date = ""
    data_cells = cells[1:] if len(cells) >= 3 else cells
    for index, cell in enumerate(data_cells, 1):
        lower = cell.lower()
        cell_dates = [_normalize_date(match) for match in _date_candidates(cell)]
        cell_dates = [item for item in cell_dates if item]
        if not cell_dates:
            continue
        if "deprecat" in lower or index == 1:
            deprecation_date = cell_dates[0]
        if any(word in lower for word in ("removal", "removed", "retire", "end of support")) or index == 2:
            removal_date = cell_dates[-1]
    if not deprecation_date and dates:
        deprecation_date = dates[0]
    if not removal_date and len(dates) >= 2:
        removal_date = dates[-1]
    elif not removal_date and "remov" in text.lower() and dates:
        removal_date = dates[-1]
    return deprecation_date, removal_date


def _date_candidates(text: str) -> list[str]:
    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b",
    ]
    results: list[str] = []
    for pattern in patterns:
        results.extend(re.findall(pattern, text, re.I))
    return results


def _normalize_date(value: str) -> str:
    raw = value.strip().replace(".", "")
    formats = (
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %Y",
        "%b %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _extract_version_hint_near_candidate(text: str, span: tuple[int, int]) -> str:
    after = text[span[1] : span[1] + 24]
    direct_match = re.match(r"\s+(?P<version>\d+(?:\.(?:\d+|x)){0,3})\b", after, re.I)
    if direct_match:
        return direct_match.group("version")
    window = text[max(0, span[0] - 80) : span[1] + 80]
    match = re.search(
        r"(?:version|versions|before|through|up to|<=|<|>=|>)\s*"
        r"(?P<version>\d+(?:\.\d+){0,3}(?:\.x)?)",
        window,
        re.I,
    )
    return match.group("version") if match else ""


def _compatibility_scope(text: str) -> str:
    lower = text.lower()
    if "windows-legacy" in lower or "windows legacy" in lower or ".net framework 4.6.1" in lower:
        return "windows_legacy_only"
    return "all_projects"


def _compatibility_impact(scope: str) -> str:
    if scope == "windows_legacy_only":
        return "Package remains relevant only for Windows-Legacy/.NET Framework 4.6.1 compatibility review."
    return "Package may affect all project compatibility modes."


def _looks_like_header(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    return "deprecation" in joined and "removal" in joined and "item" in joined


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _canonical_package(value: str) -> str:
    for short_name, package_name in SHORT_PACKAGE_MAP.items():
        if value.lower() == short_name.lower():
            return package_name
    if MODEL_PACKAGE_RE.fullmatch(value):
        return value.lower()
    parts = value.split(".")
    return ".".join(part[:1].upper() + part[1:] for part in parts)


def _entry_confidence(candidate: dict[str, Any], removal_date: str, deprecation_date: str) -> str:
    if candidate["warnings"]:
        return "medium"
    if removal_date or deprecation_date:
        return "high"
    return "medium"


def _normalization_warnings(entries: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for entry in entries:
        warnings.extend(entry.get("normalization_warnings", []))
    return sorted(set(warnings))
