# Contributing Guide

This repository is a coding-agent skill: Python analysis scripts under `scripts/`, a Node.js
installer under `installer/` and `bin/`, agent-facing docs (`SKILL.md`, `README.md`), and reference
material under `references/`. It is **not** a UiPath Studio project, so day-to-day work uses ordinary
Git from the CLI or your editor.

## Branching Strategy

| Branch | Purpose |
|---|---|
| `main` | Stable, deployable code — protected |
| `develop` | Integration branch for ongoing work |
| `feature/your-name-description` | Personal feature branches |

Always branch off `develop`, not `main`. Open PRs back to `develop`; `develop` is periodically merged
to `main` after review.

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add server-side out-of-support version matching
fix: handle missing timeline cache gracefully
docs: sync README structure with scripts folder
refactor: extract shared normalizer helpers
```

## Pull Request Requirements

- At least **1 reviewer** must approve before merging to `main`
- PR description should include: what changed, how to test, any config changes needed

## How to Test

Run the test suites before opening a PR:

```bash
python3 -m unittest discover -s tests   # Python unit + contract tests
npm test                                # Node installer tests (node --test tests/*.test.js)
npm run test:browser                    # Playwright dashboard-filter test
```

## What NOT to Commit

The following are already covered by `.gitignore`; never commit them:

- `.env` and any file containing Orchestrator tokens, API keys, or client secrets
- `__pycache__/`, `*.pyc`, `*.pyo`, `.venv/`, `venv/`, `*.egg-info/` — Python artifacts
- `node_modules/`, `dist/`, `build/`, `.next/`, `test-results/`, `playwright-report/` — Node/build artifacts
- `packages/`, `*.lck` — local package and lock files

Note: `bin/` **is** tracked — `.gitignore` deliberately re-includes it (`!bin/`) because it holds the
`uipath-deprecation-skill` CLI entrypoint. Do not add `bin/` to `.gitignore`.
