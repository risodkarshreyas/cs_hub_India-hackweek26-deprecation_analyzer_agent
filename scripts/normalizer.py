from datetime import date, datetime
from typing import Any, Optional


CLIENT_STATUS_MAP = {
    "Already Removed": "removed",
    "Out Of Support": "out_of_support",
    "Removal Imminent": "removal_scheduled",
    "Removal Scheduled": "removal_scheduled",
    ".NET Framework 4.6.1 / Windows-Legacy Compatibility Impact": "deprecated",
}


def normalize_client_finding(raw: dict[str, Any], index: int, analysis_date: str) -> dict[str, Any]:
    status = CLIENT_STATUS_MAP.get(raw.get("classification", ""), "deprecated")
    severity = str(raw.get("risk_level", "medium")).lower()
    finding = _base_finding(
        index=index,
        domain="client",
        severity=severity,
        status=status,
        product="Studio/Robot activity packages",
        feature_or_package=raw.get("package_name", ""),
        environment=raw.get("project_name", ""),
        evidence=raw.get("evidence", []),
        impact=raw.get("impact", {}).get("value_added")
        if isinstance(raw.get("impact"), dict)
        else "Detected deprecated package usage in client automation evidence.",
        deadline=raw.get("removal_date", ""),
        recommended_action=raw.get("recommendation", ""),
        confidence=raw.get("confidence", "medium"),
        source_url=raw.get("source_url", ""),
        analysis_date=analysis_date,
    )
    finding.update(
        {
            "project_name": raw.get("project_name", ""),
            "package_name": raw.get("package_name", ""),
            "current_version": raw.get("current_version", ""),
            "replacement_package": raw.get("replacement_package", ""),
            "compatibility_scope": raw.get("compatibility_scope", ""),
            "project_compatibility": raw.get("project_compatibility", ""),
        }
    )
    return finding


def normalize_product_finding(raw: dict[str, Any], index: int, analysis_date: str) -> dict[str, Any]:
    """Normalize an out-of-support product-version finding (client Studio or server product)."""
    domain = raw.get("domain") or "client"
    product = raw.get("product", "")
    finding = _base_finding(
        index=index,
        domain=domain,
        severity=raw.get("severity", "high"),
        status=raw.get("status", "out_of_support"),
        product=product,
        feature_or_package=raw.get("feature_or_package") or product,
        environment=raw.get("environment") or raw.get("project_name") or "unknown",
        evidence=raw.get("evidence", []),
        impact=raw.get("impact", ""),
        deadline=raw.get("deadline", ""),
        recommended_action=raw.get("recommended_action", ""),
        confidence=raw.get("confidence", "medium"),
        source_url=raw.get("source_url", ""),
        analysis_date=analysis_date,
    )
    finding["current_version"] = raw.get("current_version", "")
    if domain == "client":
        finding["project_name"] = raw.get("project_name", "")
    else:
        finding["tenant_or_service"] = raw.get("tenant_or_service", "")
        finding["service_version"] = raw.get("service_version", "")
    # Product/version upgrades are owner or infrastructure decisions, not AI-applied edits.
    finding["mitigation_route"] = "owner_review"
    return finding


def normalize_server_finding(raw: dict[str, Any], index: int, analysis_date: str) -> dict[str, Any]:
    finding = _base_finding(
        index=index,
        domain="server",
        severity=raw.get("severity", "medium"),
        status=raw.get("status", "deprecated"),
        product=raw.get("product", ""),
        feature_or_package=raw.get("feature", raw.get("feature_or_package", "")),
        environment=raw.get("environment") or raw.get("tenant_or_service") or raw.get("delivery_model") or "server inventory",
        evidence=raw.get("evidence", []),
        impact=raw.get("impact", ""),
        deadline=raw.get("deadline", ""),
        recommended_action=raw.get("recommended_action", ""),
        confidence=raw.get("confidence", "medium"),
        source_url=raw.get("source_url", ""),
        analysis_date=analysis_date,
    )
    for field in (
        "delivery_model",
        "tenant_or_service",
        "endpoint",
        "api_field",
        "service_version",
        "configuration_object",
    ):
        finding[field] = raw.get(field, "")
    finding["recommended_skill"] = _recommended_skill(finding)
    finding["owner_hint"] = _owner_hint(finding)
    finding["mitigation_route"] = _mitigation_route(finding)
    return finding


