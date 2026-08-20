# TheResearcher

Local research agent for Security Operations teams. Focus areas: Offensive Security, Exposure Management, and Vulnerability Management.

This project runs in Docker on your machine. Data stays in the project `data/` directory.

## Status

Active development happens on the `pre-prod` branch. Promotion to `main` requires owner approval.

## Features (current)

- Web dashboard on port **50080**
- Auth with default admin `researcher` / `password` (forced password change on first login)
- Admin user management
- Multi-project research desk (section prompts, markdown paper, tasks, artifacts)
- Research Assistant (local scaffold until provider tokens are added)
- Contribution tracking (agent vs human)
- AI Checker tab with AI/human percentage signals
- Judge scoring for draft quality
- Humanize rewrite helper (style cleanup, target under 10% agent share on final work)
- Word (`.docx`) export
- Security tab for encrypted API token storage + kill switch
- Startup self-check and health endpoint

## Requirements

- Docker Desktop (or Docker Engine + Compose v2)
- Git
- Optional: Node 22+ and Python 3.12+ for non-Docker local dev

## Quick start (Docker)

```bash
git clone https://github.com/SyphenAI/TheResearcher.git
cd TheResearcher
git checkout pre-prod
copy .env.example .env   # Windows
# or: cp .env.example .env
docker compose up --build -d
```

Open: [http://localhost:50080](http://localhost:50080)

First login:

1. Username: `researcher`
2. Password: `password`
3. Change password when prompted

Windows helper:

```powershell
.\scripts\dev-up.ps1
```

## Useful commands

```bash
docker compose logs -f theresearcher
docker compose ps
docker compose down
```

Health check:

```bash
curl http://localhost:50080/api/health
```

API docs (when container is up): [http://localhost:50080/docs](http://localhost:50080/docs)

## Configuration

Environment variables (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT signing secret |
| `TOKEN_FERNET_KEY` | Optional Fernet key for token encryption (derived from `SECRET_KEY` if empty) |
| `DEFAULT_ADMIN_USERNAME` | Seed admin username |
| `DEFAULT_ADMIN_PASSWORD` | Seed admin password |
| `APP_ENV` | Environment label (`pre-prod` by default) |

Persistent volume mapping:

- Host: `./data` → Container `/app/data` (SQLite DB, app settings, encrypted tokens)
- Host: `./storage` → Container `/app/storage` (per-project uploads, exports, archives)

`storage/` contents are gitignored. Only empty folder placeholders are tracked.

The app is designed to stay inside its own project directory.

## Security notes

- Do not commit PAT files, `.env`, or anything under `data/` that holds secrets
- Use the Security tab to store provider tokens (OpenAI, Anthropic, Google, xAI, etc.)
- Use **Kill switch** to wipe stored API tokens quickly
- Default credentials exist only for first boot. Change them immediately

## Project layout

```text
backend/          FastAPI app
frontend/         React + Vite UI
data/             Local runtime data (gitignored DB files)
scripts/          Helper scripts
docker-compose.yml
Dockerfile
```

## Development workflow

1. Branch: work on `pre-prod`
2. Open a PR or request promotion to `main` only after review/approval

### Local API without full Docker UI rebuild

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set DATA_DIR=..\data
uvicorn app.main:app --host 0.0.0.0 --port 50080
```

### Frontend dev server

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to port 50080.

## Writing and output rules (product policy)

- Avoid double hyphens and em dashes in agent outputs
- Avoid robotic filler ("in conclusion", "furthermore", "delve", etc.)
- Prefer direct, conversational researcher tone with contractions
- Final published research should show under **10%** agent contribution after human edit/humanize passes

## Contributing

1. Use `pre-prod` for feature work
2. Keep changes scoped; use clear commit messages
3. Report issues in GitHub Issues
4. Request features with clear SecOps research use cases

## License

See `LICENSE`.
