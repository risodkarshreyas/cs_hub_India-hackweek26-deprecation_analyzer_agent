from datetime import date, datetime
from collections import Counter
from typing import Any, Optional, Union


def match_server_deprecations(
    inventory: dict[str, Any],
    server_rules: list[dict[str, Any]],
    analysis_date: Optional[str] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Match server inventory evidence against server deprecation rules."""
    as_of = _parse_date(analysis_date) or date.today()
    evidence = inventory.get("server_evidence", [])
    findings: list[dict[str, Any]] = []
    matched_rule_ids: set[str] = set()

    for rule in server_rules:
        matches: list[tuple[dict[str, Any], str]] = []
        for item in evidence:
            if not _delivery_model_applies(rule, item):
                continue
            if not _product_applies(rule, item):
                continue
            matched_pattern = _matched_pattern(rule, item)
            if not matched_pattern:
                continue
            matches.append((item, matched_pattern))
        if not matches:
            continue
        matched_rule_ids.add(rule["rule_id"])
        if _is_testing_module_rule(rule):
            grouped = _group_testing_evidence(matches)
            findings.append(_build_finding(rule, grouped, "Testing Module in Orchestrator", as_of))
        else:
            findings.append(_build_finding(rule, matches[0][0], matches[0][1], as_of))

    gaps = _coverage_gaps(server_rules, evidence, matched_rule_ids)
    findings.sort(key=lambda item: (_severity_rank(item["severity"]), item["product"], item["feature"]))
    return findings, gaps


def _build_finding(
    rule: dict[str, Any], evidence: Union[dict[str, Any], list[dict[str, Any]]], matched_pattern: str, as_of: date
) -> dict[str, Any]:
    deadline = rule.get("removal_date", "")
    status = _status(rule, as_of)
    severity = _severity(status, deadline, as_of)
    evidence_items = evidence if isinstance(evidence, list) else [evidence]
    primary = evidence_items[0] if evidence_items else {}
    finding_evidence = [_evidence_record(item, matched_pattern) for item in evidence_items]
    folder = primary.get("folder", "")
    tenant = primary.get("tenant_or_service") or primary.get("tenant", "")
    environment = folder or tenant or primary.get("delivery_model") or "server inventory"
    impact = f"Detected server-side usage of {rule.get('feature', '')} in inventory evidence."
    if primary.get("artifact_counts"):
        counts = ", ".join(
            f"{count} {artifact.replace('_', ' ')}" for artifact, count in primary["artifact_counts"].items()
        )
        impact = f"Detected {counts} in Orchestrator folder {folder or tenant or 'inventory'}."
    return {
        "rule_id": rule.get("rule_id", ""),
        "severity": severity,
        "status": status,
        "product": rule.get("product", primary.get("product", "")),
        "feature": rule.get("feature", ""),
        "environment": environment,
        "evidence": finding_evidence,
        "impact": impact,
        "deadline": deadline,
        "recommended_action": rule.get("recommended_alternative") or "Review UiPath migration guidance for this server-side feature.",
        "source_url": rule.get("source_url", ""),
        "confidence": _confidence(rule, primary),
        "delivery_model": primary.get("delivery_model", ""),
        "tenant_or_service": tenant,
        "endpoint": primary.get("endpoint", ""),
        "api_field": primary.get("api_field", ""),
        "service_version": primary.get("service_version", ""),
        "configuration_object": folder or primary.get("configuration_object", ""),
        "source_section": rule.get("source_section", ""),
        "source_text": rule.get("source_text", ""),
    }


def _evidence_record(evidence: dict[str, Any], matched_pattern: str) -> dict[str, Any]:
    record = {
        "path": evidence.get("path", ""),
        "object_path": evidence.get("object_path", ""),
        "matched_value": evidence.get("matched_value") or matched_pattern,
        "endpoint": evidence.get("endpoint", ""),
        "api_field": evidence.get("api_field", ""),
        "configuration_object": evidence.get("configuration_object", ""),
        "artifact_type": evidence.get("artifact_type", ""),
        "organization": evidence.get("organization", ""),
        "tenant": evidence.get("tenant", ""),
        "folder": evidence.get("folder", ""),
        "source_url": evidence.get("source_url", ""),
        "evidence_source": evidence.get("evidence_source", ""),
    }
    for key in ("artifact_counts", "representative_objects"):
        if key in evidence:
            record[key] = evidence[key]
    return {key: value for key, value in record.items() if value not in ("", None, [], {})}


def _delivery_model_applies(rule: dict[str, Any], evidence: dict[str, Any]) -> bool:
    models = [model.lower() for model in rule.get("delivery_models", []) if model]
    if not models:
        return True
    evidence_model = (evidence.get("delivery_model") or "").lower()
    if not evidence_model:
        return True
    return any(model == evidence_model for model in models)


def _product_applies(rule: dict[str, Any], evidence: dict[str, Any]) -> bool:
    rule_product = str(rule.get("product", "")).strip().lower()
    evidence_product = str(evidence.get("product", "")).strip().lower()
    return not rule_product or not evidence_product or rule_product == evidence_product


def _is_testing_module_rule(rule: dict[str, Any]) -> bool:
    feature = str(rule.get("feature", "")).lower()
    return "testing module" in feature and "orchestrator" in feature


def _group_testing_evidence(matches: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    counts: Counter[str] = Counter()
    representatives: dict[str, list[str]] = {}
    for item, _matched_pattern in matches:
        endpoint = item.get("endpoint", "")
        artifact_type = item.get("artifact_type") or _artifact_type_from_endpoint(endpoint)
        object_name = item.get("configuration_object", "")
        if artifact_type and object_name:
            counts[artifact_type] += 1
            if object_name and object_name not in representatives.setdefault(artifact_type, []) and len(
                representatives[artifact_type]
            ) < 5:
                representatives[artifact_type].append(object_name)
        identity = (item.get("path", ""), item.get("object_path", ""), endpoint, object_name)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(dict(item))

    if not unique:
        return []
    summary = dict(unique[0])
    summary["matched_value"] = "Orchestrator testing artifacts"
    summary["artifact_counts"] = dict(counts)
    summary["representative_objects"] = representatives
    summary["evidence_type"] = "service_feature"
    summary["confidence"] = "high" if all(item.get("confidence") == "high" for item in unique) else "medium"
    return [summary] + unique


def _artifact_type_from_endpoint(endpoint: str) -> str:
    return {
        "/odata/testsets": "test_set",
        "/odata/testcases": "test_case",
        "/odata/testcasedefinitions": "test_case",
        "/odata/testcaseexecutions": "test_case_execution",
        "/odata/testsetexecutions": "test_set_execution",
        "/odata/testsetschedules": "test_set_schedule",
    }.get(str(endpoint).lower(), "")


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


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 9)
