import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from matcher import match_activities_lifecycle, match_deprecations
from normalizer import normalize_client_finding, normalize_product_finding
from out_of_support_matcher import match_out_of_support_products
from project_inventory import scan_inputs
from reports import build_report_payload, render_markdown_report
from timeline import fetch_timeline, normalize_timeline_from_html
from uipath_deprecation_analyzer import _resolve_route


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

GROUPED_TIMELINE_HTML = """
<html>
  <body>
    <h3>Activities</h3>
    <h4>Upcoming removals</h4>
    <table>
      <tr>
        <th>Feature or capability</th>
        <th>Removal announced on</th>
        <th>Scheduled removal date</th>
        <th>Notes</th>
      </tr>
      <tr>
        <td>UiPath.Abbyy.Activities</td>
        <td>October 3, 2024</td>
        <td>August 2025</td>
        <td>The alternative to UiPath.Abbyy.Activities is to replace it with UiPath.IntelligenctOCR.Activities.</td>
      </tr>
      <tr>
        <td>UiPath.AbbyyEmbedded.Activities</td>
        <td>October 3, 2024</td>
        <td>August 2025</td>
        <td>The alternative for UiPath.AbbyyEmbedded.Activities is UiPath.OCR.Activities.</td>
      </tr>
      <tr>
        <td>
          Support for .NET Framework 4.6.1 in the following activity packages, starting with the mentioned version:
          UiPath.Credentials.Activities 3.x.x
          UiPath.Cryptography.Activities 2.x.x
          UiPath.System.Activities 25.x
        </td>
        <td>January 2025</td>
        <td>December 2025</td>
        <td>Windows - Legacy projects should stay on supported package versions.</td>
      </tr>
      <tr>
        <td>
          Support for .NET Framework 4.6.1 in the following activity packages, starting with the mentioned version:
          IntelligentOCR.Activities 7.x
          PDF.Activities 4.x
          DocumentUnderstanding.ML 2.x
          OCR.Activities 4.x
          CommunicationsMining.Activities 2.x
          OmniPage 2.x
        </td>
        <td>August 2025</td>
        <td>January 2026</td>
        <td>Windows - Legacy projects should stay on supported package versions.</td>
      </tr>
    </table>
    <h3>Document Understanding</h3>
    <h4>Deprecated features or capabilities</h4>
    <table>
      <tr>
        <th>Feature or capability</th>
        <th>Deprecation announced in</th>
        <th>Deprecated in</th>
        <th>Notes</th>
      </tr>
      <tr>
        <td>Security updates for Document Understanding 2022.4 ML packages: python37duv3 and python37duv4 in Automation Suite 2022.10.13 onwards</td>
        <td>August 2024</td>
        <td>August 2024</td>
        <td>We recommend updating to a newer model.</td>
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

    def test_timeline_normalization_expands_grouped_packages_and_short_names(self):
        entries = normalize_timeline_from_html(
            GROUPED_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-07T00:00:00Z",
        )

        by_name = {entry["package_name"]: entry for entry in entries}

        expected_names = {
            "UiPath.Abbyy.Activities",
            "UiPath.AbbyyEmbedded.Activities",
            "UiPath.Credentials.Activities",
            "UiPath.Cryptography.Activities",
            "UiPath.System.Activities",
            "UiPath.IntelligentOCR.Activities",
            "UiPath.PDF.Activities",
            "UiPath.DocumentUnderstanding.ML",
            "UiPath.OCR.Activities",
            "UiPath.CommunicationsMining.Activities",
            "UiPath.OmniPage.Activities",
            "python37duv3",
            "python37duv4",
        }
        self.assertTrue(expected_names.issubset(by_name.keys()))
        self.assertEqual("2025-08-01", by_name["UiPath.Abbyy.Activities"]["removal_date"])
        self.assertEqual(
            "UiPath.IntelligenctOCR.Activities",
            by_name["UiPath.Abbyy.Activities"]["replacement_package"],
        )
        self.assertEqual(
            "UiPath.OCR.Activities",
            by_name["UiPath.AbbyyEmbedded.Activities"]["replacement_package"],
        )
        self.assertEqual("", by_name["UiPath.Credentials.Activities"]["replacement_package"])
        self.assertEqual("3.x.x", by_name["UiPath.Credentials.Activities"]["affected_version"])
        self.assertEqual("25.x", by_name["UiPath.System.Activities"]["affected_version"])
        self.assertEqual("4.x", by_name["UiPath.PDF.Activities"]["affected_version"])
        self.assertEqual("2026-01-01", by_name["UiPath.PDF.Activities"]["removal_date"])
        self.assertEqual(
            "windows_legacy_only",
            by_name["UiPath.DocumentUnderstanding.ML"]["compatibility_scope"],
        )
        self.assertTrue(by_name["UiPath.PDF.Activities"]["canonicalized_from"])
        self.assertEqual([], by_name["UiPath.PDF.Activities"]["normalization_warnings"])

    def test_fetch_timeline_refreshes_by_default_and_cache_only_is_explicit(self):
        live_html = SAMPLE_TIMELINE_HTML.encode("utf-8")

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return live_html

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "timeline.json"
            cache.write_text(
                json.dumps(
                    {
                        "source_url": "cache",
                        "fetched_at": "2026-01-01T00:00:00Z",
                        "entries": [{"package_name": "UiPath.Cached.Activities"}],
                    }
                ),
                encoding="utf-8",
            )

            with patch("timeline.urlopen", return_value=_Response()) as urlopen_mock:
                entries = fetch_timeline(cache_path=cache)

            self.assertEqual("UiPath.Legacy.Activities", entries[0]["package_name"])
            self.assertEqual(1, urlopen_mock.call_count)

            with patch("timeline.urlopen") as urlopen_mock:
                cached_entries = fetch_timeline(cache_path=cache, use_cache_only=True)

            self.assertEqual("UiPath.Legacy.Activities", cached_entries[0]["package_name"])
            self.assertEqual(0, urlopen_mock.call_count)

    def test_fetch_timeline_falls_back_to_cache_when_live_fetch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "timeline.json"
            cache.write_text(
                json.dumps(
                    {
                        "source_url": "cache",
                        "fetched_at": "2026-01-01T00:00:00Z",
                        "entries": [{"package_name": "UiPath.Cached.Activities"}],
                    }
                ),
                encoding="utf-8",
            )

            with patch("timeline.urlopen", side_effect=OSError("network down")):
                entries = fetch_timeline(cache_path=cache)

        self.assertEqual("UiPath.Cached.Activities", entries[0]["package_name"])

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

    def test_xlsx_inventory_extracts_projects_products_dependencies_and_workflows(self):
        headers = [
            "Project Name",
            "Package Name",
            "Package Version",
            "Studio Version",
            "Project Compatibility",
            "Target Framework",
            "Workflow Path",
            "Environment",
            "Automation Owner",
            "Inventory Date",
        ]
        rows = [
            ["Invoice", "UiPath.Legacy.Activities", "1.2.3", "20.10.2.0", "Windows-Legacy", "net461", "Main.xaml", "Production", "Finance RPA", "2026-07-21"],
            ["Invoice", "UiPath.Legacy.Activities", "1.2.3", "20.10.2.0", "Windows-Legacy", "net461", "Retry.xaml", "Production", "Finance RPA", "2026-07-21"],
            ["Modern", "", "", "22.4.10.0", "Windows", "net6.0-windows7.0", "", "Test", "CoE", "2026-07-21"],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "inventory.xlsx"
            _write_xlsx(workbook, [("Client Inventory", [headers, *rows])])
            inventory = scan_inputs(workbook)

        self.assertEqual(2, inventory["summary"]["project_count"])
        self.assertEqual(1, inventory["summary"]["package_count"])
        self.assertEqual(2, inventory["summary"]["product_count"])
        package = inventory["package_inventory"][0]
        self.assertEqual("invoice::production", package["inventory_key"])
        self.assertEqual("1.2.3", package["version"])
        self.assertEqual(["Main.xaml", "Retry.xaml"], package["workflow_evidence"])
        self.assertEqual(2, len(package["evidence"]))
        self.assertEqual("Finance RPA", package["automation_owner"])
        self.assertEqual([], inventory["coverage_gaps"])

    def test_xlsx_inventory_reports_conflicts_invalid_rows_and_unknown_compatibility(self):
        headers = [
            "Automation / Project Name",
            "Dependency Name",
            "Dependency Version",
            "Studio Version",
            "Project Compatibility",
        ]
        rows = [
            ["Invoice", "UiPath.Legacy.Activities", "1.2.3", "", ""],
            ["Invoice", "UiPath.Legacy.Activities", "2.0.0", "", ""],
            ["Invoice", "", "1.0.0", "", ""],
            ["Invoice", "UiPath.Excel.Activities", {"formula": "1+1"}, "", ""],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "invalid.xlsx"
            _write_xlsx(workbook, [("Inventory", [headers, *rows])])
            inventory = scan_inputs(workbook)

        by_name = {item["package_name"]: item for item in inventory["package_inventory"]}
        self.assertEqual("", by_name["UiPath.Legacy.Activities"]["version"])
        self.assertTrue(by_name["UiPath.Legacy.Activities"]["version_ambiguous"])
        self.assertFalse(by_name["UiPath.Excel.Activities"]["version_reliable"])
        messages = " ".join(gap["message"] for gap in inventory["coverage_gaps"])
        self.assertIn("Conflicting versions", messages)
        self.assertIn("Dependency Name is required", messages)
        self.assertIn("formula has no cached value", messages)
        self.assertIn("compatibility is unknown", messages)
        self.assertIn("Studio Version is unavailable", messages)

    def test_xlsx_strict_mode_requires_exactly_one_matching_worksheet(self):
        headers = ["Project Name", "Package Name", "Package Version"]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "ambiguous.xlsx"
            _write_xlsx(
                workbook,
                [
                    ("One", [headers, ["A", "UiPath.Excel.Activities", "1.0.0"]]),
                    ("Two", [headers, ["B", "UiPath.System.Activities", "1.0.0"]]),
                ],
            )
            inventory = scan_inputs(workbook, xlsx_mode="strict")

        self.assertEqual([], inventory["projects"])
        self.assertIn("Multiple worksheets", inventory["coverage_gaps"][0]["message"])

    def test_xlsx_auto_mode_merges_multiple_structured_worksheets(self):
        headers = ["Project Name", "Package Name", "Package Version"]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "portfolio.xlsx"
            _write_xlsx(
                workbook,
                [
                    ("One", [headers, ["A", "UiPath.Excel.Activities", "2.20.1"]]),
                    ("Two", [headers, ["B", "UiPath.System.Activities", "23.10.6"]]),
                ],
            )
            inventory = scan_inputs(workbook)

        self.assertEqual(2, inventory["summary"]["project_count"])
        self.assertEqual(
            {"UiPath.Excel.Activities", "UiPath.System.Activities"},
            {item["package_name"] for item in inventory["package_inventory"]},
        )
        self.assertEqual(["evidence"], inventory["summary"]["xlsx_extraction_methods"])

    def test_xlsx_evidence_table_extracts_exact_dependencies_and_rejects_inferences(self):
        headers = [
            "Parent Folder",
            "Keyword",
            "File Path",
            "File Type",
            "Line Number",
            "Line Content",
            "Context",
        ]
        rows = [
            [
                "repo-a",
                "UiPath.UIAutomation.Activities",
                r"deploy\STPWireAutomation.1.0.2_extracted\lib\net45\project.json",
                ".json",
                "12",
                '"UiPath.UIAutomation.Activities": "[22.10.3]"',
                '"UiPath.System.Activities": "[22.10.8]"',
            ],
            [
                "repo-a",
                "UiPath.UIAutomation.Activities",
                r"deploy\STPWireAutomation.1.0.2_extracted\lib\net45\Temp\project.json",
                ".json",
                "12",
                '"UiPath.UIAutomation.Activities": "[22.10.3]"',
                '"UiPath.System.Activities": "[22.10.8]"',
            ],
            [
                "repo-a",
                "UiPath.UIAutomation.Activities",
                r"deploy\ModernProcess.1.0.0_extracted\content\project.json",
                ".json",
                "10",
                '"UiPath.UIAutomation.Activities.Runtime": "[23.10.13]"',
                "",
            ],
            [
                "repo-b",
                "UiPath.UIAutomation.Activities",
                r"deploy\AssemblyOnly.1.0.0_extracted\lib\net45\project.json",
                ".json",
                "20",
                '"type": "UiPath.Core.UiElement, UiPath.UIAutomation.Activities, Version=22.10.3.0"',
                "",
            ],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "search-export.xlsx"
            _write_xlsx(
                workbook,
                [
                    ("attended", [["Search Results"], headers, *rows]),
                    ("Repository Summary", [["Repository Name", "Total Matches"], ["repo-a", "3"]]),
                ],
            )
            inventory = scan_inputs(workbook)

        packages = {item["package_name"]: item for item in inventory["package_inventory"]}
        self.assertEqual({"UiPath.UIAutomation.Activities", "UiPath.System.Activities"}, set(packages))
        ui_package = packages["UiPath.UIAutomation.Activities"]
        self.assertEqual("STPWireAutomation", ui_package["project_name"])
        self.assertEqual("22.10.3", ui_package["version"])
        self.assertEqual("repo-a", ui_package["repository_name"])
        self.assertEqual("12", ui_package["source_line_number"])
        self.assertEqual("json_dependency", ui_package["evidence_kind"])
        self.assertEqual("medium", ui_package["evidence_confidence"])
        self.assertEqual("windows_legacy", ui_package["project_compatibility"])
        self.assertEqual(2, len(ui_package["evidence"]))
        self.assertEqual(["Repository Summary"], inventory["xlsx_diagnostics"][0]["ignored_sheets"])
        messages = " ".join(item["message"] for item in inventory["coverage_gaps"])
        self.assertIn("Runtime-only package evidence", messages)
        self.assertIn("Assembly type evidence", messages)
        self.assertIn("partial", messages)

        lifecycle_findings = match_activities_lifecycle(
            inventory,
            [
                {
                    "package_name": "UiPath.UIAutomation.Activities",
                    "versions_by_release": [
                        {"release_train": "2023.10", "release_label": "2023.10 LTS", "version": "23.10.20"},
                        {"release_train": "2022.10", "release_label": "2022.10 LTS", "version": "22.10.10"},
                    ],
                    "source_url": "https://example.test/lifecycle",
                    "confidence": "high",
                }
            ],
            {"2022.10": "2025-11-14"},
            analysis_date="2026-07-21",
        )
        self.assertEqual(1, len(lifecycle_findings))
        self.assertEqual("medium", lifecycle_findings[0]["confidence"])

    def test_xlsx_evidence_table_supports_nuget_xml_and_ignores_business_workbooks(self):
        evidence_headers = ["Repository", "File Path", "Line Content", "Context"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "nuget.xlsx"
            business = root / "business.xlsx"
            _write_xlsx(
                evidence,
                [
                    (
                        "Matches",
                        [
                            evidence_headers,
                            [
                                "repo-a",
                                r"deploy\Invoice.2.0.0_extracted\lib\net6.0-windows7.0\project.json",
                                '<dependency version="2.20.1" id="UiPath.Excel.Activities">',
                                "",
                            ],
                            [
                                "repo-a",
                                r"deploy\Broken.1.0.0_extracted\project.json",
                                '"UiPath.Mail.Activities": "[latest]"',
                                "",
                            ],
                        ],
                    )
                ],
            )
            _write_xlsx(
                business,
                [("Forecast", [["Project", "Version", "Context"], ["Budget", "1.0", "Approved"]])],
            )
            evidence_inventory = scan_inputs(evidence)
            business_inventory = scan_inputs(business)

        package = evidence_inventory["package_inventory"][0]
        self.assertEqual("UiPath.Excel.Activities", package["package_name"])
        self.assertEqual("2.20.1", package["version"])
        self.assertEqual("windows", package["project_compatibility"])
        self.assertIn("no exact dependency version", " ".join(
            item["message"] for item in evidence_inventory["coverage_gaps"]
        ))
        self.assertEqual([], business_inventory["package_inventory"])
        self.assertIn("No worksheet contained", business_inventory["coverage_gaps"][0]["message"])

    def test_xlsx_evidence_ambiguous_version_skips_version_scoped_rule(self):
        inventory = {
            "projects": [
                {
                    "name": "Ambiguous",
                    "inventory_key": "ambiguous",
                    "compatibility": "windows_legacy",
                }
            ],
            "package_inventory": [
                {
                    "project_name": "Ambiguous",
                    "inventory_key": "ambiguous",
                    "package_name": "UiPath.System.Activities",
                    "version": "",
                    "version_reliable": False,
                    "version_ambiguous": True,
                    "source": "xlsx_evidence",
                    "evidence": ["inventory.xlsx!/Matches/row 2"],
                }
            ],
            "workflow_inventory": [],
        }
        entries = normalize_timeline_from_html(
            GROUPED_TIMELINE_HTML,
            source_url="https://example.test/timeline",
            fetched_at="2026-07-21T00:00:00Z",
        )

        findings = match_deprecations(inventory, entries, analysis_date="2026-07-21")

        self.assertFalse(
            any(item["package_name"] == "UiPath.System.Activities" for item in findings)
        )

    def test_xlsx_conflicting_project_metadata_suppresses_only_ambiguous_checks(self):
        headers = [
            "Project Name",
            "Package Name",
            "Package Version",
            "Studio Version",
            "Project Compatibility",
            "Target Framework",
            "Automation Owner",
            "Inventory Date",
        ]
        rows = [
            ["Invoice", "UiPath.Excel.Activities", "2.0.0", "22.4.10.0", "Windows-Legacy", "net461", "Team A", "not-a-date"],
            ["Invoice", "UiPath.Excel.Activities", "2.0.0", "23.4.8.0", "Windows", "net461", "Team B", "not-a-date"],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "metadata-conflict.xlsx"
            _write_xlsx(workbook, [("Inventory", [headers, *rows])])
            inventory = scan_inputs(workbook)

        self.assertEqual(1, inventory["summary"]["package_count"])
        self.assertEqual([], inventory["product_inventory"])
        self.assertEqual("unknown", inventory["projects"][0]["compatibility"])
        self.assertEqual("", inventory["projects"][0]["automation_owner"])
        self.assertEqual("", inventory["projects"][0]["inventory_date"])
        messages = " ".join(gap["message"] for gap in inventory["coverage_gaps"])
        self.assertIn("Conflicting studio version", messages)
        self.assertIn("Conflicting compatibility", messages)
        self.assertIn("Conflicting automation owner", messages)
        self.assertIn("not a valid YYYY-MM-DD", messages)

    def test_xls_inventory_is_reported_as_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "inventory.xls"
            legacy.write_bytes(b"legacy")
            inventory = scan_inputs(legacy)

        self.assertEqual([], inventory["projects"])
        self.assertIn("Convert the workbook to .xlsx", inventory["coverage_gaps"][0]["message"])

    def test_xlsx_inventory_is_discovered_recursively_and_routes_as_mixed(self):
        headers = ["Project Name", "Package Name", "Package Version"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "portfolio" / "client"
            nested.mkdir(parents=True)
            _write_xlsx(
                nested / "inventory.xlsx",
                [("Inventory", [headers, ["Invoice", "UiPath.Excel.Activities", "2.0.0"]])],
            )
            (root / "tenant-export.json").write_text("{}", encoding="utf-8")
            inventory = scan_inputs(root)
            route = _resolve_route("auto", root)

        self.assertEqual(1, inventory["summary"]["package_count"])
        self.assertEqual("mixed", route)

    def test_xlsx_unknown_compatibility_excludes_windows_legacy_only_rule(self):
        headers = ["Project Name", "Package Name", "Package Version"]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "unknown.xlsx"
            _write_xlsx(workbook, [("Inventory", [headers, ["Invoice", "UiPath.Legacy.Activities", "1.2.3"]])])
            inventory = scan_inputs(workbook)

        timeline_entries = normalize_timeline_from_html(
            SAMPLE_TIMELINE_HTML,
            source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
            fetched_at="2026-07-21T00:00:00Z",
        )
        self.assertEqual([], match_deprecations(inventory, timeline_entries, analysis_date="2026-07-21"))

    def test_xlsx_environment_and_owner_reach_normalized_package_and_studio_findings(self):
        headers = [
            "Project Name",
            "Package Name",
            "Package Version",
            "Studio Version",
            "Project Compatibility",
            "Environment Name",
            "Automation Owner",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "owned.xlsx"
            _write_xlsx(
                workbook,
                [("Inventory", [headers, ["Invoice", "UiPath.Legacy.Activities", "1.2.3", "20.10.2.0", "Windows-Legacy", "Production", "Finance RPA"]])],
            )
            inventory = scan_inputs(workbook)

        package_findings = match_deprecations(
            inventory,
            normalize_timeline_from_html(
                SAMPLE_TIMELINE_HTML,
                source_url="https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
                fetched_at="2026-07-21T00:00:00Z",
            ),
            analysis_date="2026-07-21",
        )
        normalized_package = normalize_client_finding(package_findings[0], 1, "2026-07-21")
        self.assertEqual("Production", normalized_package["environment"])
        self.assertEqual("Finance RPA", normalized_package["owner_hint"])

        product_findings = match_out_of_support_products(
            [{**inventory["product_inventory"][0], "domain": "client"}],
            [
                {
                    "product": "Studio",
                    "version": "2020.10",
                    "release_train": "2020.10",
                    "end_of_extended_support": "2023-10-31",
                    "source_url": "https://example.test/support",
                }
            ],
            analysis_date="2026-07-21",
        )
        normalized_product = normalize_product_finding(product_findings[0], 2, "2026-07-21")
        self.assertEqual("Production", normalized_product["environment"])
        self.assertEqual("Finance RPA", normalized_product["owner_hint"])

    def test_xlsx_offline_cli_writes_all_report_formats(self):
        headers = [
            "Project Name",
            "Package Name",
            "Package Version",
            "Studio Version",
            "Project Compatibility",
            "Workflow Path",
            "Environment Name",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = root / "inventory.xlsx"
            output = root / "reports"
            _write_xlsx(
                workbook,
                [("Inventory", [headers, ["Invoice", "UiPath.Legacy.Activities", "1.2.3", "22.4.10.0", "Windows-Legacy", "Main.xaml", "Production"]])],
            )
            argv = [
                "uipath_deprecation_analyzer.py",
                "--input", str(workbook),
                "--output", str(output),
                "--mode", "client",
                "--offline",
                "--client-timeline-cache", str(ROOT / "tests" / "fixtures" / "timeline-cache.json"),
                "--activities-lifecycle-cache", str(ROOT / "tests" / "fixtures" / "activities-lifecycle-cache.json"),
                "--out-of-support-cache", str(ROOT / "tests" / "fixtures" / "out-of-support-cache.json"),
                "--analysis-date", "2026-07-21",
                "--format", "all",
            ]
            import uipath_deprecation_analyzer as cli

            with patch.object(sys, "argv", argv):
                self.assertEqual(0, cli.main())

            report = json.loads((output / "uipath_deprecation_findings.json").read_text(encoding="utf-8"))
            dashboard_html = (output / "uipath_deprecation_dashboard.html").read_text(encoding="utf-8")
            generated = {path.name for path in output.iterdir()}
            with zipfile.ZipFile(output / "uipath_deprecation_report.xlsx") as zf:
                workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")

        self.assertTrue(
            {
                "uipath_deprecation_report.md",
                "uipath_deprecation_findings.json",
                "uipath_deprecation_findings.csv",
                "uipath_deprecation_report.xlsx",
                "uipath_deprecation_dashboard.html",
            }.issubset(generated)
        )
        self.assertTrue(any(item["feature_or_package"] == "UiPath.Legacy.Activities" for item in report["findings"]))
        self.assertTrue(any(item["product"] == "Studio" for item in report["findings"]))
        self.assertEqual("Production", report["findings"][0]["environment"])
        self.assertIn("Coverage Gaps", workbook_xml)
        self.assertIn('id="findings-data"', dashboard_html)
        self.assertIn('"version":', dashboard_html)

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


def _write_xlsx(path: Path, sheets: list[tuple[str, list[list[object]]]]) -> None:
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    workbook_sheets = []
    workbook_relationships = []
    with zipfile.ZipFile(path, "w") as zf:
        for index, (name, rows) in enumerate(sheets, 1):
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            workbook_sheets.append(
                f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
            )
            workbook_relationships.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
            row_xml = []
            for row_number, row in enumerate(rows, 1):
                cell_xml = []
                for column_index, value in enumerate(row, 1):
                    reference = f"{_column_letters(column_index)}{row_number}"
                    if isinstance(value, dict) and "formula" in value:
                        cached = value.get("cached")
                        cached_xml = f"<v>{escape(str(cached))}</v>" if cached is not None else ""
                        cell_xml.append(
                            f'<c r="{reference}"><f>{escape(str(value["formula"]))}</f>{cached_xml}</c>'
                        )
                    else:
                        cell_xml.append(
                            f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
                        )
                row_xml.append(f'<row r="{row_number}">{"".join(cell_xml)}</row>')
            zf.writestr(
                f"xl/worksheets/sheet{index}.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>',
            )
        content_types.append("</Types>")
        zf.writestr("[Content_Types].xml", "".join(content_types))
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        )
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(workbook_relationships)}</Relationships>',
        )


def _column_letters(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


if __name__ == "__main__":
    unittest.main()
