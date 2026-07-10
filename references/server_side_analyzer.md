# Server-Side Analyzer

Apply `references/common_analysis_rules.md` before producing server-side results. Use this reference for product scope, server inventory inputs, detection hints, and server-specific evidence extraction.

## Scope

Use this analyzer for UiPath tenant, organization, service, export, API, and infrastructure configuration data.

Include:

- Orchestrator tenant/folder resources, APIs, permissions, roles, machines, test artifacts, assets, queues, triggers, buckets, SMTP, feeds, and authentication patterns.
- Automation Cloud organization and tenant administration settings.
- Automation Suite deployment and infrastructure configuration.
- Apps metadata and exported app definitions.
- Integration Service connectors, connections, event triggers, connector-builder usage, and connector activity metadata when available from service exports.
- Test Manager projects, integrations, connectors, and migration dependencies.
- Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Hub, Automation Ops, Maestro, Task Mining, High Availability Add-On, and related platform services when the input includes their configuration.

Exclude:

- XAML or coded workflow implementation analysis.
- Studio, Robot, browser extension, OS support, and activity package findings unless they are referenced by server-side service configuration.
- Generic lifecycle support checks that are not listed as deprecations, removals, or out-of-support server versions in UiPath documentation.

## Primary Sources

Always refresh authoritative source data before analysis unless the user explicitly requests offline mode.

Primary source:

- `https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline`

Useful supporting sources when a finding needs clarification:

- UiPath product lifecycle and out-of-support version pages.
- UiPath release notes linked from the deprecation timeline.
- Product-specific docs for migration guidance linked from the deprecation row.

Do not rely on memory for dates, statuses, or migration recommendations. Treat cached rules as stale unless their source fetch timestamp is visible and recent.

## Recommended Inputs

Accept any combination of these inputs:

- UiPath tenant or organization export files.
- Orchestrator API snapshots, OpenAPI request inventories, integration source code, API gateway logs, or Postman collections.
- Automation Suite `cluster_config.json`, `uipathctl` output, install/upgrade inventory, Kubernetes version, object storage, backup, registry, SQL, OS, and cloud provider details.
- Apps exports or app metadata JSON.
- Integration Service connector, connection, trigger, or process dependency exports.
- Test Manager project exports and connector/integration settings.
- Screenshots or CSV inventories from Admin, Orchestrator, Apps, Test Manager, or Automation Suite when APIs are unavailable.
- A manually prepared inventory table with columns such as product, feature, setting, endpoint, version, object name, environment type, evidence, and owner.

If the user has no export, ask for the minimum inventory needed for the requested product family. For example, Orchestrator API deprecations need endpoint usage evidence; Automation Suite infrastructure deprecations need deployment version and infrastructure configuration.

## Workflow

1. Identify environment context:
   - Delivery model: Automation Cloud, Automation Suite, standalone Orchestrator, hybrid, or unknown.
   - Product versions where relevant, especially Automation Suite and standalone components.
   - Tenant, folder, organization, project, and service boundaries.
   - Current date for deadline and days-to-removal calculations.

2. Build or refresh the server-side deprecation rule catalog:
   - Fetch the UiPath deprecation timeline.
   - Keep only server-side sections in scope.
   - Ignore Activities, Studio, and Robot sections unless a server-side configuration directly depends on the row.
   - Normalize each row with product, feature, lifecycle status, delivery model, announced/effective/removal dates, match hints, recommended alternative, source URL, and source section.

3. Inventory the target environment:
   - Parse JSON, CSV, YAML, XML, Terraform, Helm values, Kubernetes manifests, Postman collections, OpenAPI specs, logs, and plain text inventories with structured parsers when possible.
   - Extract evidence that can be tied to a rule: endpoint paths, API fields, roles, permissions, service versions, object names, connector names, app expression/runtime model, storage mode, backup mode, OS/Kubernetes/SQL versions, and product launcher/service usage.
   - Record where each piece of evidence came from: file path, object identifier, endpoint, line number, row number, or API response path.

4. Match rules to evidence:
   - Use exact matching for API endpoints, fields, object names, version numbers, service names, connector names, and known feature labels.
   - Use cautious fuzzy matching only for UI labels or screenshots; lower confidence unless corroborated by structured data.
   - Apply delivery-model constraints. Do not report an Automation Suite-only removal against Automation Cloud unless the source rule applies to both.
   - Apply version constraints. For example, report deployment-specific deprecations only when the deployment type and version are present.

5. Normalize findings:
   - Use the common status, severity, mitigation route, KPI, evidence, and report fields.
   - Preserve server-specific optional fields such as `delivery_model`, `tenant_or_service`, `endpoint`, `api_field`, `service_version`, and `configuration_object`.
   - Keep RPA workflow findings separate from server-side findings so remediation owners remain clear.

6. Generate server-side report outputs:
   - Server-side report output must include the static HTML dashboard by default.
   - Read `references/reporting-dashboard-ideas.md` before generating the dashboard.
   - Keep JSON and XLSX outputs alongside HTML so downstream tools can consume normalized findings.

## CLI Usage

Server-side CLI examples must include `html` as a mandatory format:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./tenant-export --output ./reports --mode server --format markdown,json,xlsx,html
```

Offline or repeatable server-side runs must also include `html`:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./tenant-export --output ./reports --mode server --server-rule-cache ./rules.json --offline --format markdown,json,xlsx,html --analysis-date 2026-07-10
```

