import csv
import html
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Union
from xml.sax.saxutils import escape


_ACTION_PAGE_SIZE = 5


def build_report_payload(
    inventory: dict[str, Any],
    timeline_entries: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    analysis_date: str,
) -> dict[str, Any]:
    class_counts = Counter(finding["classification"] for finding in findings)
    risk_counts = Counter(finding["risk_level"] for finding in findings)
    timeline_warnings = sorted(
        {
            warning
            for entry in timeline_entries
            for warning in entry.get("normalization_warnings", [])
        }
    )
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
            "timeline_warning_count": len(timeline_warnings),
        },
        "timeline_warnings": timeline_warnings,
        "projects": inventory.get("projects", []),
        "package_inventory": inventory.get("package_inventory", []),
        "timeline_entries": timeline_entries,
        "findings": findings,
        "manual_review": [
            finding for finding in findings if not finding.get("replacement_package")
        ],
        "remediation_roadmap": _roadmap(findings),
    }


def build_common_report_payload(
    findings: list[dict[str, Any]],
    analysis_date: str,
    coverage_gaps: Optional[list[dict[str, Any]]] = None,
    inventory: Optional[dict[str, Any]] = None,
    raw_client_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    coverage_gaps = coverage_gaps or []
    severity_counts = Counter(finding.get("severity", "") for finding in findings)
    status_counts = Counter(finding.get("status", "") for finding in findings)
    domain_counts = Counter(finding.get("domain", "") for finding in findings)
    product_counts = Counter(finding.get("product", "") for finding in findings)
    total_saved = sum(
        float(finding.get("time_savings_kpi", {}).get("hours_saved", 0) or 0)
        for finding in findings
    )
    return {
        "analysis_date": analysis_date,
        "summary": {
            "total_findings": len(findings),
            "severity_counts": dict(severity_counts),
            "status_counts": dict(status_counts),
            "domain_counts": dict(domain_counts),
            "product_counts": dict(product_counts),
            "coverage_gap_count": len(coverage_gaps),
            "total_estimated_hours_saved": total_saved,
        },
        "findings": findings,
        "coverage_gaps": coverage_gaps,
        "inventory_summary": (inventory or {}).get("summary", {}),
        "raw_client_summary": (raw_client_payload or {}).get("summary", {}),
        "remediation_roadmap": _common_roadmap(findings),
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    if _is_common_payload(payload):
        return _render_common_markdown_report(payload)
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


def _render_common_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    findings = payload.get("findings", [])
    lines = [
        "# UiPath Deprecation Analysis Report",
        "",
        "## Executive Summary",
        "",
        f"- Analysis date: {payload['analysis_date']}",
        f"- Findings: {summary['total_findings']}",
        f"- Severity counts: {json.dumps(summary.get('severity_counts', {}), sort_keys=True)}",
        f"- Status counts: {json.dumps(summary.get('status_counts', {}), sort_keys=True)}",
        f"- Domain counts: {json.dumps(summary.get('domain_counts', {}), sort_keys=True)}",
        f"- Product counts: {json.dumps(summary.get('product_counts', {}), sort_keys=True)}",
        f"- Estimated hours saved: {summary.get('total_estimated_hours_saved', 0)}",
    ]
    decision_summary = payload.get("decision_summary", {})
    if decision_summary:
        lines.extend(
            [
                "",
                "## What Should We Fix First?",
                "",
                f"- What can break today: {decision_summary.get('what_can_break_today', 'Review critical findings.')}",
                f"- What must migrate next: {decision_summary.get('what_must_migrate_next', 'Review scheduled findings.')}",
                f"- Affected scope: {decision_summary.get('affected_scope', 'See finding evidence.')}",
                f"- Safest modernization sequence: {decision_summary.get('safest_modernization_sequence', 'Prioritize by severity and deadline.')}",
            ]
        )
    lines.extend(["", "## Highest-Risk Findings", ""])
    lines.extend(_common_finding_bullets([f for f in findings if f.get("severity") in {"critical", "high"}][:10]))
    for title, domain in (
        ("Client-Side Findings", "client"),
        ("Server-Side Findings", "server"),
        ("Mixed Findings", "mixed"),
    ):
        lines.extend(["", f"## {title}", ""])
        lines.extend(_common_finding_bullets([f for f in findings if f.get("domain") == domain]))
    lines.extend(["", "## Remediation Roadmap", ""])
    for item in payload.get("remediation_roadmap", []):
        lines.append(f"- {item['timeframe']}: {item['action']} ({item['count']} findings)")
    lines.extend(["", "## Time Savings KPI", ""])
    lines.append(f"- Estimated total hours saved: {summary.get('total_estimated_hours_saved', 0)}")
    lines.append("- KPI estimates are conservative and based on inventory review, source matching, and remediation planning effort.")
    lines.extend(["", "## Coverage Gaps", ""])
    if payload.get("coverage_gaps"):
        for gap in payload["coverage_gaps"]:
            lines.append(f"- {gap.get('product', 'Unknown')}: {gap.get('message', gap.get('feature', 'Missing context'))}")
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def write_reports(
    payload: dict[str, Any],
    output_dir: Union[Path, str],
    formats: list[str],
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    normalized = {fmt.lower() for fmt in formats}
    if "all" in normalized:
        normalized = {"markdown", "json", "csv", "xlsx", "html"}
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
    if "html" in normalized or "dashboard" in normalized:
        path = out / "uipath_deprecation_dashboard.html"
        path.write_text(render_html_dashboard_report(payload), encoding="utf-8")
        paths["html"] = str(path)
    return paths


def _is_common_payload(payload: dict[str, Any]) -> bool:
    return "domain_counts" in payload.get("summary", {})


def render_html_dashboard_report(payload: dict[str, Any]) -> str:
    findings = payload.get("findings", [])
    coverage_gaps = payload.get("coverage_gaps", [])
    summary = _dashboard_summary(payload)
    top_findings = _sort_findings_for_dashboard(findings)
    actions = _unique_recommended_actions(findings)
    analysis_date = payload.get("analysis_date", "")
    product_rows = _product_risk_rows(findings)
    timeline_items = _timeline_items(findings, analysis_date)
    summary_rail = _summary_rail_html(findings, product_rows, coverage_gaps, summary)
    product_options = _filter_options(row["product"] for row in product_rows)
    route_options = _filter_options(finding.get("recommended_skill") or finding.get("mitigation_route") for finding in findings)
    findings_data = _dashboard_json(_findings_dashboard_data(findings))
    coverage_gaps_data = _dashboard_json(_coverage_gaps_dashboard_data(coverage_gaps))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UiPath Deprecation Risk Command Center</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d9e1ec;
      --critical: #c7352b;
      --high: #e26c2d;
      --medium: #d7a514;
      --low: #3d79c7;
      --ok: #178064;
      --slate: #41516a;
      --soft-red: #fff0ee;
      --soft-orange: #fff4e8;
      --soft-yellow: #fff8db;
      --soft-blue: #edf5ff;
      --soft-green: #eaf8f2;
      --shadow: 0 14px 34px rgba(31, 45, 61, 0.10);
    }}
    * {{
      box-sizing: border-box;
    }}
    html {{
      scroll-behavior: smooth;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    header {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    .shell {{
      width: min(1560px, calc(100% - 40px));
      margin: 0 auto;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 24px;
      padding: 22px 0;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: clamp(24px, 3vw, 34px);
      line-height: 1.08;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      max-width: 780px;
    }}
    .scan-meta {{
      min-width: 236px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcff;
      color: var(--slate);
      font-size: 13px;
    }}
    main {{
      padding: 24px 0 34px;
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .kpi {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
      min-height: 108px;
    }}
    .kpi .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
      font-weight: 700;
    }}
    .kpi .value {{
      display: block;
      margin-top: 10px;
      font-size: 30px;
      line-height: 1;
      font-weight: 800;
    }}
    .kpi .note {{
      display: block;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .critical {{ color: var(--critical); }}
    .high {{ color: var(--high); }}
    .medium {{ color: var(--medium); }}
    .ok {{ color: var(--ok); }}
    .tabs {{
      display: flex;
      gap: 8px;
      margin: 12px 0 18px;
      flex-wrap: wrap;
    }}
    .tab {{
      border: 1px solid var(--line);
      background: #ffffff;
      border-radius: 8px;
      color: var(--slate);
      padding: 9px 12px;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
    }}
    .tab.active {{
      border-color: #26384f;
      background: #26384f;
      color: #ffffff;
    }}
    .tab:hover {{
      border-color: #26384f;
      color: #26384f;
    }}
    .tab.active:hover {{
      color: #ffffff;
    }}
    .tab:focus-visible {{
      outline: 3px solid rgba(61, 121, 199, 0.35);
      outline-offset: 2px;
    }}
    #overview,
    #findings,
    #timeline,
    #coverage,
    #ai-savings {{
      scroll-margin-top: 18px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
      min-width: 0;
    }}
    .panel h2 {{
      margin: 0 0 14px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .desktop-rail {{
      display: none;
    }}
    .summary-rail {{
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    .rail-block {{
      padding-bottom: 13px;
      border-bottom: 1px solid var(--line);
    }}
    .rail-block:last-child {{
      padding-bottom: 0;
      border-bottom: 0;
    }}
    .rail-label {{
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .03em;
      text-transform: uppercase;
    }}
    .rail-list {{
      display: grid;
      gap: 7px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .rail-item {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      min-width: 0;
      color: var(--slate);
      font-size: 13px;
    }}
    .rail-item strong,
    .rail-item span:first-child {{
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .rail-metric {{
      color: var(--ink);
      font-weight: 800;
      white-space: nowrap;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 150px 1fr 42px;
      gap: 12px;
      align-items: center;
      margin: 12px 0;
    }}
    .bar-label {{
      font-weight: 700;
      color: var(--slate);
      overflow-wrap: anywhere;
    }}
    .bar-track {{
      height: 14px;
      background: #edf1f6;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--critical), var(--high));
    }}
    .deadline {{
      font-weight: 800;
      color: var(--ink);
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .pill.critical {{ background: var(--soft-red); color: var(--critical); }}
    .pill.high {{ background: var(--soft-orange); color: var(--high); }}
    .pill.medium {{ background: var(--soft-yellow); color: #8a6500; }}
    .pill.low {{ background: var(--soft-blue); color: var(--low); }}
    .pill.ok {{ background: var(--soft-green); color: var(--ok); }}
    .pill.gray {{ background: #eef1f5; color: var(--slate); }}
    .timeline {{
      display: grid;
      gap: 12px;
    }}
    .timeline-item {{
      display: grid;
      grid-template-columns: minmax(56px, 72px) minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
      max-width: 100%;
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcff;
    }}
    .timeline-content {{
      min-width: 0;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .timeline-detail {{
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .toolbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }}
    .filter {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 9px 10px;
      color: var(--slate);
      min-width: 156px;
      font: inherit;
    }}
    .search-filter {{
      flex: 1 1 240px;
      min-width: 220px;
    }}
    .filter-status {{
      align-self: center;
      color: var(--muted);
      font-size: 13px;
      margin: 0;
    }}
    .view-toggle {{
      display: inline-flex;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #ffffff;
    }}
    .toggle-button,
    .page-button,
    .evidence-button,
    .expand-button,
    .icon-button {{
      border: 0;
      background: #ffffff;
      color: var(--slate);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    .toggle-button {{
      padding: 9px 11px;
    }}
    .toggle-button + .toggle-button {{
      border-left: 1px solid var(--line);
    }}
    .toggle-button[aria-pressed="true"] {{
      background: #26384f;
      color: #ffffff;
    }}
    .pagination {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-left: auto;
    }}
    .page-button,
    .evidence-button {{
      min-height: 36px;
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 7px;
    }}
    .page-button:hover:not(:disabled),
    .evidence-button:hover {{
      border-color: #26384f;
      color: #26384f;
    }}
    .page-button:disabled {{
      cursor: default;
      opacity: .45;
    }}
    .page-label {{
      min-width: 92px;
      color: var(--slate);
      text-align: center;
      font-size: 13px;
      font-weight: 700;
    }}
    .no-filter-results td {{
      color: var(--muted);
      padding: 28px 16px;
      text-align: center;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    #top-findings-table {{
      min-width: 1280px;
    }}
    th {{
      text-align: left;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
    }}
    td {{
      border-bottom: 1px solid #edf1f6;
      padding: 12px 8px;
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    tbody tr:hover {{
      background: #fafcff;
    }}
    .group-row {{
      background: #f8fafc;
    }}
    .group-row td {{
      vertical-align: middle;
    }}
    .child-row td {{
      background: #ffffff;
    }}
    .child-row .finding-title {{
      padding-left: 26px;
      font-weight: 700;
    }}
    .expand-button {{
      display: inline-grid;
      width: 24px;
      height: 24px;
      margin-right: 4px;
      place-items: center;
      border-radius: 6px;
      background: transparent;
      font-size: 16px;
      vertical-align: middle;
    }}
    .expand-button:hover {{
      background: #eaf1fb;
    }}
    .feature {{
      font-weight: 800;
      margin-bottom: 4px;
    }}
    .finding-title {{
      font-weight: 800;
      font-size: 14px;
      color: var(--ink);
    }}
    .finding-context {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 8px 0;
    }}
    .context-tag {{
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      padding: 4px 7px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: var(--slate);
      font-size: 11px;
      overflow-wrap: anywhere;
    }}
    .evidence-summary {{
      margin-top: 10px;
      padding: 10px;
      border: 1px solid #e3e9f1;
      border-radius: 8px;
      background: #f8fafc;
    }}
    .evidence-heading {{
      margin-bottom: 8px;
      color: var(--slate);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    .evidence-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }}
    .evidence-item {{
      min-width: 0;
      padding: 8px;
      border-radius: 6px;
      background: #ffffff;
    }}
    .evidence-label {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      margin-bottom: 3px;
    }}
    .evidence-value {{
      display: block;
      color: var(--ink);
      font-size: 12px;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .artifact-counts {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }}
    .count-chip {{
      padding: 4px 7px;
      border-radius: 6px;
      background: #eaf1fb;
      color: #264c7c;
      font-size: 11px;
      font-weight: 700;
    }}
    .evidence-details {{
      margin-top: 9px;
      border-top: 1px solid #e3e9f1;
      padding-top: 8px;
    }}
    .evidence-details summary {{
      cursor: pointer;
      color: #315f96;
      font-size: 12px;
      font-weight: 700;
    }}
    .evidence-detail-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 10px;
    }}
    .evidence-detail-grid h4 {{
      margin: 0 0 5px;
      color: var(--slate);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .03em;
    }}
    .evidence-detail-grid ul {{
      margin: 0;
      padding-left: 17px;
      color: var(--slate);
      font-size: 12px;
    }}
    .evidence-detail-grid li {{
      margin: 3px 0;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .source-line {{
      margin-top: 8px;
    }}
    .drawer-overlay {{
      position: fixed;
      inset: 0;
      z-index: 50;
      background: rgba(23, 32, 51, .36);
    }}
    .evidence-drawer {{
      position: fixed;
      top: 0;
      right: 0;
      z-index: 60;
      width: min(540px, 94vw);
      height: 100vh;
      background: #ffffff;
      border-left: 1px solid var(--line);
      box-shadow: -18px 0 42px rgba(23, 32, 51, .18);
      transform: translateX(105%);
      transition: transform .2s ease;
      visibility: hidden;
    }}
    .evidence-drawer.open {{
      transform: translateX(0);
      visibility: visible;
    }}
    .drawer-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
    }}
    .drawer-header h2 {{
      margin: 3px 0 0;
      font-size: 19px;
    }}
    .drawer-body {{
      height: calc(100vh - 82px);
      padding: 18px 20px 30px;
      overflow-y: auto;
    }}
    .drawer-body .evidence-summary {{
      margin-top: 0;
    }}
    .icon-button {{
      width: 38px;
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 24px;
      line-height: 1;
    }}
    body.drawer-open {{
      overflow: hidden;
    }}
    .decision-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px 22px;
    }}
    .decision-item {{
      min-width: 0;
      padding-left: 12px;
      border-left: 3px solid var(--low);
    }}
    .decision-item.urgent {{
      border-left-color: var(--critical);
    }}
    .decision-item strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .decision-item p {{
      margin: 0;
      color: var(--slate);
      font-size: 13px;
    }}
    .muted {{
      color: var(--muted);
      font-size: 12px;
    }}
    .action-card {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 12px;
      align-items: start;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcff;
      margin-bottom: 10px;
    }}
    .action-card[hidden] {{
      display: none;
    }}
    .actions-footer {{
      display: flex;
      justify-content: flex-end;
      margin-top: 14px;
    }}
    .actions-footer .pagination {{
      margin-left: 0;
    }}
    .rank {{
      width: 30px;
      height: 30px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      background: #26384f;
      color: #ffffff;
      font-weight: 800;
    }}
    .savings-grid {{
      display: grid;
      grid-template-columns: 0.75fr 1.25fr;
      gap: 16px;
    }}
    .donut-wrap {{
      display: grid;
      place-items: center;
      padding: 12px 0;
    }}
    .donut {{
      width: 210px;
      aspect-ratio: 1;
      border-radius: 50%;
      background:
        radial-gradient(circle at center, #fff 0 58%, transparent 59%),
        conic-gradient(var(--ok) 0 var(--saved-percent), #e7ecf3 var(--saved-percent) 100%);
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
    }}
    .donut strong {{
      font-size: 38px;
      line-height: 1;
    }}
    .donut span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 6px;
      text-align: center;
    }}
    .stacked {{
      height: 18px;
      display: flex;
      border-radius: 999px;
      overflow: hidden;
      background: #edf1f6;
      margin: 8px 0 16px;
    }}
    .seg-docs {{ width: 28%; background: #64748b; }}
    .seg-inventory {{ width: 26%; background: var(--low); }}
    .seg-match {{ width: 22%; background: var(--high); }}
    .seg-plan {{ width: 16%; background: var(--medium); }}
    .seg-validate {{ width: 8%; background: var(--ok); }}
    .legend {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      color: var(--slate);
      font-size: 13px;
    }}
    .legend span::before {{
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      margin-right: 7px;
      border-radius: 2px;
      vertical-align: middle;
      background: var(--swatch);
    }}
    footer {{
      color: var(--muted);
      font-size: 12px;
      padding: 18px 0 0;
    }}
    @media (min-width: 1280px) {{
      .overview-grid {{
        grid-template-columns: minmax(320px, 0.9fr) minmax(440px, 1.15fr) minmax(280px, 0.65fr);
      }}
      .desktop-rail {{
        display: block;
      }}
      .bar-row {{
        grid-template-columns: minmax(170px, 220px) minmax(180px, 1fr) 50px;
      }}
    }}
    @media (max-width: 1279px) {{
      .shell {{
        width: min(1180px, calc(100% - 32px));
      }}
    }}
    @media (max-width: 899px) {{
      .topbar,
      .grid,
      .savings-grid {{
        grid-template-columns: 1fr;
        display: grid;
      }}
      .kpis {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .scan-meta {{
        min-width: 0;
      }}
      table {{
        min-width: 850px;
      }}
      .table-wrap {{
        overflow-x: auto;
      }}
    }}
    @media (max-width: 560px) {{
      .shell {{
        width: min(100% - 20px, 1180px);
      }}
      .kpis {{
        grid-template-columns: 1fr;
      }}
      .timeline-item,
      .action-card {{
        grid-template-columns: 1fr;
      }}
      .bar-row {{
        grid-template-columns: 1fr;
      }}
      .evidence-grid,
      .evidence-detail-grid,
      .decision-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="shell topbar">
      <div>
        <h1>UiPath Deprecation Risk Command Center</h1>
        <p class="subtitle">Static executive report generated from analyzer findings, evidence, remediation routing, and AI time-savings estimates.</p>
      </div>
      <div class="scan-meta">
        <strong>Analyzer scan</strong><br>
        Environment: {_h(summary["environment_label"])}<br>
        Source refreshed: {_h(_format_report_date(analysis_date))}<br>
        Findings: {_h(summary["total_findings"])}
      </div>
    </div>
  </header>

  <main class="shell">
    <section id="overview" class="kpis" aria-label="Key metrics">
      {_command_center_kpi("Critical", summary["critical_count"], "Already removed or blocking upgrade", "critical")}
      {_command_center_kpi("High", summary["high_count"], "Due within 180 days", "high")}
      {_command_center_kpi("Products", summary["products_impacted"], "Products impacted", "")}
      {_command_center_kpi("Next Deadline", summary["next_deadline_label"], summary["next_deadline_note"], "medium")}
      {_command_center_kpi("AI Time Saved", f'{summary["percent_saved"]}%', f'{summary["total_hours_saved"]} hours estimated saved', "ok")}
    </section>

    <nav class="tabs" aria-label="Report sections">
      <a class="tab active" href="#overview">Overview</a>
      <a class="tab" href="#findings">Findings</a>
      <a class="tab" href="#timeline">Timeline</a>
      <a class="tab" href="#coverage">Coverage</a>
      <a class="tab" href="#ai-savings">AI Savings</a>
    </nav>

    {_decision_summary_html(payload.get("decision_summary", {}))}

    <section class="grid overview-grid">
      <article class="panel">
        <h2>Risk By Product</h2>
        {_product_risk_bars(product_rows)}
      </article>

      <article id="timeline" class="panel">
        <h2>Upcoming Deadlines</h2>
        <div class="timeline">
          {_timeline_item_cards(timeline_items)}
        </div>
      </article>

      <article class="panel desktop-rail" aria-label="Action focus">
        <h2>Action Focus</h2>
        {summary_rail}
      </article>
    </section>

    <section id="findings" class="panel">
      <h2>Top Findings</h2>
      {_findings_command_table(top_findings, product_options, route_options)}
    </section>

    <section class="grid" style="margin-top: 16px;">
      <article class="panel">
        <h2>Recommended Actions</h2>
        <div id="recommended-actions-list">
          {_action_cards(actions)}
        </div>
        {_action_pagination(len(actions))}
      </article>

      <article id="ai-savings" class="panel">
        <h2>AI Savings</h2>
        <div class="savings-grid">
          <div class="donut-wrap">
            <div class="donut" style="--saved-percent: {_h(summary["percent_saved"])}%;">
              <div>
                <strong>{_h(summary["percent_saved"])}%</strong>
                <span>effort reduction</span>
              </div>
            </div>
          </div>
          <div>
            <p><strong>Manual baseline:</strong> {_h(summary["manual_baseline_hours"])} hours</p>
            <p><strong>AI-assisted effort:</strong> {_h(summary["ai_assisted_hours"])} hours</p>
            <p><strong>Estimated saved:</strong> {_h(summary["total_hours_saved"])} hours</p>
            <div class="stacked" aria-label="Savings breakdown">
              <div class="seg-docs"></div>
              <div class="seg-inventory"></div>
              <div class="seg-match"></div>
              <div class="seg-plan"></div>
              <div class="seg-validate"></div>
            </div>
            <div class="legend">
              <span style="--swatch:#64748b;">Docs review</span>
              <span style="--swatch:#3d79c7;">Inventory review</span>
              <span style="--swatch:#e26c2d;">Evidence matching</span>
              <span style="--swatch:#d7a514;">Planning</span>
              <span style="--swatch:#178064;">Validation</span>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section id="coverage" class="panel" style="margin-top: 16px;">
      <h2>Coverage Gaps</h2>
      {_coverage_gap_table(coverage_gaps)}
    </section>

    <footer>
      Generated analyzer report. Coverage gaps: {_h(len(coverage_gaps))}. Empty source URLs are shown as missing in the findings table. Source links should point to UiPath documentation and local evidence in production reports.
    </footer>
  </main>
  <div id="evidence-overlay" class="drawer-overlay" hidden></div>
  <aside id="evidence-drawer" class="evidence-drawer" aria-hidden="true" aria-labelledby="evidence-drawer-title" aria-modal="true" role="dialog">
    <div class="drawer-header">
      <div>
        <span class="muted">Finding evidence</span>
        <h2 id="evidence-drawer-title">Evidence</h2>
      </div>
      <button id="evidence-drawer-close" class="icon-button" type="button" aria-label="Close evidence drawer">&times;</button>
    </div>
    <div id="evidence-drawer-body" class="drawer-body"></div>
  </aside>
  <script type="application/json" id="findings-data">{findings_data}</script>
  <script type="application/json" id="coverage-gaps-data">{coverage_gaps_data}</script>
  <script>
    {_dashboard_javascript()}
  </script>
</body>
</html>
"""


def _dashboard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings", [])
    summary = payload.get("summary", {})
    severity_counts = summary.get("severity_counts") or Counter(
        str(finding.get("severity", "")).lower() for finding in findings
    )
    product_counts = summary.get("product_counts") or Counter(
        finding.get("product", "Unknown") or "Unknown" for finding in findings
    )
    manual = 0.0
    assisted = 0.0
    saved = 0.0
    for finding in findings:
        kpi = finding.get("time_savings_kpi", {})
        if isinstance(kpi, dict):
            manual += float(kpi.get("manual_baseline_hours", 0) or 0)
            assisted += float(kpi.get("ai_assisted_hours", 0) or 0)
            saved += float(kpi.get("hours_saved", 0) or 0)
    if not saved:
        saved = float(summary.get("total_estimated_hours_saved", 0) or 0)
    percent = round(saved / manual * 100) if manual else 0
    deadlines = [
        parsed
        for parsed in (_parse_dashboard_date(finding.get("deadline")) for finding in findings)
        if parsed
    ]
    next_deadline_date = min(deadlines) if deadlines else None
    analysis_day = _parse_dashboard_date(payload.get("analysis_date")) or date.today()
    next_deadline = next_deadline_date.isoformat() if next_deadline_date else "None"
    next_finding = next(
        (
            finding
            for finding in _sort_findings_for_dashboard(findings)
            if _parse_dashboard_date(finding.get("deadline")) == next_deadline_date
        ),
        {},
    )
    return {
        "total_findings": summary.get("total_findings", len(findings)),
        "critical_count": severity_counts.get("critical", 0),
        "high_count": severity_counts.get("high", 0),
        "products_impacted": len([key for key, value in dict(product_counts).items() if key and value]),
        "next_deadline": next_deadline,
        "next_deadline_label": _deadline_kpi_label(next_deadline_date, analysis_day),
        "next_deadline_note": next_finding.get("feature_or_package") or "No dated findings",
        "manual_baseline_hours": round(manual, 2),
        "ai_assisted_hours": round(assisted, 2),
        "total_hours_saved": round(saved, 2),
        "percent_saved": percent,
        "environment_label": _environment_label(findings),
    }


def _product_risk_rows(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, Counter] = defaultdict(Counter)
    for finding in findings:
        product = finding.get("product") or "Unknown"
        rows[product][str(finding.get("severity", "low")).lower()] += 1
    return [
        {
            "product": product,
            "critical": counts.get("critical", 0),
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
            "total": sum(counts.values()),
        }
        for product, counts in sorted(rows.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    ]


def _deadline_rows(findings: list[dict[str, Any]], analysis_date: str) -> list[dict[str, Any]]:
    baseline = _parse_dashboard_date(analysis_date) or date.today()
    buckets = {
        "Overdue": 0,
        "0-30 days": 0,
        "31-90 days": 0,
        "91-180 days": 0,
        "180+ days": 0,
        "No date": 0,
    }
    for finding in findings:
        parsed = _parse_dashboard_date(finding.get("deadline"))
        if not parsed:
            buckets["No date"] += 1
            continue
        days = (parsed - baseline).days
        if days < 0:
            buckets["Overdue"] += 1
        elif days <= 30:
            buckets["0-30 days"] += 1
        elif days <= 90:
            buckets["31-90 days"] += 1
        elif days <= 180:
            buckets["91-180 days"] += 1
        else:
            buckets["180+ days"] += 1
    return [{"bucket": bucket, "count": count} for bucket, count in buckets.items()]


def _timeline_items(findings: list[dict[str, Any]], analysis_date: str) -> list[dict[str, Any]]:
    baseline = _parse_dashboard_date(analysis_date) or date.today()
    items: list[dict[str, Any]] = []
    for finding in _sort_findings_for_dashboard(findings):
        parsed = _parse_dashboard_date(finding.get("deadline"))
        if not parsed:
            continue
        days = (parsed - baseline).days
        items.append(
            {
                "date": parsed,
                "days": days,
                "severity": str(finding.get("severity", "low")).lower(),
                "status": str(finding.get("status", "")).lower(),
                "title": finding.get("feature_or_package") or finding.get("product") or "Finding",
                "finding": finding,
            }
        )
    return items[:4]


def _sort_findings_for_dashboard(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        findings,
        key=lambda finding: (
            severity_rank.get(str(finding.get("severity", "low")).lower(), 4),
            _parse_dashboard_date(finding.get("deadline")) or date.max,
            finding.get("product", ""),
            finding.get("feature_or_package", ""),
        ),
    )


def _unique_recommended_actions(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for finding in _sort_findings_for_dashboard(findings):
        key = (
            _normalize_action_value(_action_feature(finding)),
            _normalize_action_value(_action_recommendation(finding)),
        )
        if key in seen:
            continue
        seen.add(key)
        actions.append(finding)
    return actions


def _normalize_action_value(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _command_center_kpi(label: str, value: Any, note: Any, value_class: str) -> str:
    css = f" {value_class}" if value_class else ""
    return (
        '<div class="kpi">'
        f'<span class="label">{_h(label)}</span>'
        f'<span class="value{css}">{_h(value)}</span>'
        f'<span class="note">{_h(note)}</span>'
        "</div>"
    )


def _summary_rail_html(
    findings: list[dict[str, Any]],
    product_rows: list[dict[str, Any]],
    coverage_gaps: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    critical_items = [
        finding
        for finding in _sort_findings_for_dashboard(findings)
        if str(finding.get("severity", "")).lower() == "critical"
        or str(finding.get("status", "")).lower() == "removed"
    ]
    critical_seen: set[str] = set()
    critical_rows = []
    for finding in critical_items:
        label = str(finding.get("feature_or_package") or finding.get("product") or "Unnamed finding")
        if label in critical_seen:
            continue
        critical_seen.add(label)
        critical_rows.append(
            '<li class="rail-item">'
            f'<span>{_h(label)}</span>'
            f'<span class="pill {_pill_class(finding.get("severity"))}">{_h(str(finding.get("status", "review")).replace("_", " ").title())}</span>'
            '</li>'
        )
        if len(critical_rows) == 4:
            break

    package_counts = Counter(
        str(finding.get("feature_or_package") or finding.get("product") or "Unknown")
        for finding in findings
    )
    impacted_rows = [
        '<li class="rail-item">'
        f'<span>{_h(name)}</span>'
        f'<span class="rail-metric">{_h(count)}</span>'
        '</li>'
        for name, count in package_counts.most_common(4)
    ]
    product_total = sum(row.get("total", 0) for row in product_rows)
    critical_html = "".join(critical_rows) or '<li class="rail-item"><span>No critical packages</span><span class="rail-metric">0</span></li>'
    impacted_html = "".join(impacted_rows) or '<li class="rail-item"><span>No impacted packages</span><span class="rail-metric">0</span></li>'

    return (
        '<div class="summary-rail">'
        '<div class="rail-block">'
        '<span class="rail-label">Critical removed packages</span>'
        f'<ul class="rail-list">{critical_html}</ul>'
        '</div>'
        '<div class="rail-block">'
        '<span class="rail-label">Most impacted packages</span>'
        f'<ul class="rail-list">{impacted_html}</ul>'
        '</div>'
        '<div class="rail-block">'
        '<span class="rail-label">Portfolio signals</span>'
        '<ul class="rail-list">'
        f'<li class="rail-item"><span>Coverage gaps</span><span class="rail-metric">{_h(len(coverage_gaps))}</span></li>'
        f'<li class="rail-item"><span>Product findings</span><span class="rail-metric">{_h(product_total)}</span></li>'
        f'<li class="rail-item"><span>AI hours saved</span><span class="rail-metric">{_h(summary["total_hours_saved"])}</span></li>'
        '</ul>'
        '</div>'
        '</div>'
    )


def _decision_summary_html(summary: dict[str, Any]) -> str:
    if not summary:
        return ""
    items = (
        ("What can break today?", summary.get("what_can_break_today"), "urgent"),
        ("What must migrate next?", summary.get("what_must_migrate_next"), ""),
        ("Which workflows and packages are affected?", summary.get("affected_scope"), ""),
        ("What is the safest sequence?", summary.get("safest_modernization_sequence"), ""),
    )
    body = "".join(
        f'<div class="decision-item {css_class}"><strong>{_h(label)}</strong><p>{_h(value)}</p></div>'
        for label, value, css_class in items
        if value
    )
    return (
        '<section class="panel" style="margin-bottom: 16px;">'
        '<h2>What Should We Fix First?</h2>'
        f'<div class="decision-grid">{body}</div>'
        '</section>'
    )


def _filter_options(values: Any) -> str:
    unique = {
        _filter_value(value): str(value).strip()
        for value in values
        if str(value or "").strip()
    }
    return "\n".join(
        f'<option value="{_h(normalized)}">{_h(label)}</option>'
        for normalized, label in sorted(unique.items(), key=lambda item: item[1].lower())
    )


def _filter_value(value: Any) -> str:
    return str(value or "").strip().lower()


def _finding_route_value(finding: dict[str, Any]) -> str:
    return str(finding.get("recommended_skill") or finding.get("mitigation_route") or "").strip()


def _product_risk_bars(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="muted">No product risk found.</p>'
    max_total = max(row["total"] for row in rows) or 1
    return "\n".join(
        '<div class="bar-row">'
        f'<div class="bar-label">{_h(row["product"])}</div>'
        f'<div class="bar-track"><div class="bar-fill" style="width: {max(round(row["total"] / max_total * 100), 8)}%;"></div></div>'
        f'<strong>{_h(row["total"])}</strong>'
        "</div>"
        for row in rows[:6]
    )


def _timeline_item_cards(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="muted">No dated findings.</p>'
    return "\n".join(
        '<div class="timeline-item">'
        f'<div class="deadline">{_h(_short_deadline(item["date"]))}</div>'
        '<div class="timeline-content">'
        f'<strong>{_h(item["title"])}</strong>'
        f'<div class="timeline-detail">{_finding_evidence_html(item["finding"], compact=True)}</div>'
        "</div>"
        f'<span class="pill {_pill_class(item["severity"])}">{_h(_days_label(item["days"], item["status"]))}</span>'
        "</div>"
        for item in items
    )


def _findings_dashboard_data(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only the fields needed by the interactive findings table."""
    rows = []
    for index, finding in enumerate(_sort_findings_for_dashboard(findings), 1):
        rows.append(
            {
                "id": str(finding.get("id") or f"finding-{index}"),
                "severity": str(finding.get("severity") or "low").lower(),
                "product": finding.get("product") or "Unknown",
                "feature_or_package": finding.get("feature_or_package") or "Unnamed finding",
                "version": finding.get("current_version") or finding.get("service_version") or "",
                "affected_version": finding.get("affected_version") or "",
                "min_supported_version": finding.get("min_supported_version") or "",
                "status": finding.get("status") or "",
                "environment": finding.get("environment") or "",
                "project_name": finding.get("project_name") or "",
                "domain": finding.get("domain") or "",
                "confidence": finding.get("confidence") or "",
                "deadline": _display_deadline(finding.get("deadline")),
                "route": _finding_route_value(finding),
                "hours_saved": _kpi_value(finding, "hours_saved"),
                "percent_saved": _kpi_value(finding, "percent_saved"),
                "evidence_html": _finding_evidence_html(finding),
            }
        )
    return rows


def _coverage_gaps_dashboard_data(gaps: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "product": str(gap.get("product") or "Unknown"),
            "type": str(gap.get("type") or "coverage_gap"),
            "message": str(gap.get("message") or gap.get("feature") or "Missing context"),
        }
        for gap in gaps
    ]


def _dashboard_json(value: Any) -> str:
    """Serialize a safe, compact JSON data island for the self-contained report."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _findings_command_table(
    findings: list[dict[str, Any]],
    product_options: str = "",
    route_options: str = "",
) -> str:
    return f"""
      <div class="toolbar">
        <input id="findings-search" class="filter search-filter" type="search" placeholder="Search package, project, status, or version" aria-label="Search findings">
        <select id="findings-severity-filter" class="filter" aria-label="Severity filter">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select id="findings-product-filter" class="filter" aria-label="Product filter">
          <option value="">All products</option>
          {product_options}
        </select>
        <select id="findings-route-filter" class="filter" aria-label="Route filter">
          <option value="">All routes</option>
          {route_options}
        </select>
        <div class="view-toggle" role="group" aria-label="Findings view">
          <button id="findings-grouped-view" class="toggle-button" type="button" aria-pressed="true">Grouped</button>
          <button id="findings-flat-view" class="toggle-button" type="button" aria-pressed="false">Flat</button>
        </div>
        <div class="pagination" aria-label="Findings pages">
          <button id="findings-prev-page" class="page-button" type="button">Previous</button>
          <span id="findings-page-label" class="page-label">Page 0 of 0</span>
          <button id="findings-next-page" class="page-button" type="button">Next</button>
        </div>
        <p id="findings-filter-status" class="filter-status" role="status" aria-live="polite">Loading {_h(len(findings))} findings...</p>
      </div>
      <div class="table-wrap">
        <table id="top-findings-table">
          <thead><tr>
            <th style="width: 100px;">Severity</th>
            <th style="width: 135px;">Product</th>
            <th>Activity / Package</th>
            <th style="width: 105px;">Version</th>
            <th style="width: 120px;">Affected</th>
            <th style="width: 125px;">Deadline</th>
            <th style="width: 155px;">Route</th>
            <th style="width: 115px;">AI Saved</th>
            <th style="width: 120px;">Evidence</th>
          </tr></thead>
          <tbody></tbody>
        </table>
      </div>
    """


def _action_cards(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return '<p class="muted">No recommended actions.</p>'
    return "\n".join(
        f'<div class="action-card" data-action-index="{index}"{" hidden" if index > _ACTION_PAGE_SIZE else ""}>'
        f'<div class="rank">{index}</div>'
        "<div>"
        f'<strong>{_h(_action_title(finding))}</strong>'
        f'<div class="muted">{_h(_action_recommendation(finding))}</div>'
        "</div>"
        f'<span class="pill {_pill_class(finding.get("severity"))}">{_h(str(finding.get("severity", "low")).title())}</span>'
        "</div>"
        for index, finding in enumerate(findings, 1)
    )


def _action_pagination(action_count: int) -> str:
    if action_count <= _ACTION_PAGE_SIZE:
        return ""
    pages = (action_count + _ACTION_PAGE_SIZE - 1) // _ACTION_PAGE_SIZE
    return (
        '<div class="actions-footer">'
        '<div class="pagination" aria-label="Recommended action pages">'
        '<button id="actions-prev-page" class="page-button" type="button">Previous</button>'
        f'<span id="actions-page-label" class="page-label">Page 1 of {_h(pages)}</span>'
        '<button id="actions-next-page" class="page-button" type="button">Next</button>'
        "</div>"
        "</div>"
    )


def _timeline_detail(finding: dict[str, Any]) -> str:
    evidence = _evidence_text(finding.get("evidence", []))
    if evidence and evidence != "missing":
        return f"Evidence: {evidence}"
    return finding.get("impact") or finding.get("recommended_action") or "Review finding evidence and remediation guidance."


def _finding_context_html(finding: dict[str, Any]) -> str:
    """Render scannable finding context instead of flattening it into one long line."""
    scope_label = "Project" if finding.get("domain") == "client" else "Folder"
    scope_value = (
        finding.get("project_name") or finding.get("environment")
        if finding.get("domain") == "client"
        else finding.get("configuration_object")
    )
    values = [
        ("Status", str(finding.get("status", "")).replace("_", " ").title()),
        ("Environment", finding.get("environment")),
        (scope_label, scope_value),
        ("Confidence", finding.get("confidence")),
    ]
    tags = "".join(
        f'<span class="context-tag"><strong>{_h(label)}:</strong>&nbsp;{_h(value)}</span>'
        for label, value in values
        if value
    )
    return f'<div class="finding-context">{tags}</div>' if tags else ""


def _finding_evidence_html(finding: dict[str, Any], compact: bool = False) -> str:
    """Render evidence as labeled context, counts, and expandable detail lists."""
    evidence = finding.get("evidence", [])
    records = evidence if isinstance(evidence, list) else [evidence]
    dictionaries = [record for record in records if isinstance(record, dict)]
    scalar_values = [str(record) for record in records if record not in (None, "", [], {}) and not isinstance(record, dict)]
    if not dictionaries and not scalar_values:
        return '<div class="evidence-summary"><span class="evidence-heading">Evidence</span><span class="evidence-value">Missing</span></div>'

    context = _evidence_context(dictionaries, finding)
    counts = _evidence_counts(dictionaries)
    endpoints = _unique_evidence_values(dictionaries, "endpoint")
    paths = _unique_evidence_values(dictionaries, "path")
    objects = _evidence_objects(dictionaries)
    signals = _unique_evidence_values(dictionaries, "matched_value")
    source = finding.get("source_url") or context.get("source_url")

    if compact:
        summary_bits = []
        if counts:
            summary_bits.append("; ".join(f"{_human_label(key)}: {value}" for key, value in counts.items()))
        if context.get("project"):
            summary_bits.append(f"Project: {context['project']}")
        elif context.get("folder"):
            summary_bits.append(f"Folder: {context['folder']}")
        if context.get("evidence_source"):
            summary_bits.append(f"Source: {context['evidence_source']}")
        reference = f'<div class="source-line muted">Reference: {_source_html(source)}</div>' if source else ""
        return (
            '<div class="evidence-summary">'
            '<div class="evidence-heading">Evidence summary</div>'
            f'<span class="evidence-value">{_h(" | ".join(summary_bits) or "Available")}</span>'
            f'{reference}'
            '</div>'
        )

    context_cells = []
    for label, key in (
        ("Project", "project"),
        ("Organization", "organization"),
        ("Tenant", "tenant"),
        ("Folder", "folder"),
        ("Evidence source", "evidence_source"),
    ):
        value = context.get(key)
        if value:
            context_cells.append(
                f'<div class="evidence-item"><span class="evidence-label">{_h(label)}</span>'
                f'<span class="evidence-value">{_h(value)}</span></div>'
            )
    if source:
        context_cells.append(
            f'<div class="evidence-item"><span class="evidence-label">Reference</span>'
            f'<span class="evidence-value">{_source_html(source)}</span></div>'
        )
    if scalar_values:
        context_cells.append(
            '<div class="evidence-item"><span class="evidence-label">Captured evidence</span>'
            f'<span class="evidence-value">{_h("; ".join(scalar_values))}</span></div>'
        )

    count_chips = "".join(
        f'<span class="count-chip">{_h(_human_label(key))}: {_h(value)}</span>'
        for key, value in counts.items()
    )
    detail_blocks = []
    if endpoints:
        detail_blocks.append(_evidence_detail_list("Endpoints", endpoints))
    if paths:
        detail_blocks.append(_evidence_detail_list("Evidence files", paths))
    if objects:
        detail_blocks.append(_evidence_detail_list("Representative objects", objects))
    if signals:
        detail_blocks.append(_evidence_detail_list("Matched signals", signals))
    details = "".join(detail_blocks) or '<p class="muted">No additional details captured.</p>'
    context_html = "".join(context_cells) or '<div class="evidence-item"><span class="evidence-value">Available</span></div>'
    counts_html = f'<div class="artifact-counts">{count_chips}</div>' if count_chips else ""
    return (
        '<div class="evidence-summary">'
        '<div class="evidence-heading">Evidence summary</div>'
        f'<div class="evidence-grid">{context_html}</div>'
        f'{counts_html}'
        '<details class="evidence-details">'
        '<summary>View evidence details</summary>'
        f'<div class="evidence-detail-grid">{details}</div>'
        '</details>'
        '</div>'
    )


def _evidence_context(records: list[dict[str, Any]], finding: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in ("project", "organization", "tenant", "folder", "evidence_source", "source_url"):
        value = next((record.get(key) for record in records if record.get(key)), None)
        if value:
            context[key] = value
    if finding.get("domain") == "client":
        if not context.get("project"):
            context["project"] = finding.get("project_name") or finding.get("environment")
    elif finding.get("environment") and not context.get("folder"):
        context["folder"] = finding.get("configuration_object") or finding.get("environment")
    return context


def _evidence_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for record in records:
        values = record.get("artifact_counts")
        if isinstance(values, dict):
            for key, value in values.items():
                if value not in (None, "", 0):
                    counts[str(key)] = value
    return dict(sorted(counts.items()))


def _unique_evidence_values(records: list[dict[str, Any]], key: str, limit: int = 8) -> list[str]:
    values: list[str] = []
    for record in records:
        value = record.get(key)
        if value not in (None, "", [], {}):
            text = str(value)
            if text not in values:
                values.append(text)
    return values[:limit]


def _evidence_objects(records: list[dict[str, Any]], limit: int = 8) -> list[str]:
    values: list[str] = []
    for record in records:
        representative = record.get("representative_objects")
        if isinstance(representative, dict):
            candidates = [item for items in representative.values() if isinstance(items, list) for item in items]
        else:
            candidates = [record.get("configuration_object")] if record.get("configuration_object") else []
        for value in candidates:
            if value not in (None, "") and str(value) not in values:
                values.append(str(value))
    return values[:limit]


def _evidence_detail_list(title: str, values: list[str]) -> str:
    items = "".join(f"<li>{_h(value)}</li>" for value in values)
    return f"<div><h4>{_h(title)}</h4><ul>{items}</ul></div>"


def _human_label(value: Any) -> str:
    return str(value).replace("_", " ").title()


def _pill_class(value: Any) -> str:
    severity = str(value or "low").lower()
    if severity in {"critical", "high", "medium", "low"}:
        return severity
    if severity in {"removed", "overdue"}:
        return "critical"
    if severity == "out_of_support":
        return "high"
    return "gray"


def _route_pill_class(finding: dict[str, Any]) -> str:
    skill = str(finding.get("recommended_skill", "")).lower()
    route = str(finding.get("mitigation_route", "")).lower()
    if "test" in skill:
        return "low"
    if "platform" in skill or route == "ai_assisted_change":
        return "high"
    if route == "owner_review":
        return "gray"
    return "low"


def _short_deadline(value: date) -> str:
    return value.strftime("%d %b")


def _days_label(days: int, status: str = "") -> str:
    if days < 0:
        if status == "informational":
            return "Past milestone"
        return "Overdue"
    if days == 0:
        return "Today"
    return f"{days} days"


def _display_deadline(value: Any) -> str:
    parsed = _parse_dashboard_date(value)
    if not parsed:
        return "No date"
    return parsed.strftime("%d %b %Y")


def _format_report_date(value: Any) -> str:
    parsed = _parse_dashboard_date(value)
    if not parsed:
        return "Unknown"
    return parsed.strftime("%d %b %Y")


def _deadline_kpi_label(deadline: Optional[date], analysis_day: date) -> str:
    if not deadline:
        return "None"
    days = (deadline - analysis_day).days
    if days < 0:
        return "Overdue"
    if days == 0:
        return "Today"
    return f"{days}d"


def _environment_label(findings: list[dict[str, Any]]) -> str:
    domains = sorted({finding.get("domain", "") for finding in findings if finding.get("domain")})
    if not domains:
        return "Unknown"
    if domains == ["client"]:
        return "Client automation project"
    if domains == ["server"]:
        return "Server/platform export"
    return "Mixed client/server evidence"


def _action_title(finding: dict[str, Any]) -> str:
    feature = _action_feature(finding)
    severity = str(finding.get("severity", "")).lower()
    if severity == "critical":
        return f"Remediate {feature}"
    return f"Plan remediation for {feature}"


def _action_feature(finding: dict[str, Any]) -> str:
    return finding.get("feature_or_package") or finding.get("product") or "Deprecation finding"


def _action_recommendation(finding: dict[str, Any]) -> str:
    return finding.get("recommended_action") or "Review UiPath migration guidance."


def _product_risk_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class=\"muted\">No product risk found.</p>"
    max_total = max(row["total"] for row in rows) or 1
    body = "\n".join(
        "<tr>"
        f"<td>{_h(row['product'])}</td>"
        f"<td>{_h(row['critical'])}</td>"
        f"<td>{_h(row['high'])}</td>"
        f"<td>{_h(row['medium'])}</td>"
        f"<td>{_h(row['low'])}</td>"
        f"<td><div class=\"bar-track\"><div class=\"bar\" style=\"width: {round(row['total'] / max_total * 100)}%\"></div></div></td>"
        "</tr>"
        for row in rows
    )
    return f"<table><thead><tr><th>Product</th><th>Critical</th><th>High</th><th>Medium</th><th>Low</th><th>Total</th></tr></thead><tbody>{body}</tbody></table>"


def _deadline_table(rows: list[dict[str, Any]]) -> str:
    body = "\n".join(
        f"<tr><td>{_h(row['bucket'])}</td><td>{_h(row['count'])}</td></tr>"
        for row in rows
    )
    return f"<table><thead><tr><th>Deadline Bucket</th><th>Findings</th></tr></thead><tbody>{body}</tbody></table>"


def _findings_table(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "<p class=\"muted\">No findings.</p>"
    body = "\n".join(
        "<tr>"
        f"<td>{_severity_badge(finding.get('severity'))}</td>"
        f"<td>{_h(finding.get('product', ''))}</td>"
        f"<td>{_h(finding.get('feature_or_package', ''))}</td>"
        f"<td>{_h(_evidence_text(finding.get('evidence', [])))}</td>"
        f"<td>{_h(finding.get('deadline') or 'No date')}</td>"
        f"<td>{_h(finding.get('mitigation_route', ''))}</td>"
        f"<td>{_h(finding.get('recommended_skill', ''))}</td>"
        f"<td>{_h(_kpi_value(finding, 'hours_saved'))}</td>"
        "</tr>"
        for finding in findings
    )
    return (
        "<table><thead><tr><th>Severity</th><th>Product</th><th>Feature or Package</th>"
        "<th>Evidence</th><th>Deadline</th><th>Mitigation Route</th><th>Recommended Skill</th><th>AI Hours Saved</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _actions_table(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "<p class=\"muted\">No recommended actions.</p>"
    body = "\n".join(
        "<tr>"
        f"<td>{_severity_badge(finding.get('severity'))}</td>"
        f"<td>{_h(finding.get('deadline') or 'No date')}</td>"
        f"<td>{_h(finding.get('product', ''))}</td>"
        f"<td>{_h(finding.get('recommended_action', ''))}</td>"
        f"<td>{_h(finding.get('owner_hint', ''))}</td>"
        "</tr>"
        for finding in findings
    )
    return "<table><thead><tr><th>Severity</th><th>Deadline</th><th>Product</th><th>Action</th><th>Owner</th></tr></thead><tbody>" + body + "</tbody></table>"


def _coverage_gap_table(gaps: list[dict[str, Any]]) -> str:
    return f"""
      <div class="toolbar">
        <input id="coverage-search" class="filter search-filter" type="search" placeholder="Search coverage gaps" aria-label="Search coverage gaps">
        <div class="pagination" aria-label="Coverage gap pages">
          <button id="coverage-prev-page" class="page-button" type="button">Previous</button>
          <span id="coverage-page-label" class="page-label">Page 0 of 0</span>
          <button id="coverage-next-page" class="page-button" type="button">Next</button>
        </div>
        <p id="coverage-filter-status" class="filter-status" role="status" aria-live="polite">Loading {_h(len(gaps))} coverage gaps...</p>
      </div>
      <div class="table-wrap">
        <table id="coverage-gaps-table">
          <thead><tr><th style="width: 180px;">Product</th><th style="width: 180px;">Type</th><th>Message</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    """


def _dashboard_javascript() -> str:
    """Client-side rendering for paged findings, evidence, and coverage gaps."""
    return r"""
    (() => {
      const PAGE_SIZE = 25;
      const normalize = (value) => String(value || "").trim().toLowerCase();
      const readData = (id) => {
        const element = document.getElementById(id);
        if (!element) return [];
        try {
          const parsed = JSON.parse(element.textContent || "[]");
          return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
          console.error(`Unable to parse dashboard data from #${id}`, error);
          return [];
        }
      };
      const setText = (element, value) => {
        element.textContent = String(value ?? "");
        return element;
      };
      const make = (tag, className, value) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (value !== undefined) setText(element, value);
        return element;
      };
      const appendCell = (row, value, className = "") => {
        const cell = make("td", className);
        if (value instanceof Node) cell.appendChild(value);
        else setText(cell, value);
        row.appendChild(cell);
        return cell;
      };
      const severityClass = (value) => ["critical", "high", "medium", "low"].includes(normalize(value))
        ? normalize(value)
        : "low";
      const routeClass = (value) => {
        const route = normalize(value);
        if (route.includes("test")) return "low";
        if (route.includes("platform") || route === "ai_assisted_change") return "high";
        if (route === "owner_review") return "gray";
        return "low";
      };
      const pill = (value, className) => make("span", `pill ${className}`, value || "Not set");
      const titleCase = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
      const displayVersion = (value) => String(value || "").trim() || "Not captured";
      const displayAffectedVersion = (finding) => finding.affected_version || finding.min_supported_version || "—";
      const savedLabel = (hours, percent) => `${Number(hours || 0).toFixed(2).replace(/\.00$/, "")}h / ${Number(percent || 0)}%`;
      const scopeLabel = (finding) => finding.project_name || finding.environment || "Unknown scope";
      const severityRank = { critical: 0, high: 1, medium: 2, low: 3 };
      const monthNumbers = { Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5, Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11 };
      const deadlineRank = (value) => {
        const parts = String(value || "").split(" ");
        if (parts.length !== 3 || monthNumbers[parts[1]] === undefined) return Number.POSITIVE_INFINITY;
        return Date.UTC(Number(parts[2]), monthNumbers[parts[1]], Number(parts[0]));
      };
      const unique = (values) => [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
      const nearestDeadline = (findings) => {
        const dated = findings.filter((finding) => deadlineRank(finding.deadline) !== Number.POSITIVE_INFINITY);
        if (!dated.length) return "No date";
        return dated.reduce((nearest, finding) => deadlineRank(finding.deadline) < deadlineRank(nearest.deadline) ? finding : nearest).deadline;
      };
      const contextTags = (cell, entries) => {
        const values = entries.filter(([, value]) => String(value || "").trim());
        if (!values.length) return;
        const container = make("div", "finding-context");
        values.forEach(([label, value]) => {
          const tag = make("span", "context-tag");
          const strong = make("strong", "", `${label}:`);
          tag.append(strong, document.createTextNode(` ${value}`));
          container.appendChild(tag);
        });
        cell.appendChild(container);
      };

      const findings = readData("findings-data");
      const findingsById = new Map(findings.map((finding) => [String(finding.id), finding]));
      const findingsBody = document.querySelector("#top-findings-table tbody");
      const findingsStatus = document.getElementById("findings-filter-status");
      const findingsPageLabel = document.getElementById("findings-page-label");
      const findingsPrev = document.getElementById("findings-prev-page");
      const findingsNext = document.getElementById("findings-next-page");
      const groupedButton = document.getElementById("findings-grouped-view");
      const flatButton = document.getElementById("findings-flat-view");
      const findingControls = {
        search: document.getElementById("findings-search"),
        severity: document.getElementById("findings-severity-filter"),
        product: document.getElementById("findings-product-filter"),
        route: document.getElementById("findings-route-filter"),
      };
      let findingsPage = 1;
      let findingsView = "grouped";
      const expandedGroups = new Set();

      const filteredFindings = () => {
        const search = normalize(findingControls.search?.value);
        const severity = normalize(findingControls.severity?.value);
        const product = normalize(findingControls.product?.value);
        const route = normalize(findingControls.route?.value);
        return findings.filter((finding) => {
          const searchable = normalize([
            finding.feature_or_package,
            finding.project_name,
            finding.environment,
            finding.status,
            finding.version,
            finding.affected_version,
            finding.min_supported_version,
          ].join(" "));
          return (!search || searchable.includes(search))
            && (!severity || normalize(finding.severity) === severity)
            && (!product || normalize(finding.product) === product)
            && (!route || normalize(finding.route) === route);
        });
      };

      const groupFindings = (rows) => {
        const grouped = new Map();
        rows.forEach((finding) => {
          const key = normalize(finding.feature_or_package) || String(finding.id);
          if (!grouped.has(key)) grouped.set(key, { key, feature: finding.feature_or_package, findings: [] });
          grouped.get(key).findings.push(finding);
        });
        return [...grouped.values()];
      };

      const evidenceButton = (finding) => {
        const button = make("button", "evidence-button", "View evidence");
        button.type = "button";
        button.dataset.findingId = String(finding.id);
        return button;
      };

      const appendFindingRow = (finding, child = false) => {
        const row = make("tr", child ? "finding-row child-row" : "finding-row flat-row");
        appendCell(row, pill(titleCase(finding.severity), severityClass(finding.severity)));
        appendCell(row, finding.product);
        const findingCell = appendCell(row, "");
        findingCell.appendChild(make("div", "finding-title", child ? scopeLabel(finding) : finding.feature_or_package));
        contextTags(findingCell, child
          ? [["Status", titleCase(finding.status)], ["Confidence", titleCase(finding.confidence)]]
          : [["Project", finding.project_name], ["Environment", finding.environment], ["Status", titleCase(finding.status)]]);
        appendCell(row, displayVersion(finding.version));
        appendCell(row, displayAffectedVersion(finding));
        appendCell(row, finding.deadline || "No date");
        appendCell(row, pill(finding.route || "Owner review", routeClass(finding.route)));
        appendCell(row, savedLabel(finding.hours_saved, finding.percent_saved));
        appendCell(row, evidenceButton(finding));
        findingsBody.appendChild(row);
      };

      const appendGroupRow = (group) => {
        const members = group.findings;
        const representative = [...members].sort((left, right) =>
          (severityRank[normalize(left.severity)] ?? 4) - (severityRank[normalize(right.severity)] ?? 4)
          || deadlineRank(left.deadline) - deadlineRank(right.deadline)
        )[0];
        const products = unique(members.map((finding) => finding.product));
        const versions = unique(members.map((finding) => finding.version));
        const routes = unique(members.map((finding) => finding.route));
        const projects = unique(members.map((finding) => finding.project_name));
        const totalHours = members.reduce((total, finding) => total + Number(finding.hours_saved || 0), 0);
        const maxPercent = members.reduce((maximum, finding) => Math.max(maximum, Number(finding.percent_saved || 0)), 0);
        const expanded = expandedGroups.has(group.key);
        const row = make("tr", "finding-row group-row");
        row.tabIndex = 0;
        row.setAttribute("role", "button");
        row.setAttribute("aria-expanded", String(expanded));
        const toggle = () => {
          if (expandedGroups.has(group.key)) expandedGroups.delete(group.key);
          else expandedGroups.add(group.key);
          renderFindings();
        };
        row.addEventListener("click", toggle);
        row.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggle();
          }
        });
        appendCell(row, pill(titleCase(representative.severity), severityClass(representative.severity)));
        appendCell(row, products.length === 1 ? products[0] : `${products.length} products`);
        const featureCell = appendCell(row, "");
        const expand = make("button", "expand-button", expanded ? "▾" : "▸");
        expand.type = "button";
        expand.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} ${group.feature}`);
        expand.addEventListener("click", (event) => {
          event.stopPropagation();
          toggle();
        });
        featureCell.append(expand, make("span", "finding-title", group.feature));
        appendCell(row, versions.length === 0 ? "Not captured" : versions.length === 1 ? versions[0] : `${versions.length} versions`);
        appendCell(row, projects.length ? `${projects.length} project${projects.length === 1 ? "" : "s"}` : `${members.length} finding${members.length === 1 ? "" : "s"}`);
        appendCell(row, nearestDeadline(members));
        appendCell(row, pill(routes.length === 1 ? routes[0] : `${routes.length} routes`, routeClass(representative.route)));
        appendCell(row, savedLabel(totalHours, maxPercent));
        appendCell(row, `${members.length} record${members.length === 1 ? "" : "s"}`);
        findingsBody.appendChild(row);
        if (expanded) members.forEach((finding) => appendFindingRow(finding, true));
      };

      const renderFindings = () => {
        if (!findingsBody) return;
        const matching = filteredFindings();
        const items = findingsView === "grouped" ? groupFindings(matching) : matching;
        const pages = Math.ceil(items.length / PAGE_SIZE);
        findingsPage = pages ? Math.min(Math.max(findingsPage, 1), pages) : 0;
        const start = findingsPage ? (findingsPage - 1) * PAGE_SIZE : 0;
        const currentItems = items.slice(start, start + PAGE_SIZE);
        findingsBody.replaceChildren();
        if (!currentItems.length) {
          const empty = make("tr", "no-filter-results");
          const cell = appendCell(empty, "No findings match these filters.");
          cell.colSpan = 9;
          findingsBody.appendChild(empty);
        } else if (findingsView === "grouped") {
          currentItems.forEach(appendGroupRow);
        } else {
          currentItems.forEach((finding) => appendFindingRow(finding));
        }
        if (findingsStatus) {
          findingsStatus.textContent = findingsView === "grouped"
            ? `Showing ${matching.length} finding${matching.length === 1 ? "" : "s"} in ${items.length} group${items.length === 1 ? "" : "s"}`
            : `Showing ${matching.length} of ${findings.length} finding${findings.length === 1 ? "" : "s"}`;
        }
        if (findingsPageLabel) findingsPageLabel.textContent = `Page ${findingsPage} of ${pages}`;
        if (findingsPrev) findingsPrev.disabled = findingsPage <= 1;
        if (findingsNext) findingsNext.disabled = findingsPage === 0 || findingsPage >= pages;
        groupedButton?.setAttribute("aria-pressed", String(findingsView === "grouped"));
        flatButton?.setAttribute("aria-pressed", String(findingsView === "flat"));
      };

      Object.values(findingControls).forEach((control) => {
        const eventName = control?.type === "search" ? "input" : "change";
        control?.addEventListener(eventName, () => {
          findingsPage = 1;
          renderFindings();
        });
      });
      groupedButton?.addEventListener("click", () => {
        findingsView = "grouped";
        findingsPage = 1;
        renderFindings();
      });
      flatButton?.addEventListener("click", () => {
        findingsView = "flat";
        findingsPage = 1;
        renderFindings();
      });
      findingsPrev?.addEventListener("click", () => {
        findingsPage = Math.max(1, findingsPage - 1);
        renderFindings();
      });
      findingsNext?.addEventListener("click", () => {
        findingsPage += 1;
        renderFindings();
      });

      const ACTION_PAGE_SIZE = 5;
      const actionCards = Array.from(document.querySelectorAll("#recommended-actions-list .action-card"));
      const actionsPageLabel = document.getElementById("actions-page-label");
      const actionsPrev = document.getElementById("actions-prev-page");
      const actionsNext = document.getElementById("actions-next-page");
      let actionsPage = 1;
      const renderActions = () => {
        if (!actionCards.length) return;
        const pages = Math.ceil(actionCards.length / ACTION_PAGE_SIZE);
        actionsPage = Math.min(Math.max(actionsPage, 1), pages);
        const start = (actionsPage - 1) * ACTION_PAGE_SIZE;
        const end = start + ACTION_PAGE_SIZE;
        actionCards.forEach((card, index) => {
          card.hidden = index < start || index >= end;
        });
        if (actionsPageLabel) actionsPageLabel.textContent = `Page ${actionsPage} of ${pages}`;
        if (actionsPrev) actionsPrev.disabled = actionsPage <= 1;
        if (actionsNext) actionsNext.disabled = actionsPage >= pages;
      };
      actionsPrev?.addEventListener("click", () => {
        actionsPage = Math.max(1, actionsPage - 1);
        renderActions();
      });
      actionsNext?.addEventListener("click", () => {
        actionsPage += 1;
        renderActions();
      });

      const drawer = document.getElementById("evidence-drawer");
      const drawerOverlay = document.getElementById("evidence-overlay");
      const drawerTitle = document.getElementById("evidence-drawer-title");
      const drawerBody = document.getElementById("evidence-drawer-body");
      const drawerClose = document.getElementById("evidence-drawer-close");
      let lastEvidenceTrigger = null;
      const closeDrawer = () => {
        drawer?.classList.remove("open");
        drawer?.setAttribute("aria-hidden", "true");
        if (drawerOverlay) drawerOverlay.hidden = true;
        document.body.classList.remove("drawer-open");
        lastEvidenceTrigger?.focus();
      };
      const openDrawer = (finding, trigger) => {
        if (!drawer || !drawerBody) return;
        lastEvidenceTrigger = trigger;
        if (drawerTitle) drawerTitle.textContent = `${finding.feature_or_package} — ${scopeLabel(finding)}`;
        drawerBody.innerHTML = finding.evidence_html || '<p class="muted">Evidence is missing.</p>';
        drawer.classList.add("open");
        drawer.setAttribute("aria-hidden", "false");
        if (drawerOverlay) drawerOverlay.hidden = false;
        document.body.classList.add("drawer-open");
        drawerClose?.focus();
      };
      document.addEventListener("click", (event) => {
        const trigger = event.target.closest(".evidence-button");
        if (!trigger) return;
        event.stopPropagation();
        const finding = findingsById.get(String(trigger.dataset.findingId));
        if (finding) openDrawer(finding, trigger);
      });
      drawerClose?.addEventListener("click", closeDrawer);
      drawerOverlay?.addEventListener("click", closeDrawer);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && drawer?.classList.contains("open")) closeDrawer();
      });

      const coverageGaps = readData("coverage-gaps-data");
      const coverageBody = document.querySelector("#coverage-gaps-table tbody");
      const coverageSearch = document.getElementById("coverage-search");
      const coverageStatus = document.getElementById("coverage-filter-status");
      const coveragePageLabel = document.getElementById("coverage-page-label");
      const coveragePrev = document.getElementById("coverage-prev-page");
      const coverageNext = document.getElementById("coverage-next-page");
      let coveragePage = 1;
      const renderCoverage = () => {
        if (!coverageBody) return;
        const search = normalize(coverageSearch?.value);
        const matching = coverageGaps.filter((gap) => !search || normalize([gap.product, gap.type, gap.message].join(" ")).includes(search));
        const pages = Math.ceil(matching.length / PAGE_SIZE);
        coveragePage = pages ? Math.min(Math.max(coveragePage, 1), pages) : 0;
        const start = coveragePage ? (coveragePage - 1) * PAGE_SIZE : 0;
        coverageBody.replaceChildren();
        const current = matching.slice(start, start + PAGE_SIZE);
        if (!current.length) {
          const empty = make("tr", "no-filter-results");
          const cell = appendCell(empty, coverageGaps.length ? "No coverage gaps match this search." : "No coverage gaps.");
          cell.colSpan = 3;
          coverageBody.appendChild(empty);
        } else {
          current.forEach((gap) => {
            const row = document.createElement("tr");
            appendCell(row, gap.product);
            appendCell(row, titleCase(gap.type));
            appendCell(row, gap.message);
            coverageBody.appendChild(row);
          });
        }
        if (coverageStatus) coverageStatus.textContent = `Showing ${matching.length} of ${coverageGaps.length} coverage gaps`;
        if (coveragePageLabel) coveragePageLabel.textContent = `Page ${coveragePage} of ${pages}`;
        if (coveragePrev) coveragePrev.disabled = coveragePage <= 1;
        if (coverageNext) coverageNext.disabled = coveragePage === 0 || coveragePage >= pages;
      };
      coverageSearch?.addEventListener("input", () => {
        coveragePage = 1;
        renderCoverage();
      });
      coveragePrev?.addEventListener("click", () => {
        coveragePage = Math.max(1, coveragePage - 1);
        renderCoverage();
      });
      coverageNext?.addEventListener("click", () => {
        coveragePage += 1;
        renderCoverage();
      });

      renderFindings();
      renderActions();
      renderCoverage();
    })();
    """


def _appendix_table(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "<p class=\"muted\">No appendix entries.</p>"
    body = "\n".join(
        "<tr>"
        f"<td>{_h(finding.get('id', ''))}</td>"
        f"<td><code>{_h(_evidence_text(finding.get('evidence', [])))}</code></td>"
        f"<td>{_source_html(finding.get('source_url'))}</td>"
        f"<td>{_h(finding.get('confidence', ''))}</td>"
        "</tr>"
        for finding in findings
    )
    return f"<table><thead><tr><th>ID</th><th>Raw Evidence</th><th>Source URL</th><th>Confidence</th></tr></thead><tbody>{body}</tbody></table>"


def _severity_badge(value: Any) -> str:
    severity = str(value or "low").lower()
    css = severity if severity in {"critical", "high", "medium", "low"} else "low"
    return f'<span class="severity severity-{css}">{_h(severity)}</span>'


def _source_html(value: Any) -> str:
    source = str(value or "").strip()
    if not source:
        return "missing"
    escaped = _h(source)
    if source.startswith(("http://", "https://")):
        return f'<a href="{escaped}">{escaped}</a>'
    return escaped


def _kpi_value(finding: dict[str, Any], key: str) -> Any:
    kpi = finding.get("time_savings_kpi", {})
    return kpi.get(key, 0) if isinstance(kpi, dict) else 0


def _evidence_text(evidence: Any) -> str:
    if isinstance(evidence, list):
        parts = []
        for item in evidence:
            if isinstance(item, dict):
                details = [
                    f"{key}={value}"
                    for key, value in item.items()
                    if value not in ("", None, [], {})
                ]
                parts.append(", ".join(details))
            else:
                parts.append(str(item))
        return "; ".join(part for part in parts if part) or "missing"
    if evidence:
        return str(evidence)
    return "missing"


def _parse_dashboard_date(value: Any) -> Optional[date]:
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            if fmt == "%Y-%m":
                return parsed.replace(day=1)
            if fmt == "%Y":
                return parsed.replace(month=1, day=1)
            return parsed
        except ValueError:
            continue
    return None


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _common_finding_bullets(findings: list[dict[str, Any]]) -> list[str]:
    if not findings:
        return ["- None."]
    lines: list[str] = []
    for finding in findings:
        evidence = finding.get("evidence", [])
        if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
            evidence_text = ", ".join(
                item.get("path", "") or item.get("matched_value", "")
                for item in evidence
            )
        elif isinstance(evidence, list):
            evidence_text = ", ".join(str(item) for item in evidence)
        else:
            evidence_text = str(evidence)
        lines.append(
            f"- {finding.get('id')}: {finding.get('product')} / {finding.get('feature_or_package')} "
            f"({finding.get('severity')}, {finding.get('status')}). "
            f"{finding.get('recommended_action')} Evidence: {evidence_text or 'No evidence path captured'}"
        )
    return lines


def _common_roadmap(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        if finding.get("status") == "removed" or finding.get("severity") == "critical":
            buckets["Immediate"].append(finding)
        elif finding.get("severity") == "high":
            buckets["0-6 months"].append(finding)
        elif finding.get("severity") == "medium":
            buckets["6-18 months"].append(finding)
        else:
            buckets["Monitor"].append(finding)
    actions = {
        "Immediate": "Remediate removed or breaking deprecations first",
        "0-6 months": "Schedule near-term migration",
        "6-18 months": "Track planned remediation backlog",
        "Monitor": "Monitor low-confidence or informational items",
    }
    return [
        {"timeframe": timeframe, "action": actions[timeframe], "count": len(items)}
        for timeframe, items in buckets.items()
    ]


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
            row["evidence"] = "; ".join(
                json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
                for item in finding.get("evidence", [])
            )
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
    _sheet_from_rows(wb, "Coverage Gaps", payload.get("coverage_gaps", []))
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
        ("Coverage Gaps", payload.get("coverage_gaps", [])),
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
