---
name: uipath-deprecation-analyzer
description: Use when analyzing UiPath deprecation risk or generating deprecation reports/dashboards for RPA projects, XAML, project.json, .nupkg, Studio/Robot/activity packages, Orchestrator, Orchestrator Testing Module, Test Cases, Test Sets, Test Manager migration, Automation Cloud/Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Ops, Maestro, tenant/platform exports, or mixed client/server inputs.
allowed-tools: Read, Bash(python3 *), Bash(python *), Bash(uip login status *), Bash(uip or folders list *)
---

# UiPath Deprecation Analyzer

Use this skill as the agent-facing entrypoint for UiPath deprecation analysis in any coding-agent environment that can load local skill or instruction folders. Route the input to the client-side analyzer, the server-side analyzer, or both, then normalize all final findings with the shared schema.

## Execution Workflow

1. Inspect the user request and available input path, filenames, and visible content.
2. Read `references/common_analysis_rules.md`.
3. Select `client`, `server`, or `mixed` using the routing table below.
4. Read only the route-specific analyzer reference needed for the request.
5. For an Orchestrator URL or tenant/folder request, use an authenticated browser or UiPath API capability for read-only inspection when available. Resolve the folder name and capture only supported GET resources; never create, edit, execute, publish, migrate, delete, or open mutation menus.
6. Prefer `<SKILL_DIR>/scripts/uipath_deprecation_analyzer.py` when local artifacts are available and deterministic output is useful. Resolve `<SKILL_DIR>` as described under CLI Usage; do not assume the session is running from the skill folder.
7. Read `references/reporting-dashboard-ideas.md` when the user asks for an HTML dashboard, executive dashboard, reporting UI, dashboard-ready output, or server-side report output.
8. Review generated JSON, Markdown, and HTML reports before responding when those outputs are requested or required.
9. Return an executive summary, normalized finding list, and coverage gaps. Keep coverage gaps separate from deprecation findings.

## Required References

Always read `references/common_analysis_rules.md` before producing findings or a report.

Then read only the analyzer reference needed for the request:

- `references/client_side_analyzer.md`: RPA project folders, GitHub checkouts, XAML, `project.json`, `.nupkg`, Orchestrator package exports, Studio, Robot, activity packages, package dependencies, and Windows-Legacy/.NET Framework package compatibility.
- `references/server_side_analyzer.md`: Orchestrator, Automation Cloud, Automation Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Hub, Automation Ops, Maestro, Task Mining, High Availability Add-On, tenant exports, organization settings, platform APIs, and infrastructure configuration.

## Reference Map

- `references/common_analysis_rules.md`: required for every route, output schema, severity/status rules, evidence rules, KPI rules, and guardrails.
- `references/client_side_analyzer.md`: client route workflow, evidence sources, script behavior, and legacy-to-common field mapping.
- `references/server_side_analyzer.md`: server route workflow, product scope, server evidence extraction, and matching guidance.
- `references/activities_lifecycle_schema.md` and `references/out_of_support_versions_schema.md`: activity-package lifecycle matrix and product version end-of-support datasets used for `out_of_support` findings.
- `references/report_schema.md`: legacy client report payload interpretation and mapping to common fields.
- `references/example_findings.md`: examples of normalized client, server, and mixed findings.
- `references/package_matching_rules.md` and `references/risk_scoring_model.md`: client matching, false-positive, and legacy risk details.
- `references/server_rule_schema.md` and `references/server_inventory_schema.md`: server rule catalog and evidence record details.
- `references/reporting-dashboard-ideas.md`: static HTML dashboard contract, dashboard-ready data shape, and required dashboard sections. Read when the user requests dashboard/reporting UI output or server-side report output.

## Routing

Choose the analyzer by evidence type:

| Input or request mentions | Route |
|---|---|
| RPA source project, workflow, XAML, `project.json`, `.nupkg`, `.xlsx` client inventory, Studio, Robot, activity package, NuGet dependency, package replacement, Windows-Legacy package compatibility | Client-side analyzer |
| Orchestrator tenant/folder resources, Orchestrator Testing Module, Test Cases, Test Sets, Test Set/Test Case Executions, Test Manager migration, Automation Cloud/Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding service configuration, Insights, Process Mining, Automation Hub, Automation Ops, Maestro, tenant/platform administration, APIs, infrastructure, service versions | Server-side analyzer |
| Repo plus tenant export, source code plus platform export, package dependencies plus Orchestrator/API/service configuration, unclear mixed folder | Both analyzers |

If the input is ambiguous, inspect filenames and visible content first. Prefer both analyzers when there is credible client and server evidence.

## Mixed Analysis

For mixed inputs:

1. Apply `references/common_analysis_rules.md`.
2. Run the client-side analyzer for RPA/package artifacts when present.
3. Apply the server-side analyzer to platform, tenant, service, API, and infrastructure evidence.
4. Merge results into one executive summary and one machine-readable finding list.
5. Keep evidence, domain, owner hints, confidence, and recommended skill separate per finding. Do not collapse client package evidence and server configuration evidence into a single finding unless the same deprecated item is proven by both.

