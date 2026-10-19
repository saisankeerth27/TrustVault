# TrustVault

TrustVault is a secure, multi-tenant document vault that will let organizations store, organize, share, and audit access to sensitive documents. The design enforces named-user, per-document READ and EDIT permissions in the backend, records significant actions in a tamper-evident audit trail, and gives administrators visibility into document activity.

> **Status: Phase 2 — Database schema, models, and migrations complete (awaiting review).**
> Phases 0–2 are implemented: documentation, the frontend/backend scaffold, and the verified PostgreSQL schema with Alembic migrations. Authentication, document upload/download, permission endpoints, audit writing, and real document data are **not** implemented yet. There is no live deployment, and the migration has **not** been applied to the Supabase project.

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
| Database | Supabase PostgreSQL |
| ORM / migrations | SQLAlchemy 2.x (psycopg 3), Alembic |
| Object storage (planned) | Wasabi private S3-compatible storage |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| Testing | pytest, FastAPI TestClient, embedded-postgres, frontend build/type checks |

## Repository Structure

```text
TrustVault/
├── backend/
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/0001_initial_schema.py
│   ├── alembic.ini
│   ├── app/
│   │   ├── api/            # Routers (health for Phase 1)
│   │   ├── core/           # Settings, logging, error handlers
│   │   ├── db/             # Base, URL helpers, engine/session management
│   │   ├── models/         # SQLAlchemy models and enums
│   │   ├── schemas/        # Pydantic response models
│   │   ├── services/       # Reserved for later phases
│   │   ├── __init__.py
│   │   └── main.py         # FastAPI application factory
│   ├── tests/              # pytest suite (health, CORS, schema, migrations)
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
│   ├── DATABASE.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── REQUIREMENTS.md
├── THREATS.md
├── PROMPTS.md
├── render.yaml
└── README.md
```

## Getting Started

### Requirements

- **Node.js** 24.16.0 with npm 11.13.0 (the versions used to verify these phases). A current Node.js release should also work.
- **Python** 3.13.13 (the version used to verify these phases).
- npm and the Python `venv` module.

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

Set `DATABASE_URL` in `backend/.env` to your Supabase direct connection string (port 5432), then apply migrations:

```powershell
alembic upgrade head
```

Start the API:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health endpoint: <http://127.0.0.1:8000/health>
- OpenAPI documentation: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

The health endpoint reports **process health only**. It does not check the database or object storage; those checks will be added when the integrations exist.

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

## Database

The Phase 2 schema has four tables — `users`, `documents`, `document_permissions`, and `audit_events` — with UUID primary keys, enforced checks, foreign keys, partial unique indexes, and a `pg_trgm` index for document name search. Highlighted decisions:

- Roles and statuses are constrained strings; no native PostgreSQL enums.
- Emails are stored lowercased and uniquely constrained.
- Document permissions keep a full grant/revoke history with a partial unique index allowing only one active grant per user/document pair.
- Audit events reference users and documents with `ON DELETE SET NULL` so history survives deletion.
- Documents use soft deletion (`deleted_at`).

Full column, constraint, and index detail, plus RLS planning and connection management, is in [docs/DATABASE.md](docs/DATABASE.md). The migration is applied only through Alembic; `alembic upgrade head` is a manual step during deployment.

Alembic commands (from `backend/`):

```powershell
alembic current
alembic upgrade head
alembic downgrade -1
alembic check
```

## Environment Variables

Templates are committed; real values are not.

### Backend — `backend/.env.example`

| Variable | Purpose | Required |
|----------|---------|----------|
| `APP_NAME` | API display name | No (default provided) |
| `APP_VERSION` | API version | No (default provided) |
| `APP_ENV` | `development`, `test`, or `production` | No (default `development`) |
| `LOG_LEVEL` | Logging verbosity | No (default `INFO`) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact frontend origins | Yes for frontend calls |
| `DATABASE_URL` | PostgreSQL/Supabase connection string (direct port 5432 for migrations) | Yes for database work |
| `DB_POOL_SIZE` | SQLAlchemy pool size | No (default `5`) |
| `DB_MAX_OVERFLOW` | SQLAlchemy overflow allowance | No (default `10`) |

`CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173`. A wildcard is rejected outside `development`. JWT, Wasabi, and Supabase API variables are documented as comments only and are not used yet.

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

The suite currently has 25 tests. It verifies:
- The application imports and exposes the expected title/version.
- `GET /health` behavior, including that it exposes no configuration.
- The consistent JSON error envelope and CORS behavior.
- Database URL normalization and Supabase pooler/SSL detection.
- Model/table/column/index definitions for all four tables.
- Database constraints: unique and normalized email, owner foreign key, non-negative file size, internal storage keys, valid permission values, duplicate active grant rejection, regrant-after-revocation history, audit retention via `ON DELETE SET NULL`, JSON-object details, and hash format.
- The Alembic migration: `upgrade head`, `alembic check` for model/migration drift, `downgrade base`, and re-`upgrade`.

Database tests start an **embedded PostgreSQL** instance in a temporary directory and never contact Supabase or read `DATABASE_URL`.

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

No document, authentication, permission, or audit endpoints exist yet.

## Deployment Preparation

No deployment has been performed or verified, and no migration has been applied to Supabase.

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
- Environment: `APP_ENV=production`, `LOG_LEVEL=INFO`, `DATABASE_URL`, and a real `CORS_ALLOWED_ORIGINS` value. Render supplies `PORT`.
- Migrations are **not** run automatically. Run `alembic upgrade head` from a trusted shell with the production `DATABASE_URL` before or after deploying schema changes.

Deployment requires access to the Vercel, Render, and Supabase accounts and has not been authorized or attempted.

## Deferred Decisions (Phase 3)

Authentication is not implemented. These decisions must be finalized in Phase 3 and are intentionally absent from the frontend:

- Access-token storage mechanism (secure httpOnly cookie versus in-memory token).
- Token refresh strategy and Axios interceptor behavior.
- Refresh-token rotation and revocation semantics (the `refresh_tokens` table will be introduced then).
- Whether the backend continues using a single privileged database role or assumes a per-user identity (this determines the RLS policy design).

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
- The database schema exists, but RLS is not enabled and no authorization path exists yet.
- The migration has not been applied to the Supabase project.
- No document upload, download, search, or storage integration.
- No permission grant or revocation endpoints (the schema exists).
- No audit writing, hash chain, or administrator activity views.
- No live deployment; only configuration is prepared.
- The backend health check is process-only.
- The frontend displays intentional empty states and claims no document data.
- No production CSP or HSTS configuration yet (planned for Phase 10).

## Project Status

| Phase | Status |
|-------|--------|
| 0 — Requirements and Repository Foundation | Complete |
| 1 — Project Scaffold and Early Deployment | Complete — awaiting review |
| 2 — Database Schema and Migrations | Complete — awaiting review |
| 3 — Authentication and Roles | Not started (next) |
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
- [Database Design](docs/DATABASE.md)
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
- [Threat Model](THREATS.md)
- [AI Development Log](PROMPTS.md)

## Security Note for Contributors

Never commit credentials, database passwords, service-role keys, access tokens, or private keys. If a secret is exposed, treat it as compromised and rotate it immediately.
