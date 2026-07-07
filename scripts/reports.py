import csv
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


def build_report_payload(
    inventory: dict[str, Any],
    timeline_entries: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    analysis_date: str,
) -> dict[str, Any]:
    class_counts = Counter(finding["classification"] for finding in findings)
    risk_counts = Counter(finding["risk_level"] for finding in findings)
    return {
        "analysis_date": analysis_date,
        "summary": {
            "total_projects_scanned": len(inventory.get("projects", [])),
            "total_packages_scanned": len(inventory.get("package_inventory", [])),
            "total_timeline_package_entries": len(timeline_entries),
            "total_findings": len(findings),
            "classification_counts": dict(class_counts),
            "risk_counts": dict(risk_counts),
            "manual_review_count": sum(
                1 for finding in findings if not finding.get("replacement_package")
            ),
        },
        "projects": inventory.get("projects", []),
        "package_inventory": inventory.get("package_inventory", []),
        "timeline_entries": timeline_entries,
        "findings": findings,
        "manual_review": [
            finding for finding in findings if not finding.get("replacement_package")
        ],
        "remediation_roadmap": _roadmap(findings),
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    findings = payload.get("findings", [])
    lines = [
        "# UiPath Deprecation Analysis Report",
        "",
        "## Executive Summary",
        "",
        f"- Analysis date: {payload['analysis_date']}",
        f"- Projects scanned: {summary['total_projects_scanned']}",
        f"- Packages scanned: {summary['total_packages_scanned']}",
        f"- Timeline package entries considered: {summary['total_timeline_package_entries']}",
        f"- Findings: {summary['total_findings']}",
        "",
        "## Highest-Risk Findings",
        "",
    ]
    high_risk = [
        finding
        for finding in findings
        if finding.get("risk_level") in {"Critical", "High"}
    ]
    lines.extend(_finding_bullets(high_risk[:10]))
    for classification in (
        "Already Removed",
        "Removal Imminent",
        "Removal Scheduled",
        ".NET Framework 4.6.1 / Windows-Legacy Compatibility Impact",
    ):
        lines.extend(["", f"## {classification}", ""])
        lines.extend(
            _finding_bullets(
                [f for f in findings if f.get("classification") == classification]
            )
        )
    lines.extend(["", "## Replacement Mapping", ""])
    if findings:
        for finding in findings:
            replacement = finding.get("replacement_package") or "No direct replacement stated - review manually."
            lines.append(f"- {finding['package_name']}: {replacement}")
    else:
        lines.append("- No replacement mappings needed.")
    lines.extend(["", "## Windows-Legacy Impact", ""])
    legacy_findings = [
        f
        for f in findings
        if f.get("project_compatibility") == "windows_legacy"
        or f.get("compatibility_scope") == "windows_legacy_only"
    ]
    lines.extend(_finding_bullets(legacy_findings))
    lines.extend(["", "## Manual Review", ""])
    lines.extend(_finding_bullets(payload.get("manual_review", [])))
    lines.extend(["", "## Remediation Roadmap", ""])
    for item in payload.get("remediation_roadmap", []):
        lines.append(f"- {item['timeframe']}: {item['action']} ({item['count']} findings)")
    lines.extend(["", "## Assumptions and Confidence Notes", ""])
    lines.append("- Only NuGet/activity package timeline entries are considered.")
    lines.append("- Recommendations use UiPath-documented replacements when present.")
    lines.append("- Effort and value estimates are conservative and evidence-based.")
    return "\n".join(lines) + "\n"


def write_reports(
    payload: dict[str, Any],
    output_dir: Path | str,
    formats: list[str],
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    normalized = {fmt.lower() for fmt in formats}
    if "all" in normalized:
        normalized = {"markdown", "json", "csv", "xlsx"}
    paths: dict[str, str] = {}
    if "markdown" in normalized or "md" in normalized:
        path = out / "uipath_deprecation_report.md"
        path.write_text(render_markdown_report(payload), encoding="utf-8")
        paths["markdown"] = str(path)
    if "json" in normalized:
        path = out / "uipath_deprecation_findings.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        paths["json"] = str(path)
    if "csv" in normalized:
        path = out / "uipath_deprecation_findings.csv"
        _write_findings_csv(payload, path)
        paths["csv"] = str(path)
    if "xlsx" in normalized or "excel" in normalized:
        path = out / "uipath_deprecation_report.xlsx"
        _write_excel(payload, path)
        paths["xlsx"] = str(path)
    return paths


def _finding_bullets(findings: list[dict[str, Any]]) -> list[str]:
    if not findings:
        return ["- None."]
    lines: list[str] = []
    for finding in findings:
        evidence = ", ".join(finding.get("evidence", [])) or "No evidence path captured"
        lines.append(
            f"- {finding.get('package_name')} in {finding.get('project_name')}: "
            f"{finding.get('risk_level')} risk, {finding.get('urgency')}. "
            f"{finding.get('recommendation')} Evidence: {evidence}"
        )
    return lines


def _roadmap(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        if finding.get("classification") == "Already Removed":
            buckets["Immediate"].append(finding)
        elif finding.get("classification") == "Removal Imminent":
            buckets["0-6 months"].append(finding)
        elif "Windows-Legacy" in finding.get("classification", ""):
            buckets["Compatibility migration"].append(finding)
        else:
            buckets["6-18 months"].append(finding)
    actions = {
        "Immediate": "Remediate removed packages first",
        "0-6 months": "Schedule near-term package migration",
        "Compatibility migration": "Plan Windows-Legacy to Windows/Cross-platform migration",
        "6-18 months": "Track planned remediation backlog",
    }
    return [
        {"timeframe": timeframe, "action": actions[timeframe], "count": len(items)}
        for timeframe, items in buckets.items()
    ]


def _write_findings_csv(payload: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "project_name",
        "package_name",
        "current_version",
        "classification",
        "risk_level",
        "urgency",
        "recommendation",
        "replacement_package",
        "deprecation_date",
        "removal_date",
        "confidence",
        "source_url",
        "evidence",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for finding in payload.get("findings", []):
            row = {name: finding.get(name, "") for name in fieldnames}
            row["evidence"] = "; ".join(finding.get("evidence", []))
            writer.writerow(row)


def _write_excel(payload: dict[str, Any], path: Path) -> None:
    try:
        import openpyxl
    except ImportError:
        _write_excel_stdlib(payload, path)
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    for key, value in payload["summary"].items():
        ws.append([key, json.dumps(value) if isinstance(value, dict) else value])
    _sheet_from_rows(wb, "Findings", payload.get("findings", []))
    _sheet_from_rows(wb, "Package Inventory", payload.get("package_inventory", []))
    _sheet_from_rows(
        wb,
        "Replacement Mapping",
        [
            {
                "package_name": f.get("package_name"),
                "replacement_package": f.get("replacement_package")
                or "No direct replacement stated - review manually.",
                "recommendation": f.get("recommendation"),
            }
            for f in payload.get("findings", [])
        ],
    )
    _sheet_from_rows(
        wb,
        "Windows-Legacy Impact",
        [
            f
            for f in payload.get("findings", [])
            if f.get("compatibility_scope") == "windows_legacy_only"
            or f.get("project_compatibility") == "windows_legacy"
        ],
    )
    _sheet_from_rows(wb, "Manual Review", payload.get("manual_review", []))
    _sheet_from_rows(wb, "Remediation Roadmap", payload.get("remediation_roadmap", []))
    wb.save(path)


def _write_excel_stdlib(payload: dict[str, Any], path: Path) -> None:
    sheets = [
        ("Summary", [{"metric": key, "value": value} for key, value in payload["summary"].items()]),
        ("Findings", payload.get("findings", [])),
        ("Package Inventory", payload.get("package_inventory", [])),
        (
            "Replacement Mapping",
            [
                {
                    "package_name": f.get("package_name"),
                    "replacement_package": f.get("replacement_package")
                    or "No direct replacement stated - review manually.",
                    "recommendation": f.get("recommendation"),
                }
                for f in payload.get("findings", [])
            ],
        ),
        (
            "Windows-Legacy Impact",
            [
                f
                for f in payload.get("findings", [])
                if f.get("compatibility_scope") == "windows_legacy_only"
                or f.get("project_compatibility") == "windows_legacy"
            ],
        ),
        ("Manual Review", payload.get("manual_review", [])),
        ("Remediation Roadmap", payload.get("remediation_roadmap", [])),
    ]

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        zf.writestr("_rels/.rels", _root_rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml(sheets))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        for idx, (_title, rows) in enumerate(sheets, 1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _worksheet_xml(rows))


def _sheet_from_rows(workbook: Any, title: str, rows: list[dict[str, Any]]) -> None:
    ws = workbook.create_sheet(title[:31])
    if not rows:
        ws.append(["No records"])
        return
    keys = sorted({key for row in rows for key in row.keys()})
    ws.append(keys)
    for row in rows:
        ws.append([
            json.dumps(row.get(key)) if isinstance(row.get(key), (dict, list)) else row.get(key, "")
            for key in keys
        ])


def _content_types_xml(sheet_count: int) -> str:
    overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for idx in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  {overrides}
</Types>'''


def _root_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''


def _workbook_xml(sheets: list[tuple[str, list[dict[str, Any]]]]) -> str:
    sheet_xml = "\n".join(
        f'<sheet name="{escape(title[:31])}" sheetId="{idx}" r:id="rId{idx}"/>'
        for idx, (title, _rows) in enumerate(sheets, 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    {sheet_xml}
  </sheets>
</workbook>'''


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = "\n".join(
        f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>'
        for idx in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {rels}
</Relationships>'''


def _worksheet_xml(rows: list[dict[str, Any]]) -> str:
    if rows:
        keys = sorted({key for row in rows for key in row.keys()})
        table = [keys] + [
            [
                json.dumps(row.get(key)) if isinstance(row.get(key), (dict, list)) else row.get(key, "")
                for key in keys
            ]
            for row in rows
        ]
    else:
        table = [["No records"]]
    row_xml = "\n".join(
        f'<row r="{row_idx}">'
        + "".join(
            f'<c r="{_column_name(col_idx)}{row_idx}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            for col_idx, value in enumerate(row, 1)
        )
        + "</row>"
        for row_idx, row in enumerate(table, 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    {row_xml}
  </sheetData>
</worksheet>'''


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name
