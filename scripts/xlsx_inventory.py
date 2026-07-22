import re
import posixpath
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET


_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_VERSION_RE = re.compile(r"\d")
_CELL_COLUMN_RE = re.compile(r"([A-Z]+)", re.I)
_SEMVER_RE = re.compile(r"\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?")
_PACKAGE_NAME_PATTERN = (
    r"UiPath\.(?:[A-Za-z0-9_.-]+\.Activities(?:\.Runtime)?|DocumentUnderstanding\.ML)"
)
_JSON_DEPENDENCY_RE = re.compile(
    rf'["\'](?P<package>{_PACKAGE_NAME_PATTERN})["\']\s*:\s*'
    rf'["\']\[?(?P<version>{_SEMVER_RE.pattern})\]?["\']',
    re.I,
)
_XML_DEPENDENCY_RE = re.compile(r"<dependency\b(?P<attributes>[^>]*)>", re.I)
_XML_ATTRIBUTE_RE = re.compile(r"(?P<name>id|version)\s*=\s*[\"'](?P<value>[^\"']+)[\"']", re.I)
_ASSEMBLY_REFERENCE_RE = re.compile(
    rf"(?P<package>{_PACKAGE_NAME_PATTERN})\s*,\s*Version=(?P<version>{_SEMVER_RE.pattern})",
    re.I,
)
_PACKAGE_TOKEN_RE = re.compile(_PACKAGE_NAME_PATTERN, re.I)
_EXTRACTED_ROOT_RE = re.compile(r"(?i)(?P<root>.*?_extracted)(?:/|$)")
_ARTIFACT_VERSION_RE = re.compile(r"^(?P<name>.+?)\.\d+(?:\.\d+){1,3}$")

_HEADER_ALIASES = {
    "automationprojectname": "project_name",
    "automationname": "project_name",
    "projectname": "project_name",
    "dependencyname": "dependency_name",
    "dependecyname": "dependency_name",
    "packagename": "dependency_name",
    "dependencyversion": "dependency_version",
    "dependecyversion": "dependency_version",
    "packageversion": "dependency_version",
    "studioversion": "studio_version",
    "projectcompatibility": "compatibility",
    "compatibility": "compatibility",
    "targetframework": "target_framework",
    "targetframeworktype": "target_framework",
    "workflowxamlpath": "workflow_path",
    "workflowpath": "workflow_path",
    "xamlpath": "workflow_path",
    "projectversion": "project_version",
    "sourceartifact": "source_artifact",
    "environmentname": "environment_name",
    "environment": "environment_name",
    "automationowner": "automation_owner",
    "owner": "automation_owner",
    "inventorydate": "inventory_date",
}
_REQUIRED_HEADERS = {"project_name", "dependency_name", "dependency_version"}
_PROJECT_FIELDS = (
    "studio_version",
    "compatibility",
    "target_framework",
    "project_version",
    "automation_owner",
    "inventory_date",
)

_EVIDENCE_HEADER_ALIASES = {
    **_HEADER_ALIASES,
    "parentfolder": "repository_name",
    "repository": "repository_name",
    "repositoryname": "repository_name",
    "repo": "repository_name",
    "projectfolder": "repository_name",
    "keyword": "package_hint",
    "dependency": "package_hint",
    "package": "package_hint",
    "filepath": "source_path",
    "sourcepath": "source_path",
    "artifactpath": "source_path",
    "path": "source_path",
    "filetype": "file_type",
    "linenumber": "source_line_number",
    "line": "source_line_number",
    "linecontent": "line_content",
    "content": "line_content",
    "match": "line_content",
    "matchedtext": "line_content",
    "context": "context",
    "surroundingtext": "context",
    "packageversion": "package_version",
    "dependencyversion": "package_version",
    "version": "package_version",
    "packagename": "package_hint",
    "dependencyname": "package_hint",
}

_EVIDENCE_CONTENT_FIELDS = {"line_content", "context"}
_EVIDENCE_PROVENANCE_FIELDS = {
    "source_path",
    "source_artifact",
    "repository_name",
    "project_name",
}


def scan_xlsx_workbook(
    path: Path,
    evidence_root: Path,
    xlsx_mode: str = "auto",
) -> dict[str, Any]:
    """Scan a structured inventory or conservatively extract evidence from tabular XLSX exports."""
    if xlsx_mode not in {"auto", "strict", "evidence"}:
        raise ValueError(f"Unsupported XLSX mode: {xlsx_mode}")
    relative_path = _relative(path, evidence_root)
    try:
        sheets = _read_workbook(path)
    except Exception as exc:  # noqa: BLE001 - workbook errors are surfaced as coverage gaps
        result = _empty_result()
        result["coverage_gaps"].append(
            _gap(relative_path, f"Could not read XLSX workbook: {exc}", feature="XLSX inventory")
        )
        result["diagnostics"] = _diagnostics([], "none")
        return result

    structured_matches = [
        (sheet, header)
        for sheet in sheets
        if (header := _find_header(sheet["rows"]))
        and _REQUIRED_HEADERS.issubset(set(header[1].values()))
    ]
    if xlsx_mode == "strict" or (xlsx_mode == "auto" and len(structured_matches) == 1):
        result = _scan_structured_workbook(path, evidence_root)
        result["diagnostics"] = _diagnostics(
            sheets,
            "structured" if structured_matches else "none",
            exact_dependencies_found=len(result["packages"]),
            ignored_sheets=[
                sheet["name"] for sheet in sheets if sheet not in [item[0] for item in structured_matches]
            ],
            unresolved_rows=len(result["coverage_gaps"]),
        )
        return result

    return _scan_evidence_workbook(path, evidence_root, sheets)


