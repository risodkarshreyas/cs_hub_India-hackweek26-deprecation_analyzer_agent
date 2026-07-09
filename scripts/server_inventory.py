import csv
import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


SECRET_KEY_RE = re.compile(r"(password|secret|token|key|authorization|cookie)", re.I)
ENDPOINT_RE = re.compile(r"\b(?:/odata|/api|api/Account|odata/|https?://[^\s\"']+)", re.I)
SERVER_EXTENSIONS = {".json", ".csv", ".yaml", ".yml", ".xml", ".txt", ".log"}


def scan_server_inputs(input_path: Path | str) -> dict[str, Any]:
    """Scan server/platform exports and inventories for matchable evidence."""
    root = Path(input_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input path does not exist: {root}")
    files = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
    inventory: dict[str, Any] = {
        "input_path": str(root),
        "server_evidence": [],
        "errors": [],
        "coverage_hints": [],
    }
    for path in files:
        if path.suffix.lower() not in SERVER_EXTENSIONS:
            continue
        try:
            inventory["server_evidence"].extend(_scan_file(path, root))
        except Exception as exc:  # noqa: BLE001 - collect per-file scan failures
            inventory["errors"].append({"path": str(_relative(path, root)), "error": str(exc)})
    inventory["summary"] = {
        "server_file_count": len(files),
        "server_evidence_count": len(inventory["server_evidence"]),
        "products": sorted({item.get("product", "") for item in inventory["server_evidence"] if item.get("product")}),
    }
    return inventory


def looks_like_server_input(input_path: Path | str) -> bool:
    root = Path(input_path)
    files = [root] if root.is_file() else list(root.rglob("*")) if root.exists() else []
    markers = (
        "orchestrator",
        "automation-suite",
        "cluster_config",
        "postman",
        "openapi",
        "integration-service",
        "aicenter",
        "apps",
        "tenant",
    )
    return any(any(marker in str(path).lower() for marker in markers) for path in files)


def _scan_file(path: Path, root: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _scan_json(path, root)
    if suffix == ".csv":
        return _scan_csv(path, root)
    if suffix == ".xml":
        return _scan_xml(path, root)
    return _scan_text(path, root)


def _scan_json(path: Path, root: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    evidence: list[dict[str, Any]] = []
    _walk_json(data, [], path, root, evidence)
    return evidence


def _walk_json(value: Any, object_path: list[str], path: Path, root: Path, evidence: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        current = {str(key): _redact_value(key, item) for key, item in value.items()}
        evidence.extend(_evidence_from_mapping(current, object_path, path, root))
        for key, item in value.items():
            _walk_json(item, object_path + [str(key)], path, root, evidence)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_json(item, object_path + [str(index)], path, root, evidence)
    elif isinstance(value, str):
        evidence.extend(_evidence_from_text(value, object_path, path, root))


def _evidence_from_mapping(data: dict[str, Any], object_path: list[str], path: Path, root: Path) -> list[dict[str, Any]]:
    text = json.dumps(data, sort_keys=True)
    product = _detect_product(path, text)
    tenant = _first_value(data, ("tenant", "tenantName", "organization", "folder", "service"))
    delivery_model = _detect_delivery_model(text)
    records: list[dict[str, Any]] = []

    name = _first_value(data, ("Name", "name", "displayName", "id"))
    obj_type = _first_value(data, ("Type", "type", "runtime", "management"))
    if name or obj_type:
        records.append(
            _record(
                path,
                root,
                object_path,
                product=product,
                delivery_model=delivery_model,
                tenant_or_service=tenant,
                configuration_object=str(name or obj_type),
                matched_value=str(obj_type or name),
                evidence_type="configuration_object",
                confidence="high",
            )
        )
        if "test_sets" in path.name.lower() or "test set" in f"{name} {obj_type}".lower():
            records.append(
                _record(
                    path,
                    root,
                    object_path,
                    product=product or "Orchestrator",
                    delivery_model=delivery_model,
                    tenant_or_service=tenant,
                    endpoint="/odata/TestSets",
                    configuration_object=str(name or obj_type),
                    matched_value="Orchestrator test set",
                    evidence_type="endpoint",
                    confidence="high",
                )
            )

    url = _extract_url_or_path(data)
    if url:
        records.append(
            _record(
                path,
                root,
                object_path,
                product=product,
                delivery_model=delivery_model,
                tenant_or_service=tenant,
                endpoint=_normalize_endpoint(url),
                matched_value=_normalize_endpoint(url),
                evidence_type="endpoint",
                confidence="high",
            )
        )

    for key, item in data.items():
        key_text = str(key)
        value_text = str(item)
        if _is_interesting_config(key_text, value_text):
            records.append(
                _record(
                    path,
                    root,
                    object_path + [key_text],
                    product=product,
                    delivery_model=delivery_model,
                    tenant_or_service=tenant,
                    api_field=key_text if _looks_like_api_field(key_text) else "",
                    service_version=value_text if "version" in key_text.lower() else "",
                    configuration_object=key_text,
                    matched_value=value_text,
                    evidence_type="api_field" if _looks_like_api_field(key_text) else "configuration_key",
                    confidence="high",
                )
            )
    return records


def _evidence_from_text(value: str, object_path: list[str], path: Path, root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    product = _detect_product(path, value)
    for match in ENDPOINT_RE.finditer(value):
        records.append(
            _record(
                path,
                root,
                object_path,
                product=product,
                endpoint=_normalize_endpoint(match.group(0)),
                matched_value=_normalize_endpoint(match.group(0)),
                evidence_type="endpoint",
                confidence="medium",
            )
        )
    for token in ("legacyRuntime", "Orchestrator test set", "NFS backup", "Integration Service", "python37duv3", "python37duv4"):
        if token.lower() in value.lower():
            records.append(
                _record(
                    path,
                    root,
                    object_path,
                    product=product,
                    configuration_object=token,
                    matched_value=token,
                    evidence_type="text_pattern",
                    confidence="medium",
                )
            )
    return records


def _scan_csv(path: Path, root: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), 2):
            clean = {key: _redact_value(key, value) for key, value in row.items()}
            for item in _evidence_from_mapping(clean, [f"row:{row_number}"], path, root):
                item["row"] = row_number
                evidence.append(item)
    return evidence


def _scan_xml(path: Path, root: Path) -> list[dict[str, Any]]:
    xml_text = path.read_text(encoding="utf-8", errors="ignore")
    evidence = _scan_text_content(xml_text, path, root)
    try:
        parsed = ET.fromstring(xml_text)
    except ET.ParseError:
        return evidence
    for elem in parsed.iter():
        data = {key: _redact_value(key, value) for key, value in elem.attrib.items()}
        if elem.text and elem.text.strip():
            data[_local_name(elem.tag)] = elem.text.strip()
        evidence.extend(_evidence_from_mapping(data, [_local_name(elem.tag)], path, root))
    return evidence


def _scan_text(path: Path, root: Path) -> list[dict[str, Any]]:
    return _scan_text_content(path.read_text(encoding="utf-8", errors="ignore"), path, root)


def _scan_text_content(text: str, path: Path, root: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        redacted = _redact_line(line)
        for item in _evidence_from_text(redacted, [f"line:{line_number}"], path, root):
            item["line"] = line_number
            evidence.append(item)
    return evidence


def _record(
    path: Path,
    root: Path,
    object_path: list[str],
    product: str = "",
    delivery_model: str = "",
    tenant_or_service: str = "",
    endpoint: str = "",
    api_field: str = "",
    service_version: str = "",
    configuration_object: str = "",
    matched_value: str = "",
    evidence_type: str = "",
    confidence: str = "medium",
) -> dict[str, Any]:
    return {
        "product": product,
        "delivery_model": delivery_model,
        "tenant_or_service": tenant_or_service,
        "endpoint": endpoint,
        "api_field": api_field,
        "service_version": service_version,
        "configuration_object": configuration_object,
        "path": str(_relative(path, root)),
        "object_path": ".".join(object_path),
        "line": "",
        "row": "",
        "matched_value": _redact_line(str(matched_value)),
        "evidence_type": evidence_type,
        "confidence": confidence,
    }


def _detect_product(path: Path, text: str) -> str:
    lower = f"{path} {text}".lower()
    if "test set" in lower or "orchestrator" in lower or "/odata" in lower:
        return "Orchestrator"
    if "automation-suite" in lower or "automation suite" in lower or "cluster_config" in lower:
        return "Automation Suite"
    if "integration-service" in lower or "integration service" in lower:
        return "Integration Service"
    if "aicenter" in lower or "ai center" in lower or "ml-package" in lower or "python37duv" in lower:
        return "AI Center"
    if "apps" in lower or "legacyruntime" in lower:
        return "Apps"
    return ""


def _detect_delivery_model(text: str) -> str:
    lower = text.lower()
    if "automation cloud" in lower:
        return "Automation Cloud"
    if "automation suite" in lower:
        return "Automation Suite"
    return ""


def _extract_url_or_path(data: dict[str, Any]) -> str:
    url = data.get("url")
    if isinstance(url, dict):
        if url.get("raw"):
            return str(url["raw"])
        if isinstance(url.get("path"), list):
            return "/".join(str(item) for item in url["path"])
    if isinstance(data.get("raw"), str):
        return str(data["raw"])
    if isinstance(data.get("endpoint"), str):
        return str(data["endpoint"])
    return ""


def _normalize_endpoint(value: str) -> str:
    raw = value.strip()
    if raw.startswith("http"):
        match = re.search(r"(/(?:odata|api|identity|account)/.*)$", raw, re.I)
        if match:
            return match.group(1).lstrip("/")
    return raw.lstrip("/")


def _is_interesting_config(key: str, value: str) -> bool:
    lower = f"{key} {value}".lower()
    if SECRET_KEY_RE.search(key):
        return True
    return any(
        token in lower
        for token in (
            "legacy",
            "version",
            "backup",
            "objectstore",
            "nfs",
            "runtime",
            "management",
            "python37duv",
            "connection",
        )
    )


def _looks_like_api_field(key: str) -> bool:
    return key.lower() in {"permission", "role", "field", "inputarguments", "outputarguments", "bypassbasicauthrestriction"}


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return str(data[key])
    return ""


def _redact_value(key: Any, value: Any) -> Any:
    if SECRET_KEY_RE.search(str(key)):
        return "[REDACTED]"
    if isinstance(value, str):
        return _redact_line(value)
    return value


def _redact_line(value: str) -> str:
    value = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value, flags=re.I)
    value = re.sub(r"(?i)(password|secret|token|client_secret|authorization)([\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+", r"\1\2[REDACTED]", value)
    return value


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag
