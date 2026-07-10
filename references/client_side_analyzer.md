# Client-Side Analyzer

Apply `references/common_analysis_rules.md` before producing client-side results. The Python scripts may emit legacy client fields; normalize the final presentation to the common schema.

## Scope

Use this analyzer for UiPath client-side automation artifacts:

- RPA source project folders and GitHub checkouts.
- XAML workflows and coded workflow project structure when package usage is visible.
- `project.json` dependency declarations.
- `.nupkg` packages and Orchestrator package exports.
- Studio, Robot, activity package, NuGet dependency, replacement package, and Windows-Legacy/.NET Framework 4.6.1 compatibility requests.

Do not use this analyzer for tenant/platform configuration unless it appears only as package-export context. Route Orchestrator, Automation Cloud/Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Insights, Process Mining, Automation Ops, Maestro, and platform API/configuration evidence to `references/server_side_analyzer.md`.

## Client Evidence

Valid evidence sources include:

- `project.json` dependency declarations.
- `.xaml` namespace, assembly, activity, or package references.
- `.nuspec` dependency declarations.
- Extracted `.nupkg` metadata and packaged `project.json`.
- Folder names, package file names, and project compatibility metadata when corroborated by project files.

For `.nupkg` files, use `package.nupkg!/path/inside/package` for internal evidence paths.

## Source Data

Use the live UiPath deprecation timeline by default. Cached normalized data is only a fallback when the live fetch fails or when the user explicitly requests offline/repeatable analysis with `--use-cache-only`.

The client scripts normalize package-like timeline entries. Keep entries such as `UiPath.*.Activities`, canonicalized short package names, `UiPath.DocumentUnderstanding.ML`, and Document Understanding ML package identifiers when they appear in the timeline.

## Workflow

1. Identify the input: source project folder, GitHub checkout, folder of `.nupkg` packages, Orchestrator package export, or mixed folder.
2. If Orchestrator package download is needed, use available UiPath/Orchestrator tooling in the environment. Do not ask for or store secrets; use existing authenticated CLI/session state.
3. Run the analyzer when client artifacts are present:

   ```bash
   python scripts/uipath_deprecation_analyzer.py --input ./repo --output ./reports --format markdown,json,csv,xlsx
   ```

4. Review the Markdown report first for executive summary, highest-risk findings, replacement mapping, Windows-Legacy impact, manual review items, and remediation roadmap.
5. Use the JSON report for normalization, CSV for portfolio tracking, and Excel for stakeholder review. Add `html` to `--format` when the user requests a dashboard or static executive report.
6. Confirm package evidence paths before recommending remediation.
7. Recommend only replacement packages stated in the UiPath timeline. If none is stated, use: `No direct replacement stated - review manually.`
8. Normalize the final response to the common finding schema.

## Scripts

Keep these scripts unchanged unless the user explicitly requests implementation changes:

- `scripts/uipath_deprecation_analyzer.py`: CLI entrypoint.
- `scripts/project_inventory.py`: scans source projects and `.nupkg` packages using embedded UiPath project discovery and package inventory logic.
- `scripts/timeline.py`: fetches, filters, normalizes, and caches package-like timeline entries.
- `scripts/matcher.py`: matches project/package inventory to normalized timeline entries and classifies risk.
- `scripts/reports.py`: generates Markdown, JSON, CSV, Excel, and optional HTML dashboard outputs.

CLI flags:

```text
--input PATH
--output PATH
--refresh-timeline
--use-cache-only
--timeline-cache PATH
--format markdown,json,csv,xlsx[,html]
--include-xaml
--include-nupkg
--strict
--analysis-date YYYY-MM-DD
```

Live timeline refresh is the default. Use `--use-cache-only` with `--timeline-cache` for offline or repeatable audits. Use `--analysis-date` for repeatable classification and tests. Use `--strict` to skip Windows-Legacy-only timeline entries for non-legacy projects.

## Raw Client References

Read these only when interpreting or extending client script behavior:

- `references/normalized_timeline_schema.md`: package-only normalized timeline fields.
- `references/package_matching_rules.md`: package matching and false-positive rules for the current scripts.
- `references/report_schema.md`: legacy raw client report payload and its mapping to the common schema.
- `references/risk_scoring_model.md`: legacy raw client risk fields and their mapping to common severity.
- `references/example_findings.md`: common normalized examples for client, server, and mixed findings.

## Legacy-to-Common Mapping

When client script output uses old field names, map them before presenting:

| Raw client field | Common field |
|---|---|
| `risk_level` | `severity` |
| `classification` | `status` |
| `package_name` | `feature_or_package` and optional `package_name` |
| `recommendation` | `recommended_action` |
| `removal_date` | `deadline` |
| `source_url` | `source_url` |
| `project_name` | optional `project_name` |
| `current_version` | optional `current_version` |
| `replacement_package` | optional `replacement_package` |
| `compatibility_scope` | optional `compatibility_scope` |
| `project_compatibility` | optional `project_compatibility` |

Set client defaults when the raw report omits common fields:

- `domain`: `client`
- `product`: `Studio/Robot activity packages` unless a more specific product is proven.
- `environment`: project compatibility, package export source, or `Unknown client project`.
- `mitigation_route`: usually `ai_assisted_change` when package/workflow edits are feasible, otherwise `owner_review` or `manual_only`.
- `recommended_skill`: `uipath-rpa` for workflow or package changes; `uipath-deprecation-analyzer` for assessment-only follow-up.
- `owner_hint`: `RPA maintainer` unless project metadata identifies a team.

## Validation

Before presenting repository changes as final, run from the skill package root:

```bash
python -m unittest discover -s tests
```

Confirm:

- timeline parsing ignores non-NuGet entries,
- project and `.nupkg` inventory includes evidence paths,
- findings include evidence, classification/status, recommendation/action, severity/risk, confidence, and source URL,
- Markdown, JSON, CSV, Excel, and optional HTML reports are generated when requested.
