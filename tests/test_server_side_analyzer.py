import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalizer import normalize_client_finding, normalize_server_finding
from reports import build_common_report_payload, render_html_dashboard_report, render_markdown_report
from server_inventory import scan_server_inputs
from server_matcher import match_server_deprecations
from server_rules import normalize_server_rules_from_html


SERVER_TIMELINE_HTML = """
<html>
  <body>
    <h3>Orchestrator and Test Manager</h3>
    <table>
      <tr><th>Feature or capability</th><th>Deprecation announced in</th><th>Scheduled removal date</th><th>Notes</th></tr>
      <tr>
        <td>Testing Module in Orchestrator</td>
        <td>October 2023</td>
        <td>June 30, 2026</td>
        <td>Migrate Orchestrator test cases, test sets, and test schedules to Test Manager.</td>
      </tr>
      <tr>
        <td>Legacy Orchestrator API endpoint api/Account/Authenticate</td>
        <td>January 2025</td>
        <td>December 31, 2026</td>
        <td>Use OAuth-based authentication instead.</td>
      </tr>
    </table>
    <h3>Automation Suite</h3>
    <table>
      <tr><th>Feature or capability</th><th>Deprecation announced in</th><th>Scheduled removal date</th><th>Notes</th></tr>
      <tr>
        <td>Automation Suite backup tool with NFS backup and external objectstore</td>
        <td>February 2025</td>
        <td>February 1, 2026</td>
        <td>Move to the supported backup and restore flow.</td>
      </tr>
    </table>
    <h3>Integration Service</h3>
    <table>
      <tr><th>Feature or capability</th><th>Deprecation announced in</th><th>Scheduled removal date</th><th>Notes</th></tr>
      <tr>
        <td>Connection management in Integration Service</td>
        <td>March 2025</td>
        <td>September 2026</td>
        <td>Create and manage connections in Orchestrator.</td>
      </tr>
    </table>
    <h3>Apps</h3>
    <table>
      <tr><th>Feature or capability</th><th>Deprecation announced in</th><th>Scheduled removal date</th><th>Notes</th></tr>
      <tr>
        <td>Legacy Apps runtime</td>
        <td>April 2025</td>
        <td>October 2026</td>
        <td>Migrate apps to the modern runtime.</td>
      </tr>
    </table>
  </body>
</html>
"""


