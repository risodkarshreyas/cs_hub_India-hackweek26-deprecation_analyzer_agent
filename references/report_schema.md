# Legacy Client Report Schema

The client analyzer scripts build one JSON payload and render Markdown, CSV, and Excel from it. This file documents the raw client payload. Final user-facing reports must be normalized to `references/common_analysis_rules.md`.

Top-level fields:

| Field | Meaning |
|---|---|
| `analysis_date` | Date used for classification. |
| `summary` | Counts for projects, packages, timeline entries, findings, risks, and manual review. |
| `projects` | Source and `.nupkg` project/package units scanned. |
| `package_inventory` | Package evidence records. |
| `timeline_entries` | Normalized package-only timeline entries. |
| `findings` | Matched deprecation findings. |
| `manual_review` | Findings without documented replacement package. |
| `remediation_roadmap` | Grouped actions by urgency window. |

Raw client finding fields:

- `project_name`
- `package_name`
- `current_version`
- `classification`
- `risk_level`
- `urgency`
- `recommendation`
- `replacement_package`
- `affected_version`
- `deprecation_date`
- `removal_date`
- `compatibility_scope`
- `project_compatibility`
- `evidence`
- `source_url`
- `source_section_title`
- `source_text`
- `confidence`
- `owner_action`
- `validation_steps`
- `impact`

Normalize raw findings before presentation:

| Raw client field | Common field |
|---|---|
| `classification` | `status` |
| `risk_level` | `severity` |
| `package_name` | `feature_or_package` and optional `package_name` |
| `recommendation` | `recommended_action` |
| `removal_date` | `deadline` |
| `source_url` | `source_url` |
| `evidence` | `evidence` |
| `confidence` | `confidence` |

Add common fields that the raw client payload may not include: `id`, `domain`, `product`, `environment`, `mitigation_route`, `recommended_skill`, `time_savings_kpi`, and `owner_hint`.

Excel worksheets:

- Summary
- Findings
- Package Inventory
- Replacement Mapping
- Windows-Legacy Impact
- Manual Review
- Remediation Roadmap

## Dashboard-Ready Payload

The static HTML dashboard is generated from the normalized common payload, not from the legacy raw client payload or Excel formatting.

Top-level dashboard payload fields:

| Field | Meaning |
|---|---|
| `analysis_date` | Date used for classification and deadline buckets. |
| `summary` | Aggregate counts and KPI totals. |
| `findings` | Normalized common finding objects. |
| `coverage_gaps` | Missing or incomplete evidence that should not be reported as confirmed findings. |
| `inventory_summary` | Optional route and inventory counts. |
| `raw_client_summary` | Optional legacy client summary for traceability. |
| `remediation_roadmap` | Grouped remediation actions. |

Dashboard summary metrics should include or derive:

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

The HTML dashboard must use `feature_or_package` and nested `time_savings_kpi` values from normalized findings. Do not introduce dashboard-only replacements such as `feature`, `manual_baseline_hours`, or `hours_saved` at the finding root.