def _base_finding(
    index: int,
    domain: str,
    severity: str,
    status: str,
    product: str,
    feature_or_package: str,
    environment: str,
    evidence: Any,
    impact: str,
    deadline: str,
    recommended_action: str,
    confidence: str,
    source_url: str,
    analysis_date: str,
) -> dict[str, Any]:
    finding = {
        "id": f"F-{index:03d}",
        "severity": str(severity or "medium").lower(),
        "status": status or "deprecated",
        "domain": domain,
        "product": product,
        "feature_or_package": feature_or_package,
        "environment": environment or "unknown",
        "evidence": evidence if isinstance(evidence, list) else [evidence],
        "impact": impact or "Deprecated usage detected in provided evidence.",
        "deadline": deadline or "",
        "recommended_action": recommended_action or "Review UiPath migration guidance.",
        "mitigation_route": "owner_review",
        "recommended_skill": "uipath-deprecation-analyzer",
        "time_savings_kpi": _time_savings_kpi(domain, evidence, analysis_date),
        "owner_hint": "Platform admin" if domain == "server" else "RPA maintainer",
        "confidence": confidence or "medium",
        "source_url": source_url,
    }
    finding["recommended_skill"] = _recommended_skill(finding)
    finding["owner_hint"] = _owner_hint(finding)
    finding["mitigation_route"] = _mitigation_route(finding)
    return finding


def _recommended_skill(finding: dict[str, Any]) -> str:
    product = finding.get("product", "").lower()
    feature = finding.get("feature_or_package", "").lower()
    if finding.get("domain") == "client":
        return "uipath-rpa"
    if "test manager" in product or "testing module" in feature or "test " in feature:
        return "uipath-test"
    if "apps" in product:
        return "uipath-coded-apps"
    if "maestro" in product:
        return "uipath-maestro-flow"
    return "uipath-platform"


def _owner_hint(finding: dict[str, Any]) -> str:
    product = finding.get("product", "").lower()
    feature = finding.get("feature_or_package", "").lower()
    if finding.get("domain") == "client":
        return "RPA maintainer"
    if "test manager" in product or "testing module" in feature:
        return "QA/Test Manager owner"
    if "integration" in product:
        return "Integration owner"
    if "apps" in product:
        return "Apps owner"
    if "automation suite" in product:
        return "Infrastructure owner"
    return "Platform admin"


def _mitigation_route(finding: dict[str, Any]) -> str:
    if finding.get("severity") == "critical":
        return "ai_assisted_change"
    if finding.get("confidence") == "low":
        return "owner_review"
    return "ai_assisted_change" if finding.get("recommended_skill") != "uipath-deprecation-analyzer" else "auto_assess"


def _time_savings_kpi(domain: str, evidence: Any, analysis_date: str) -> dict[str, Any]:
    count = len(evidence) if isinstance(evidence, list) else 1
    if domain == "server":
        manual = 6.0 + min(count, 4)
        assisted = 2.0
        basis = "AI mapped server inventory evidence to UiPath deprecation rules, ranked risk, and drafted remediation ownership."
    else:
        manual = 4.0 + min(count, 3)
        assisted = 1.5
        basis = "AI matched project package evidence to the UiPath timeline and drafted the replacement route."
    saved = max(manual - assisted, 0)
    percent = round(saved / manual * 100) if manual else 0
    return {
        "manual_baseline_hours": manual,
        "ai_assisted_hours": assisted,
        "hours_saved": saved,
        "percent_saved": percent,
        "basis": basis,
        "confidence": "medium",
    }


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
