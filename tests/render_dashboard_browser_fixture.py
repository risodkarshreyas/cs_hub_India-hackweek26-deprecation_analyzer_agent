import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from normalizer import normalize_server_finding
from reports import build_common_report_payload, render_html_dashboard_report


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: render_dashboard_browser_fixture.py OUTPUT_PATH")

    findings = []
    for index in range(12):
        product = "R&D <Core>" if index == 11 else ("Orchestrator" if index % 2 else "Apps")
        finding = normalize_server_finding(
            {
                "product": product,
                "feature": f"Finding {index + 1}",
                "status": "removed" if index % 3 == 0 else "deprecated",
                "severity": "critical" if index % 3 == 0 else "high",
                "deadline": f"2026-0{(index % 9) + 1}-01",
                "recommended_action": "Review and remediate.",
                "evidence": [f"evidence-{index + 1}.json"],
                "confidence": "high",
                "source_url": "source",
            },
            index + 1,
            "2026-07-10",
        )
        finding["recommended_skill"] = "uipath-test" if index % 2 else "uipath-platform"
        findings.append(finding)

    findings[-1]["recommended_skill"] = ""
    findings[-1]["mitigation_route"] = "owner_review"
    payload = build_common_report_payload(
        findings=findings,
        analysis_date="2026-07-10",
        coverage_gaps=[{"type": "missing_context", "product": "Apps", "message": "Missing export."}],
    )
    output = Path(sys.argv[1])
    output.write_text(render_html_dashboard_report(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
