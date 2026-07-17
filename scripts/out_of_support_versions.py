import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union
from urllib.request import Request, urlopen

from timeline import _clean_text, _date_candidates, _normalize_date, _TimelineTableParser


DEFAULT_OUT_OF_SUPPORT_URL = (
    "https://docs.uipath.com/overview/other/latest/overview/out-of-support-versions"
)

# Version trains look like 2022.10 or 2022.10.18. A leading product cell is any cell that is
# not a version, a support model, or a date.
_VERSION_RE = re.compile(r"^\d{4}\.\d+(?:\.\d+)*$")
_TRAIN_RE = re.compile(r"\b(\d{4}\.\d+)")
_SUPPORT_MODELS = {"LTS", "FTS"}

# Canonical product families. Order matters: the first token found in the label wins, so more
# specific tokens (for example "test manager for jira") are listed before broader ones.
_PRODUCT_CANONICAL = [
    ("test manager for jira", "Test Manager for Jira"),
    ("test manager", "Test Manager"),
    ("studiox", "Studio"),
    ("studio web", "Studio Web"),
    ("studio", "Studio"),
    ("assistant", "Assistant"),
    ("robot", "Robot"),
    ("orchestrator", "Orchestrator"),
    ("action center", "Action Center"),
    ("ai center", "AI Center"),
    ("aicenter", "AI Center"),
    ("ai computer vision", "AI Computer Vision"),
    ("document understanding", "Document Understanding"),
    ("data service", "Data Service"),
    ("apps", "Apps"),
    ("integration service", "Integration Service"),
    ("automation ops", "Automation Ops"),
    ("automation hub", "Automation Hub"),
    ("automation suite", "Automation Suite"),
    ("insights", "Insights"),
    ("process mining", "Process Mining"),
    ("task mining", "Task Mining"),
    ("task capture", "Task Capture"),
    ("maestro", "Maestro"),
]


def fetch_out_of_support_versions(
    source_url: str = DEFAULT_OUT_OF_SUPPORT_URL,
    cache_path: Optional[Union[Path, str]] = None,
    refresh: bool = False,
    use_cache_only: bool = False,
) -> list[dict[str, Any]]:
    """Fetch and normalize the UiPath out-of-support versions page, with cache fallback."""
    cache = Path(cache_path) if cache_path else None
    if use_cache_only and cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["entries"]
    if use_cache_only:
        raise FileNotFoundError(f"Out-of-support cache does not exist: {cache}")

    request = Request(source_url, headers={"User-Agent": "uipath-deprecation-analyzer/1.0"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - official docs URL
            content = response.read().decode("utf-8", errors="ignore")
    except Exception:
        if cache and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))["entries"]
        raise

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entries = normalize_out_of_support_from_html(content, source_url, fetched_at)
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


def normalize_out_of_support_from_html(
    content: str,
    source_url: str,
    fetched_at: str,
) -> list[dict[str, Any]]:
    """Normalize the product-version out-of-support tables into matchable entries.

    The product column uses ``rowspan``, so the product name only appears on the first
    version row of each block. We classify cells by content (product/version/model/date) and
    carry the last seen product name forward across continuation rows.
    """
    parser = _TimelineTableParser()
    parser.feed(content)
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    current_product = ""

    for row in parser.rows:
        cells = [cell.strip() for cell in row["cells"] if cell.strip()]
        if not cells or _looks_like_header(cells):
            current_product = ""  # a header row starts a new table/block
            continue

        version = next((cell for cell in cells if _VERSION_RE.match(cell)), "")
        model = next((cell for cell in cells if cell.upper() in _SUPPORT_MODELS), "")
        date_cell = next(
            (cell for cell in cells if _date_candidates(cell) and not _VERSION_RE.match(cell)),
            "",
        )
        product_cell = next(
            (
                cell
                for cell in cells
                if cell != version
                and cell != model
                and cell != date_cell
                and not _VERSION_RE.match(cell)
                and cell.upper() not in _SUPPORT_MODELS
            ),
            "",
        )
        if product_cell:
            current_product = _canonical_product(product_cell)
        if not version or not current_product:
            continue

        end_of_extended_support = _normalize_date(date_cell) if date_cell else ""
        warnings: list[str] = []
        if date_cell and not end_of_extended_support:
            warnings.append(f"Unparseable end-of-support date: {date_cell}")
        train = _release_train(version)
        key = (current_product.lower(), version)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "product": current_product,
                "version": version,
                "release_train": train,
                "support_model": model.upper(),
                "end_of_extended_support": end_of_extended_support,
                "source_url": source_url,
                "source_section_title": row.get("section_title", ""),
                "source_text": _clean_text(" | ".join(cells)),
                "confidence": "high" if end_of_extended_support else "medium",
                "fetched_at": fetched_at,
                "normalization_warnings": warnings,
            }
        )
    return entries


def out_of_support_trains(
    entries: list[dict[str, Any]],
    analysis_date: Optional[str] = None,
) -> dict[str, dict[str, str]]:
    """Map each ``product -> release_train`` that is out of support as of the analysis date.

    Returns ``{product_lower: {train: end_of_extended_support}}``. A train is included only
    when at least one listed version for that product has an End of Extended Support date on
    or before the analysis date, so future-dated rows are excluded.
    """
    as_of = _parse_date(analysis_date) or datetime.now(timezone.utc).date()
    trains: dict[str, dict[str, str]] = {}
    for entry in entries:
        eos = _parse_date(entry.get("end_of_extended_support"))
        if not eos or eos > as_of:
            continue
        product = str(entry.get("product", "")).strip().lower()
        train = entry.get("release_train", "")
        if not product or not train:
            continue
        product_trains = trains.setdefault(product, {})
        # Keep the latest end-of-support date seen for a train.
        existing = product_trains.get(train, "")
        if not existing or entry.get("end_of_extended_support", "") > existing:
            product_trains[train] = entry.get("end_of_extended_support", "")
    return trains


def platform_out_of_support_trains(
    entries: list[dict[str, Any]],
    analysis_date: Optional[str] = None,
    reference_products: tuple[str, ...] = ("studio", "robot", "orchestrator"),
) -> dict[str, str]:
    """Collapse the reference product trains into a single platform train support view.

    Activity packages ship with platform releases, so the client-side lifecycle floor uses
    the core platform products (Studio/Robot/Orchestrator) as the representative signal for
    whether a release train is still supported. Returns ``{train: end_of_extended_support}``.
    """
    per_product = out_of_support_trains(entries, analysis_date)
    collapsed: dict[str, str] = {}
    for product, trains in per_product.items():
        if product not in reference_products:
            continue
        for train, eos in trains.items():
            if train not in collapsed or eos > collapsed[train]:
                collapsed[train] = eos
    return collapsed


def _looks_like_header(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    return "product" in joined and "version" in joined and "support" in joined


def _canonical_product(label: str) -> str:
    lower = _clean_text(label).lower()
    for token, product in _PRODUCT_CANONICAL:
        if token in lower:
            return product
    # Fall back to the cleaned label with trademark glyphs stripped.
    return _clean_text(label).replace("™", "").strip()


def _release_train(version: str) -> str:
    match = _TRAIN_RE.search(version)
    return match.group(1) if match else ""


def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
