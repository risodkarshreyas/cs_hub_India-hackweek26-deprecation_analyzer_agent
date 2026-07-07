# Contributing Guide

## Branching Strategy

| Branch | Purpose |
|---|---|
| `main` | Stable, deployable code — protected |
| `develop` | Integration branch for ongoing work |
| `feature/your-name-description` | Personal feature branches |

Always branch off `develop`, not `main`. Open PRs back to `develop`; `develop` is periodically merged to `main` after review.

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add claims extraction workflow
fix: handle null queue item response
docs: update setup instructions
refactor: extract helper activities into shared library
```

## UiPath Studio Git Workflow

> **Important:** Always use Studio's built-in **Team > Git Init** for the very first commit on a new repo. Do NOT run `git init` from the CLI on a UiPath project — Studio writes its own project metadata during init.

- Only enable branch protection on `main` **after** the first Studio push succeeds.
- Use Studio's Git panel for day-to-day commits and branch switches to avoid corrupting Studio project metadata.

## Pull Request Requirements

- At least **1 reviewer** must approve before merging to `main`
- PR description should include: what changed, how to test, any config changes needed

## What NOT to Commit

Never commit the following:

- `.local/`, `.objects/`, `.autopilot/` — Studio runtime artifacts
- `*.lck` — lock files
- `.env`, `appsettings.Production.json`, `credentials.json`, `connection_strings.json` — environment config with secrets
- Any file containing Orchestrator tokens, API keys, or client secrets
- `node_modules/`, `bin/`, `obj/`, `.venv/` — build/dependency artifacts (these are in .gitignore)
