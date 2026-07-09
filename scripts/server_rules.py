import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from timeline import DEFAULT_TIMELINE_URL, _TimelineTableParser, _clean_text, _date_candidates, _normalize_date


SERVER_PRODUCTS = {
    "orchestrator": "Orchestrator",
    "test manager": "Test Manager",
    "automation cloud": "Automation Cloud",
    "automation suite": "Automation Suite",
    "apps": "Apps",
    "integration service": "Integration Service",
    "action center": "Action Center",
    "ai center": "AI Center",
    "document understanding": "Document Understanding",
    "insights": "Insights",
    "process mining": "Process Mining",
    "automation hub": "Automation Hub",
    "automation ops": "Automation Ops",
    "maestro": "Maestro",
    "task mining": "Task Mining",
    "high availability": "High Availability Add-On",
}


def fetch_server_rules(
    source_url: str = DEFAULT_TIMELINE_URL,
    cache_path: Path | str | None = None,
    refresh: bool = False,
    use_cache_only: bool = False,
) -> list[dict[str, Any]]:
    """Fetch and normalize server-side UiPath deprecation rules."""
    cache = Path(cache_path) if cache_path else None
    if use_cache_only and cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["entries"]
    if use_cache_only:
        raise FileNotFoundError(f"Server rule cache does not exist: {cache}")

    request = Request(source_url, headers={"User-Agent": "uipath-deprecation-analyzer/1.0"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - official docs URL
            content = response.read().decode("utf-8", errors="ignore")
    except Exception:
        if cache and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))["entries"]
        raise

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entries = normalize_server_rules_from_html(content, source_url, fetched_at)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "source_url": source_url,
                    "fetched_at": fetched_at,
                    "entries": entries,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return entries


def normalize_server_rules_from_html(
    content: str,
    source_url: str,
    fetched_at: str,
) -> list[dict[str, Any]]:
    """Normalize non-package server/platform timeline rows into matchable rules."""
    parser = _TimelineTableParser()
    parser.feed(content)
    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in parser.rows:
        cells = row["cells"]
        if not cells or _looks_like_header(cells):
            continue
        text = _clean_text(" | ".join(cells))
        product = _detect_product(row.get("section_title", ""), text)
        if not product or _looks_like_client_package_row(text):
            continue
        feature = cells[0].strip()
        if not feature:
            continue
        deprecation_date, removal_date = _extract_dates(cells, text)
        rule_id = _rule_id(product, feature)
        if rule_id in seen:
            continue
        seen.add(rule_id)
        rules.append(
            {
                "rule_id": rule_id,
                "product": product,
                "feature": feature,
                "lifecycle_status": _lifecycle_status(text, removal_date, deprecation_date),
                "delivery_models": _delivery_models(product, text),
                "deprecation_date": deprecation_date,
                "removal_date": removal_date,
                "match": _build_match(feature, text),
                "recommended_alternative": _recommended_alternative(text),
                "source_url": source_url,
                "source_section": row.get("section_title", ""),
                "source_text": text,
                "confidence": "high" if removal_date or deprecation_date else "medium",
                "fetched_at": fetched_at,
            }
        )
    return rules


def _looks_like_header(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    return "feature" in joined and ("deprecation" in joined or "removal" in joined)


def _looks_like_client_package_row(text: str) -> bool:
    lower = text.lower()
    return "uipath." in lower and (".activities" in lower or ".ml" in lower) and not any(
        token in lower for token in ("ai center", "document understanding", "service configuration")
    )


def _detect_product(section: str, text: str) -> str:
    haystack = f"{section} {text}".lower()
    if "orchestrator" in haystack:
        return "Orchestrator"
    for token, product in SERVER_PRODUCTS.items():
        if token in haystack:
            return product
    return ""


def _extract_dates(cells: list[str], text: str) -> tuple[str, str]:
    deprecation_date = ""
    removal_date = ""
    for index, cell in enumerate(cells[1:], 1):
        lower = cell.lower()
        dates = [_normalize_date(match) for match in _date_candidates(cell)]
        dates = [item for item in dates if item]
        if not dates:
            continue
        if "deprecat" in lower or "announc" in lower or index == 1:
            deprecation_date = dates[0]
        if any(word in lower for word in ("removal", "removed", "retire", "support")) or index == 2:
            removal_date = dates[-1]
    all_dates = [_normalize_date(match) for match in _date_candidates(text)]
    all_dates = [item for item in all_dates if item]
    if not deprecation_date and all_dates:
        deprecation_date = all_dates[0]
    if not removal_date and len(all_dates) > 1:
        removal_date = all_dates[-1]
    return deprecation_date, removal_date


def _lifecycle_status(text: str, removal_date: str, deprecation_date: str) -> str:
    lower = text.lower()
    if "removed" in lower and not removal_date:
        return "removed"
    if removal_date:
        return "removal_scheduled"
    if "out of support" in lower or "end of support" in lower:
        return "out_of_support"
    if deprecation_date or "deprecat" in lower:
        return "deprecated"
    return "informational"


def _delivery_models(product: str, text: str) -> list[str]:
    lower = text.lower()
    models: list[str] = []
    if "automation cloud" in lower:
        models.append("Automation Cloud")
    if "automation suite" in lower or product == "Automation Suite":
        models.append("Automation Suite")
    if "standalone" in lower:
        models.append("standalone Orchestrator")
    return models


def _build_match(feature: str, text: str) -> dict[str, Any]:
    patterns = _patterns(feature, text)
    types = {"service_feature"}
    if any("/" in pattern for pattern in patterns):
        types.add("endpoint")
    if any(token in text.lower() for token in ("field", "permission", "role")):
        types.add("api_field")
    if any(token in text.lower() for token in ("backup", "storage", "registry", "kubernetes", "sql", "nfs")):
        types.add("configuration_key")
    if "connector" in text.lower() or "connection" in text.lower():
        types.add("connector_name")
    return {"types": sorted(types), "patterns": patterns}


def _patterns(feature: str, text: str) -> list[str]:
    candidates = {feature}
    candidates.update(re.findall(r"\b(?:api|odata|identity|account)/[A-Za-z0-9_./{}-]+", text, re.I))
    candidates.update(re.findall(r"/(?:odata|api|identity|account)/[A-Za-z0-9_./{}-]+", text, re.I))
    if "test set" in text.lower() or "testing module" in text.lower():
        candidates.update({"Orchestrator test set", "Orchestrator test cases", "Orchestrator test schedules"})
    if "nfs backup" in text.lower():
        candidates.update({"NFS backup", "external objectstore"})
    if "legacy apps runtime" in text.lower():
        candidates.update({"legacyRuntime", "legacy Apps runtime"})
    if "connection management" in text.lower():
        candidates.update({"Integration Service", "connection management"})
    return sorted(candidates)


def _recommended_alternative(text: str) -> str:
    match = re.search(r"\b(?:migrate|move|use|create|manage|replace)[^.]+\.", text, re.I)
    return match.group(0).strip() if match else "Review UiPath migration guidance for this server-side feature."


def _rule_id(product: str, feature: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{product}-{feature}".lower()).strip("-")
    return f"uipath-server-{slug}"
