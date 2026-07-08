---
name: uipath-server-deprecation-analyzer
description: Analyze UiPath server-side platform usage for deprecated, removed, or soon-to-be-removed features across Orchestrator, Automation Cloud, Automation Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Hub, Automation Ops, Maestro, Task Mining, and related platform services. Use this only for server-side deprecation analysis; do not analyze RPA workflow XAML, Studio, Robot, or activity package deprecations here.
---

# UiPath Server Deprecation Analyzer

Use this skill to find deprecated UiPath server-side features in tenant, organization, service, export, API, and infrastructure configuration data. RPA workflow, Studio, Robot, and activity package checks are intentionally out of scope and should be handled by the existing RPA workflow analyzer.

## Scope

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
- Studio, Robot, browser extension, OS support, and activity package findings unless they are referenced by a server-side service configuration.
- Generic lifecycle support checks that are not listed as deprecations, removals, or out-of-support server versions in UiPath documentation.

## Primary Sources

Always refresh authoritative source data before analysis unless the user explicitly requests offline mode.

Primary source:
- `https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline`

Useful supporting sources when a finding needs clarification:
- UiPath product lifecycle and out-of-support version pages.
- UiPath release notes linked from the deprecation timeline.
- Product-specific docs for migration guidance linked from the deprecation row.

Do not rely on memory for dates, statuses, or migration recommendations. UiPath says the deprecation timeline is subject to change, so treat cached rules as stale unless their source fetch timestamp is visible and recent.

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
   - Current date for days-to-removal calculations.

2. Build or refresh the server-side deprecation rule catalog:
   - Fetch the UiPath deprecation timeline.
   - Keep only server-side sections in scope.
   - Ignore Activities, Studio, and Robot sections unless a server-side configuration directly depends on the row.
   - Normalize each row into the rule schema below.
   - Preserve the source URL, product section, lifecycle status, announced date, effective date, removed date, notes, and recommended alternative.

3. Inventory the target environment:
   - Parse JSON, CSV, YAML, XML, Terraform, Helm values, Kubernetes manifests, Postman collections, OpenAPI specs, logs, and plain text inventories with structured parsers when possible.
   - Extract evidence that can be tied to a rule: endpoint paths, API fields, roles, permissions, service versions, object names, connector names, app expression/runtime model, storage mode, backup mode, OS/Kubernetes/SQL versions, and product launcher/service usage.
   - Record where each piece of evidence came from: file path, object identifier, endpoint, line number, row number, or API response path.

4. Match rules to evidence:
   - Use exact matching for API endpoints, fields, object names, version numbers, service names, connector names, and known feature labels.
   - Use cautious fuzzy matching only for UI labels or screenshots; mark confidence below `high` unless corroborated by structured data.
   - Apply delivery-model constraints. For example, do not report an Automation Suite-only removal against Automation Cloud unless the source rule applies to both.
   - Apply version constraints. For example, report Automation Suite 2023.4 EKS/AKS deprecation only when that deployment type and version are present.

5. Classify each finding:
   - `removed`: the feature is already removed for the detected environment.
   - `removal_scheduled`: the feature is still present but has a scheduled removal date.
   - `deprecated`: deprecated with no known removal date.
   - `upcoming_deprecation`: deprecation announced for a future date.
   - `out_of_support`: only use when the source is an out-of-support page, not the deprecation timeline.
   - `informational`: relevant migration note with no direct impact detected.

6. Prioritize:
   - `critical`: removed already, or usage will break execution, authentication, access control, test execution, deployment, backup/restore, or upgrade.
   - `high`: removal is scheduled within 180 days or blocks a known upgrade path.
   - `medium`: deprecated or scheduled beyond 180 days with clear usage evidence.
   - `low`: weak evidence, indirect dependency, or informational migration guidance.

7. Produce actionable remediation:
   - Explain the detected deprecated feature and why it matters.
   - Include exact evidence.
   - Provide the UiPath-recommended alternative when the source includes one.
   - State whether remediation is configuration, migration, API/code update, infrastructure upgrade, product transition, or owner follow-up.
   - Recommend the next mitigation route: apply with this skill, invoke another UiPath skill, create an owner task, or request missing evidence.
   - Estimate the time-savings KPI for using AI-assisted analysis or mitigation instead of manual discovery and planning.
   - Do not claim automatic migration unless the source states it.

## Mitigation Routing

After producing findings, recommend implementation paths. Keep the detection work in this skill, then route execution to the narrowest available skill or owner.

Use this skill for:
- Refreshing the deprecation catalog.
- Mapping findings to evidence.
- Producing risk-ranked remediation plans.
- Drafting migration checklists, acceptance criteria, and validation steps.
- Re-running the analysis after remediation evidence is available.

Invoke another skill when mitigation requires product-specific implementation:
- `uipath-platform`: Orchestrator, Automation Cloud, Automation Suite, Integration Service, tenant settings, assets, queues, folders, roles, machines, packages, processes, external apps, API authentication, storage, licensing, and deployment changes.
- `uipath-test`: Test Manager project, test case, test set, execution, report, and Orchestrator testing-module migration work.
- `uipath-maestro-flow`: Maestro flow changes, especially migration from C# expressions to JavaScript expressions.
- `uipath-human-in-the-loop`: Approval gates, owner attestations, remediation sign-off, or Action Center task design for high-risk changes.
- `uipath-diagnostics`: Failed jobs, broken selectors, permission failures, queue issues, publish errors, or post-remediation production symptoms.
- `uipath-solution-design`: Large cross-product modernization plans, PDD-to-SDD conversion, or multi-workstream migration design.
- `uipath-data-fabric`: Data Service entity or record changes discovered as part of a server-side remediation.
- `uipath-coded-apps`: Coded Web App or Coded Action App remediation. For low-code UiPath Apps, use this skill to plan and create owner tasks unless a dedicated Apps implementation skill is available.
- `uipath-rpa`: Only when the server-side finding proves that workflow code must change. Keep the original finding here and hand off the workflow change to the existing RPA analyzer or RPA implementation skill.

