import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from activities_lifecycle import normalize_activities_lifecycle_from_html
from matcher import match_activities_lifecycle
from out_of_support_matcher import (
    collect_server_product_records,
    match_out_of_support_products,
)
from out_of_support_versions import (
    normalize_out_of_support_from_html,
    out_of_support_trains,
    platform_out_of_support_trains,
)
from project_inventory import scan_inputs

ANALYSIS_DATE = "2026-07-17"
FETCHED_AT = "2026-07-17T00:00:00+00:00"
ALC_URL = "https://docs.uipath.com/overview/other/latest/overview/activities-lifecycle"
OOS_URL = "https://docs.uipath.com/overview/other/latest/overview/out-of-support-versions"


def _alc_entries():
    html = (FIXTURES / "activities-lifecycle.html").read_text(encoding="utf-8")
    return normalize_activities_lifecycle_from_html(html, ALC_URL, FETCHED_AT)


def _oos_entries():
    html = (FIXTURES / "out-of-support-versions.html").read_text(encoding="utf-8")
    return normalize_out_of_support_from_html(html, OOS_URL, FETCHED_AT)


class ActivitiesLifecycleNormalizationTests(unittest.TestCase):
    def test_matrix_is_parsed_into_release_trains(self):
        entries = _alc_entries()
        excel = next(e for e in entries if e["package_name"] == "UiPath.Excel.Activities")
        bands = {v["release_train"]: v["version"] for v in excel["versions_by_release"]}
        self.assertEqual(bands["2025.10"], "3.3.1")
        self.assertEqual(bands["2023.10"], "2.22.4")
        self.assertEqual(bands["2018.4"], "2.5.1")


class OutOfSupportNormalizationTests(unittest.TestCase):
    def test_rowspan_product_is_carried_forward(self):
        entries = _oos_entries()
        studio_versions = {e["version"] for e in entries if e["product"] == "Studio"}
        # Every Studio row must be attributed to Studio despite the rowspan product cell.
        self.assertEqual(
            studio_versions,
            {"2023.4.14", "2022.10.18", "2022.4.10", "2021.10.10", "2018.4.8"},
        )
        orchestrator = {e["release_train"] for e in entries if e["product"] == "Orchestrator"}
        self.assertEqual(orchestrator, {"2022.10", "2022.4", "2021.10"})

    def test_studiox_label_is_canonicalized_to_studio(self):
        entries = _oos_entries()
        self.assertNotIn("Studio StudioX", {e["product"] for e in entries})

    def test_platform_trains_out_of_support(self):
        trains = platform_out_of_support_trains(_oos_entries(), ANALYSIS_DATE)
        self.assertIn("2022.10", trains)
        self.assertIn("2023.4", trains)
        # Supported trains are absent from the out-of-support set.
        self.assertNotIn("2023.10", trains)
        self.assertNotIn("2024.10", trains)

    def test_future_dated_row_is_not_out_of_support(self):
        # If the analysis date precedes an end-of-support date, that train is still supported.
        trains = platform_out_of_support_trains(_oos_entries(), "2025-01-01")
        self.assertNotIn("2022.10", trains)  # Studio 2022.10 EOS is Oct 27, 2025.


