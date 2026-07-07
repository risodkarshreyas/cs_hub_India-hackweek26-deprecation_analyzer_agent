# Risk Scoring Model

Risk is conservative and date-driven.

| Classification | Risk | Urgency |
|---|---|---|
| Already Removed | Critical | Immediate |
| Removal Imminent | High | Next 0-6 months |
| Removal Scheduled | Medium | Plan within 6-18 months |
| Windows-Legacy/.NET Framework impact | High | Prioritize compatibility migration planning |

Effort estimates:

- `low`: one affected workflow or package-only change likely.
- `medium`: multiple workflows or uncertain XAML impact.
- `high`: already removed package, broad workflow use, or project compatibility migration likely.

Impact fields:

- `affected_project_count`
- `affected_workflow_count`
- `affected_package_count`
- `remediation_effort`
- `likely_migration_complexity`
- `estimated_time_saved`
- `value_added`
- `confidence`

Use low confidence when workflow count, owner, compatibility mode, or replacement path cannot be inferred from evidence.
