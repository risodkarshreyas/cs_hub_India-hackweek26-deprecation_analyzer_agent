# Reporting Dashboard Contract

Use this reference when the user asks for an HTML dashboard, executive dashboard, reporting UI, dashboard-ready output, or server-side report output for UiPath deprecation findings.

The dashboard must be generated from the normalized common report payload. Do not reverse-engineer Excel workbook formatting.

## Static HTML Dashboard Contract

Generate a self-contained static HTML file:

- Output file: `uipath_deprecation_dashboard.html`
- Runtime: no external server, JavaScript, CSS, fonts, or CDN dependency
- Styling: inline CSS in the HTML document
- Source data: same normalized payload used for Markdown, JSON, CSV, and XLSX outputs

The dashboard must keep JSON and XLSX outputs as compatibility artifacts. HTML is additive and must not change the common finding schema.

## Inputs

Preferred input:

- `uipath_deprecation_findings.json`: normalized analyzer payload with top-level `summary`, `findings`, and `coverage_gaps`.

Optional split inputs for future dashboard-only tools:

- `findings.json`: list of normalized finding objects.
- `summary.json`: aggregate counts and scan metadata.
- `scan_metadata.json`: environment name, scan timestamp, source refresh timestamp, analyzer version, and input file list.

If split inputs are absent, compute dashboard metrics from the normalized payload.

## Required Sections

The HTML dashboard must include:

- Header with report title, analysis date, total findings, and next deadline.
- KPI row with critical count, high count, products impacted, next deadline, and total AI hours saved.
- Risk by product table or bar-style summary.
- Deadline timeline grouped into overdue, 0-30, 31-90, 91-180, 180+ days, and no date.
- Top findings table with severity, product, `feature_or_package`, evidence, deadline, mitigation route, recommended skill, and AI hours saved.
- Recommended actions sorted by severity and deadline.
- AI savings section with manual baseline hours, AI-assisted hours, hours saved, percent saved, and KPI basis or confidence when available.
- Coverage gaps section.
- Appendix with source URLs and raw evidence.

## Data Contract

Use the common finding schema from `references/common_analysis_rules.md`.

Required finding fields:

- `id`
- `severity`
- `status`
- `domain`
- `product`
- `feature_or_package`
- `environment`
- `evidence`
- `impact`
- `deadline`
- `recommended_action`
- `mitigation_route`
- `recommended_skill`
- `time_savings_kpi`
- `owner_hint`
- `confidence`
- `source_url`

Use nested KPI values from `time_savings_kpi`:

- `manual_baseline_hours`
- `ai_assisted_hours`
- `hours_saved`
- `percent_saved`
- `basis`
- `confidence`

Do not replace `feature_or_package` with `feature` in the dashboard contract. Server-side raw findings may use `feature`, but normalized output must use `feature_or_package`.

## Summary Metrics

Derive these metrics from the payload when not already present:

- `total_findings`
- `severity_counts`
- `status_counts`
- `domain_counts`
- `product_counts`
- `coverage_gap_count`
- `total_estimated_hours_saved`
- next deadline
- products impacted
- deadline bucket counts
- manual baseline hours total
- AI-assisted hours total
- hours saved total
- percent saved

## Display Rules

- Use consistent severity colors:
  - `critical`: red
  - `high`: orange
  - `medium`: amber
  - `low`: blue or gray
- Show every finding with a source URL, or mark the source as `missing`.
- Show evidence for every confirmed finding. If evidence is absent, label the item as missing evidence and treat the missing context as a coverage gap where possible.
- Keep recommendations action-oriented.
- Keep coverage gaps separate from findings.
- Escape all displayed values before writing HTML.
- Redact tokens, passwords, client secrets, cookies, bearer headers, connection strings, and keys before display. Preserve existing `[REDACTED]` markers.

## CLI Expectations

The analyzer should support:

```bash
python scripts/uipath_deprecation_analyzer.py --input <path> --output <reports> --mode auto --format markdown,json,xlsx,html
```

Server-side examples must include `html` as a mandatory output format:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./tenant-export --output ./reports --mode server --format markdown,json,xlsx,html
```

Client-side examples may include `html` when the user requests a dashboard.
