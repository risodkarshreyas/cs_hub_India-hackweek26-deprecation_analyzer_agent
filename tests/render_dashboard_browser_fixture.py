import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from normalizer import normalize_server_finding
from reports import build_common_report_payload, render_html_dashboard_report


def main() -> int:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: render_dashboard_browser_fixture.py OUTPUT_PATH [ACTION_GROUP_COUNT]")

    group_count = int(sys.argv[2]) if len(sys.argv) == 3 else 30

    findings = []
    for group_index in range(group_count):
        for project_index in range(2):
            index = group_index * 2 + project_index
            product = "R&D <Core>" if group_index == 29 else ("Orchestrator" if group_index % 2 else "Apps")
            finding = normalize_server_finding(
                {
                    "product": product,
                    "feature": f"Finding {group_index + 1}",
                    "status": "removed" if group_index % 3 == 0 else "deprecated",
                    "severity": "critical" if group_index % 3 == 0 else "high",
                    "deadline": f"2026-{(group_index % 9) + 1:02d}-01",
                    "recommended_action": "Review and remediate.",
                    "evidence": [f"evidence-{group_index + 1}-{project_index + 1}.json"],
                    "confidence": "high",
                    "source_url": "source",
                },
                index + 1,
                "2026-07-10",
            )
            finding["project_name"] = f"Project {project_index + 1}"
            finding["service_version"] = f"{group_index + 1}.0.{project_index}"
            finding["recommended_skill"] = "uipath-test" if project_index else "uipath-platform"
            if group_index == 29:
                finding["recommended_skill"] = ""
                finding["mitigation_route"] = "owner_review"
            findings.append(finding)

    payload = build_common_report_payload(
        findings=findings,
        analysis_date="2026-07-10",
        coverage_gaps=[
            {"type": "missing_context", "product": "Apps", "message": f"Missing export {index + 1}."}
            for index in range(group_count)
        ],
    )
    output = Path(sys.argv[1])
    output.write_text(render_html_dashboard_report(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
