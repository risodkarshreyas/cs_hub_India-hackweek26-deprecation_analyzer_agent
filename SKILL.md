---
name: uipath-deprecation-analyzer
description: Use when analyzing UiPath deprecation risk for RPA projects, XAML, project.json, .nupkg, Studio/Robot/activity packages, Orchestrator, Automation Cloud/Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Ops, Maestro, tenant/platform exports, or mixed client/server inputs.
---

# UiPath Deprecation Analyzer

Use this skill as the single entrypoint for UiPath deprecation analysis. Route the input to the client-side analyzer, the server-side analyzer, or both, then normalize all final findings with the shared schema.

## Required References

Always read `references/common_analysis_rules.md` before producing findings or a report.

Then read only the analyzer reference needed for the request:

- `references/client_side_analyzer.md`: RPA project folders, GitHub checkouts, XAML, `project.json`, `.nupkg`, Orchestrator package exports, Studio, Robot, activity packages, package dependencies, and Windows-Legacy/.NET Framework package compatibility.
- `references/server_side_analyzer.md`: Orchestrator, Automation Cloud, Automation Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding, Insights, Process Mining, Automation Hub, Automation Ops, Maestro, Task Mining, High Availability Add-On, tenant exports, organization settings, platform APIs, and infrastructure configuration.

## Routing

Choose the analyzer by evidence type:

| Input or request mentions | Route |
|---|---|
| RPA source project, workflow, XAML, `project.json`, `.nupkg`, Studio, Robot, activity package, NuGet dependency, package replacement, Windows-Legacy package compatibility | Client-side analyzer |
| Orchestrator tenant/folder resources, Automation Cloud/Suite, Apps, Integration Service, Test Manager, Action Center, AI Center, Document Understanding service configuration, Insights, Process Mining, Automation Hub, Automation Ops, Maestro, tenant/platform administration, APIs, infrastructure, service versions | Server-side analyzer |
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