## Output Contract

Every final report, regardless of route, must use the common finding fields from `references/common_analysis_rules.md`. Preserve analyzer-specific fields only as optional additions.

Report coverage gaps separately from findings. A missing export, missing XAML scan, or unavailable tenant API is not a deprecation finding.

The existing client scripts remain unchanged. When their raw output uses legacy client field names, normalize the final presentation to the common schema before responding.

## Script Support

Use `scripts/uipath_deprecation_analyzer.py` for deterministic analysis when local artifacts are available:

- `--mode client`: scan RPA source, XAML, `.nupkg`, `.xlsx` client inventories, and package dependencies.
- `--mode server`: scan tenant/platform/API/service/infrastructure artifacts and match server-side deprecation rules.
- `--mode mixed`: run both routes and merge normalized findings.
- `--mode auto`: choose client, server, or mixed based on detected artifacts.

Server-side script details are documented in `references/server_rule_schema.md` and `references/server_inventory_schema.md`.

### Live Orchestrator Inspection

For an authenticated Orchestrator tenant or folder, collect only read-only testing resources when the request concerns the Testing Module:

- Resolve the requested folder before scanning and preserve its tenant, organization, folder, delivery model, and source URL in a `context.json` sidecar.
- Capture `/odata/TestSets`, `/odata/TestCaseDefinitions`, `/odata/TestCaseExecutions`, `/odata/TestSetExecutions`, and `/odata/TestSetSchedules` when available.
- Sanitize snapshots before analysis. Remove owner identifiers, machine names, job keys, credentials, cookies, bearer headers, and tokens.
- Do not install preview UI automation packages automatically. If authentication or a permitted browser/API capability is unavailable, request a sanitized export or screenshot and report the unavailable live inventory as a coverage gap with reduced confidence.

### CLI Usage

`<SKILL_DIR>` means the folder containing this `SKILL.md`. It is a documentation placeholder, not a literal environment variable. Substitute the skill directory exposed or discovered by the current agent.

| Agent | Skill directory | Invocation |
|---|---|---|
| Claude Code | `${CLAUDE_SKILL_DIR}` | `python3 "${CLAUDE_SKILL_DIR}/scripts/uipath_deprecation_analyzer.py" ...` |
| Codex | `$CODEX_HOME/skills/uipath-deprecation-analyzer`, `~/.codex/skills/uipath-deprecation-analyzer`, or repo `.agents/skills/uipath-deprecation-analyzer` | `python3 "<skill-dir>/scripts/uipath_deprecation_analyzer.py" ...` |
| Copilot CLI | `$COPILOT_HOME/skills/uipath-deprecation-analyzer` or `~/.copilot/skills/uipath-deprecation-analyzer` | `python3 "<skill-dir>/scripts/uipath_deprecation_analyzer.py" ...` |

Recommended default after resolving the placeholder:

```bash
python3 "<SKILL_DIR>/scripts/uipath_deprecation_analyzer.py" --input <path> --output <reports> --mode auto --format markdown,json,html
```

Use `html` in `--format` to generate `uipath_deprecation_dashboard.html`. Server-side report output should include HTML. Use `--offline` to avoid live UiPath docs fetches. Use `--timeline-cache` or `--client-timeline-cache` for normalized client timeline cache JSON. Use `--server-rule-cache` for normalized server-side rule cache JSON. Use `--analysis-date YYYY-MM-DD` for repeatable classification.

Client evidence workbooks must use modern `.xlsx`; legacy `.xls` inputs produce a conversion coverage gap. `--xlsx-mode auto` prefers the structured inventory schema and then conservatively extracts exact package/version evidence from recognizable repository/search tables. Use `strict` to require the documented headers or `evidence` to force fallback extraction. The schemas, confidence rules, diagnostics, and coverage behavior are documented in `references/client_inventory_xlsx.md`.

Every run also refreshes two support-lifecycle pages to surface `out_of_support` findings (severity `high`):

- The activities-lifecycle page flags installed activity-package (dependency) versions that are below the package's minimum supported version. Override the source with `--activities-lifecycle-url` and cache it with `--activities-lifecycle-cache`.
- The out-of-support versions page flags detected UiPath product versions (client Studio `studioVersion` and server `service_version`) whose release train has reached end of extended support. Override the source with `--out-of-support-url` and cache it with `--out-of-support-cache`.

Both checks respect `--offline`/`--use-cache-only` and fall back to their cache files when the live pages are unavailable.

## Runtime Notes

- Python 3.10 or later is required to run the scripts. Prefer `python3`; the installer doctor also checks `python` as a fallback.
- Live UiPath deprecation timeline refresh is the default.
- Offline mode requires suitable cache files.
- `openpyxl` is optional for richer XLSX generation; `scripts/reports.py` has a standard-library fallback.

## Validation

For documentation or script changes, run:

```bash
python3 -m unittest discover -s tests
```

These validation steps are for skill development and maintenance, not mandatory for every end-user analysis.
