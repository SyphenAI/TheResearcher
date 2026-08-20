# TheResearcher backlog tracker

Last updated: 2026-08-12 (evening) · branches `main` and `pre-prod` @ `29bf2bb`

Use this file to resume work. Status values: `not started` | `in progress` | `completed` | `partial` | `blocked`.

**App:** http://127.0.0.1:50080 · **Stack:** FastAPI + React/Vite in Docker · **Data:** `./data` + `./storage` (gitignored contents)

---

## Foundation (shipped)

| ID | Task | Status | Notes |
|----|------|--------|-------|
| B01 | Workspace git setup (`pre-prod` from `main`) | completed | Remote: SyphenAI/TheResearcher |
| B02 | Dockerize app (Dockerfile + compose, port 50080) | completed | Image `theresearcher:pre-prod` |
| B03 | Auth (researcher/password, force change, users) | completed | Admin role can create users |
| B04 | Research dashboard shell (projects, sections, paper) | completed | Desk: sections, prompt, paper, tasks, artifacts |
| B05 | Security tab + encrypted tokens + kill switch | completed | SQLite Fernet; Research/Judge toggles; Test; Global Kill |
| B06 | AI checker tab + contribution metrics | completed | Quick local + live panel; desk agent/human % |
| B07 | Judge + humanize + docx export | completed | Local + live multi-model judge; local/live humanize; publish gate export |
| B08 | README + backlog | completed | Keep this file current when shipping features |
| B09 | Docker build/run verification | completed | Health endpoint on :50080 |
| B10 | Push `pre-prod` to origin | completed | `origin/pre-prod` @ `29bf2bb` |
| B11 | Home dashboard vs research workspace split | completed | Home = metrics/list/radar; open project = desk |
| B12 | Promote `pre-prod` → `main` | completed | Fast-forward; `origin/main` @ `29bf2bb` (2026-08-12 night) |
| B13 | Storage under tool dirs (not user home scatter) | completed | `storage/projects`, `archive`, `tmp` |
| B14 | Project archive / restore | completed | Delete archives; restore from dashboard |
| B15 | Backups (data + storage zip) | completed | Security tab: create / list / restore |
| B16 | Usage & cost estimate log | completed | Security; Settings daily cost alert |

---

## Product features (current state)

| ID | Task | Status | Notes |
|----|------|--------|-------|
| P01 | Live provider agents (OpenAI/Anthropic/Google/xAI) | completed | Multi-agent panel: researcher → critic → red_team → synth (`agents.py` + `llm.py`) |
| P01b | Preferred model per token + live model picker | completed | Security preferred model; desk/AI Checker picker (e.g. Haiku vs Sonnet) |
| P01c | Assistant apply vs draft accounting | completed | Agent % only on Apply; resync after deletes; Refresh desk |
| P02 | Diagram / visualization generator | completed | Mermaid attack/STRIDE/controls + insert into paper |
| P03 | MITRE + STRIDE structured assessment UI | partial | Desk framework maps + assistant framing; not a full standalone assessor |
| P04 | SaaS control review templates | partial | Control packs + templates; can deepen later |
| P05 | Gartner-style / domain research templates | partial | Template store + domain scaffolds; **Analyst Insights note (ITRBP)** pack for writing exercise structure |
| P05b | Paper-area MD → Word download | completed | Download Word (section) + full paper; `as_draft` skips publish gate; improved export_docx tables/code |
| P06 | Peer review workflow | partial | Peer review list/add on desk; not multi-user collab |
| P07 | Citation manager + scholar search | completed | APA-style fields; Crossref + Semantic Scholar + OpenAlex + Google Scholar (SerpAPI); year_from/year_to filters |
| P08 | MFA for local accounts | not started | Password auth only |
| P09 | Collaborative simultaneous editing | not started | Single-user local edits |
| P10 | MCP bridge for host agents | partial | Expanded tools + FastMCP when `pip install -r requirements-mcp.txt`; stdlib NDJSON fallback. Not every desk endpoint yet. |
| P11 | Automated test suite | not started | API + style lint for banned dashes/phrases |
| P12 | Optional syphen.ai visual theme pass | not started | Current dark theme is independent |
| P13 | Search: local library FTS | completed | Projects, sections, citations, artifacts |
| P14 | Search: scholar (world) + summarize | completed | Scholar tab; summarize URL/upload/paste (local or live) |
| P15 | Research radar (dashboard bottom) | completed | News RSS + papers for follow topics; 1–30 day window; cache + Update now |
| P16 | Evidence check + publish gate | completed | Uncited claims, checklist insert, Settings thresholds |
| P17 | Humanize local vs live + Accept/Reject | completed | Red/green diff; undo after accept; desk + AI Checker |
| P18 | Desk UX: busy / thinking, drafts, tasks | completed | Thinking banner; dismiss assistant draft; tasks complete/edit/delete |
| P19 | Autosave + section versions | completed | ~3s autosave; version list/restore |
| P20 | PDF OCR for sparse extracts | completed | Tesseract in image; AI Checker / summarize path |
| P21 | README screenshots / OSS polish | not started | Low priority until public push story |