def _empty_result() -> dict[str, Any]:
    return {
        "projects": [],
        "packages": [],
        "products": [],
        "workflows": [],
        "xaml_references": [],
        "coverage_gaps": [],
        "errors": [],
    }


def _diagnostics(
    sheets: list[dict[str, Any]],
    extraction_method: str,
    exact_dependencies_found: int = 0,
    inferred_records_rejected: int = 0,
    ignored_sheets: list[str] | None = None,
    unresolved_rows: int = 0,
) -> dict[str, Any]:
    return {
        "workbooks_scanned": 1,
        "sheets_scanned": len(sheets),
        "rows_scanned": sum(len(sheet.get("rows", [])) for sheet in sheets),
        "extraction_method": extraction_method,
        "exact_dependencies_found": exact_dependencies_found,
        "inferred_records_rejected": inferred_records_rejected,
        "ignored_sheets": ignored_sheets or [],
        "unresolved_rows": unresolved_rows,
    }


def discover_xlsx(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".xlsx" else []
    return sorted(
        path
        for path in root.rglob("*.xlsx")
        if path.name.lower() != "uipath_deprecation_report.xlsx"
    )


def discover_legacy_xls(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".xls" else []
    return sorted(root.rglob("*.xls"))


def _scan_structured_workbook(path: Path, evidence_root: Path) -> dict[str, Any]:
    result: dict[str, list[dict[str, Any]]] = {
        "projects": [],
        "packages": [],
        "products": [],
        "workflows": [],
        "xaml_references": [],
        "coverage_gaps": [],
        "errors": [],
    }
    relative_path = _relative(path, evidence_root)
    try:
        sheets = _read_workbook(path)
    except Exception as exc:  # noqa: BLE001 - workbook errors are surfaced as coverage gaps
        result["coverage_gaps"].append(
            _gap(relative_path, f"Could not read XLSX workbook: {exc}", feature="XLSX inventory")
        )
        return result

    matching = []
    for sheet in sheets:
        header = _find_header(sheet["rows"])
        if header and _REQUIRED_HEADERS.issubset(set(header[1].values())):
            matching.append((sheet, header))
    if len(matching) != 1:
        message = (
            "No worksheet contains the required Automation / Project Name, Dependency Name, "
            "and Dependency Version headers."
            if not matching
            else "Multiple worksheets contain the required inventory headers; exactly one is allowed."
        )
        result["coverage_gaps"].append(_gap(relative_path, message, feature="XLSX worksheet selection"))
        return result

    sheet, (header_row_number, header_map) = matching[0]
    records: list[dict[str, Any]] = []
    for row_number, cells in sheet["rows"]:
        if row_number <= header_row_number:
            continue
        record = {
            field: _cell_value(cells.get(column_index))
            for column_index, field in header_map.items()
        }
        if not any(record.values()):
            continue
        record["row_number"] = row_number
        record["formula_missing"] = {
            field
            for column_index, field in header_map.items()
            if cells.get(column_index, {}).get("formula_missing")
        }
        project_name = record.get("project_name", "").strip()
        if not project_name:
            result["coverage_gaps"].append(
                _row_gap(relative_path, sheet["name"], row_number, "Automation / Project Name is required.")
            )
            continue
        record["project_name"] = project_name
        record["environment_name"] = record.get("environment_name", "").strip()
        record["inventory_key"] = _inventory_key(project_name, record["environment_name"])
        record["evidence"] = _evidence(relative_path, sheet["name"], record)
        for field in sorted(record["formula_missing"]):
            result["coverage_gaps"].append(
                _row_gap(
                    relative_path,
                    sheet["name"],
                    row_number,
                    f"{field.replace('_', ' ').title()} formula has no cached value.",
                )
            )
        records.append(record)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["inventory_key"]].append(record)

    package_records: dict[tuple[str, str], dict[str, Any]] = {}
    workflow_seen: set[tuple[str, str]] = set()
    xaml_seen: set[tuple[str, str, str]] = set()
    for inventory_key, unit_rows in grouped.items():
        first = unit_rows[0]
        metadata: dict[str, str] = {}
        conflicted_fields: set[str] = set()
        for field in _PROJECT_FIELDS:
            values = sorted({row.get(field, "").strip() for row in unit_rows if row.get(field, "").strip()})
            if len(values) > 1:
                result["coverage_gaps"].append(
                    _gap(
                        relative_path,
                        f"Conflicting {field.replace('_', ' ')} values for {first['project_name']}"
                        f"{_environment_suffix(first['environment_name'])}; the affected check was suppressed.",
                        feature=field,
                    )
                )
                conflicted_fields.add(field)
                metadata[field] = ""
            else:
                metadata[field] = values[0] if values else ""

        compatibility = _normalize_compatibility(metadata["compatibility"])
        if metadata["compatibility"] and compatibility == "unknown":
            result["coverage_gaps"].append(
                _gap(relative_path, f"Invalid Project Compatibility value '{metadata['compatibility']}'.", feature="project compatibility")
            )
        elif not metadata["compatibility"] and "compatibility" not in conflicted_fields:
            compatibility = _compatibility_from_framework(metadata["target_framework"])
        if compatibility == "unknown":
            result["coverage_gaps"].append(
                _gap(
                    relative_path,
                    f"Project compatibility is unknown for {first['project_name']}"
                    f"{_environment_suffix(first['environment_name'])}; Windows-Legacy-only rules were excluded.",
                    feature="project compatibility",
                )
            )

        studio_version = metadata["studio_version"]
        if studio_version and not _VERSION_RE.search(studio_version):
            result["coverage_gaps"].append(
                _gap(relative_path, f"Studio Version '{studio_version}' has no numeric component.", feature="Studio version")
            )
            studio_version = ""
        if not studio_version:
            result["coverage_gaps"].append(
                _gap(
                    relative_path,
                    f"Studio Version is unavailable for {first['project_name']}"
                    f"{_environment_suffix(first['environment_name'])}; Studio lifecycle coverage was skipped.",
                    feature="Studio version",
                )
            )

        inventory_date = metadata["inventory_date"]
        if inventory_date:
            try:
                date.fromisoformat(inventory_date)
            except ValueError:
                result["coverage_gaps"].append(
                    _gap(relative_path, f"Inventory Date '{inventory_date}' is not a valid YYYY-MM-DD date.", feature="inventory date")
                )
                inventory_date = ""

        project = {
            "name": first["project_name"],
            "inventory_key": inventory_key,
            "environment_name": first["environment_name"],
            "description": "",
            "version": metadata["project_version"],
            "path": relative_path,
            "source": "xlsx",
            "compatibility": compatibility,
            "target_framework": metadata["target_framework"],
            "automation_owner": metadata["automation_owner"],
            "inventory_date": inventory_date,
            "xaml_files": [],
        }
        result["projects"].append(project)
        if studio_version:
            result["products"].append(
                {
                    "product": "Studio",
                    "version": studio_version,
                    "project_name": first["project_name"],
                    "inventory_key": inventory_key,
                    "environment": first["environment_name"] or first["project_name"],
                    "automation_owner": metadata["automation_owner"],
                    "source": "xlsx",
                    "confidence": "high",
                    "evidence": sorted({row["evidence"] for row in unit_rows if row.get("studio_version")}),
                }
            )

        for row in unit_rows:
            dependency_name = row.get("dependency_name", "").strip()
            dependency_version = row.get("dependency_version", "").strip()
            workflow_path = row.get("workflow_path", "").strip()
            if not dependency_name and not dependency_version:
                continue
            if not dependency_name:
                result["coverage_gaps"].append(
                    _row_gap(relative_path, sheet["name"], row["row_number"], "Dependency Name is required when Dependency Version is populated.")
                )
                continue

            version_reliable = bool(dependency_version and _VERSION_RE.search(dependency_version))
            if "dependency_version" in row["formula_missing"]:
                version_reliable = False
            elif not dependency_version:
                result["coverage_gaps"].append(
                    _row_gap(relative_path, sheet["name"], row["row_number"], "Dependency Version is missing; only package-wide rules can be evaluated.")
                )
            elif not version_reliable:
                result["coverage_gaps"].append(
                    _row_gap(relative_path, sheet["name"], row["row_number"], f"Dependency Version '{dependency_version}' has no numeric component; only package-wide rules can be evaluated.")
                )

            key = (inventory_key, dependency_name.lower())
            package = package_records.get(key)
            candidate_version = dependency_version if version_reliable else ""
            if package is None:
                package = {
                    "project_name": first["project_name"],
                    "inventory_key": inventory_key,
                    "environment_name": first["environment_name"],
                    "automation_owner": metadata["automation_owner"],
                    "package_name": dependency_name,
                    "version": candidate_version,
                    "version_reliable": version_reliable,
                    "source": "xlsx",
                    "project_compatibility": compatibility,
                    "evidence": [row["evidence"]],
                    "workflow_evidence": [],
                    "evidence_kind": "structured_inventory",
                    "evidence_confidence": "high" if workflow_path else "medium",
                    "repository_name": "",
                    "source_line_number": "",
                }
                package_records[key] = package
            else:
                package["evidence"] = sorted(set(package["evidence"]) | {row["evidence"]})
                if candidate_version and package.get("version") and candidate_version != package["version"]:
                    package["version"] = ""
                    package["version_reliable"] = False
                    package["version_ambiguous"] = True
                    result["coverage_gaps"].append(
                        _gap(
                            relative_path,
                            f"Conflicting versions were supplied for {dependency_name} in {first['project_name']}"
                            f"{_environment_suffix(first['environment_name'])}; only package-wide rules can be evaluated.",
                            feature=dependency_name,
                        )
                    )
                elif candidate_version and not package.get("version") and not package.get("version_ambiguous"):
                    package["version"] = candidate_version
                    package["version_reliable"] = True

            if workflow_path:
                package["workflow_evidence"] = sorted(set(package["workflow_evidence"]) | {workflow_path})
                workflow_key = (inventory_key, workflow_path.lower())
                if workflow_key not in workflow_seen:
                    workflow_seen.add(workflow_key)
                    result["workflows"].append(
                        {
                            "project_name": first["project_name"],
                            "inventory_key": inventory_key,
                            "path": workflow_path,
                            "source": "xlsx",
                        }
                    )
                xaml_key = (inventory_key, dependency_name.lower(), workflow_path.lower())
                if xaml_key not in xaml_seen:
                    xaml_seen.add(xaml_key)
                    result["xaml_references"].append(
                        {
                            "project_name": first["project_name"],
                            "inventory_key": inventory_key,
                            "package_name": dependency_name,
                            "path": workflow_path,
                        }
                    )

    result["packages"] = list(package_records.values())
    return result


def _scan_evidence_workbook(
    path: Path,
    evidence_root: Path,
    sheets: list[dict[str, Any]],
) -> dict[str, Any]:
    result = _empty_result()
    relative_path = _relative(path, evidence_root)
    relevant: list[tuple[dict[str, Any], tuple[int, dict[int, str]]]] = []
    ignored_sheets: list[str] = []
    for sheet in sheets:
        header = _find_evidence_header(sheet["rows"])
        if header and _evidence_sheet_has_uipath_rows(sheet["rows"], header):
            relevant.append((sheet, header))
        else:
            ignored_sheets.append(sheet["name"])

    package_records: dict[tuple[str, str], dict[str, Any]] = {}
    projects: dict[str, dict[str, Any]] = {}
    products: dict[tuple[str, str], dict[str, Any]] = {}
    workflows: dict[tuple[str, str], dict[str, Any]] = {}
    xaml_references: dict[tuple[str, str, str], dict[str, Any]] = {}
    rejected: set[tuple[str, str, str]] = set()
    exact_dependencies_found = 0
    inferred_records_rejected = 0
    unresolved_rows: set[tuple[str, int]] = set()

    for sheet, (header_row_number, header_map) in relevant:
        for row_number, cells in sheet["rows"]:
            if row_number <= header_row_number:
                continue
            row = {
                field: _cell_value(cells.get(column_index))
                for column_index, field in header_map.items()
            }
            if not any(row.values()):
                continue
            row["row_number"] = row_number
            row["formula_missing"] = {
                field
                for column_index, field in header_map.items()
                if cells.get(column_index, {}).get("formula_missing")
            }
            for field in sorted(row["formula_missing"]):
                result["coverage_gaps"].append(
                    _row_gap(
                        relative_path,
                        sheet["name"],
                        row_number,
                        f"{field.replace('_', ' ').title()} formula has no cached value.",
                    )
                )

            identity = _evidence_identity(path, relative_path, row)
            compatibility, target_framework = _evidence_compatibility(row)
            environment = row.get("environment_name", "").strip()
            automation_owner = row.get("automation_owner", "").strip()
            project = projects.setdefault(
                identity["inventory_key"],
                {
                    "name": identity["project_name"],
                    "inventory_key": identity["inventory_key"],
                    "environment_name": environment,
                    "description": "",
                    "version": row.get("project_version", "").strip(),
                    "path": identity["source_artifact"] or relative_path,
                    "source": "xlsx_evidence",
                    "compatibility": compatibility,
                    "target_framework": target_framework,
                    "automation_owner": automation_owner,
                    "inventory_date": row.get("inventory_date", "").strip(),
                    "repository_name": identity["repository_name"],
                    "xaml_files": [],
                },
            )
            if project["compatibility"] == "unknown" and compatibility != "unknown":
                project["compatibility"] = compatibility
                project["target_framework"] = target_framework

            studio_version = row.get("studio_version", "").strip()
            if studio_version and _VERSION_RE.search(studio_version):
                product_key = (identity["inventory_key"], studio_version)
                products[product_key] = {
                    "product": "Studio",
                    "version": studio_version,
                    "project_name": identity["project_name"],
                    "inventory_key": identity["inventory_key"],
                    "environment": environment or identity["project_name"],
                    "automation_owner": automation_owner,
                    "source": "xlsx_evidence",
                    "confidence": "medium",
                    "evidence": [
                        _evidence_row(
                            relative_path, sheet["name"], row_number, row, identity, "studio_version"
                        )
                    ],
                }

            workflow_path = row.get("workflow_path", "").strip()
            source_path = row.get("source_path", "").strip() or row.get("source_artifact", "").strip()
            if not workflow_path and source_path.lower().endswith(".xaml"):
                workflow_path = source_path
            if workflow_path:
                workflow_key = (identity["inventory_key"], workflow_path.lower())
                workflows[workflow_key] = {
                    "project_name": identity["project_name"],
                    "inventory_key": identity["inventory_key"],
                    "path": workflow_path,
                    "source": "xlsx_evidence",
                }
                if workflow_path not in project["xaml_files"]:
                    project["xaml_files"].append(workflow_path)

            text_fields = [
                row.get("line_content", ""),
                row.get("context", ""),
            ]
            combined_text = "\n".join(value for value in text_fields if value)
            extracted = _extract_dependencies(combined_text)
            package_hint = _canonical_package_name(row.get("package_hint", ""))
            package_version = _clean_version(row.get("package_version", ""))
            if package_hint and package_version:
                extracted.append((package_hint, package_version, "split_columns"))

            row_seen: set[tuple[str, str, str]] = set()
            accepted_packages: set[str] = set()
            for package_name, version, evidence_kind in extracted:
                candidate_key = (package_name.lower(), version, evidence_kind)
                if candidate_key in row_seen:
                    continue
                row_seen.add(candidate_key)
                if package_name.lower().endswith(".runtime"):
                    inferred_records_rejected += _reject_evidence_once(
                        result,
                        rejected,
                        relative_path,
                        sheet["name"],
                        row_number,
                        identity,
                        package_name,
                        "runtime_dependency",
                        "Runtime-only package evidence cannot be mapped to a base activity-package lifecycle rule safely.",
                    )
                    unresolved_rows.add((sheet["name"], row_number))
                    continue
                if not _SEMVER_RE.fullmatch(version):
                    inferred_records_rejected += _reject_evidence_once(
                        result,
                        rejected,
                        relative_path,
                        sheet["name"],
                        row_number,
                        identity,
                        package_name,
                        "malformed_version",
                        f"Package version '{version}' is not a supported numeric version.",
                    )
                    unresolved_rows.add((sheet["name"], row_number))
                    continue

                accepted_packages.add(package_name.lower())
                exact_dependencies_found += 1
                evidence = _evidence_row(
                    relative_path, sheet["name"], row_number, row, identity, evidence_kind
                )
                key = (identity["inventory_key"], package_name.lower())
                package = package_records.get(key)
                if package is None:
                    package = {
                        "project_name": identity["project_name"],
                        "inventory_key": identity["inventory_key"],
                        "environment_name": environment,
                        "automation_owner": automation_owner,
                        "package_name": package_name,
                        "version": version,
                        "version_reliable": True,
                        "source": "xlsx_evidence",
                        "project_compatibility": compatibility,
                        "evidence": [evidence],
                        "workflow_evidence": [workflow_path] if workflow_path else [],
                        "evidence_kind": evidence_kind,
                        "evidence_confidence": "medium",
                        "repository_name": identity["repository_name"],
                        "source_line_number": row.get("source_line_number", "").strip(),
                    }
                    package_records[key] = package
                else:
                    package["evidence"] = sorted(set(package["evidence"]) | {evidence})
                    if (
                        package.get("project_compatibility") == "unknown"
                        and compatibility != "unknown"
                    ):
                        package["project_compatibility"] = compatibility
                    if workflow_path:
                        package["workflow_evidence"] = sorted(
                            set(package.get("workflow_evidence", [])) | {workflow_path}
                        )
                    if package.get("version") and package["version"] != version:
                        package["version"] = ""
                        package["version_reliable"] = False
                        package["version_ambiguous"] = True
                        result["coverage_gaps"].append(
                            _gap(
                                identity["source_artifact"] or relative_path,
                                f"Conflicting versions were extracted for {package_name} in "
                                f"{identity['project_name']}; version-scoped checks were suppressed.",
                                feature=package_name,
                            )
                        )
                    elif not package.get("version") and not package.get("version_ambiguous"):
                        package["version"] = version
                        package["version_reliable"] = True

                if workflow_path:
                    ref_key = (identity["inventory_key"], package_name.lower(), workflow_path.lower())
                    xaml_references[ref_key] = {
                        "project_name": identity["project_name"],
                        "inventory_key": identity["inventory_key"],
                        "package_name": package_name,
                        "path": workflow_path,
                    }

            for assembly in _ASSEMBLY_REFERENCE_RE.finditer(combined_text):
                package_name = _canonical_package_name(assembly.group("package"))
                if package_name.lower() in accepted_packages:
                    continue
                inferred_records_rejected += _reject_evidence_once(
                    result,
                    rejected,
                    relative_path,
                    sheet["name"],
                    row_number,
                    identity,
                    package_name,
                    "assembly_reference",
                    "Assembly type evidence is not proof of an installed NuGet dependency.",
                )
                unresolved_rows.add((sheet["name"], row_number))

            tokens = {_canonical_package_name(match.group(0)) for match in _PACKAGE_TOKEN_RE.finditer(combined_text)}
            if tokens and not extracted and not list(_ASSEMBLY_REFERENCE_RE.finditer(combined_text)):
                unresolved_rows.add((sheet["name"], row_number))
                for package_name in tokens:
                    inferred_records_rejected += _reject_evidence_once(
                        result,
                        rejected,
                        relative_path,
                        sheet["name"],
                        row_number,
                        identity,
                        package_name,
                        "unresolved_package",
                        "A UiPath package name was present, but no exact dependency version could be extracted.",
                    )

    result["projects"] = list(projects.values()) if package_records or products else []
    result["packages"] = list(package_records.values())
    result["products"] = list(products.values())
    result["workflows"] = list(workflows.values())
    result["xaml_references"] = list(xaml_references.values())
    if not relevant:
        result["coverage_gaps"].append(
            _gap(
                relative_path,
                "No worksheet contained both recognizable evidence-table headers and UiPath package evidence.",
                feature="XLSX evidence-table selection",
            )
        )
    elif not package_records:
        result["coverage_gaps"].append(
            _gap(
                relative_path,
                "Relevant XLSX evidence was found, but no exact base package/version dependency could be extracted.",
                feature="XLSX evidence extraction",
            )
        )
    else:
        unknown_compatibility = sum(
            1 for project in projects.values() if project.get("compatibility") == "unknown"
        )
        if unknown_compatibility:
            result["coverage_gaps"].append(
                _gap(
                    relative_path,
                    f"Project compatibility is unknown for {unknown_compatibility} extracted artifacts; "
                    "Windows-Legacy-only rules were excluded for those artifacts.",
                    feature="project compatibility",
                )
            )
        if not products:
            result["coverage_gaps"].append(
                _gap(
                    relative_path,
                    "The evidence workbook does not provide Studio or Robot versions; product lifecycle coverage was skipped.",
                    feature="Studio/Robot versions",
                )
            )
        result["coverage_gaps"].append(
            _gap(
                relative_path,
                "Evidence-table extraction is partial: only package/version declarations visible in the workbook were assessed.",
                feature="XLSX inventory completeness",
            )
        )

    result["diagnostics"] = _diagnostics(
        sheets,
        "evidence" if relevant else "none",
        exact_dependencies_found=exact_dependencies_found,
        inferred_records_rejected=inferred_records_rejected,
        ignored_sheets=ignored_sheets,
        unresolved_rows=len(unresolved_rows),
    )
    return result


def _find_evidence_header(
    rows: list[tuple[int, dict[int, dict[str, Any]]]],
) -> tuple[int, dict[int, str]] | None:
    best: tuple[int, dict[int, str]] | None = None
    best_score = 0
    populated = 0
    for row_number, cells in rows:
        if not any(_cell_value(cell) for cell in cells.values()):
            continue
        populated += 1
        if populated > 50:
            break
        header_map: dict[int, str] = {}
        for column_index, cell in cells.items():
            field = _EVIDENCE_HEADER_ALIASES.get(_normalize_header(_cell_value(cell)))
            if field and field not in header_map.values():
                header_map[column_index] = field
        fields = set(header_map.values())
        has_content = bool(fields & _EVIDENCE_CONTENT_FIELDS) or {
            "package_hint",
            "package_version",
        }.issubset(fields)
        has_provenance = bool(fields & _EVIDENCE_PROVENANCE_FIELDS)
        score = len(fields) if has_content and has_provenance else 0
        if score > best_score:
            best = (row_number, header_map)
            best_score = score
    return best


def _evidence_sheet_has_uipath_rows(
    rows: list[tuple[int, dict[int, dict[str, Any]]]],
    header: tuple[int, dict[int, str]],
) -> bool:
    header_row, header_map = header
    for row_number, cells in rows:
        if row_number <= header_row:
            continue
        values = [_cell_value(cells.get(column)) for column in header_map]
        if _PACKAGE_TOKEN_RE.search("\n".join(values)):
            return True
    return False


def _extract_dependencies(text: str) -> list[tuple[str, str, str]]:
    dependencies: list[tuple[str, str, str]] = []
    for match in _JSON_DEPENDENCY_RE.finditer(text):
        dependencies.append(
            (
                _canonical_package_name(match.group("package")),
                _clean_version(match.group("version")),
                "json_dependency",
            )
        )
    for tag in _XML_DEPENDENCY_RE.finditer(text):
        attributes = {
            item.group("name").lower(): item.group("value")
            for item in _XML_ATTRIBUTE_RE.finditer(tag.group("attributes"))
        }
        package_name = _canonical_package_name(attributes.get("id", ""))
        version = _clean_version(attributes.get("version", ""))
        if package_name and version:
            dependencies.append((package_name, version, "nuget_dependency"))
    return dependencies


def _canonical_package_name(value: str) -> str:
    match = _PACKAGE_TOKEN_RE.search(str(value or ""))
    if not match:
        return ""
    package = match.group(0)
    return "UiPath." + package[len("UiPath.") :]


def _clean_version(value: str) -> str:
    match = _SEMVER_RE.search(str(value or ""))
    return match.group(0) if match else ""


def _evidence_identity(path: Path, relative_path: str, row: dict[str, Any]) -> dict[str, str]:
    repository_name = row.get("repository_name", "").strip()
    explicit_project = row.get("project_name", "").strip()
    source_path = row.get("source_path", "").strip() or row.get("source_artifact", "").strip()
    normalized_path = source_path.replace("\\", "/")
    extracted_match = _EXTRACTED_ROOT_RE.search(normalized_path)
    source_artifact = extracted_match.group("root") if extracted_match else source_path
    artifact_label = PurePosixPath(source_artifact.replace("\\", "/")).name if source_artifact else ""
    if artifact_label.lower().endswith("_extracted"):
        artifact_label = artifact_label[: -len("_extracted")]
    project_match = _ARTIFACT_VERSION_RE.match(artifact_label)
    derived_project = project_match.group("name") if project_match else artifact_label
    project_name = explicit_project or derived_project or repository_name or path.stem
    environment = row.get("environment_name", "").strip()
    identity_parts = [repository_name or project_name, source_artifact or project_name, environment]
    inventory_key = "::".join(_normalize_header(part) for part in identity_parts if part)
    return {
        "project_name": project_name,
        "inventory_key": inventory_key or _normalize_header(project_name),
        "repository_name": repository_name,
        "source_artifact": source_artifact or relative_path,
    }


def _evidence_compatibility(row: dict[str, Any]) -> tuple[str, str]:
    explicit = row.get("compatibility", "").strip()
    if explicit:
        return _normalize_compatibility(explicit), row.get("target_framework", "").strip()
    target_framework = row.get("target_framework", "").strip()
    source_path = row.get("source_path", "").strip() or row.get("source_artifact", "").strip()
    if not target_framework:
        match = re.search(
            r"(?i)(?:^|[/\\])(net(?:45|461|462|472|48|standard\d+(?:\.\d+)?|[678](?:\.\d+)?(?:-windows[^/\\]*)?))(?:[/\\]|$)",
            source_path,
        )
        target_framework = match.group(1) if match else ""
    return _compatibility_from_framework(target_framework), target_framework


def _evidence_row(
    relative_path: str,
    sheet_name: str,
    row_number: int,
    row: dict[str, Any],
    identity: dict[str, str],
    evidence_kind: str,
) -> str:
    details = [f"{relative_path}!/{sheet_name}/row {row_number}"]
    source_path = row.get("source_path", "").strip() or row.get("source_artifact", "").strip()
    if source_path:
        details.append(f"source={source_path}")
    if row.get("source_line_number", "").strip():
        details.append(f"line={row['source_line_number'].strip()}")
    if identity["repository_name"]:
        details.append(f"repository={identity['repository_name']}")
    details.append(f"method={evidence_kind}")
    return "; ".join(details)


def _reject_evidence_once(
    result: dict[str, Any],
    rejected: set[tuple[str, str, str]],
    relative_path: str,
    sheet_name: str,
    row_number: int,
    identity: dict[str, str],
    package_name: str,
    evidence_kind: str,
    reason: str,
) -> int:
    key = (identity["inventory_key"], package_name.lower(), evidence_kind)
    if key in rejected:
        return 0
    rejected.add(key)
    result["coverage_gaps"].append(
        _gap(
            f"{relative_path}!/{sheet_name}/row {row_number}",
            f"{package_name}: {reason}",
            feature=evidence_kind,
        )
    )
    return 1


def unsupported_xls_gap(path: Path, evidence_root: Path) -> dict[str, Any]:
    return _gap(
        _relative(path, evidence_root),
        "Legacy .xls input is not supported. Convert the workbook to .xlsx and run the analyzer again.",
        feature="legacy XLS inventory",
    )


def _read_workbook(path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        shared_strings = _shared_strings(zf)
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        relationships = _workbook_relationships(zf)
        sheets = []
        for sheet in workbook.iter():
            if _local_name(sheet.tag) != "sheet" or sheet.attrib.get("state", "visible") != "visible":
                continue
            relationship_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
            target = relationships.get(relationship_id or "")
            if not target:
                continue
            xml_path = _worksheet_path(target)
            rows = _read_worksheet(zf.read(xml_path), shared_strings)
            sheets.append({"name": sheet.attrib.get("name", "Worksheet"), "rows": rows})
        return sheets


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t") for item in root if _local_name(item.tag) == "si"]


def _workbook_relationships(zf: zipfile.ZipFile) -> dict[str, str]:
    root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    return {
        item.attrib.get("Id", ""): item.attrib.get("Target", "")
        for item in root
        if _local_name(item.tag) == "Relationship"
    }


def _worksheet_path(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(str(PurePosixPath("xl") / target))


def _read_worksheet(raw_xml: bytes, shared_strings: list[str]) -> list[tuple[int, dict[int, dict[str, Any]]]]:
    root = ET.fromstring(raw_xml)
    rows = []
    for row in root.iter():
        if _local_name(row.tag) != "row":
            continue
        row_number = int(row.attrib.get("r", len(rows) + 1))
        cells: dict[int, dict[str, Any]] = {}
        for cell in row:
            if _local_name(cell.tag) != "c":
                continue
            column_index = _column_index(cell.attrib.get("r", "A1"))
            cell_type = cell.attrib.get("t", "")
            formula = next((node for node in cell if _local_name(node.tag) == "f"), None)
            value_node = next((node for node in cell if _local_name(node.tag) == "v"), None)
            if cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter() if _local_name(node.tag) == "t")
            else:
                value = value_node.text if value_node is not None and value_node.text is not None else ""
                if cell_type == "s" and value:
                    index = int(value)
                    value = shared_strings[index] if index < len(shared_strings) else ""
            cells[column_index] = {
                "value": str(value).strip(),
                "formula_missing": formula is not None
                and (value_node is None or value_node.text is None),
            }
        rows.append((row_number, cells))
    return rows


def _find_header(rows: list[tuple[int, dict[int, dict[str, Any]]]]) -> tuple[int, dict[int, str]] | None:
    populated = 0
    for row_number, cells in rows:
        if not any(_cell_value(cell) for cell in cells.values()):
            continue
        populated += 1
        if populated > 50:
            break
        header_map: dict[int, str] = {}
        duplicate = False
        for column_index, cell in cells.items():
            field = _HEADER_ALIASES.get(_normalize_header(_cell_value(cell)))
            if not field:
                continue
            if field in header_map.values():
                duplicate = True
                break
            header_map[column_index] = field
        if not duplicate and _REQUIRED_HEADERS.issubset(set(header_map.values())):
            return row_number, header_map
    return None


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _cell_value(cell: dict[str, Any] | None) -> str:
    return str((cell or {}).get("value", "")).strip()


def _column_index(reference: str) -> int:
    match = _CELL_COLUMN_RE.match(reference)
    letters = match.group(1).upper() if match else "A"
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - ord("A") + 1
    return value - 1


def _inventory_key(project_name: str, environment_name: str) -> str:
    return f"{project_name.strip().lower()}::{environment_name.strip().lower()}"


def _normalize_compatibility(value: str) -> str:
    normalized = re.sub(r"[^a-z]", "", value.lower())
    if normalized in {"windowslegacy", "legacy"}:
        return "windows_legacy"
    if normalized in {"crossplatform", "cross", "portable"}:
        return "cross_platform"
    if normalized == "windows":
        return "windows"
    return "unknown"


def _compatibility_from_framework(framework: str) -> str:
    raw = framework.lower()
    if any(token in raw for token in ("legacy", "net45", "net461", "net462", "net472", "net48")):
        return "windows_legacy"
    if "netstandard" in raw or "cross" in raw or "portable" in raw:
        return "cross_platform"
    if any(token in raw for token in ("windows", "net6", "net7", "net8")):
        return "windows"
    return "unknown"


def _evidence(relative_path: str, sheet_name: str, record: dict[str, Any]) -> str:
    details = [f"{relative_path}!/{sheet_name}/row {record['row_number']}"]
    if record.get("source_artifact"):
        details.append(f"source={record['source_artifact']}")
    if record.get("workflow_path"):
        details.append(f"workflow={record['workflow_path']}")
    return "; ".join(details)


def _gap(path: str, message: str, feature: str) -> dict[str, Any]:
    return {
        "type": "client_inventory",
        "product": "Studio/Robot activity packages",
        "feature": feature,
        "path": path,
        "message": message,
    }


def _row_gap(path: str, sheet: str, row: int, message: str) -> dict[str, Any]:
    return _gap(f"{path}!/{sheet}/row {row}", message, feature="XLSX row validation")


def _environment_suffix(environment: str) -> str:
    return f" in environment {environment}" if environment else ""


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag
