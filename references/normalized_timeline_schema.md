# Normalized Timeline Schema

Normalized timeline entries are stored as JSON objects. The live UiPath deprecation timeline remains authoritative; cached entries are fallback data.

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

Rules:

- Keep package entries only.
- Prefer explicit package names over inferred feature names.
- Set `windows_legacy_only` when the timeline mentions Windows-Legacy or `.NET Framework 4.6.1`.
- Do not invent replacements. Leave `replacement_package` empty if the docs do not state one.
