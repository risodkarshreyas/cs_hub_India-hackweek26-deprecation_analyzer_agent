# Client Inventory XLSX Schema

Use a modern `.xlsx` workbook when source projects or NuGet packages are unavailable. The analyzer accepts either the structured inventory contract below or recognizable repository/search evidence tables. Legacy `.xls` files are not parsed; convert them to `.xlsx` first.

## Parsing Modes

- `auto` (default): use the structured inventory when exactly one matching sheet exists; otherwise inspect recognizable evidence tables.
- `strict`: require exactly one sheet with the structured inventory headers.
- `evidence`: force evidence-table extraction even when structured headers are present.

Choose the mode with `--xlsx-mode auto|strict|evidence`. Input workbooks are read-only and are never rewritten.

## Structured Workbook Contract

In `strict` mode, the workbook must contain exactly one visible worksheet whose header row includes these required headers. In `auto` mode, one matching sheet selects this structured path; multiple matching sheets are processed through the evidence-table path and merged conservatively.

- `Automation / Project Name`
- `Dependency Name`
- `Dependency Version`

Accepted aliases include `Project Name`, `Automation Name`, `Package Name`, and `Package Version`. Header matching ignores case, spaces, and punctuation.

Optional columns:

| Column | Purpose |
|---|---|
| `Studio Version` | Enables Studio release-train out-of-support analysis. |
| `Project Compatibility` | Accepts `Windows-Legacy`, `Windows`, or `Cross-platform`. |
| `Target Framework` | Preserves the raw target and derives compatibility when the explicit value is absent. |
| `Workflow / XAML Path` | Adds package-specific workflow evidence; repeat a dependency row for each workflow. |
| `Project Version` | Records the analyzed automation release. |
| `Source Artifact` | Identifies the project, package, or export that supplied the row. |
| `Environment Name` | Separates the same automation across environments. |
| `Automation Owner` | Supplies the normalized finding owner hint. |
| `Inventory Date` | Accepts `YYYY-MM-DD` and records evidence freshness. |

Each dependency row needs both dependency fields. A row with both fields blank is valid project metadata. Store versions as text so Excel does not alter semantic versions.

## Analysis Rules

- The analysis unit is `(Automation / Project Name, Environment Name)`.
- Identical package/version rows merge while retaining distinct workflow and row evidence.
- Conflicting versions remain usable only for package-wide rules; version-scoped and support-floor checks are suppressed.
- Missing or malformed versions follow the same package-wide-only behavior.
- Unknown compatibility excludes Windows-Legacy-only rules.
- Missing workflow paths lower impact confidence but do not block package analysis.
- A valid Studio version creates a Studio lifecycle record. XLSX input does not create Robot lifecycle records.
- Workbook, worksheet, row, source artifact, and workflow provenance are preserved in evidence.
- Invalid rows and unavailable coverage are reported as coverage gaps, not deprecation findings.

## Flexible Evidence Tables

Evidence-table extraction recognizes normalized aliases such as `Parent Folder`, `Repository`, `Project Name`, `File Path`, `Source Artifact`, `Keyword`, `Package`, `Line Number`, `Line Content`, and `Context`. The analyzer searches the first 50 populated rows for a header and scans every relevant detail sheet; summary sheets without UiPath package evidence are ignored.

Exact JSON/project dependency declarations, NuGet XML dependency declarations, and explicit package/version column pairs can create package inventory records. Multiple declarations in a context cell are extracted and deduplicated. Project identity is derived from an extracted package/project path when available, with repository or parent-folder values retained as provenance. Framework segments such as `lib/net45`, `net461`, `net6.0-windows`, and `netstandard` supply compatibility evidence.

Conservative evidence rules apply:

- Exact package/version declarations are matchable with at most `medium` evidence confidence.
- Runtime-only packages, assembly type references, malformed versions, and ambiguous associations are coverage gaps, not findings.
- Separate extracted automation artifacts inside one repository remain separate analysis units.
- Duplicate search rows and temporary-project paths merge while preserving distinct evidence locations.
- Search exports are partial inventories. Missing Studio/Robot versions and dependencies not visible in the workbook remain explicit coverage gaps.

Reports include additive XLSX diagnostics: workbooks, sheets, and rows scanned; extraction method; exact dependencies found; rejected inferred records; ignored sheets; and unresolved rows.

## Copyable Template

Create one worksheet and paste these headers and example rows. Format version columns as text.

| Automation / Project Name | Dependency Name | Dependency Version | Studio Version | Project Compatibility | Target Framework | Workflow / XAML Path | Project Version | Source Artifact | Environment Name | Automation Owner | Inventory Date |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Invoice Processing | UiPath.Excel.Activities | 2.20.1 | 22.4.10.0 | Windows-Legacy | net461 | Main.xaml | 1.3.0 | InvoiceProcessing.1.3.0.nupkg | Production | Finance RPA | 2026-07-21 |
| Invoice Processing | UiPath.Excel.Activities | 2.20.1 | 22.4.10.0 | Windows-Legacy | net461 | Framework/Process.xaml | 1.3.0 | InvoiceProcessing.1.3.0.nupkg | Production | Finance RPA | 2026-07-21 |
| Queue Dispatcher | UiPath.System.Activities | 23.4.5 | 23.4.8.0 | Windows | net6.0-windows7.0 | Main.xaml | 2.0.0 | QueueDispatcher/project.json | Test | Automation CoE | 2026-07-21 |

Run the workbook directly:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./client-inventory.xlsx --output ./reports --mode client --format markdown,json,csv,xlsx,html
```

For a repository/search export, the same command uses `--xlsx-mode auto` by default. Add `--xlsx-mode strict` to disable fallback extraction.