class ServerSideAnalyzerTests(unittest.TestCase):
    def test_server_rule_normalization_keeps_non_package_rows(self):
        rules = normalize_server_rules_from_html(
            SERVER_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-09T00:00:00Z",
        )

        by_feature = {rule["feature"]: rule for rule in rules}

        self.assertIn("Testing Module in Orchestrator", by_feature)
        self.assertIn("Automation Suite backup tool with NFS backup and external objectstore", by_feature)
        self.assertIn("Connection management in Integration Service", by_feature)
        self.assertIn("Legacy Apps runtime", by_feature)
        self.assertEqual("Orchestrator", by_feature["Testing Module in Orchestrator"]["product"])
        self.assertEqual("2026-06-30", by_feature["Testing Module in Orchestrator"]["removal_date"])
        self.assertIn("service_feature", by_feature["Testing Module in Orchestrator"]["match"]["types"])
        self.assertIn("api/Account/Authenticate", by_feature["Legacy Orchestrator API endpoint api/Account/Authenticate"]["match"]["patterns"])

    def test_server_inventory_extracts_structured_evidence_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _write_server_fixture(Path(tmp))

            inventory = scan_server_inputs(root)

        evidence = inventory["server_evidence"]
        endpoints = {item["endpoint"] for item in evidence if item.get("endpoint")}
        objects = {item["configuration_object"] for item in evidence if item.get("configuration_object")}
        values = json.dumps(evidence)

        self.assertIn("/odata/TestSets", endpoints)
        self.assertIn("api/Account/Authenticate", endpoints)
        self.assertIn("Regression Suite", objects)
        self.assertIn("legacyRuntime", values)
        self.assertIn("[REDACTED]", values)
        self.assertNotIn("super-secret", values)
        self.assertNotIn("Bearer abc123", values)
        self.assertGreaterEqual(inventory["summary"]["server_evidence_count"], 6)

    def test_server_matcher_matches_rules_and_reports_coverage_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _write_server_fixture(Path(tmp))
            inventory = scan_server_inputs(root)
        rules = normalize_server_rules_from_html(
            SERVER_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-09T00:00:00Z",
        )

        findings, gaps = match_server_deprecations(inventory, rules, analysis_date="2026-07-09")

        features = {finding["feature"] for finding in findings}
        self.assertIn("Testing Module in Orchestrator", features)
        self.assertIn("Legacy Orchestrator API endpoint api/Account/Authenticate", features)
        self.assertIn("Automation Suite backup tool with NFS backup and external objectstore", features)
        self.assertTrue(all(gap["type"] == "missing_context" for gap in gaps))

    def test_server_matcher_skips_delivery_model_mismatch(self):
        inventory = {
            "server_evidence": [
                {
                    "product": "Automation Suite",
                    "delivery_model": "Automation Cloud",
                    "matched_value": "NFS backup",
                    "path": "cluster_config.json",
                    "evidence_type": "configuration_key",
                    "confidence": "high",
                }
            ]
        }
        rules = [
            {
                "rule_id": "uipath-server-automation-suite-nfs-backup",
                "product": "Automation Suite",
                "feature": "NFS backup",
                "lifecycle_status": "removal_scheduled",
                "delivery_models": ["Automation Suite"],
                "deprecation_date": "2025-02-01",
                "removal_date": "2026-02-01",
                "match": {"types": ["configuration_key"], "patterns": ["NFS backup"]},
                "recommended_alternative": "Use supported backup storage.",
                "source_url": "source",
                "source_section": "Automation Suite",
                "source_text": "NFS backup",
                "confidence": "high",
            }
        ]

        findings, _gaps = match_server_deprecations(inventory, rules, analysis_date="2026-07-09")

        self.assertEqual([], findings)

    def test_common_normalization_for_client_and_server_findings(self):
        client = normalize_client_finding(
            {
                "project_name": "LegacyProcess",
                "package_name": "UiPath.Legacy.Activities",
                "current_version": "1.2.3",
                "classification": "Already Removed",
                "risk_level": "Critical",
                "recommendation": "Replace with UiPath.Modern.Activities.",
                "removal_date": "2026-01-01",
                "evidence": ["LegacyProcess/project.json"],
                "confidence": "high",
                "source_url": "source",
            },
            1,
            "2026-07-09",
        )
        server = normalize_server_finding(
            {
                "product": "Orchestrator",
                "feature": "Testing Module in Orchestrator",
                "status": "removed",
                "severity": "critical",
                "deadline": "2026-06-30",
                "recommended_action": "Migrate to Test Manager.",
                "evidence": [{"path": "test_sets.json", "matched_value": "Regression Suite"}],
                "confidence": "high",
                "source_url": "source",
                "delivery_model": "Automation Cloud",
                "tenant_or_service": "FinanceTenant",
                "configuration_object": "Regression Suite",
            },
            2,
            "2026-07-09",
        )

        for finding in (client, server):
            for field in (
                "id",
                "severity",
                "status",
                "domain",
                "product",
                "feature_or_package",
                "environment",
                "evidence",
                "impact",
                "deadline",
                "recommended_action",
                "mitigation_route",
                "recommended_skill",
                "time_savings_kpi",
                "owner_hint",
                "confidence",
                "source_url",
            ):
                self.assertIn(field, finding)
        self.assertEqual("client", client["domain"])
        self.assertEqual("server", server["domain"])
        self.assertEqual("uipath-test", server["recommended_skill"])

    def test_common_report_renders_server_and_coverage_gap_sections(self):
        finding = normalize_server_finding(
            {
                "product": "Orchestrator",
                "feature": "Testing Module in Orchestrator",
                "status": "removed",
                "severity": "critical",
                "deadline": "2026-06-30",
                "recommended_action": "Migrate to Test Manager.",
                "evidence": [{"path": "test_sets.json", "matched_value": "Regression Suite"}],
                "confidence": "high",
                "source_url": "source",
            },
            1,
            "2026-07-09",
        )

        payload = build_common_report_payload(
            findings=[finding],
            analysis_date="2026-07-09",
            coverage_gaps=[{"type": "missing_context", "product": "Apps", "message": "No Apps export found."}],
        )
        markdown = render_markdown_report(payload)

        self.assertIn("Executive Summary", markdown)
        self.assertIn("Server-Side Findings", markdown)
        self.assertIn("Coverage Gaps", markdown)
        self.assertIn("Time Savings KPI", markdown)

    def test_html_dashboard_contains_required_sections_and_redacted_evidence(self):
        finding = normalize_server_finding(
            {
                "product": "Orchestrator",
                "feature": "Legacy Orchestrator API endpoint api/Account/Authenticate",
                "status": "removed",
                "severity": "critical",
                "deadline": "2026-06-30",
                "recommended_action": "Move to OAuth-based authentication.",
                "evidence": [
                    {
                        "path": "api/postman_collection.json",
                        "endpoint": "api/Account/Authenticate",
                        "matched_value": "[REDACTED]",
                    }
                ],
                "confidence": "high",
                "source_url": "",
            },
            1,
            "2026-07-10",
        )
        payload = build_common_report_payload(
            findings=[finding],
            analysis_date="2026-07-10",
            coverage_gaps=[{"type": "missing_context", "product": "Apps", "message": "No Apps export found."}],
        )

        html = render_html_dashboard_report(payload)

        for section in (
            "KPI Row",
            "Risk by Product",
            "Deadline Timeline",
            "Top Findings",
            "Coverage Gaps",
            "AI Savings",
        ):
            self.assertIn(section, html)
        self.assertIn("[REDACTED]", html)
        self.assertIn("missing", html)
        self.assertNotIn("Bearer abc123", html)

    def test_cli_routes_server_and_mixed_modes_with_cache_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = _write_server_fixture(tmp_path / "server")
            cache = tmp_path / "server-rules.json"
            output = tmp_path / "reports"
            rules = normalize_server_rules_from_html(
                SERVER_TIMELINE_HTML,
                source_url="source",
                fetched_at="2026-07-09T00:00:00Z",
            )
            cache.write_text(json.dumps({"entries": rules}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "uipath_deprecation_analyzer.py"),
                    "--input",
                    str(input_dir),
                    "--output",
                    str(output),
                    "--mode",
                    "server",
                    "--server-rule-cache",
                    str(cache),
                    "--offline",
                    "--format",
                    "html,json",
                    "--analysis-date",
                    "2026-07-09",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            cli_payload = json.loads(result.stdout)
            report_path = Path(cli_payload["reports"]["json"])
            html_path = Path(cli_payload["reports"]["html"])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")

        self.assertGreaterEqual(report["summary"]["total_findings"], 1)
        self.assertIn("server", report["summary"]["domain_counts"])
        self.assertIn("Risk by Product", html)
        self.assertIn("Deadline Timeline", html)
        self.assertIn("Top Findings", html)
        self.assertIn("Coverage Gaps", html)
        self.assertIn("AI Savings", html)


def _write_server_fixture(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "orchestrator").mkdir()
    (root / "api").mkdir()
    (root / "automation-suite").mkdir()
    (root / "apps").mkdir()
    (root / "integration-service").mkdir()
    (root / "aicenter").mkdir()

    (root / "orchestrator" / "test_sets.json").write_text(
        json.dumps(
            {
                "tenant": "FinanceTenant",
                "delivery_model": "Automation Cloud",
                "value": [{"Name": "Regression Suite", "Type": "Orchestrator test set"}],
            }
        ),
        encoding="utf-8",
    )
    (root / "api" / "postman_collection.json").write_text(
        json.dumps(
            {
                "info": {"name": "Legacy auth calls"},
                "item": [
                    {
                        "name": "Authenticate",
                        "request": {
                            "url": {"raw": "https://cloud.uipath.com/api/Account/Authenticate", "path": ["api", "Account", "Authenticate"]},
                            "header": [{"key": "Authorization", "value": "Bearer abc123"}],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "automation-suite" / "cluster_config.json").write_text(
        json.dumps(
            {
                "delivery_model": "Automation Suite",
                "automation_suite_version": "2022.10.5",
                "backup": {"type": "NFS backup", "external_objectstore": True},
                "sql_password": "super-secret",
            }
        ),
        encoding="utf-8",
    )
    (root / "apps" / "legacy_app.json").write_text(
        json.dumps({"name": "Expense App", "runtime": "legacyRuntime", "expressionLanguage": "legacy"}),
        encoding="utf-8",
    )
    (root / "integration-service" / "connections.json").write_text(
        json.dumps({"connections": [{"name": "SharePoint", "management": "Integration Service"}]}),
        encoding="utf-8",
    )
    (root / "aicenter" / "ml-packages.json").write_text(
        json.dumps({"packages": [{"name": "python37duv3", "version": "1.0"}]}),
        encoding="utf-8",
    )
    return root


if __name__ == "__main__":
    unittest.main()
