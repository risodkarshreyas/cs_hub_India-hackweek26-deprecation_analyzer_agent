# Client Package Timeline Schema

Normalized client/package timeline entries are stored as JSON objects. The live UiPath deprecation timeline remains authoritative; cached entries are fallback or explicit offline data. Server-side rules use `references/server_rule_schema.md`.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `package_name` | string | NuGet/activity package name, usually `UiPath.*.Activities`. |
| `affected_version` | string | Version, version prefix, or comparison range when detectable. Empty means all detected versions require review. |
| `deprecation_date` | `YYYY-MM-DD` string | Deprecation date when stated. |
| `removal_date` | `YYYY-MM-DD` string | Removal/end-of-support date when stated. |
| `replacement_package` | string | Replacement package stated by UiPath docs. Empty means no direct replacement was stated. |
| `compatibility_scope` | string | `all_projects` or `windows_legacy_only`. |
| `project_compatibility_impact` | string | Human-readable compatibility note. |
| `source_url` | string | UiPath documentation URL. |
| `source_section_title` | string | Heading near the source row/table. |
| `source_text` | string | Normalized source snippet used to derive the entry. |
| `confidence` | string | `high`, `medium`, or `low` extraction confidence. |
| `fetched_at` | ISO datetime | Fetch/normalization timestamp. |

Optional fields:

| Field | Type | Meaning |
|---|---|---|
| `canonicalized_from` | string | Original short or package-like name when the analyzer mapped it to a canonical package name. Empty when no mapping was needed. |
| `normalization_warnings` | string array | Parser warnings that should be reviewed before relying on the normalized entry. Empty means no parser warning was emitted. |

Rules:

- Keep package entries only.
- Prefer explicit package names over inferred feature names.
- Expand grouped timeline rows into one normalized entry per package-like item.
- Canonicalize known short names, such as `PDF.Activities`, to their package form, such as `UiPath.PDF.Activities`.
- Use the live timeline by default. Use cached data only as fallback or when offline/cache-only mode is explicitly requested.
- Set `windows_legacy_only` when the timeline mentions Windows-Legacy or `.NET Framework 4.6.1`.
- Do not invent replacements. Leave `replacement_package` empty if the docs do not state one.
