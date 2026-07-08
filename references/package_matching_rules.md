# Package Matching Rules

Use these rules when interpreting analyzer results or extending `scripts/matcher.py`.

## Package Evidence

Valid evidence sources:

- `project.json` dependency declarations.
- `.xaml` namespace, assembly, or activity package references.
- `.nuspec` dependency declarations.
- extracted `.nupkg` metadata and packaged `project.json`.

Every finding must retain evidence paths. For `.nupkg` files, use `package.nupkg!/path/inside/package`.

## Matching

Match in this order:

1. Exact package name, case-insensitive.
2. Version applicability when the normalized timeline has `affected_version`.
3. Compatibility applicability, especially `windows_legacy_only`.

Avoid fuzzy matching package names unless a human is reviewing the finding. False positives are worse than missed manual-review items.

## Legacy Client Classification

The client scripts currently classify raw package findings relative to `--analysis-date`:

- `Already Removed`: removal date is before the analysis date.
- `Removal Imminent`: removal date is within 6 months.
- `Removal Scheduled`: removal date is more than 6 months and up to 18 months away.
- `.NET Framework 4.6.1 / Windows-Legacy Compatibility Impact`: package impact is limited to Windows-Legacy/.NET Framework compatibility and the project is Windows-Legacy.

If a timeline entry lacks a removal date but maps to a package, classify conservatively as scheduled/manual review and lower confidence.

Before presenting results to a user, map these raw values to the common `status` values in `references/common_analysis_rules.md`.

## Recommendations

- If `replacement_package` exists, recommend replacing with that package.
- If the issue is Windows-Legacy compatibility, recommend migration from Windows-Legacy or version pinning only when the docs explicitly support it.
- If no replacement is stated, output exactly: `No direct replacement stated - review manually.`
- Before final presentation, map `recommendation` to the common `recommended_action` field.
