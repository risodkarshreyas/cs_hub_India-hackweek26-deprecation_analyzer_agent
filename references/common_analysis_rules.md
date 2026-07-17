# Common Analysis Rules

Apply these rules before producing client-side, server-side, or mixed UiPath deprecation findings.

## Source of Truth

Use the live UiPath deprecation timeline as the default authoritative source:

`https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline`

Two additional authoritative pages drive `out_of_support` findings and are refreshed on every client/server run:

- Activity package (dependency) support floors: `https://docs.uipath.com/overview/other/latest/overview/activities-lifecycle`
- UiPath product version end-of-support dates: `https://docs.uipath.com/overview/other/latest/overview/out-of-support-versions`

Refresh live source data by default. Use cached data only when the live fetch fails, when offline mode is explicitly requested, or for repeatable tests with a visible cache timestamp. Use the out-of-support and activities-lifecycle pages only for `out_of_support` findings. An out-of-support dependency version or product version maps to `high` severity, because running an unsupported version means no vendor support or security fixes even though nothing is scheduled for removal.

Do not rely on memory for dates, statuses, removal scope, or alternatives.

## Evidence and Matching

Every finding requires evidence. Evidence must identify the source artifact and the matched value.

Prefer evidence in this order:

1. Exact structured evidence: package names, versions, API endpoints, API fields, service names, connector names, object names, deployment versions, configuration keys, tenant export paths, or file paths.
2. Semi-structured evidence: CSV rows, inventory tables, logs, OpenAPI/Postman entries, screenshots with visible labels.
3. Natural-language descriptions from the user, only when no structured source is available.

Use exact matching first. Use cautious fuzzy matching only for UI labels, screenshots, or inconsistent export names. Fuzzy matches must have confidence below `high` unless corroborated by structured evidence.

Apply scope constraints before reporting:

- Do not report client package deprecations against server-only evidence.
- Do not report server or platform deprecations against RPA package evidence unless a server configuration directly references the deprecated feature.
- Apply delivery model, product version, compatibility, and date constraints from the source row.
- Require known evidence and rule products to agree before reporting a server finding. Delivery-model labels such as Automation Cloud or Automation Suite do not replace the product identified by the evidence.
- When multiple structured records represent one server capability in the same tenant or folder, group them into one finding and preserve artifact counts, endpoints, object paths, and representative object names in the evidence array.
- If evidence is missing or incomplete, report a coverage gap instead of a finding.

## Classification

Use only these `status` values:

| Status | Use when |
|---|---|
| `removed` | The feature, package, API, service behavior, or support path is already removed for the detected environment as of the analysis date. |
| `removal_scheduled` | Usage is detected and the source gives a future removal or enforcement date. |
| `deprecated` | Usage is detected and deprecated, but no removal date is stated. |
| `upcoming_deprecation` | The source announces a future deprecation date and the environment will be in scope. |
| `out_of_support` | A product, version, OS, database, runtime, or platform combination is out of support according to an authoritative support page. |
| `informational` | Relevant migration or lifecycle note with no direct impacted usage detected. |

Map legacy client classifications to common statuses:

| Legacy client classification | Common status |
|---|---|
| `Already Removed` | `removed` |
| `Removal Imminent` | `removal_scheduled` |
| `Removal Scheduled` | `removal_scheduled` |
| `.NET Framework 4.6.1 / Windows-Legacy Compatibility Impact` | `deprecated` unless the source explicitly states removal or out-of-support |

## Severity and Priority

Use the `severity` field as the shared priority model. Use only these values:

| Severity | Use when |
|---|---|
| `critical` | Already removed, currently breaking, or expected to break execution, authentication, access control, deployment, backup/restore, test execution, or upgrade paths immediately. |
| `high` | Scheduled removal is within 180 days, Windows-Legacy/package compatibility blocks modernization, or the finding blocks a known upgrade or release. |
| `medium` | Deprecated or scheduled beyond 180 days with clear usage evidence and a known remediation path. |
| `low` | Weak or indirect evidence, informational note, monitoring item, or no direct usage but the environment is plausibly in scope. |

When raw analyzer output uses `risk_level`, convert it to lowercase `severity`.

## Mitigation Route

Use one `mitigation_route` per finding:

| Route | Use when |
|---|---|
| `auto_assess` | AI can refresh sources, map evidence, rank risk, and draft remediation without changing the environment. |
| `ai_assisted_change` | AI can draft or apply a change through an appropriate UiPath skill, script, CLI, or code edit after approval. |
| `owner_review` | A human owner must confirm scope, business impact, access, or timing before remediation. |
| `manual_only` | The change needs vendor support, production approval, irreversible migration, unavailable admin UI access, or a manual cutover. |
| `monitor` | No direct usage is found, but the item should be watched because the environment is in scope. |

