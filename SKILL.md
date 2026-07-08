---
name: uipath-deprecation-analyzer
description: Analyze UiPath RPA source projects, GitHub checkouts, mixed folders, and Orchestrator-downloaded .nupkg packages for deprecated, removed, or soon-to-be-removed NuGet activity packages using the live UiPath deprecation timeline. Use when auditing UiPath package dependencies, Windows-Legacy/.NET Framework 4.6.1 compatibility impact, replacement package recommendations, remediation roadmaps, portfolio risk, or deprecation reports.
---

# UiPath Deprecation Analyzer

Use this skill to audit UiPath automation projects and package artifacts for NuGet activity packages that are deprecated, removed, or scheduled for removal.

## Source of Truth

Use the live UiPath deprecation timeline:

`https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline`

Fetch the live timeline by default every time the skill is used. Cached normalized data is only a fallback when the live fetch fails, or an explicit offline/repeatable test aid when `--use-cache-only` is requested.

## Scope Rules

Analyze NuGet/activity package items and package-like ML/OCR entries that can map to project dependencies or package artifacts. Keep entries such as `UiPath.*.Activities`, canonicalized short package names, `UiPath.DocumentUnderstanding.ML`, and Document Understanding ML package identifiers when they appear in the timeline.

## Workflow

1. Identify the input: source project folder, GitHub checkout, folder of `.nupkg` packages, Orchestrator package export, or mixed folder.
2. If Orchestrator package download is needed, use the available UiPath/Orchestrator tooling in the environment. Do not ask for or store secrets; use existing authenticated CLI/session state.
3. Run the analyzer:

   ```bash
   python scripts/uipath_deprecation_analyzer.py --input ./repo --output ./reports --format markdown,json,csv,xlsx
   ```

4. Review the Markdown report first for executive summary, highest-risk findings, replacement mapping, Windows-Legacy impact, manual review items, and remediation roadmap.
5. Use the JSON report for automation, CSV for portfolio tracking, and Excel for stakeholder review.
6. For each finding, confirm package evidence paths before recommending remediation.
7. Only recommend replacement packages stated in the UiPath timeline. If none is stated, use: `No direct replacement stated - review manually.`

## Scripts

- `scripts/uipath_deprecation_analyzer.py`: CLI entrypoint.
- `scripts/project_inventory.py`: scans source projects and `.nupkg` packages using embedded UiPath project discovery and package inventory logic.
- `scripts/timeline.py`: fetches, filters, normalizes, and caches package-like timeline entries.
- `scripts/matcher.py`: matches project/package inventory to normalized timeline entries and classifies risk.
- `scripts/reports.py`: generates Markdown, JSON, CSV, and Excel outputs.

CLI flags:

```text
--input PATH
--output PATH
--refresh-timeline
--use-cache-only
--timeline-cache PATH
--format markdown,json,csv,xlsx
--include-xaml
--include-nupkg
--strict
--analysis-date YYYY-MM-DD
```

Live timeline refresh is the default. Use `--use-cache-only` with `--timeline-cache` for offline or repeatable audits. Use `--analysis-date` for repeatable classification and tests. Use `--strict` to skip Windows-Legacy-only timeline entries for non-legacy projects.

## References

Read only the reference needed for the task:

- `references/normalized_timeline_schema.md`: normalized timeline fields.
- `references/package_matching_rules.md`: matching, classification, and false-positive rules.
- `references/report_schema.md`: report payload and output structure.
- `references/risk_scoring_model.md`: risk, urgency, effort, and value model.
- `references/example_findings.md`: examples of expected findings and recommendations.

## Validation

Before presenting results as final, run:

```bash
python -m unittest discover -s tests
```

For this repository, run from the skill package root.

Confirm:

- timeline parsing ignores non-NuGet entries,
- project and `.nupkg` inventory includes evidence paths,
- findings include package name, version, classification, recommendation, risk, urgency, confidence, and source URL,
- Markdown, JSON, CSV, and Excel reports are generated when requested.
