# Activities Lifecycle Schema

Normalized entries from the UiPath **activities lifecycle** page:

`https://docs.uipath.com/overview/other/latest/overview/activities-lifecycle`

The live page is authoritative; cached entries are fallback or explicit offline data. See
`references/normalized_timeline_schema.md` for the separate deprecation-timeline schema.

## What the page contains

The page is a matrix. Each row is an activity package. Each column is a platform release
train (for example `2025.10 LTS`, `2024.10 LTS`, ... `2018.4 LTS`). Each cell holds the
package **version shipped in that release train**. The page itself does **not** carry an
in-support / out-of-support status per cell; that status is derived from whether the release
train is still supported.

Support status is therefore computed at match time, not baked into the cache:

- The set of out-of-support release trains comes from
  `references/out_of_support_versions_schema.md` (a train is out of support when its End of
  Extended Support date is on or before the analysis date).
- A package version is out of support when it is lower than the package's
  **minimum still-supported version** — the version shipped in the oldest release train that
  is still supported.

Storing the full release-train version map (instead of a precomputed floor) keeps the cache
correct as trains age out; the floor is a function of the analysis date.

## Entry shape

Each entry is a JSON object.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `package_name` | string | Canonical activity package name, usually `UiPath.*.Activities` or `.ML`. |
| `versions_by_release` | array | Ordered list of `{ "release_train": "2024.10", "release_label": "2024.10 LTS", "version": "2.24.4" }`, newest train first. |
| `source_url` | string | UiPath documentation URL. |
| `source_section_title` | string | Section heading (for example `Packages included in on-premises releases`). |
| `source_text` | string | Normalized source snippet used to derive the entry. |
| `confidence` | string | `high`, `medium`, or `low` extraction confidence. |
| `fetched_at` | ISO datetime | Fetch/normalization timestamp. |

Optional fields:

| Field | Type | Meaning |
|---|---|---|
| `normalization_warnings` | string array | Parser warnings to review before relying on the entry. |

## Rules

- Keep activity-package rows only; skip header rows and non-package rows.
- Preserve every release-train column that holds a parseable version.
- Derive `release_train` as the first two dotted components of the column header
  (`2024.10 LTS` -> `2024.10`).
- Canonicalize package short names the same way the timeline normalizer does.
- Do not invent versions or support status. When the matrix cannot be parsed, add a
  normalization warning and lower confidence rather than guessing a floor.