Recommended skill hints:

| Work type | `recommended_skill` |
|---|---|
| RPA workflow, XAML, coded workflow, package updates | `uipath-rpa` |
| Orchestrator, Automation Cloud/Suite, Integration Service, tenant settings, assets, queues, folders, roles, machines, processes, API authentication, storage, licensing, deployment | `uipath-platform` |
| Test Manager or testing-module migration | `uipath-test` |
| Maestro flow changes | `uipath-maestro-flow` |
| Action Center approval, sign-off, validation, or owner gates | `uipath-human-in-the-loop` |
| Coded Web Apps or Coded Action Apps | `uipath-coded-apps` |
| Data Service/Data Fabric remediation | `uipath-data-fabric` |
| Detection, reassessment, reporting, or remediation planning only | `uipath-deprecation-analyzer` |

## Time-Savings KPI

Every finding and every overall report must include a `time_savings_kpi` object:

```json
{
  "manual_baseline_hours": 8.0,
  "ai_assisted_hours": 2.0,
  "hours_saved": 6.0,
  "percent_saved": 75,
  "basis": "AI refreshed the UiPath timeline, matched environment evidence to rules, ranked risk, and drafted remediation steps.",
  "confidence": "medium"
}
```

Calculate:

- `hours_saved = manual_baseline_hours - ai_assisted_hours`
- `percent_saved = round(hours_saved / manual_baseline_hours * 100)` when `manual_baseline_hours` is greater than zero.

Estimate manual baseline conservatively:

- Rule discovery and documentation review: 1-4 hours per product family.
- RPA project/package inventory review: 1-6 hours per repository or package set.
- Tenant or export inventory review: 2-8 hours per tenant depending on volume.
- API usage search across repositories, logs, and Postman/OpenAPI collections: 2-12 hours.
- Remediation planning and owner mapping: 1-4 hours per finding group.
- Validation checklist preparation: 0.5-2 hours per finding group.

Estimate AI-assisted effort as the expected human-in-the-loop time to provide inputs, approve changes, review findings, and validate outputs. Do not count unattended analysis time as human effort unless it blocks a person.

Use KPI confidence:

- `high`: measured manual effort exists or the same mitigation has been performed before.
- `medium`: inventory quality is good and estimates use the baseline ranges above.
- `low`: evidence is incomplete, screenshots are used, or remediation ownership is unclear.

## Report Shape

Return an executive summary and a machine-readable finding list.

Executive summary:

- Overall risk posture.
- Count by severity, status, domain, and product.
- Top actions for the next 30, 90, and 180 days when deadlines exist.
- Total estimated AI time savings and assumptions.
- Coverage gaps and unknowns that require owner confirmation or more exports.

When HTML/dashboard output is requested, render it from the same normalized report payload. Do not introduce dashboard-only field names that conflict with the common finding schema. Server-side report output should include the static HTML dashboard described in `references/reporting-dashboard-ideas.md`.

Every final finding must include these fields:

- `id`
- `severity`
- `status`
- `domain`
- `product`
- `feature_or_package`
- `environment`
- `evidence`
- `impact`
- `deadline`
- `recommended_action`
- `mitigation_route`
- `recommended_skill`
- `time_savings_kpi`
- `owner_hint`
- `confidence`
- `source_url`

Use `domain` values `client`, `server`, or `mixed`. Prefer `client` or `server`; use `mixed` only when one finding is supported by both RPA/package evidence and tenant/platform evidence.

Preserve client-specific optional fields when available:

- `project_name`
- `package_name`
- `current_version`
- `replacement_package`
- `compatibility_scope`
- `project_compatibility`

Preserve server-specific optional fields when available:

- `delivery_model`
- `tenant_or_service`
- `endpoint`
- `api_field`
- `service_version`
- `configuration_object`

Evidence should be an array of structured evidence objects or concise strings. Include file path, line/row/object path, API endpoint, tenant/service name, package version, and matched source value when available.

## Guardrails

- Do not invent dates, replacements, migration tools, or product alternatives.
- Only recommend replacement packages or platform alternatives stated in UiPath documentation or clearly provided by the user.
- Redact secrets, tokens, passwords, client secrets, connection strings, cookies, bearer headers, keys, and personal data not needed for the finding.
- Separate coverage gaps from findings.
- Keep owner hints actionable, such as `RPA maintainer`, `Platform admin`, `QA/Test Manager owner`, `Security owner`, `Integration owner`, or `Infrastructure owner`.
- State uncertainty directly. Lower confidence when source data is incomplete, fuzzy matched, stale, or screenshot-derived.
