from datetime import date, datetime
from typing import Any


def match_server_deprecations(
    inventory: dict[str, Any],
    server_rules: list[dict[str, Any]],
    analysis_date: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Match server inventory evidence against server deprecation rules."""
    as_of = _parse_date(analysis_date) or date.today()
    evidence = inventory.get("server_evidence", [])
    findings: list[dict[str, Any]] = []
    matched_rule_ids: set[str] = set()

    for rule in server_rules:
        for item in evidence:
            if not _delivery_model_applies(rule, item):
                continue
            matched_pattern = _matched_pattern(rule, item)
            if not matched_pattern:
                continue
            matched_rule_ids.add(rule["rule_id"])
            findings.append(_build_finding(rule, item, matched_pattern, as_of))
            break

    gaps = _coverage_gaps(server_rules, evidence, matched_rule_ids)
    findings.sort(key=lambda item: (_severity_rank(item["severity"]), item["product"], item["feature"]))
    return findings, gaps


def _build_finding(rule: dict[str, Any], evidence: dict[str, Any], matched_pattern: str, as_of: date) -> dict[str, Any]:
    deadline = rule.get("removal_date", "")
    status = _status(rule, as_of)
    severity = _severity(status, deadline, as_of)
    return {
        "rule_id": rule.get("rule_id", ""),
        "severity": severity,
        "status": status,
        "product": rule.get("product", evidence.get("product", "")),
        "feature": rule.get("feature", ""),
        "environment": evidence.get("tenant_or_service") or evidence.get("delivery_model") or "server inventory",
        "evidence": [
            {
                "path": evidence.get("path", ""),
                "object_path": evidence.get("object_path", ""),
                "matched_value": evidence.get("matched_value") or matched_pattern,
                "endpoint": evidence.get("endpoint", ""),
                "api_field": evidence.get("api_field", ""),
            }
        ],
        "impact": f"Detected server-side usage of {rule.get('feature', '')} in inventory evidence.",
        "deadline": deadline,
        "recommended_action": rule.get("recommended_alternative") or "Review UiPath migration guidance for this server-side feature.",
        "source_url": rule.get("source_url", ""),
        "confidence": _confidence(rule, evidence),
        "delivery_model": evidence.get("delivery_model", ""),
        "tenant_or_service": evidence.get("tenant_or_service", ""),
        "endpoint": evidence.get("endpoint", ""),
        "api_field": evidence.get("api_field", ""),
        "service_version": evidence.get("service_version", ""),
        "configuration_object": evidence.get("configuration_object", ""),
        "source_section": rule.get("source_section", ""),
        "source_text": rule.get("source_text", ""),
    }


def _delivery_model_applies(rule: dict[str, Any], evidence: dict[str, Any]) -> bool:
    models = [model.lower() for model in rule.get("delivery_models", []) if model]
    if not models:
        return True
    evidence_model = (evidence.get("delivery_model") or "").lower()
    if not evidence_model:
        return True
    return any(model == evidence_model for model in models)


def _matched_pattern(rule: dict[str, Any], evidence: dict[str, Any]) -> str:
    patterns = rule.get("match", {}).get("patterns", [])
    haystack_values = [
        evidence.get("endpoint", ""),
        evidence.get("api_field", ""),
        evidence.get("service_version", ""),
        evidence.get("configuration_object", ""),
        evidence.get("matched_value", ""),
        evidence.get("evidence_type", ""),
    ]
    haystack = " | ".join(str(value) for value in haystack_values if value).lower()
    for pattern in patterns:
        pattern_text = str(pattern).strip()
        if not pattern_text:
            continue
        if pattern_text.lower().lstrip("/") in haystack or pattern_text.lower() in haystack:
            return pattern_text
    return ""


def _status(rule: dict[str, Any], as_of: date) -> str:
    removal = _parse_date(rule.get("removal_date"))
    if removal and removal < as_of:
        return "removed"
    return rule.get("lifecycle_status") or ("removal_scheduled" if removal else "deprecated")


def _severity(status: str, deadline: str, as_of: date) -> str:
    if status == "removed":
        return "critical"
    removal = _parse_date(deadline)
    if removal and 0 <= (removal - as_of).days <= 180:
        return "high"
    if status in {"removal_scheduled", "deprecated", "out_of_support"}:
        return "medium"
    return "low"


def _coverage_gaps(
    rules: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    matched_rule_ids: set[str],
) -> list[dict[str, Any]]:
    products_with_evidence = {item.get("product") for item in evidence if item.get("product")}
    gaps: list[dict[str, Any]] = []
    for rule in rules:
        product = rule.get("product", "")
        if rule.get("rule_id") in matched_rule_ids or product in products_with_evidence:
            continue
        gaps.append(
            {
                "type": "missing_context",
                "product": product,
                "feature": rule.get("feature", ""),
                "message": f"No server inventory evidence was available for {product}.",
            }
        )
    return gaps


def _confidence(rule: dict[str, Any], evidence: dict[str, Any]) -> str:
    if rule.get("confidence") == "high" and evidence.get("confidence") == "high":
        return "high"
    if evidence.get("confidence") in {"high", "medium"}:
        return "medium"
    return "low"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 9)
