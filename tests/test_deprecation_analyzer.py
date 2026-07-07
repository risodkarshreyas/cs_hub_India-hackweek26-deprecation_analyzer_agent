import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from matcher import match_deprecations
from project_inventory import scan_inputs
from reports import build_report_payload, render_markdown_report
from timeline import normalize_timeline_from_html


SAMPLE_TIMELINE_HTML = """
<html>
  <body>
    <h2>Activity package deprecations</h2>
    <table>
      <tr>
        <th>Item</th>
        <th>Deprecation date</th>
        <th>Removal date</th>
        <th>Details</th>
      </tr>
      <tr>
        <td>UiPath.Legacy.Activities package</td>
        <td>2025-01-01</td>
        <td>2026-01-01</td>
        <td>Replace with UiPath.Modern.Activities. Windows-Legacy .NET Framework 4.6.1 support drops.</td>
      </tr>
      <tr>
        <td>Automation Suite backup tool</td>
        <td>2025-02-01</td>
        <td>2026-02-01</td>
        <td>Infrastructure-only deprecation, not a NuGet package.</td>
      </tr>
    </table>
  </body>
</html>
"""


class DeprecationAnalyzerTests(unittest.TestCase):
    def test_timeline_normalization_keeps_only_package_entries(self):
        entries = normalize_timeline_from_html(
            SAMPLE_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-07T00:00:00Z",
        )

        self.assertEqual(1, len(entries))
        self.assertEqual("UiPath.Legacy.Activities", entries[0]["package_name"])
        self.assertEqual("UiPath.Modern.Activities", entries[0]["replacement_package"])
        self.assertEqual("windows_legacy_only", entries[0]["compatibility_scope"])

    def test_source_project_inventory_extracts_dependency_and_xaml_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "LegacyProcess"
            project_dir.mkdir()
            (project_dir / "project.json").write_text(
                json.dumps(
                    {
                        "name": "LegacyProcess",
                        "description": "fixture",
                        "projectVersion": "1.0.0",
                        "runtimeOptions": {
                            "targetFramework": "Legacy",
                            "studioProjectType": "Process",
                        },
                        "dependencies": {
                            "UiPath.Legacy.Activities": "1.2.3",
                            "UiPath.Excel.Activities": "2.0.0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (project_dir / "Main.xaml").write_text(
                """<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
    xmlns:legacy="clr-namespace:UiPath.Legacy.Activities;assembly=UiPath.Legacy.Activities">
  <legacy:DoThing DisplayName="Legacy activity" />
</Activity>""",
                encoding="utf-8",
            )

            inventory = scan_inputs(Path(tmp), include_xaml=True, include_nupkg=False)

        packages = {
            package["package_name"]: package for package in inventory["package_inventory"]
        }
        self.assertIn("UiPath.Legacy.Activities", packages)
        self.assertEqual("1.2.3", packages["UiPath.Legacy.Activities"]["version"])
        self.assertTrue(packages["UiPath.Legacy.Activities"]["evidence"])
        self.assertEqual("windows_legacy", inventory["projects"][0]["compatibility"])

    def test_nupkg_inventory_extracts_nuspec_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            nupkg_path = Path(tmp) / "LegacyProcess.1.0.0.nupkg"
            with zipfile.ZipFile(nupkg_path, "w") as zf:
                zf.writestr(
                    "LegacyProcess.nuspec",
                    """<?xml version="1.0"?>
<package>
  <metadata>
    <id>LegacyProcess</id>
    <version>1.0.0</version>
    <dependencies>
      <dependency id="UiPath.Legacy.Activities" version="1.2.3" />
    </dependencies>
  </metadata>
</package>""",
                )
                zf.writestr(
                    "lib/net45/project.json",
                    json.dumps(
                        {
                            "name": "LegacyProcess",
                            "dependencies": {"UiPath.Excel.Activities": "2.0.0"},
                        }
                    ),
                )

            inventory = scan_inputs(Path(tmp), include_xaml=True, include_nupkg=True)

        names = {package["package_name"] for package in inventory["package_inventory"]}
        self.assertIn("UiPath.Legacy.Activities", names)
        self.assertIn("UiPath.Excel.Activities", names)

    def test_matching_classifies_removed_package_and_adds_recommendation(self):
        inventory = {
            "projects": [
                {
                    "name": "LegacyProcess",
                    "compatibility": "windows_legacy",
                    "source": "source",
                    "path": "LegacyProcess",
                    "xaml_files": ["Main.xaml"],
                }
            ],
            "package_inventory": [
                {
                    "project_name": "LegacyProcess",
                    "package_name": "UiPath.Legacy.Activities",
                    "version": "1.2.3",
                    "source": "project.json",
                    "evidence": ["LegacyProcess/project.json"],
                }
            ],
            "workflow_inventory": [{"project_name": "LegacyProcess", "path": "Main.xaml"}],
        }
        timeline_entries = normalize_timeline_from_html(
            SAMPLE_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-07T00:00:00Z",
        )

        findings = match_deprecations(
            inventory, timeline_entries, analysis_date="2026-07-07"
        )

        self.assertEqual(1, len(findings))
        self.assertEqual("Already Removed", findings[0]["classification"])
        self.assertEqual("Critical", findings[0]["risk_level"])
        self.assertEqual(
            "Replace with UiPath.Modern.Activities.",
            findings[0]["recommendation"],
        )
        self.assertEqual(["LegacyProcess/project.json"], findings[0]["evidence"])

    def test_markdown_report_contains_required_sections(self):
        payload = build_report_payload(
            inventory={
                "projects": [{"name": "LegacyProcess"}],
                "package_inventory": [{"package_name": "UiPath.Legacy.Activities"}],
            },
            timeline_entries=[],
            findings=[
                {
                    "classification": "Already Removed",
                    "package_name": "UiPath.Legacy.Activities",
                    "project_name": "LegacyProcess",
                    "recommendation": "Replace with UiPath.Modern.Activities.",
                    "risk_level": "Critical",
                    "urgency": "Immediate",
                    "confidence": "high",
                    "evidence": ["LegacyProcess/project.json"],
                    "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
                }
            ],
            analysis_date="2026-07-07",
        )

        markdown = render_markdown_report(payload)

        self.assertIn("Executive Summary", markdown)
        self.assertIn("Already Removed", markdown)
        self.assertIn("Replacement Mapping", markdown)
        self.assertIn("Windows-Legacy Impact", markdown)
        self.assertIn("Remediation Roadmap", markdown)

    def test_windows_legacy_only_entries_do_not_flag_known_windows_projects(self):
        inventory = {
            "projects": [
                {
                    "name": "WindowsProcess",
                    "compatibility": "windows",
                    "source": "source",
                    "path": "WindowsProcess",
                    "xaml_files": ["Main.xaml"],
                }
            ],
            "package_inventory": [
                {
                    "project_name": "WindowsProcess",
                    "package_name": "UiPath.Legacy.Activities",
                    "version": "1.2.3",
                    "source": "project.json",
                    "evidence": ["WindowsProcess/project.json"],
                }
            ],
            "workflow_inventory": [],
        }
        timeline_entries = normalize_timeline_from_html(
            SAMPLE_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-07T00:00:00Z",
        )

        findings = match_deprecations(
            inventory, timeline_entries, analysis_date="2026-07-07"
        )

        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
