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
from reports import (
    _unique_recommended_actions,
    build_common_report_payload,
    render_html_dashboard_report,
    render_markdown_report,
)
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

ORCHESTRATOR_TIMELINE_HTML = """
<html>
  <body>
    <h3>Upcoming removals</h3>
    <table>
      <tr><th>Feature or capability</th><th>Removal announced in</th><th>Scheduled removal date</th><th>Notes</th></tr>
      <tr>
        <td>Testing Module in Orchestrator</td>
        <td>November 11, 2025</td>
        <td>June 30, 2026</td>
        <td>As of January 1, 2026, the Testing module in Orchestrator will not display any test results anymore. Test Set creation and execution in Orchestrator will be removed, with Test Manager becoming the sole platform for creating and executing test sets.</td>
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

    def test_orchestrator_testing_artifacts_are_grouped_with_context_and_redacted(self):
        inventory = scan_server_inputs(ROOT / "tests" / "fixtures" / "orchestrator-test-management")
        rules = normalize_server_rules_from_html(
            ORCHESTRATOR_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-13T00:00:00Z",
        )

        endpoints = {item["endpoint"] for item in inventory["server_evidence"] if item.get("endpoint")}
        evidence_text = json.dumps(inventory["server_evidence"])
        self.assertTrue(
            {
                "/odata/TestSets",
                "/odata/TestCaseDefinitions",
                "/odata/TestCaseExecutions",
                "/odata/TestSetExecutions",
            }.issubset(endpoints)
        )
        self.assertNotIn(
            "/odata/TestSetSchedules",
            {item["endpoint"] for item in inventory["server_evidence"] if item.get("endpoint")},
        )
        self.assertIn("Nilekha&Demo", evidence_text)
        self.assertIn("UiPath default", evidence_text)
        self.assertNotIn("125785", evidence_text)
        self.assertNotIn("private-job-key", evidence_text)
        self.assertNotIn("private-machine", evidence_text)

        findings, _gaps = match_server_deprecations(inventory, rules, analysis_date="2026-07-13")

        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertEqual("Orchestrator", finding["product"])
        self.assertEqual("Testing Module in Orchestrator", finding["feature"])
        self.assertEqual("removed", finding["status"])
        self.assertEqual("critical", finding["severity"])
        self.assertEqual("Nilekha&Demo", finding["environment"])
        self.assertEqual("UiPath default", finding["tenant_or_service"])
        self.assertEqual("Nilekha&Demo", finding["configuration_object"])
        self.assertIn("Test Manager", finding["recommended_action"])
        summary = finding["evidence"][0]
        self.assertEqual(
            {
                "test_set": 2,
                "test_case": 3,
                "test_case_execution": 2,
                "test_set_execution": 1,
            },
            summary["artifact_counts"],
        )
        self.assertEqual(
            "https://staging.uipath.com/uipathtamindia/UiPathDefault/orchestrator_/test/sets?tid=184&fid=791",
            summary["source_url"],
        )
        self.assertIn("/odata/TestCaseDefinitions", {item.get("endpoint") for item in finding["evidence"]})
        self.assertIn("Login.xaml", json.dumps(finding["evidence"]))

    def test_orchestrator_testing_cli_writes_json_and_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cache = tmp_path / "server-rules.json"
            output = tmp_path / "reports"
            rules = normalize_server_rules_from_html(
                ORCHESTRATOR_TIMELINE_HTML,
                source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
                fetched_at="2026-07-13T00:00:00Z",
            )
            cache.write_text(json.dumps({"entries": rules}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "uipath_deprecation_analyzer.py"),
                    "--input",
                    str(ROOT / "tests" / "fixtures" / "orchestrator-test-management"),
                    "--output",
                    str(output),
                    "--mode",
                    "server",
                    "--server-rule-cache",
                    str(cache),
                    "--offline",
                    "--format",
                    "json,csv,html",
                    "--analysis-date",
                    "2026-07-13",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            paths = json.loads(result.stdout)["reports"]
            report = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            csv_report = Path(paths["csv"]).read_text(encoding="utf-8")
            html = Path(paths["html"]).read_text(encoding="utf-8")

        self.assertEqual(1, report["summary"]["total_findings"])
        self.assertIn("Nilekha&Demo", json.dumps(report))
        self.assertIn("Test Manager", json.dumps(report))
        self.assertIn("/odata/TestCaseDefinitions", json.dumps(report))
        self.assertIn("/odata/TestCaseDefinitions", csv_report)
        self.assertIn("Nilekha&Demo", csv_report)
        self.assertIn("UiPath Deprecation Risk Command Center", html)
        self.assertIn("Nilekha&amp;Demo", html)
        self.assertIn("Test Manager", html)

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
        self.assertGreater(markdown.index("## Coverage Gaps"), markdown.index("## Time Savings KPI"))
        self.assertTrue(markdown.rstrip().endswith("- Apps: No Apps export found."))

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
                        "path": "api/postman_collection_with_a_very_long_nested_folder_name/collections/orchestrator/legacy/authentication/postman_collection.json",
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
            "UiPath Deprecation Risk Command Center",
            "shell topbar",
            "class=\"kpis\"",
            "class=\"tabs\"",
            "class=\"panel\"",
            "timeline-item",
            "timeline-detail",
            "action-card",
            "class=\"donut\"",
            "evidence-summary",
            "artifact-counts",
            "View evidence details",
            "Evidence files",
            "Risk By Product",
            "Upcoming Deadlines",
            "Top Findings",
            "Recommended Actions",
            "AI Savings",
            "Coverage Gaps",
            "href=\"#overview\"",
            "href=\"#findings\"",
            "href=\"#timeline\"",
            "href=\"#coverage\"",
            "href=\"#ai-savings\"",
            "id=\"overview\"",
            "id=\"findings\"",
            "id=\"timeline\"",
            "id=\"coverage\"",
            "id=\"ai-savings\"",
            "overflow-wrap: anywhere",
        ):
            self.assertIn(section, html)
        self.assertIn("[REDACTED]", html)
        self.assertIn("postman_collection_with_a_very_long_nested_folder_name", html)
        self.assertIn("missing", html)
        self.assertNotIn("artifact_counts={", html)
        self.assertNotIn("Bearer abc123", html)
        self.assertGreater(html.index('id="coverage"'), html.index('id="ai-savings"'))
        self.assertGreater(html.index('id="coverage"'), html.index("Recommended Actions"))
        self.assertLess(html.index('id="coverage"'), html.index("<footer>"))

    def test_html_dashboard_filters_cover_all_ranked_findings(self):
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

        html = render_html_dashboard_report(payload)
        data = json.loads(html.split('id="findings-data">', 1)[1].split("</script>", 1)[0])

        self.assertEqual(12, len(data))
        self.assertEqual(0, html.count('class="finding-row"'))
        self.assertIn('id="top-findings-table"', html)
        self.assertIn('id="findings-search"', html)
        self.assertIn('id="findings-severity-filter"', html)
        self.assertIn('id="findings-product-filter"', html)
        self.assertIn('id="findings-route-filter"', html)
        self.assertIn('id="findings-grouped-view"', html)
        self.assertIn('id="findings-page-label"', html)
        self.assertIn('id="evidence-drawer"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("Loading 12 findings", html)
        self.assertTrue(any(item["product"] == "R&D <Core>" for item in data))
        self.assertIn('value="r&amp;d &lt;core&gt;"', html)
        self.assertTrue(any(item["route"] == "owner_review" for item in data))
        self.assertIn("No findings match these filters.", html)
        self.assertIn('readData("findings-data")', html)
        self.assertIn('findingsView = "grouped"', html)

    def test_recommended_actions_are_deduplicated_without_mutating_findings(self):
        findings = [
            {
                "id": "lower-priority-duplicate",
                "feature_or_package": " UiPath.OCR.Activities ",
                "recommended_action": "No direct replacement stated - review manually.",
                "severity": "high",
                "deadline": "2026-01-01",
                "product": "Studio/Robot activity packages",
            },
            {
                "id": "highest-priority-duplicate",
                "feature_or_package": "uipath.ocr.activities",
                "recommended_action": "  no direct replacement stated   - REVIEW manually. ",
                "severity": "critical",
                "deadline": "2026-12-01",
                "product": "Studio/Robot activity packages",
            },
            {
                "id": "different-action",
                "feature_or_package": "UiPath.OCR.Activities",
                "recommended_action": "Replace with a supported OCR package.",
                "severity": "medium",
                "deadline": "2027-01-01",
                "product": "Studio/Robot activity packages",
            },
            {
                "id": "different-feature",
                "feature_or_package": "UiPath.Abbyy.Activities",
                "recommended_action": "No direct replacement stated - review manually.",
                "severity": "low",
                "deadline": "2027-02-01",
                "product": "Studio/Robot activity packages",
            },
        ]
        original = json.loads(json.dumps(findings))

        actions = _unique_recommended_actions(findings)

        self.assertEqual(3, len(actions))
        self.assertEqual("highest-priority-duplicate", actions[0]["id"])
        self.assertEqual(
            {"highest-priority-duplicate", "different-action", "different-feature"},
            {action["id"] for action in actions},
        )
        self.assertEqual(original, findings)

    def test_html_dashboard_labels_client_scope_as_project(self):
        finding = normalize_client_finding(
            {
                "project_name": "LegacyProcess",
                "package_name": "UiPath.Legacy.Activities",
                "current_version": "1.2.3",
                "classification": "Already Removed",
                "risk_level": "Critical",
                "recommendation": "Replace the package.",
                "removal_date": "2026-01-01",
                "evidence": ["LegacyProcess/project.json"],
                "confidence": "high",
                "source_url": "source",
            },
            1,
            "2026-07-13",
        )
        payload = build_common_report_payload([finding], "2026-07-13")

        html = render_html_dashboard_report(payload)
        data = json.loads(html.split('id="findings-data">', 1)[1].split("</script>", 1)[0])

        self.assertEqual("LegacyProcess", data[0]["project_name"])
        self.assertIn('<span class="evidence-label">Project</span>', data[0]["evidence_html"])
        self.assertNotIn('<span class="evidence-label">Folder</span>', data[0]["evidence_html"])
        self.assertIn('["Project", finding.project_name]', html)

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
        self.assertIn("UiPath Deprecation Risk Command Center", html)
        self.assertIn("Risk By Product", html)
        self.assertIn("Upcoming Deadlines", html)
        self.assertIn("Top Findings", html)
        self.assertIn("Recommended Actions", html)
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