Recommend one of these mitigation actions per finding:
- `auto_assess`: AI can analyze evidence and produce a remediation plan, but should not change the tenant.
- `ai_assisted_change`: AI can draft or apply the change through an appropriate skill or CLI after approval.
- `owner_review`: Human product owner, platform admin, security owner, or QA owner must confirm scope.
- `manual_only`: Change requires vendor support, tenant admin UI access unavailable to the agent, production approval, or irreversible migration.
- `monitor`: No direct usage found, but the item should be watched because the environment is in scope.

## Time-Savings KPI

For every finding and for the overall report, include an AI time-savings KPI. This is an estimate unless measured with real execution logs.

Use this structure:

```json
{
  "time_savings_kpi": {
    "manual_baseline_hours": 8.0,
    "ai_assisted_hours": 2.0,
    "hours_saved": 6.0,
    "percent_saved": 75,
    "basis": "AI refreshed the UiPath timeline, matched tenant export evidence to rules, ranked risk, and drafted remediation steps.",
    "confidence": "medium"
  }
}
```

Calculate:
- `hours_saved = manual_baseline_hours - ai_assisted_hours`
- `percent_saved = round(hours_saved / manual_baseline_hours * 100)`

Estimate manual baseline conservatively:
- Rule discovery and documentation review: 1-4 hours per product family.
- Tenant or export inventory review: 2-8 hours per tenant depending on volume.
- API usage search across repositories/logs/Postman collections: 2-12 hours.
- Remediation planning and owner mapping: 1-4 hours per finding group.
- Validation checklist preparation: 0.5-2 hours per finding group.

Estimate AI-assisted effort as the expected human-in-the-loop time to provide inputs, approve changes, review findings, and validate outputs. Do not count unattended analysis time as human effort unless the process blocks a person.

Set confidence:
- `high`: measured manual effort exists or the same mitigation has been performed before.
- `medium`: inventory quality is good and the estimate uses the baseline ranges above.
- `low`: evidence is incomplete, screenshots are used, or remediation ownership is unclear.

## Rule Schema

Use this normalized shape internally and in generated artifacts when useful:

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

## Product-Specific Detection Hints

### Orchestrator

Look for:
- Classic folder remnants: `/OrganizationUnits`, `/odata/Robots`, `Environments`, classic robots, standard machines, and old machine-key flows.
- Deprecated API fields and endpoints: `api/Account/Authenticate`, `/Alerts`, `OrganizationUnits` on users, `RobotValues`, `SetActive`, `VerifySmtpSetting`, `HostLicenseId`, password fields, `IsEmailConfirmed`, `BypassBasicAuthRestriction`, `InputArguments`, `OutputArguments`, report endpoints, feature flag endpoints, and count behavior on jobs/queue items.
- Access model issues: mixed roles, break-inheritance settings, deprecated role names in API payloads, old permissions.
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
- Generic connector activities in Microsoft OneDrive and SharePoint, Microsoft Outlook 365, Gmail, Google Drive, and Google Sheets service assets when the inventory exposes activity usage.
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
- Document Understanding 2022.4 ML packages using deprecated Python package families.
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

## Output Format

Return both an executive summary and a machine-readable finding list.

Executive summary:
- Overall risk posture.
- Count by severity and product.
- Top actions for the next 30, 90, and 180 days.
- Total estimated AI time savings and the assumptions behind it.
- Unknowns that require tenant access or owner confirmation.

Finding fields:
- `id`
- `severity`
- `status`
- `product`
- `feature`
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

Example:

```json
{
  "id": "F-001",
  "severity": "high",
  "status": "removal_scheduled",
  "product": "Orchestrator",
  "feature": "Testing Module in Orchestrator",
  "environment": "Automation Cloud",
  "evidence": "Tenant export contains 12 test sets and 4 schedules managed in Orchestrator.",
  "impact": "Test results and test execution from Orchestrator are being removed; Test Manager becomes the required platform.",
  "deadline": "2026-06-30",
  "recommended_action": "Migrate test cases, test sets, executions, and schedules to Test Manager using UiPath migration guidance. Confirm whether test data queues are excluded from the migration.",
  "mitigation_route": "ai_assisted_change",
  "recommended_skill": "uipath-test",
  "time_savings_kpi": {
    "manual_baseline_hours": 10.0,
    "ai_assisted_hours": 3.0,
    "hours_saved": 7.0,
    "percent_saved": 70,
    "basis": "AI identified Orchestrator test artifacts, mapped the deprecation deadline, selected Test Manager migration as the route, and drafted validation steps.",
    "confidence": "medium"
  },
  "owner_hint": "QA/Test Manager owner",
  "confidence": "high",
  "source_url": "https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline"
}
```

## Guardrails

- Never invent deprecation dates or alternatives.
- Distinguish deprecated, removed, upcoming removal, out-of-support, and upgrade incompatibility.
- If evidence is absent, report a coverage gap rather than a finding.
- Prefer structured evidence over screenshots or natural-language descriptions.
- When data contains secrets, redact tokens, passwords, client secrets, connection strings, cookies, and bearer headers.
- Keep RPA workflow findings separate from server-side findings so remediation owners remain clear.
