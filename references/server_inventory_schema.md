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

Rules:

- Redact secrets, tokens, passwords, cookies, bearer headers, keys, and connection strings before matching or reporting.
- Prefer structured JSON/CSV/XML evidence over text patterns.
- Keep coverage gaps separate from findings when required product, delivery model, or version context is missing.
