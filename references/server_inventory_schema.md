# Server Inventory Schema

Server inventory records are extracted from tenant exports, API inventories, Postman/OpenAPI files, Automation Suite configuration, service exports, CSV inventories, logs, and plain text evidence.

Each evidence record uses these fields:

| Field | Meaning |
|---|---|
| `product` | Detected UiPath product or service family. |
| `delivery_model` | Automation Cloud, Automation Suite, standalone Orchestrator, hybrid, or empty when unknown. |
| `tenant_or_service` | Tenant, organization, folder, service, site, or cluster identifier when available. |
| `endpoint` | API route, OData path, webhook URL pattern, or OpenAPI/Postman operation path. |
| `api_field` | Deprecated request/response field, permission, role, or setting name. |
| `service_version` | Product, Automation Suite, component, OS, Kubernetes, SQL, or runtime version. |
| `configuration_object` | App, connector, connection, trigger, queue, process, bucket, test set, machine, role, policy, cluster setting, Helm value, Kubernetes resource, or admin setting. |
| `path` | Source file path relative to the scanned root. |
| `object_path` | JSON/XML object path, CSV row, or text line marker. |
| `line` | Text line number when available. |
| `row` | CSV row number when available. |
| `matched_value` | Redacted value used for rule matching. |
| `evidence_type` | One of `endpoint`, `api_field`, `service_feature`, `configuration_key`, `service_version`, `configuration_object`, or `text_pattern`. |
| `confidence` | `high`, `medium`, or `low` evidence extraction confidence. |
| `artifact_type` | Optional server artifact classification such as `test_set`, `test_case`, `test_case_execution`, `test_set_execution`, or `test_set_schedule`. |
| `organization` | Organization name from a sanitized context sidecar. |
| `tenant` | Tenant name from a sanitized context sidecar. |
| `folder` | Orchestrator folder name associated with the API snapshot. |
| `source_url` | User-supplied tenant or service URL for the captured evidence. |
| `evidence_source` | Provenance such as `live_api`, `export`, `csv`, `text`, or `screenshot`. |

Rules:

- Redact secrets, tokens, passwords, cookies, bearer headers, keys, and connection strings before matching or reporting.
- Prefer structured JSON/CSV/XML evidence over text patterns.
- For Orchestrator testing, map the following collections to canonical endpoints: `TestSets` -> `/odata/TestSets`, `TestCaseDefinitions` and `TestCases` -> `/odata/TestCaseDefinitions` or `/odata/TestCases`, `TestCaseExecutions` -> `/odata/TestCaseExecutions`, `TestSetExecutions` -> `/odata/TestSetExecutions`, and `TestSetSchedules` -> `/odata/TestSetSchedules`.
- Use folder context to group duplicate Test Set, Test Case, and execution signals into one capability finding. Retain counts and representative names in structured evidence.
- Keep coverage gaps separate from findings when required product, delivery model, or version context is missing.

## Sanitized Orchestrator Context

When a live API response is captured from a tenant folder, store context separately from the response collections:

```json
{
  "product": "Orchestrator",
  "delivery_model": "Automation Cloud",
  "organization": "example-org",
  "tenant": "UiPath default",
  "folder": "Nilekha&Demo",
  "source_url": "https://example.invalid/orchestrator_/test/sets",
  "evidence_source": "live_api"
}
```

Do not store access tokens, cookies, credentials, bearer headers, owner IDs, machine names, or job keys in the context or API snapshots.
