# TheResearcher backlog tracker

Last updated: 2026-08-12

Use this file to resume work. Status values: `not started` | `in progress` | `completed` | `blocked`.

## Now / next

| ID | Task | Status | Notes |
|----|------|--------|-------|
| B01 | Workspace git setup (`pre-prod` from `main`) | completed | Remote: SyphenAI/TheResearcher |
| B02 | Dockerize app (Dockerfile + compose, port 50080) | completed | Image `theresearcher:pre-prod` |
| B03 | Auth (researcher/password, force change, users) | completed | Admin role can create users |
| B04 | Research dashboard shell (projects, sections, paper) | completed | Left prompt / right markdown |
| B11 | Primary home dashboard vs research workspace split | completed | Home = metrics/list/start; open project = desk |
| B05 | Security tab + encrypted tokens + kill switch | completed | Local SQLite encrypted values |
| B06 | AI checker tab + contribution metrics | completed | Heuristic local checker |
| B07 | Judge + humanize + docx export | completed | Local offline implementations |
| B08 | README + backlog | completed | This file |
| B09 | Docker build/run verification | completed | Image healthy on http://localhost:50080 |
| B10 | Push `pre-prod` branch to origin | completed | origin/pre-prod @ 4ed496d |

## Near-term product gaps

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P01 | Wire live provider agents (OpenAI/Anthropic/Google/xAI) using Security tokens | not started | Local scaffold returns offline drafts today |
| P02 | Diagram / visualization generator | not started | Spec in start_here.md |
| P03 | MITRE + STRIDE structured assessment UI | not started | Backend framing exists in assistant text only |
| P04 | SaaS control review templates | not started | |
| P05 | Gartner-style research workflow templates | not started | |
| P06 | Peer review workflow | not started | Judge is single-user local scoring |
| P07 | Citation manager (APA/MLA/Chicago) | not started | Basic citation stubs in assistant |
| P08 | MFA for local accounts | not started | Password auth only |
| P09 | Collaborative simultaneous editing | not started | Single-user local edits now |
| P10 | Public packaging (MCP server / multi-model download story) | not started | Design later |
| P11 | Automated test suite (API + style lint for banned dashes/phrases) | not started | |
| P12 | Optional syphen.ai visual theme pass | not started | Current dark theme is independent |

## Ops / hygiene

| ID | Task | Status | Notes |
|----|------|--------|-------|
| O01 | Keep PAT files gitignored | completed | `TheResearcher_dev_pat.txt*` ignored |
| O02 | Ensure app only writes under project `data/` | completed | Volume `./data:/app/data` |
| O03 | Promote `pre-prod` → `main` | blocked | Requires owner approval only |

## Session log

### 2026-08-12

- Read `start_here.md` requirements
- PAT discovered as `TheResearcher_dev_pat.txt.txt` (also copied to expected name)
- Authenticated to GitHub as `SyphenAI`, repo `SyphenAI/TheResearcher`
- Created local `pre-prod` branch from `main`
- Scaffolded Dockerized FastAPI + React app with core research desk features
- Docker Desktop engine was flaky on first start; build succeeded after daemon came up
- Verified container health, login, and UI shell on port 50080
- Pushed `pre-prod` to origin
