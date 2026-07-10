import csv
import html
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Union
from xml.sax.saxutils import escape


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
        "",
        "## Highest-Risk Findings",
        "",
    ]
    lines.extend(_common_finding_bullets([f for f in findings if f.get("severity") in {"critical", "high"}][:10]))
    for title, domain in (
        ("Client-Side Findings", "client"),
        ("Server-Side Findings", "server"),
        ("Mixed Findings", "mixed"),
    ):
        lines.extend(["", f"## {title}", ""])
        lines.extend(_common_finding_bullets([f for f in findings if f.get("domain") == domain]))
    lines.extend(["", "## Coverage Gaps", ""])
    if payload.get("coverage_gaps"):
        for gap in payload["coverage_gaps"]:
            lines.append(f"- {gap.get('product', 'Unknown')}: {gap.get('message', gap.get('feature', 'Missing context'))}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Remediation Roadmap", ""])
    for item in payload.get("remediation_roadmap", []):
        lines.append(f"- {item['timeframe']}: {item['action']} ({item['count']} findings)")
    lines.extend(["", "## Time Savings KPI", ""])
    lines.append(f"- Estimated total hours saved: {summary.get('total_estimated_hours_saved', 0)}")
    lines.append("- KPI estimates are conservative and based on inventory review, source matching, and remediation planning effort.")
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
    top_findings = _sort_findings_for_dashboard(findings)[:10]
    actions = _sort_findings_for_dashboard(findings)
    analysis_date = payload.get("analysis_date", "")
    product_rows = _product_risk_rows(findings)
    deadline_rows = _deadline_rows(findings, analysis_date)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UiPath Deprecation Dashboard</title>
  <style>
    :root {{
      --critical: #b42318;
      --high: #c2410c;
      --medium: #b7791f;
      --low: #3b556e;
      --ink: #172033;
      --muted: #5f6b7a;
      --line: #d9dee7;
      --panel: #f7f8fb;
      --bg: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    header, main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    header {{ border-bottom: 1px solid var(--line); }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    h2 {{ margin: 28px 0 12px; font-size: 20px; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 18px; }}
    .kpi {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--panel); }}
    .kpi .value {{ font-size: 24px; font-weight: 700; }}
    .kpi .label {{ color: var(--muted); font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; table-layout: fixed; }}
    th, td {{ border: 1px solid var(--line); padding: 8px; vertical-align: top; text-align: left; word-break: break-word; }}
    th {{ background: var(--panel); font-size: 13px; }}
    td {{ font-size: 13px; }}
    .severity {{ display: inline-block; border-radius: 999px; color: white; padding: 2px 8px; font-weight: 700; font-size: 12px; }}
    .severity-critical {{ background: var(--critical); }}
    .severity-high {{ background: var(--high); }}
    .severity-medium {{ background: var(--medium); color: #111827; }}
    .severity-low {{ background: var(--low); }}
    .bar-track {{ height: 10px; background: #e9edf3; border-radius: 999px; overflow: hidden; }}
    .bar {{ height: 10px; background: #2f6f9f; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    .muted {{ color: var(--muted); }}
    a {{ color: #1d4ed8; }}
    code {{ white-space: pre-wrap; font-family: Menlo, Consolas, monospace; font-size: 12px; }}
  </style>
</head>
<body>
  <header>
    <h1>UiPath Deprecation Dashboard</h1>
    <div class="meta">
      Analysis date: {_h(analysis_date or "unknown")} |
      Total findings: {_h(summary["total_findings"])} |
      Next deadline: {_h(summary["next_deadline"])}
    </div>
    <section aria-label="KPI Row" class="kpis">
      {_kpi("Critical", summary["critical_count"])}
      {_kpi("High", summary["high_count"])}
      {_kpi("Products Impacted", summary["products_impacted"])}
      {_kpi("Next Deadline", summary["next_deadline"])}
      {_kpi("AI Hours Saved", summary["total_hours_saved"])}
    </section>
  </header>
  <main>
    <section>
      <h2>Risk by Product</h2>
      {_product_risk_table(product_rows)}
    </section>

    <section>
      <h2>Deadline Timeline</h2>
      {_deadline_table(deadline_rows)}
    </section>

    <section>
      <h2>Top Findings</h2>
      {_findings_table(top_findings)}
    </section>

    <section>
      <h2>Recommended Actions</h2>
      {_actions_table(actions)}
    </section>

    <section>
      <h2>AI Savings</h2>
      <div class="grid">
        <div class="panel"><h3>Manual Baseline Hours</h3><div class="kpi"><div class="value">{_h(summary["manual_baseline_hours"])}</div></div></div>
        <div class="panel"><h3>AI-Assisted Hours</h3><div class="kpi"><div class="value">{_h(summary["ai_assisted_hours"])}</div></div></div>
        <div class="panel"><h3>Hours Saved</h3><div class="kpi"><div class="value">{_h(summary["total_hours_saved"])}</div></div></div>
        <div class="panel"><h3>Percent Saved</h3><div class="kpi"><div class="value">{_h(summary["percent_saved"])}%</div></div></div>
      </div>
      <p class="muted">Savings are aggregated from each finding's <code>time_savings_kpi</code>.</p>
    </section>

    <section>
      <h2>Coverage Gaps</h2>
      {_coverage_gap_table(coverage_gaps)}
    </section>

    <section>
      <h2>Appendix</h2>
      {_appendix_table(findings)}
    </section>
  </main>
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
    next_deadline = min(deadlines).isoformat() if deadlines else "None"
    return {
        "total_findings": summary.get("total_findings", len(findings)),
        "critical_count": severity_counts.get("critical", 0),
        "high_count": severity_counts.get("high", 0),
        "products_impacted": len([key for key, value in dict(product_counts).items() if key and value]),
        "next_deadline": next_deadline,
        "manual_baseline_hours": round(manual, 2),
        "ai_assisted_hours": round(assisted, 2),
        "total_hours_saved": round(saved, 2),
        "percent_saved": percent,
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


def _kpi(label: str, value: Any) -> str:
    return f'<div class="kpi"><div class="value">{_h(value)}</div><div class="label">{_h(label)}</div></div>'


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
    if not gaps:
        return "<p class=\"muted\">None.</p>"
    body = "\n".join(
        "<tr>"
        f"<td>{_h(gap.get('product', 'Unknown'))}</td>"
        f"<td>{_h(gap.get('type', 'coverage_gap'))}</td>"
        f"<td>{_h(gap.get('message', gap.get('feature', 'Missing context')))}</td>"
        "</tr>"
        for gap in gaps
    )
    return f"<table><thead><tr><th>Product</th><th>Type</th><th>Message</th></tr></thead><tbody>{body}</tbody></table>"


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
