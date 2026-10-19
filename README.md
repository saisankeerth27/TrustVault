# TrustVault

TrustVault is a secure, multi-tenant document vault that will let organizations store, organize, share, and audit access to sensitive documents. The design enforces named-user, per-document READ and EDIT permissions in the backend, records significant actions in a tamper-evident audit trail, and gives administrators visibility into document activity.

> **Status: Phase 1 — Application scaffold complete (awaiting review).**
> The frontend and backend skeletons, tooling, tests, and deployment configuration exist. Authentication, database tables, document upload/download, permissions, audit persistence, and real document data are **not** implemented yet. There is no live production deployment.

## Project Objective

Provide a document management system where authorization is guaranteed by the backend, not by hiding frontend controls. Document owners will decide exactly who can read or edit each document; viewers will see only what is shared with them; administrators will oversee activity and audit history.

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Routing | React Router |
| HTTP client | Axios |
| Forms / validation | React Hook Form, Zod |
| Backend | Python, FastAPI |
| Database (planned) | Supabase PostgreSQL |
| ORM / migrations (planned) | SQLAlchemy 2.x, Alembic |
| Object storage (planned) | Wasabi private S3-compatible storage |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| Testing | pytest, FastAPI TestClient, frontend build/type checks |

## Repository Structure

```text
TrustVault/
├── backend/
│   ├── app/
│   │   ├── api/            # Routers (health for Phase 1)
│   │   ├── core/           # Settings, logging, error handlers
│   │   ├── schemas/        # Pydantic response models
│   │   ├── services/       # Reserved for later phases
│   │   ├── __init__.py
│   │   └── main.py         # FastAPI application factory
│   ├── tests/              # pytest suite
│   ├── .env.example
│   ├── pytest.ini
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/
│   │   ├── app/            # Router and application setup
│   │   ├── components/     # Layout and shadcn/ui components
│   │   ├── lib/            # Shared utilities (cn)
│   │   ├── pages/          # Login, Dashboard, Documents, Not Found
│   │   ├── services/       # Central Axios client
│   │   └── types/          # Shared TypeScript types
│   ├── .env.example
│   ├── components.json     # shadcn/ui configuration
│   ├── vercel.json
│   └── package.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── REQUIREMENTS.md
├── THREATS.md
├── PROMPTS.md
├── render.yaml
└── README.md
```

## Getting Started

### Requirements

- **Node.js** 24.16.0 with npm 11.13.0 (the versions used to verify this phase). Use a current Node.js release if different.
- **Python** 3.13.13 (the version used to verify this phase)
- npm and the Python `venv` module

### 1. Clone and enter the repository

```bash
git clone https://github.com/saisankeerth27/TrustVault.git
cd TrustVault
```

### 2. Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Start the API:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health endpoint: <http://127.0.0.1:8000/health>
- OpenAPI documentation: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

The health endpoint reports **process health only**. It does not check the database or object storage because those integrations do not exist yet.

### 3. Frontend setup

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

The Vite development server is available at <http://localhost:5173>. `VITE_API_BASE_URL` must point at the running FastAPI backend (default `http://localhost:8000`).

### Frontend routes

| Route | Purpose | Status |
|-------|---------|--------|
| `/` | Redirects to `/dashboard` | Scaffold |
| `/login` | Login placeholder form | No authentication |
| `/dashboard` | Scaffold status and live health check | Reads `/health` only |
| `/documents` | Intentional empty state | No document APIs |
| `*` | Not-found page | Scaffold |

Frontend route protection, hidden controls, and client-side validation are **not** security controls. Backend authorization begins in later phases.

## Environment Variables

Templates are committed; real values are not.

### Backend — `backend/.env.example`

| Variable | Purpose | Phase 1 required |
|----------|---------|------------------|
| `APP_NAME` | API display name | No (default provided) |
| `APP_VERSION` | API version | No (default provided) |
| `APP_ENV` | `development`, `test`, or `production` | No (default `development`) |
| `LOG_LEVEL` | Logging verbosity | No (default `INFO`) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact frontend origins | Yes for frontend calls |

`CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173`. A wildcard is rejected outside the `development` environment. Database, JWT, Wasabi, and Supabase variables are documented as comments only and are not used in Phase 1.

### Frontend — `frontend/.env.example`

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Base URL for the FastAPI backend |

