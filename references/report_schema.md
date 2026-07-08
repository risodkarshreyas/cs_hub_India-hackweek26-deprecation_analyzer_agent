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
