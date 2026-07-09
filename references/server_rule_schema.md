# Server Rule Schema

Server rules are normalized deprecation timeline rows for UiPath platform, tenant, API, service, and infrastructure features. The live UiPath deprecation timeline remains authoritative; cached rules are fallback data or explicit offline input.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `rule_id` | string | Stable generated id, prefixed with `uipath-server-`. |
| `product` | string | UiPath product or service family, such as Orchestrator or Automation Suite. |
| `feature` | string | Deprecated server-side feature, capability, API, service behavior, or infrastructure item. |
| `lifecycle_status` | string | Common status hint: `removed`, `removal_scheduled`, `deprecated`, `out_of_support`, or `informational`. |
| `delivery_models` | string array | Scope constraints such as `Automation Cloud`, `Automation Suite`, or `standalone Orchestrator`; empty means not constrained. |
| `deprecation_date` | string | Normalized `YYYY-MM-DD` date when detected. |
| `removal_date` | string | Normalized `YYYY-MM-DD` removal or enforcement date when detected. |
| `match` | object | Match types and patterns used by `scripts/server_matcher.py`. |
| `recommended_alternative` | string | UiPath-documented migration or replacement guidance when detected. |
| `source_url` | string | Source documentation URL. |
| `source_section` | string | Timeline heading near the source row. |
| `source_text` | string | Normalized source row text. |
| `confidence` | string | `high`, `medium`, or `low`. |
| `fetched_at` | string | ISO timestamp for live source fetch or normalization. |

`match.types` may include `endpoint`, `api_field`, `service_feature`, `configuration_key`, `service_version`, `connector_name`, `object_name`, or `text_pattern`.

Rules:

- Keep server/platform rows and exclude client package-only rows.
- Do not invent dates or replacements.
- Prefer exact endpoint, field, object, connector, service, and version patterns.
- Apply `delivery_models` before reporting a finding.
