import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SkillContractTests(unittest.TestCase):
    def test_root_skill_routes_client_server_and_mixed_inputs(self):
        skill = read_text("SKILL.md")

        self.assertIn("references/common_analysis_rules.md", skill)
        self.assertIn("references/reporting-dashboard-ideas.md", skill)
        self.assertIn("Client-side analyzer", skill)
        self.assertIn("Server-side analyzer", skill)
        self.assertIn("Both analyzers", skill)
        self.assertIn("RPA source project", skill)
        self.assertIn("Orchestrator tenant/folder resources", skill)
        self.assertIn("Repo plus tenant export", skill)

    def test_common_rules_define_shared_output_contract(self):
        common = read_text("references/common_analysis_rules.md")

        for status in (
            "removed",
            "removal_scheduled",
            "deprecated",
            "upcoming_deprecation",
            "out_of_support",
            "informational",
        ):
            self.assertIn(f"`{status}`", common)

        for severity in ("critical", "high", "medium", "low"):
            self.assertIn(f"`{severity}`", common)

        for route in (
            "auto_assess",
            "ai_assisted_change",
            "owner_review",
            "manual_only",
            "monitor",
        ):
            self.assertIn(f"`{route}`", common)

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
            self.assertIn(f"- `{field}`", common)

    def test_examples_cover_client_server_and_mixed_common_shapes(self):
        examples = read_text("references/example_findings.md")

        self.assertIn('"domain": "client"', examples)
        self.assertIn('"domain": "server"', examples)
        self.assertIn('"domain": "mixed"', examples)
        self.assertIn('"time_savings_kpi"', examples)
        self.assertIn('"recommended_skill"', examples)
        self.assertIn("Mixed Analysis Report", examples)

    def test_active_docs_do_not_contain_stale_guidance(self):
        active_docs = [
            "README.md",
            "SKILL.md",
            "references/client_side_analyzer.md",
            "references/common_analysis_rules.md",
            "references/example_findings.md",
            "references/server_side_analyzer.md",
        ]
        combined = "\n".join(read_text(path) for path in active_docs)

        self.assertNotIn("intentionally ignores non-package deprecations", combined)
        self.assertNotIn("legacy examples", combined)
        self.assertNotIn("Only NuGet/activity package timeline entries are considered", combined)

    def test_skill_metadata_and_fixtures_exist(self):
        metadata = read_text("agents/openai.yaml")

        self.assertIn('display_name: "UiPath Deprecation Analyzer"', metadata)
        self.assertIn('short_description: "Route UiPath deprecation analysis"', metadata)
        self.assertIn(
            'default_prompt: "Use $uipath-deprecation-analyzer to analyze UiPath client/server artifacts for deprecation risk and return normalized findings."',
            metadata,
        )
        self.assertIn("allow_implicit_invocation: true", metadata)

        common_finding = json.loads(read_text("tests/fixtures/common-finding.json"))
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
            self.assertIn(field, common_finding)

        raw_client_fixture = json.loads(read_text("tests/fixtures/raw-client-expected-finding.json"))
        self.assertIn("classification", raw_client_fixture)
        self.assertIn("risk_level", raw_client_fixture)
        self.assertFalse((ROOT / "tests/fixtures/expected-finding.json").exists())

    def test_server_reference_requires_html_dashboard_output(self):
        server = read_text("references/server_side_analyzer.md")

        self.assertIn("must include the static HTML dashboard", server)
        self.assertIn("--format markdown,json,xlsx,html", server)
        self.assertIn("references/reporting-dashboard-ideas.md", server)


if __name__ == "__main__":
    unittest.main()
