# Report Schema

The analyzer builds one JSON payload and renders Markdown, CSV, and Excel from it.

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

Finding fields:

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

Excel worksheets:

- Summary
- Findings
- Package Inventory
- Replacement Mapping
- Windows-Legacy Impact
- Manual Review
- Remediation Roadmap
