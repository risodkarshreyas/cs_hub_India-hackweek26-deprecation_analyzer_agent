# UiPath Deprecation Analyzer Skill

Portable Codex skill for routing UiPath deprecation analysis across client-side automation artifacts, server-side platform evidence, or mixed client/server inputs.

The live UiPath deprecation timeline is the default source of truth:

```text
https://docs.uipath.com/overview/other/latest/overview/deprecation-timeline
```

## What This Skill Does

- Routes RPA projects, XAML, `project.json`, `.nupkg`, Studio, Robot, and activity package requests to the client-side analyzer.
- Routes Orchestrator, Automation Cloud/Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Ops, Maestro, and tenant/platform configuration requests to the server-side analyzer.
- Routes mixed repositories or mixed export folders to both analyzers and merges findings into one normalized report shape.
- Applies shared matching, classification, severity, mitigation-route, KPI, evidence, and reporting rules from `references/common_analysis_rules.md`.
- Preserves the existing Python client analyzer as raw client tooling for package/XAML inventory and reports.

## Project Structure

```text
.
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- scripts/
|   |-- uipath_deprecation_analyzer.py
|   |-- project_inventory.py
|   |-- timeline.py
|   |-- matcher.py
|   `-- reports.py
|-- references/
|   |-- common_analysis_rules.md
|   |-- client_side_analyzer.md
|   |-- server_side_analyzer.md
|   |-- normalized_timeline_schema.md
|   |-- package_matching_rules.md
|   |-- report_schema.md
|   |-- risk_scoring_model.md
|   `-- example_findings.md
`-- tests/
    |-- test_deprecation_analyzer.py
    |-- test_skill_contract.py
    `-- fixtures/
```

## Analyzer Routes

Use `SKILL.md` as the entrypoint:

- Client route: RPA source projects, GitHub checkouts, XAML workflows, `project.json`, `.nupkg`, package dependencies, package replacements, and Windows-Legacy/.NET Framework package compatibility.
- Server route: Orchestrator tenant/folder resources, Automation Cloud/Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Hub, Automation Ops, Maestro, Task Mining, High Availability Add-On, APIs, service versions, and platform/infrastructure configuration.
- Mixed route: source projects plus tenant exports, package evidence plus platform API/configuration evidence, or folders where both client and server artifacts are credible.

Every route must apply `references/common_analysis_rules.md` before producing final findings.

## Output Contract

Final agent-facing and user-facing reports must include an executive summary plus a machine-readable finding list. Every final finding uses the common fields from `references/common_analysis_rules.md`:

```text
id, severity, status, domain, product, feature_or_package, environment,
evidence, impact, deadline, recommended_action, mitigation_route,
recommended_skill, time_savings_kpi, owner_hint, confidence, source_url
```

Client-only optional fields include `project_name`, `package_name`, `current_version`, `replacement_package`, `compatibility_scope`, and `project_compatibility`.

Server-only optional fields include `delivery_model`, `tenant_or_service`, `endpoint`, `api_field`, `service_version`, and `configuration_object`.

Coverage gaps are reported separately from findings.

## Existing Client Scripts

The scripts under `scripts/` are intentionally retained as raw client analyzer tooling. They scan package/XAML evidence and generate Markdown, JSON, CSV, and Excel reports with legacy raw client fields such as `classification`, `risk_level`, and `recommendation`.

Agents must normalize those raw fields before final presentation:

- `classification` -> `status`
- `risk_level` -> `severity`
- `recommendation` -> `recommended_action`
- `removal_date` -> `deadline`
- `package_name` -> `feature_or_package` and optional `package_name`

No server-side analyzer script is included yet; server-side analysis is instruction-driven through `references/server_side_analyzer.md`.

## Client Script Quick Start

From this repository root:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./path/to/uipath/repo --output ./reports --format markdown,json,csv,xlsx
```

Offline or repeatable run using a cached timeline file:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./path/to/uipath/repo --output ./reports --timeline-cache ./tests/fixtures/timeline-cache.json --use-cache-only --format markdown,json,csv,xlsx --analysis-date 2026-07-07
```

Run against a folder of `.nupkg` files:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./packages --output ./reports --include-nupkg
```

## Validation

Run the unit and contract tests:

```bash
python -m unittest discover -s tests
```

Validate skill metadata:

```bash
python C:\Users\jeet.doshi\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
```