---

## Ops / hygiene

| ID | Task | Status | Notes |
|----|------|--------|-------|
| O01 | Keep PAT files gitignored | completed | `TheResearcher_dev_pat.txt*` ignored |
| O02 | App writes under project `data/` + `storage/` | completed | Compose volumes; never commit secrets/DB |
| O03 | `local/` session handoff gitignored | completed | Agent notes only; not product docs |
| O04 | Reference comments on reasoning code | completed | `agents.py`, `llm.py`, `ai_style.py`, `research.py`, `mcp_server.py` header |

---

## Next (parked)

| Priority | Item | Notes |
|----------|------|-------|
| Content | Official Gartner research topic | **Not received yet** — do not invent; practice OffSec/EM/VM until it lands |
| Product | Deeper scaffolds after practice papers or topic | Templates already usable |
| Product | Per-project follow topics | Optional; global follow topics in Settings work today |
| Product | Richer section history UI (diff versions) | Snapshots exist; UI is list+restore |
| Product | MCP: more endpoints / resources / Claude config doc | Core tools + FastMCP path shipped; wire client config when ready |
| Product | Automated tests (P11) | Highest engineering hygiene gap |
| Docs | README screenshots + feature list refresh | README still reads early-scaffold in places |

---

## Design rules (do not regress)

1. Local-first; data under tool `data/` / `storage/`.
2. Agent prose: no em dashes / double hyphens; human voice; short audits.
3. Delete project = archive under `storage/archive/` (restore supported).
4. Preferred model per token for cost control.
5. Humanize: explicit local vs live; desk Accept before writing section.
6. Research radar stays at **bottom** of dashboard.
7. AI Checker **quick** = local only; live panel / Judge / Research Assistant are multi-model where documented.
8. Research Assistant draft does **not** write paper until Apply.

---

## Session log

### 2026-08-12 (day → night)

- Scaffolded Dockerized FastAPI + React research desk; auth, projects, security tokens
- Live multi-agent Research Assistant, judge panel, local/live humanize, AI Checker quick + live
- Scholar search (desk + global; Crossref/S2/OpenAlex + Google Scholar via SerpAPI), year filters, research radar, summarize, FTS search
- Evidence + publish gate, diagrams, backups, usage/cost alert, section versions, autosave
- Desk polish: thinking banner, refresh desk / AI check section, contribution resync, tasks complete/edit/delete
- Code reference comments on reasoning path; MCP server docstring expanded
- Pushed `pre-prod` and fast-forwarded `main` to `29bf2bb`; local Docker left running healthy on :50080

### Resume checklist

```powershell
cd D:\TheResearcher
docker compose ps
curl.exe -fsS http://127.0.0.1:50080/api/health
git log --oneline -5
# Optional local notes: local/SESSION_HANDOFF.md (gitignored)
```
