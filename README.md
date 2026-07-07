# UiPath Deprecation Analyzer Skill

Portable coding-agent skill for auditing UiPath RPA projects and package artifacts for deprecated, removed, or soon-to-be-removed NuGet activity packages.

The skill uses the live UiPath deprecation timeline as the source of truth:

```text
https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline
```

## What This Skill Does

- Scans UiPath source projects, GitHub checkouts, mixed folders, and `.nupkg` package folders.
- Extracts package evidence from `project.json`, `.xaml`, `.nuspec`, and `.nupkg` contents.
- Fetches and normalizes package-only entries from the UiPath deprecation timeline.
- Matches project package usage against deprecated, removed, and scheduled-removal package entries.
- Flags Windows-Legacy / `.NET Framework 4.6.1` compatibility impact.
- Generates Markdown, JSON, CSV, and Excel reports with recommendations and impact analysis.

## Project Structure

```text
.
|-- SKILL.md
|-- scripts/
|   |-- uipath_deprecation_analyzer.py
|   |-- project_inventory.py
|   |-- timeline.py
|   |-- matcher.py
|   `-- reports.py
|-- references/
|   |-- normalized_timeline_schema.md
|   |-- package_matching_rules.md
|   |-- report_schema.md
|   |-- risk_scoring_model.md
|   `-- example_findings.md
`-- tests/
    |-- test_deprecation_analyzer.py
    `-- fixtures/
```

## Prerequisites

- Python 3.10 or newer.
- Network access when using `--refresh-timeline`.
- Optional: `openpyxl` for richer Excel output. If it is not installed, the script writes a minimal `.xlsx` using the Python standard library.
- Optional: authenticated UiPath/Orchestrator tooling if you need to download `.nupkg` packages before scanning.

## Supported Inputs

Use `--input` to point to any of these:

- a local UiPath RPA project folder,
- a GitHub repository checkout containing one or more UiPath projects,
- a folder of Orchestrator-downloaded `.nupkg` packages,
- a mixed folder containing source projects and package artifacts.

## Quick Start

From this repository root:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./path/to/uipath/repo --output ./reports --refresh-timeline --format markdown,json,csv,xlsx
```

Offline or repeatable run using a cached timeline file:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./path/to/uipath/repo --output ./reports --timeline-cache ./tests/fixtures/timeline-cache.json --format markdown,json,csv,xlsx --analysis-date 2026-07-07
```

Run against a folder of `.nupkg` files:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./packages --output ./reports --include-nupkg --refresh-timeline
```

## CLI Options

```text
--input PATH              Project, repository, mixed folder, or .nupkg folder to scan.
--output PATH             Directory where reports are written.
--refresh-timeline        Fetch the latest UiPath deprecation timeline.
--timeline-cache PATH     Read/write normalized timeline cache JSON.
--format LIST             Comma-separated formats: markdown,json,csv,xlsx,all.
--include-xaml            Include XAML namespace/activity package evidence.
--include-nupkg           Include .nupkg package inspection.
--strict                  Skip Windows-Legacy-only entries for non-legacy or unknown projects.
--analysis-date DATE      Use YYYY-MM-DD for repeatable classification.
```

## Generated Reports

The analyzer writes reports under `--output`:

- `uipath_deprecation_report.md`: human-readable executive and technical report.
- `uipath_deprecation_findings.json`: structured automation payload.
- `uipath_deprecation_findings.csv`: portfolio tracking export.
- `uipath_deprecation_report.xlsx`: workbook with summary, findings, package inventory, replacement mapping, Windows-Legacy impact, manual review, and roadmap sheets.

## How Coding Agents Should Use It

Agents such as Codex, Claude Code, Copilot, and Antigravity should load `SKILL.md` first. The skill file defines:

- when to use the skill,
- which timeline source to trust,
- which non-package timeline entries to ignore,
- which scripts to run,
- which reference files to read for schemas, matching rules, and risk scoring.

The main execution path is:

1. Identify the input folder.
2. Decide whether to refresh the live timeline or use an existing cache.
3. Run `scripts/uipath_deprecation_analyzer.py`.
4. Review the Markdown report first.
5. Use JSON/CSV/Excel outputs for automation, tracking, and stakeholder review.

## Validation

Run the unit tests:

```bash
python -m unittest discover -s tests
```

Validate the skill metadata if the Codex skill creator tools are available:

```bash
python C:\Users\jeet.doshi\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
```

## Notes

- The analyzer only treats NuGet/activity package timeline entries as actionable findings.
- It intentionally ignores non-package deprecations such as platform infrastructure, Docker/Kubernetes dependencies, AI Center model changes, Apps UI changes, and Orchestrator platform features without package impact.
- If UiPath docs do not state a replacement package, the recommendation is: `No direct replacement stated - review manually.`