Only non-secret configuration belongs in `VITE_*` variables, because Vite embeds them in the browser bundle. Never place database passwords, service-role keys, or storage secrets in frontend environment variables.

## Testing and Checks

### Backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

Current suite (7 tests) verifies:
- The application imports and exposes the expected title/version.
- `GET /health` returns the documented response.
- The health response does not expose configuration or secrets.
- Unknown routes return the consistent JSON error envelope.
- OpenAPI schema and documentation routes are available.
- Allowed CORS origins receive the CORS header; untrusted origins do not.

### Frontend

```powershell
cd frontend
npm run typecheck
npm run lint
npm run build
```

All three commands are expected to pass. `npm run build` runs the TypeScript project build and the Vite production build.

> No cross-user authorization tests exist yet. Authorization is not implemented; those tests belong to Phase 8.

## API Baseline

- **Health:** `GET /health` → `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`
- **Errors:** JSON envelope `{"error":{"code":"...","message":"...","details":"..."}}` where applicable.
- **CORS:** Loaded from `CORS_ALLOWED_ORIGINS`; production wildcards are rejected.
- **OpenAPI:** Enabled at `/docs` and `/openapi.json`.

## Deployment Preparation

No deployment has been performed or verified.

### Vercel (frontend)

- Project root: `frontend/`
- Build command: `npm run build`
- Output directory: `dist`
- SPA rewrite: configured in `frontend/vercel.json` so deep links serve `index.html`
- Environment: set `VITE_API_BASE_URL` to the Render backend URL

### Render (backend)

- Configuration: `render.yaml`
- Root directory: `backend/`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Environment: `APP_ENV=production`, `LOG_LEVEL=INFO`, and a real `CORS_ALLOWED_ORIGINS` value (for example, the Vercel production origin). Render supplies `PORT`.

Deployment requires access to the Vercel and Render accounts and has not been authorized or attempted in Phase 1.

## Deferred Decisions (Phase 3)

Authentication is not implemented. The following decisions must be finalized in Phase 3 and are intentionally absent from the frontend:

- Access-token storage mechanism (secure httpOnly cookie versus in-memory token).
- Token refresh strategy and Axios interceptor behavior.
- Refresh-token rotation and revocation semantics.

No authentication interceptors or assumed token formats exist in the Phase 1 client.

## Security Principles

- **Backend is authoritative.** Hiding a UI control is not authorization; every request will be verified server-side.
- **Deny by default.** Access will require explicit ownership, role, or permission grant.
- **Defense in depth.** Application checks, Supabase RLS, private storage, and audit logging layer together.
- **Immutable audit history.** Audit records will be append-only and hash-chained; external checkpoints are planned to detect privileged tampering.
- **Secrets never touch source control.** Only `.env.example` templates with placeholders are committed.
- **Fail closed.** External-service failures will deny access rather than bypass checks.
- **Restricted CORS.** Production CORS allows only configured origins; wildcards are rejected outside development.

See [THREATS.md](THREATS.md) for the full threat model.

## Current Limitations

- No user registration, login, sessions, or roles.
- No database schema, migrations, or Supabase connection.
- No document upload, download, search, or storage integration.
- No permission grants, revocation, or authorization enforcement.
- No audit persistence or administrator activity views.
- No live deployment; only configuration is prepared.
- The backend health check is process-only.
- The frontend displays intentional empty states and claims no document data.
- No production CSP or HSTS configuration yet (planned for Phase 10).

## Project Status

| Phase | Status |
|-------|--------|
| 0 — Requirements and Repository Foundation | Complete |
| 1 — Project Scaffold and Early Deployment | Complete — awaiting review |
| 2 — Database Schema and Migrations | Not started (next) |
| 3 — Authentication and Roles | Not started |
| 4 — Private Storage and Validated Uploads | Not started |
| 5 — Document Management and Search | Not started |
| 6 — Document Permissions and Revocation | Not started |
| 7 — Audit Trail and Administrator Activity | Not started |
| 8 — Security Tests and Threat-Model Verification | Not started |
| 9 — Complete Frontend | Not started |
| 10 — Deployment Hardening and End-to-End Verification | Not started |
| 11 — Final Submission and Demo | Not started |

## Planning Documents

- [Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
- [Threat Model](THREATS.md)
- [AI Development Log](PROMPTS.md)

## Security Note for Contributors

Never commit credentials, database passwords, service-role keys, access tokens, or private keys. If a secret is exposed, treat it as compromised and rotate it immediately.
