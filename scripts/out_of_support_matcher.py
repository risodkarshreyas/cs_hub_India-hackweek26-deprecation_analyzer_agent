import re
from typing import Any, Optional

from out_of_support_versions import _canonical_product, out_of_support_trains


_TRAIN_IN_TEXT_RE = re.compile(r"\b(\d{2,4})\.(\d+)")


def match_out_of_support_products(
    product_records: list[dict[str, Any]],
    out_of_support_entries: list[dict[str, Any]],
    analysis_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Flag detected UiPath product versions whose release train is out of support.

    ``product_records`` is the unified list of detected product versions: client Studio
    versions from ``project.json`` (``domain='client'``) and server ``service_version``
    evidence (``domain='server'``). A record is out of support when its product/release train
    matches a version on the UiPath out-of-support versions page whose End of Extended Support
    date is on or before the analysis date.
    """
    trains_by_product = out_of_support_trains(out_of_support_entries, analysis_date)
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for record in product_records:
        raw_product = str(record.get("product", "")).strip()
        raw_version = str(record.get("version", "")).strip()
        if not raw_product or not raw_version:
            continue
        product = _canonical_product(raw_product)
        train = _normalize_train(raw_version)
        if not train:
            continue
        product_trains = trains_by_product.get(product.lower())
        if not product_trains or train not in product_trains:
            continue

        domain = record.get("domain") or "client"
        environment = (
            record.get("environment")
            or record.get("project_name")
            or record.get("tenant_or_service")
            or ("server inventory" if domain == "server" else "client project")
        )
        key = (product.lower(), train, str(environment).lower())
        if key in seen:
            continue
        seen.add(key)

        end_of_support = product_trains[train]
        findings.append(
            {
                "domain": domain,
                "product": product,
                "feature_or_package": f"{product} {train}",
                "current_version": raw_version,
                "release_train": train,
                "status": "out_of_support",
                "severity": "high",
                "environment": environment,
                "project_name": record.get("project_name", ""),
                "tenant_or_service": record.get("tenant_or_service", ""),
                "service_version": raw_version if domain == "server" else "",
                "deadline": end_of_support,
                "evidence": _evidence(record, raw_product, raw_version),
                "impact": (
                    f"Detected {product} {raw_version} (release train {train}), which reached "
                    f"end of extended support on {end_of_support} and no longer receives "
                    "technical support or security fixes."
                ),
                "recommended_action": (
                    f"Upgrade {product} from {raw_version} to a version in a currently "
                    "supported release train (Mainstream or Extended support)."
                ),
                "source_url": record.get("source_url")
                or _entry_source_url(out_of_support_entries),
                "confidence": record.get("confidence", "medium"),
            }
        )

    return findings


def collect_server_product_records(server_inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Build product-version records from server evidence that carries a service version."""
    records: list[dict[str, Any]] = []
    for item in server_inventory.get("server_evidence", []):
        product = item.get("product", "")
        version = item.get("service_version", "")
        if not product or not version:
            continue
        records.append(
            {
                "product": product,
                "version": version,
                "domain": "server",
                "tenant_or_service": item.get("tenant_or_service")
                or item.get("tenant", "")
                or item.get("folder", ""),
                "environment": item.get("delivery_model") or item.get("tenant", ""),
                "evidence": [item.get("path", "")] if item.get("path") else [],
                "source_url": item.get("source_url", ""),
                "confidence": item.get("confidence", "medium"),
            }
        )
    return records


def _normalize_train(version: str) -> str:
    """Return the ``YYYY.MM`` release train for a product version string.

    Handles both four-digit-year forms (``2022.10.15``) and short forms (``23.10.5.0``).
    """
    match = _TRAIN_IN_TEXT_RE.search(version)
    if not match:
        return ""
    year = int(match.group(1))
    if year < 100:
        year += 2000
    return f"{year}.{int(match.group(2))}"


def _evidence(record: dict[str, Any], product: str, version: str) -> list[Any]:
    evidence = record.get("evidence")
    if isinstance(evidence, list) and evidence:
        return evidence
    if evidence:
        return [evidence]
    return [f"{product} version {version}"]


def _entry_source_url(entries: list[dict[str, Any]]) -> str:
    for entry in entries:
        if entry.get("source_url"):
            return entry["source_url"]
    return ""
