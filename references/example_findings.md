# Common Example Findings

## Removed Package

```json
{
  "id": "F-001",
  "severity": "critical",
  "status": "removed",
  "domain": "client",
  "product": "Studio/Robot activity packages",
  "feature_or_package": "UiPath.Legacy.Activities",
  "environment": "FinanceInvoiceBot",
  "evidence": ["FinanceInvoiceBot/project.json"],
  "impact": "The project references a package that is already removed according to the UiPath timeline.",
  "deadline": "2026-01-01",
  "recommended_action": "Replace with UiPath.Modern.Activities.",
  "mitigation_route": "ai_assisted_change",
  "recommended_skill": "uipath-rpa",
  "time_savings_kpi": {
    "manual_baseline_hours": 4.0,
    "ai_assisted_hours": 1.0,
    "hours_saved": 3.0,
    "percent_saved": 75,
    "basis": "AI matched project package evidence to the UiPath timeline and drafted the replacement route.",
    "confidence": "medium"
  },
  "owner_hint": "RPA maintainer",
  "confidence": "high",
  "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
  "project_name": "FinanceInvoiceBot",
  "package_name": "UiPath.Legacy.Activities",
  "current_version": "1.2.3",
  "replacement_package": "UiPath.Modern.Activities"
}
```

## Windows-Legacy Compatibility Impact

```json
{
  "id": "F-002",
  "severity": "high",
  "status": "deprecated",
  "domain": "client",
  "product": "Studio/Robot activity packages",
  "feature_or_package": "UiPath.SomePackage.Activities",
  "environment": "Windows-Legacy project",
  "evidence": ["LegacyDesktopBot/project.json"],
  "impact": "The package has a Windows-Legacy/.NET Framework compatibility impact that can block modernization.",
  "deadline": "",
  "recommended_action": "Migrate from Windows-Legacy or pin to the last supported package version documented by UiPath.",
  "mitigation_route": "owner_review",
  "recommended_skill": "uipath-rpa",
  "time_savings_kpi": {
    "manual_baseline_hours": 5.0,
    "ai_assisted_hours": 1.5,
    "hours_saved": 3.5,
    "percent_saved": 70,
    "basis": "AI identified project compatibility and mapped package risk to the timeline.",
    "confidence": "medium"
  },
  "owner_hint": "RPA maintainer",
  "confidence": "medium",
  "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
  "project_name": "LegacyDesktopBot",
  "package_name": "UiPath.SomePackage.Activities",
  "compatibility_scope": "windows_legacy_only",
  "project_compatibility": "Windows-Legacy"
}
```

## Manual Review

```json
{
  "id": "F-003",
  "severity": "medium",
  "status": "removal_scheduled",
  "domain": "client",
  "product": "Studio/Robot activity packages",
  "feature_or_package": "UiPath.Example.Activities",
  "environment": "ClaimsBot",
  "evidence": ["ClaimsBot.xaml"],
  "impact": "The project references a package with a scheduled removal and no direct replacement stated in the source.",
  "deadline": "2026-12-31",
  "recommended_action": "No direct replacement stated - review manually.",
  "mitigation_route": "owner_review",
  "recommended_skill": "uipath-rpa",
  "time_savings_kpi": {
    "manual_baseline_hours": 3.0,
    "ai_assisted_hours": 1.0,
    "hours_saved": 2.0,
    "percent_saved": 67,
    "basis": "AI found workflow evidence and isolated the package for owner review.",
    "confidence": "medium"
  },
  "owner_hint": "RPA maintainer",
  "confidence": "medium",
  "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
  "project_name": "ClaimsBot",
  "package_name": "UiPath.Example.Activities"
}
```

## Server-Side Orchestrator Finding

```json
{
  "id": "F-101",
  "severity": "high",
  "status": "removal_scheduled",
  "domain": "server",
  "product": "Orchestrator",
  "feature_or_package": "Testing Module in Orchestrator",
  "environment": "Automation Cloud tenant",
  "evidence": [
    {
      "path": "tenant-export/orchestrator/test_sets.json",
      "object": "Regression Suite",
      "matched_value": "Orchestrator test set"
    }
  ],
  "impact": "The tenant still manages test artifacts in Orchestrator for a feature scheduled for removal; ownership should move to Test Manager.",
  "deadline": "2026-06-30",
  "recommended_action": "Migrate test cases, test sets, schedules, execution history review, and validation ownership to Test Manager using UiPath migration guidance.",
  "mitigation_route": "ai_assisted_change",
  "recommended_skill": "uipath-test",
  "time_savings_kpi": {
    "manual_baseline_hours": 10.0,
    "ai_assisted_hours": 3.0,
    "hours_saved": 7.0,
    "percent_saved": 70,
    "basis": "AI mapped tenant export evidence to the timeline, selected Test Manager as the remediation route, and drafted owner validation steps.",
    "confidence": "medium"
  },
  "owner_hint": "QA/Test Manager owner",
  "confidence": "high",
  "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
  "delivery_model": "Automation Cloud",
  "tenant_or_service": "FinanceTenant",
  "configuration_object": "Orchestrator test set"
}
```

## Mixed Analysis Report

```json
{
  "executive_summary": {
    "overall_risk_posture": "High because the same deprecated Document Understanding ML package appears in project package evidence and AI Center service configuration.",
    "counts": {
      "severity": {
        "high": 1
      },
      "status": {
        "removal_scheduled": 1
      },
      "domain": {
        "mixed": 1
      },
      "product": {
        "Document Understanding": 1
      }
    },
    "coverage_gaps": []
  },
  "findings": [
    {
      "id": "F-201",
      "severity": "high",
      "status": "removal_scheduled",
      "domain": "mixed",
      "product": "Document Understanding",
      "feature_or_package": "UiPath.DocumentUnderstanding.ML",
      "environment": "ClaimsBot project and AI Center tenant",
      "evidence": [
        {
          "path": "ClaimsBot/project.json",
          "matched_value": "UiPath.DocumentUnderstanding.ML"
        },
        {
          "path": "tenant-export/aicenter/ml-packages.json",
          "object": "ClaimsExtractionModel",
          "matched_value": "UiPath.DocumentUnderstanding.ML"
        }
      ],
      "impact": "The same deprecated ML package is referenced by client automation code and tenant ML package configuration, so remediation requires coordinated RPA and platform ownership.",
      "deadline": "2026-01-01",
      "recommended_action": "Coordinate package migration with RPA maintainers and AI Center owners; use only UiPath-documented replacement guidance.",
      "mitigation_route": "owner_review",
      "recommended_skill": "uipath-deprecation-analyzer",
      "time_savings_kpi": {
        "manual_baseline_hours": 12.0,
        "ai_assisted_hours": 3.0,
        "hours_saved": 9.0,
        "percent_saved": 75,
        "basis": "AI correlated project dependency evidence with tenant ML package evidence and separated the remediation owners.",
        "confidence": "medium"
      },
      "owner_hint": "RPA maintainer and Platform admin",
      "confidence": "high",
      "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
      "project_name": "ClaimsBot",
      "package_name": "UiPath.DocumentUnderstanding.ML",
      "tenant_or_service": "AI Center",
      "configuration_object": "ML package"
    }
  ]
}
```
