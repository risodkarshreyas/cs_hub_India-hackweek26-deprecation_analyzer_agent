# Out-of-Support Product Versions Schema

Normalized entries from the UiPath **out-of-support versions** page:

`https://docs.uipath.com/overview/other/latest/overview/out-of-support-versions`

The live page is authoritative; cached entries are fallback or explicit offline data. Every
row on that page is a product version whose extended support has ended, so the page is a
catalog of already out-of-support product versions. The analyzer only reports a detected
product version as `out_of_support` when the matched row's `end_of_extended_support` date is
on or before the analysis date, so a future-dated row (should UiPath ever add one) is treated
as informational rather than out of support.

Each entry is a JSON object.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `product` | string | Canonical UiPath product family, e.g. `Studio`, `Robot`, `Orchestrator`, `AI Center`. Normalized from the page label (for example `Studio StudioX` maps to `Studio`). |
| `version` | string | The specific product version listed, e.g. `2022.10.18`. |
| `release_train` | string | Major.minor release train derived from `version`, e.g. `2022.10`. Used for train-level matching when a customer runs a different patch of the same train. |
| `support_model` | string | `LTS`, `FTS`, or empty when the row does not state one. |
| `end_of_extended_support` | `YYYY-MM-DD` string | End of Extended Support date, empty when not parseable. |
| `source_url` | string | UiPath documentation URL. |
| `source_section_title` | string | Heading near the source row/table. |
| `source_text` | string | Normalized source snippet used to derive the entry. |
| `confidence` | string | `high`, `medium`, or `low` extraction confidence. |
| `fetched_at` | ISO datetime | Fetch/normalization timestamp. |

Optional fields:

| Field | Type | Meaning |
|---|---|---|
| `normalization_warnings` | string array | Parser warnings to review before relying on the entry. |

Rules:

- The product column often uses `rowspan`, so the product name only appears on the first
  version row of each block. Carry the last seen product name forward across rows that omit
  it.
- Derive `release_train` as the first two dotted components of `version`.
- Canonicalize product names to a single family (`Studio StudioX` -> `Studio`,
  `AI Center™` -> `AI Center`).
- Do not invent dates. Leave `end_of_extended_support` empty when the date is unparseable and
  add a normalization warning.
