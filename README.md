# UiPath Deprecation Analyzer Skill

Portable coding-agent skill for routing UiPath deprecation analysis across client-side automation artifacts, server-side platform evidence, or mixed client/server inputs.

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

## Prerequisites

- A coding-agent environment that can load local skill or instruction folders, such as Codex, Claude Code, Copilot, Antigravity, or a similar agent.
- Python 3 installed and available as `python`.
- Node.js 20 or later if you want to use the bundled skill installer CLI.
- Internet access for the default live refresh from the UiPath deprecation timeline.
- Optional: `openpyxl` for richer XLSX output. If it is not installed, the analyzer writes XLSX files with a built-in standard-library fallback.
- For offline or repeatable runs, cached client timeline and/or server rule JSON files.

## Using This With Coding Agents

`SKILL.md` is the agent-facing entrypoint. Different agents have different local-skill or instruction installation mechanisms, so place or register this folder according to your agent's documentation.

Generic prompt:

```text
Use the UiPath deprecation analyzer skill in this folder to analyze <path> for UiPath deprecation risk.
```

Codex/OpenAI example:

```text
Use $uipath-deprecation-analyzer to analyze <path> for UiPath deprecation risk and return normalized findings.
```

`agents/openai.yaml` provides OpenAI/Codex UI metadata and implicit-invocation settings. Other agents can ignore it and use `SKILL.md`, `references/`, and `scripts/` directly.

The skill inspects the available evidence and routes the request to the client-side analyzer, the server-side analyzer, or both.

## Setup

1. Download or clone this repository.
2. Install the skill with the bundled installer, or manually place this folder where your target coding agent can discover local skills or instruction folders.
3. Open a terminal at this repository root.
4. Optionally create and activate a virtual environment.
5. Run the Node installer tests and Python unit/contract tests:

   ```bash
   npm test
   python -m unittest discover -s tests
   ```

6. Run the analyzer CLI directly, or ask your coding agent to use `SKILL.md`.

## Skill Installation

The recommended install path is the bundled Node CLI. From the repository root, first preview what would be written:

```bash
npx . install --agent codex --dry-run
```

Then install for one agent:

```bash
npx . install --agent codex
```

Install for every supported target:

```bash
npx . install --agent all
```

Replace an existing installed copy:

```bash
npx . install --agent codex --force
```

Run installer health checks:

```bash
npx . doctor
```

Installer options:

- `--agent <codex|claude|copilot|all>`: target agent. Repeat it or pass `all`. If omitted, the installer detects supported agents.
- `--dry-run`: show planned writes without creating or replacing files.
- `--force`: replace an existing installed skill target.
- `--strict`: fail when no install targets are detected.
- `--source <path>`: install from a specific skill folder. Defaults to this package root.

Installer targets:

- Codex native skill: `$CODEX_HOME/skills/uipath-deprecation-analyzer` when `CODEX_HOME` is set, otherwise `~/.codex/skills/uipath-deprecation-analyzer`.
- Claude native skill: `~/.claude/skills/uipath-deprecation-analyzer`.
- Copilot compatibility adapter: `~/.config/uipath-deprecation-skill/copilot/uipath-deprecation-analyzer.md`.

Manual installation is still supported: copy `SKILL.md`, `agents/`, `references/`, and `scripts/` into the skill location expected by your coding agent.

## Input Examples

- Client inputs: UiPath source projects, GitHub checkouts, `project.json`, `.xaml`, `.nupkg`, and folders of package files.
- Server inputs: exported JSON/CSV/XML/text from Orchestrator, Apps, Automation Suite, Integration Service, AI Center, API collections, tenant settings, service versions, and platform configuration.
- Mixed inputs: one folder that contains both RPA source/package evidence and tenant/platform export evidence.

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
|   |-- reporting-dashboard-ideas.md
|   |-- server_rule_schema.md
|   |-- server_inventory_schema.md
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

Use `SKILL.md` as the agent entrypoint:

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

## Outputs

Depending on `--format`, the CLI writes these files under the output directory:

- `uipath_deprecation_report.md`
- `uipath_deprecation_findings.json`
- `uipath_deprecation_findings.csv`
- `uipath_deprecation_report.xlsx`
- `uipath_deprecation_dashboard.html`

Coverage gaps, such as missing exports or unavailable context, are reported separately from deprecation findings.

The HTML dashboard is generated from the same normalized findings payload as the JSON, Markdown, CSV, and XLSX reports. It is an additive static dashboard output and does not replace JSON or Excel artifacts.

## Analyzer Scripts

The scripts under `scripts/` support client-side, server-side, and mixed deprecation analysis. Client scanning still produces raw package findings internally, then normalizes them to the shared output contract. Server scanning extracts platform evidence, matches it to server-side deprecation rules, and reports coverage gaps separately from findings.

Client raw fields are normalized before final presentation:

- `classification` -> `status`
- `risk_level` -> `severity`
- `recommendation` -> `recommended_action`
- `removal_date` -> `deadline`
- `package_name` -> `feature_or_package` and optional `package_name`

Server-side rules and evidence records are documented in `references/server_rule_schema.md` and `references/server_inventory_schema.md`.

## CLI Quick Start

From this repository root, use `--mode auto` as the default first run. It detects client, server, or mixed evidence based on the input folder:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./path/to/uipath/evidence --output ./reports --mode auto --format markdown,json,xlsx,html
```

Client-side RPA source project or package folder:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./path/to/uipath/repo --output ./reports --mode client --format markdown,json,csv,xlsx,html
```

Server-side tenant/platform export:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./tenant-export --output ./reports --mode server --format markdown,json,xlsx,html
```

Mixed repo plus platform export:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./mixed-folder --output ./reports --mode mixed --format markdown,json,xlsx,html
```

Offline or repeatable client run using a cached timeline file:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./path/to/uipath/repo --output ./reports --timeline-cache ./tests/fixtures/timeline-cache.json --use-cache-only --format markdown,json,csv,xlsx,html --analysis-date 2026-07-07
```

Run against a folder of `.nupkg` files:

```bash
python scripts/uipath_deprecation_analyzer.py --input ./packages --output ./reports --include-nupkg
```

Cache options:

- `--offline`: use cache files only and do not fetch live UiPath docs.
- `--timeline-cache`: alias for `--client-timeline-cache`.
- `--client-timeline-cache`: normalized client deprecation timeline cache JSON.
- `--server-rule-cache`: normalized server-side deprecation rule cache JSON.

## Validation

Run the unit and contract tests:

```bash
python -m unittest discover -s tests
```

Validate skill metadata:

```bash
python C:\Users\jeet.doshi\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
```