## Server Evidence Extraction

Extract these evidence types when available:

- `delivery_model`: Automation Cloud, Automation Suite, standalone Orchestrator, hybrid, or unknown.
- `tenant_or_service`: tenant name, organization, folder, service, site, or cluster identifier.
- `endpoint`: API route, OData path, webhook URL pattern, or OpenAPI operation.
- `api_field`: deprecated request/response field, query option, permission, role, or setting name.
- `service_version`: product, Automation Suite, standalone component, OS, Kubernetes, SQL, or runtime version.
- `configuration_object`: app, connector, connection, trigger, queue, process, bucket, test set, machine, role, policy, cluster setting, Helm value, Kubernetes resource, or admin setting.

Redact secrets before reporting evidence.

## Product Detection Hints

### Orchestrator

Look for:

- Classic folder remnants: `/OrganizationUnits`, `/odata/Robots`, `Environments`, classic robots, standard machines, and old machine-key flows.
- Deprecated API fields and endpoints: `api/Account/Authenticate`, `/Alerts`, `OrganizationUnits` on users, `RobotValues`, `SetActive`, `VerifySmtpSetting`, `HostLicenseId`, password fields, `IsEmailConfirmed`, `BypassBasicAuthRestriction`, `InputArguments`, `OutputArguments`, report endpoints, feature flag endpoints, and count behavior on jobs/queue items.
- Access model issues: mixed roles, break-inheritance settings, deprecated role names in API payloads, and old permissions.
- Tenant settings: tenant-level SMTP, SMB storage in Automation Suite, old SQL or Windows Server dependencies.
- Test execution from Orchestrator instead of Test Manager.

### Automation Cloud

Look for:

- Removed or deprecated identity/admin endpoints.
- Legacy user licensing.
- Old accounts/groups or classic navigation references in user documentation or screenshots.
- External connections that cannot support TLS 1.2 or later.
- Legacy Orchestrator API access using refresh-token exchange through `account.uipath.com/oauth/token`.

### Automation Suite

Look for:

- Automation Suite version, deployment type, and upgrade target.
- Interactive installer usage on Linux.
- EKS/AKS backup mode, NFS backup with external objectstore, internal Docker registry, SMB storage, AWS Signature Version 2, old deployment templates, `diagnostics-report.sh`, `uipathctl.sh`, Orchestrator Configurator Tool, unsupported RHEL/Kubernetes/SQL combinations, host licensing, and legacy user licensing.
- Task Mining service availability and upgrade impact.

### Apps

Look for:

- Legacy expression-language apps.
- Legacy Apps runtime usage.
- Connections in VB Apps.
- Apps connected to standalone Orchestrator when upgrading Automation Suite to versions where that compatibility no longer works.
- Automation Suite Apps deployments on older versions requiring MongoDB security posture changes.

### Integration Service

Look for:

- Generic connector activities in Microsoft OneDrive and SharePoint, Microsoft Outlook 365, Gmail, Google Drive, and Google Sheets service assets when inventory exposes activity usage.
- Connection management or creation still performed in Integration Service instead of Orchestrator.
- References to the Integration Service entry in Automation Cloud product launcher.
- Build tab workflows or documentation for connectors.

### Test Manager

Look for:

- Standalone Test Manager version and upgrade plan.
- Native ServiceNow and qTest connector usage.
- Orchestrator testing module dependencies, including test cases, test sets, schedules, executions, and test result consumption.
- Missing migration path from Orchestrator test artifacts to Test Manager.

### AI Center and Document Understanding

Look for:

- Bring-your-own-model packages, out-of-the-box open source model usage, preview/open-source package versions, Python36/Python37 packages, and old ML packages.
- UiPath Chinese, Japanese, Korean OCR usage.
- Document Understanding service configuration that references deprecated ML package families.
- Helix Extractor model versions and CMK constraints where applicable.

### Insights and Process Mining

Look for:

- Insights versions 2021.4 and earlier.
- Deprecated Insights data model dimensions such as queue specific/analytics/output fields or robot raw message fields.
- Process Mining Airflow versions older than the supported baseline, old upload settings, marker files, and old process graph layouts.

### Other Server Services

Look for:

- Action Center legacy Form Action audit data expectations and deprecated process service pages.
- Automation Hub classic URL usage in Open API integrations.
- Automation Ops Solutions Management links or scripts that still expect management inside Automation Ops.
- Maestro C# expressions where flow metadata is available.
- Task Mining service or legacy project usage.
- High Availability Add-On OS platform versions.

## Server-Specific Rule Shape

Use this internal rule shape when building a server catalog:

```json
{
  "rule_id": "uipath-server-orchestrator-testing-module-removal",
  "product": "Orchestrator",
  "feature": "Testing Module in Orchestrator",
  "lifecycle_status": "removal_scheduled",
  "delivery_models": ["Automation Cloud", "Automation Suite"],
  "introduced_or_announced": "October 2023",
  "effective_date": {
    "Automation Cloud": "2026-01-01"
  },
  "removal_date": {
    "Automation Cloud": "2026-06-30"
  },
  "match": {
    "type": "service_feature",
    "patterns": ["Orchestrator test cases", "Orchestrator test sets", "Orchestrator test schedules", "Testing Module in Orchestrator"]
  },
  "recommended_alternative": "Migrate test artifacts and execution to Test Manager.",
  "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline",
  "source_section": "Orchestrator and Test Manager"
}
```