class ActivitiesLifecycleMatchTests(unittest.TestCase):
    def test_below_floor_version_is_flagged_and_supported_is_not(self):
        inventory = {
            "projects": [{"name": "P", "compatibility": "windows"}],
            "package_inventory": [
                {
                    "project_name": "P",
                    "package_name": "UiPath.Excel.Activities",
                    "version": "2.0.0",
                    "evidence": ["project.json"],
                },
                {
                    "project_name": "P",
                    "package_name": "UiPath.System.Activities",
                    "version": "25.10.5",
                    "evidence": ["project.json"],
                },
            ],
        }
        trains = platform_out_of_support_trains(_oos_entries(), ANALYSIS_DATE)
        findings = match_activities_lifecycle(inventory, _alc_entries(), trains, ANALYSIS_DATE)
        flagged = {f["package_name"] for f in findings}
        self.assertEqual(flagged, {"UiPath.Excel.Activities"})
        finding = findings[0]
        self.assertEqual(finding["classification"], "Out Of Support")
        self.assertEqual(finding["risk_level"], "High")
        self.assertEqual(finding["min_supported_version"], "2.22.4")

    def test_no_supported_train_yields_no_finding(self):
        # When every train is out of support (no floor), avoid a false positive.
        inventory = {
            "projects": [{"name": "P"}],
            "package_inventory": [
                {
                    "project_name": "P",
                    "package_name": "UiPath.Excel.Activities",
                    "version": "2.0.0",
                    "evidence": ["project.json"],
                }
            ],
        }
        every_train = {
            v["release_train"]: "2020-01-01"
            for e in _alc_entries()
            for v in e["versions_by_release"]
        }
        findings = match_activities_lifecycle(inventory, _alc_entries(), every_train, ANALYSIS_DATE)
        self.assertEqual(findings, [])


class ProductOutOfSupportMatchTests(unittest.TestCase):
    def test_client_studio_train_is_flagged(self):
        records = [{"product": "Studio", "version": "22.10.5", "domain": "client", "project_name": "P"}]
        findings = match_out_of_support_products(records, _oos_entries(), ANALYSIS_DATE)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["status"], "out_of_support")
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["release_train"], "2022.10")
        self.assertEqual(findings[0]["deadline"], "2025-10-27")

    def test_supported_train_is_not_flagged(self):
        records = [{"product": "Studio", "version": "2024.10.3", "domain": "client"}]
        findings = match_out_of_support_products(records, _oos_entries(), ANALYSIS_DATE)
        self.assertEqual(findings, [])

    def test_server_service_version_is_flagged(self):
        server_inventory = {
            "server_evidence": [
                {
                    "product": "Orchestrator",
                    "service_version": "2022.10.4",
                    "path": "export/orchestrator.json",
                    "tenant": "Prod",
                }
            ]
        }
        records = collect_server_product_records(server_inventory)
        findings = match_out_of_support_products(records, _oos_entries(), ANALYSIS_DATE)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["domain"], "server")
        self.assertEqual(findings[0]["product"], "Orchestrator")
        self.assertEqual(findings[0]["service_version"], "2022.10.4")


class ProjectInventoryProductTests(unittest.TestCase):
    def test_studio_version_is_captured(self):
        inventory = scan_inputs(FIXTURES / "out-of-support-project")
        products = inventory["product_inventory"]
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["product"], "Studio")
        self.assertEqual(products[0]["version"], "22.10.5")


class EndToEndTests(unittest.TestCase):
    def test_offline_run_produces_out_of_support_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "reports"
            timeline_cache = Path(tmp) / "timeline.json"
            timeline_cache.write_text(
                json.dumps({"source_url": "x", "fetched_at": FETCHED_AT, "entries": []}),
                encoding="utf-8",
            )
            argv = [
                "uipath_deprecation_analyzer.py",
                "--input", str(FIXTURES / "out-of-support-project"),
                "--output", str(output),
                "--mode", "client",
                "--offline",
                "--client-timeline-cache", str(timeline_cache),
                "--activities-lifecycle-cache", str(FIXTURES / "activities-lifecycle-cache.json"),
                "--out-of-support-cache", str(FIXTURES / "out-of-support-cache.json"),
                "--analysis-date", ANALYSIS_DATE,
                "--format", "json",
            ]
            import uipath_deprecation_analyzer as cli

            with patch.object(sys, "argv", argv):
                self.assertEqual(cli.main(), 0)

            findings = json.loads(
                (output / "uipath_deprecation_findings.json").read_text(encoding="utf-8")
            )
            findings = findings["findings"] if isinstance(findings, dict) else findings
            oos = [f for f in findings if f["status"] == "out_of_support"]
            self.assertTrue(any(f["feature_or_package"] == "UiPath.Excel.Activities" for f in oos))
            self.assertTrue(any(str(f.get("product")) == "Studio" for f in oos))
            self.assertTrue(all(f["severity"] == "high" for f in oos))


if __name__ == "__main__":
    unittest.main()
