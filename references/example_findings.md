# Example Findings

## Removed Package

```json
{
  "project_name": "FinanceInvoiceBot",
  "package_name": "UiPath.Legacy.Activities",
  "current_version": "1.2.3",
  "classification": "Already Removed",
  "risk_level": "Critical",
  "urgency": "Immediate",
  "recommendation": "Replace with UiPath.Modern.Activities.",
  "evidence": ["FinanceInvoiceBot/project.json"],
  "confidence": "high"
}
```

## Windows-Legacy Compatibility Impact

```json
{
  "project_name": "LegacyDesktopBot",
  "package_name": "UiPath.SomePackage.Activities",
  "classification": ".NET Framework 4.6.1 / Windows-Legacy Compatibility Impact",
  "risk_level": "High",
  "urgency": "Prioritize Windows/Cross-platform migration planning",
  "recommendation": "Migrate from Windows-Legacy or pin to the last supported package version documented by UiPath.",
  "evidence": ["LegacyDesktopBot/project.json"],
  "confidence": "medium"
}
```

## Manual Review

```json
{
  "project_name": "ClaimsBot",
  "package_name": "UiPath.Example.Activities",
  "classification": "Removal Scheduled",
  "recommendation": "No direct replacement stated - review manually.",
  "evidence": ["ClaimsBot.xaml"],
  "confidence": "medium"
}
```
