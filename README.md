# TrustVault

TrustVault is a secure, multi-tenant document vault that will let organizations store, organize, share, and audit access to sensitive documents. The design enforces named-user, per-document READ and EDIT permissions in the backend, records significant actions in a tamper-evident audit trail, and gives administrators visibility into document activity.

> **Status: Phase 3 — Authentication and roles implemented and verified locally (awaiting review).**
> Phases 0–3 are implemented: documentation, the frontend/backend scaffold, the verified PostgreSQL schema, and database-backed authentication with role enforcement. Document upload/download, permission endpoints, audit writing, and real document data are **not** implemented yet. There is no live deployment, and migrations have **not** been applied to the Supabase project.

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
| Authentication | bcrypt, PyJWT (HS256), rotating refresh tokens |
| Object storage (planned) | Wasabi private S3-compatible storage |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| Testing | pytest, FastAPI TestClient, embedded-postgres, frontend build/type checks |

## Repository Structure

```text
TrustVault/
├── backend/
│   ├── alembic/
│   │   ├── versions/
│   │   │   ├── 0001_initial_schema.py
│   │   │   └── 0002_add_refresh_tokens.py
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── app/
│   │   ├── api/            # Health and auth routers, authentication dependencies
│   │   ├── core/           # Settings, security, rate limiting, logging, errors
│   │   ├── db/             # Base, URL helpers, engine/session management
│   │   ├── models/         # SQLAlchemy models and enums
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # Authentication service
│   │   └── main.py         # FastAPI application factory
│   ├── scripts/            # Account provisioning CLI
│   ├── tests/              # pytest suite
│   ├── .env.example
│   ├── alembic.ini
│   ├── pytest.ini
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/
│   │   ├── app/            # Router and application setup
│   │   ├── auth/           # In-memory token store and auth provider
│   │   ├── components/     # Layout, route guards, and UI primitives
│   │   ├── lib/            # Shared utilities and role labels
│   │   ├── pages/          # Login, Dashboard, Documents, Admin, Not Found
│   │   ├── services/       # Axios client and auth API functions
│   │   └── types/          # Shared TypeScript types
│   ├── .env.example
│   ├── components.json
│   ├── package.json
│   └── vercel.json
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

Set `DATABASE_URL` to your Supabase direct connection string (port 5432) and generate a real `JWT_SECRET`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use the generated value for `JWT_SECRET` in `backend/.env`. Apply migrations:

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

The health endpoint reports **process health only**. It does not check the database or object storage.

### 3. Provision an account

Public registration creates a **Viewer** only. Create elevated accounts explicitly from `backend/`:

```powershell
python -m scripts.create_user --email admin@example.com --name "Admin User" --role ADMINISTRATOR
```

The script prompts for a password with `getpass`, or reads `TRUSTVAULT_USER_PASSWORD` if set. It never prints the password or hash. Document-owner and administrator roles must be provisioned this way; clients cannot request a role.

### 4. Frontend setup

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

The Vite development server is available at <http://localhost:5173>. `VITE_API_BASE_URL` must point at the running FastAPI backend (default `http://localhost:8000`). The browser sends the HttpOnly refresh cookie with credentialed API requests.

### Frontend routes

| Route | Purpose | Access |
|-------|---------|--------|
| `/login` | Real login form and session bootstrap | Public |
| `/dashboard` | Authenticated health/status dashboard | Any signed-in user |
| `/documents` | Intentional empty state; no document APIs yet | Any signed-in user |
| `/admin` | Administrator area with role-gated route | `ADMINISTRATOR` only |
| `/` | Redirects to `/dashboard` | Any signed-in user |
| `*` | Not-found page | Any signed-in user |

Protected routes redirect unauthenticated visitors to `/login`. An authenticated user without the required role sees a 403 state, but the backend remains the security boundary.

## Authentication and Authorization

Phase 3 implements:

- **Access tokens:** HS256 JWTs, 15-minute default lifetime, with issuer/audience validation and `sub`, `role`, `sid`, `type`, `jti`, `iat`, `nbf`, and `exp` claims.
- **Refresh tokens:** random opaque values stored only as SHA-256 hashes in `refresh_tokens`. Rotation preserves a family identifier; reuse of a rotated token revokes the entire family.
- **Refresh cookie:** `trustvault_refresh`, `HttpOnly`, scoped to `/api/v1/auth`, with `SameSite`/`Secure` controlled by environment settings. The access token is kept in frontend memory only.
- **Active-session checks:** every protected request verifies the token signature, issuer/audience, account status, and an active refresh-token family. Logout, account disablement, and reuse detection therefore invalidate existing access tokens immediately.
- **Passwords:** bcrypt with a configurable work factor (default 12), a 12-character minimum, a 72-byte maximum, and generic login errors with dummy-hash timing work for unknown accounts.
- **RBAC:** `ADMINISTRATOR`, `DOCUMENT_OWNER`, and `VIEWER`; authorization reads the current database role rather than trusting a token claim.
- **CSRF mitigation:** Origin allow-list checks on auth POSTs, no wildcard CORS with credentials, and cookie scoping. This is an origin-based control, not a per-session CSRF token.
- **Rate limiting:** process-local sliding window, default 10 attempts per 60 seconds, keyed by client IP plus normalized email for login and by IP for registration. Multi-instance production deployments need a shared limiter.

Public registration always creates a `VIEWER`. Use the CLI for `DOCUMENT_OWNER` or `ADMINISTRATOR` accounts.

## Database

The Phase 3 schema has five tables — `users`, `refresh_tokens`, `documents`, `document_permissions`, and `audit_events` — with UUID primary keys, enforced checks, foreign keys, partial unique indexes, and a `pg_trgm` index for document name search. Highlighted decisions:

- Roles and statuses are constrained strings; no native PostgreSQL enums.
- Emails are stored lowercased and uniquely constrained.
- Refresh tokens are stored only as SHA-256 hashes, grouped by session family, with expiry and revocation timestamps.
- Document permissions keep a full grant/revoke history with a partial unique index allowing only one active grant per user/document pair.
- Audit events reference users and documents with `ON DELETE SET NULL` so history survives deletion.
- Documents use soft deletion (`deleted_at`).

Full column, constraint, and index detail, plus RLS planning and connection management, is in [docs/DATABASE.md](docs/DATABASE.md). Migrations are applied only through Alembic; `alembic upgrade head` is a manual deployment step.

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
| `JWT_SECRET` | HS256 signing secret; production requires at least 32 characters | Yes |
| `JWT_ALGORITHM` | JWT algorithm; only `HS256` is accepted | No (default `HS256`) |
| `JWT_ISSUER` / `JWT_AUDIENCE` | JWT issuer/audience validation values | No (defaults provided) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime | No (default `15`) |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-token lifetime | No (default `7`) |
| `BCRYPT_ROUNDS` | bcrypt cost factor (4–16; production default `12`) | No (default `12`) |
| `AUTH_COOKIE_SECURE` | Require HTTPS for the refresh cookie | No (default `false`; must be `true` in production) |
| `AUTH_COOKIE_SAMESITE` | `lax`, `strict`, or `none` (`none` requires Secure) | No (default `lax`) |
| `AUTH_RATE_LIMIT_ATTEMPTS` | Attempts per sliding window | No (default `10`) |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | Sliding-window length | No (default `60`) |

`CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173`. A wildcard is rejected outside `development`. Wasabi and Supabase API variables remain documented as future-phase placeholders.

### Frontend — `frontend/.env.example`

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Base URL for the FastAPI backend |

Only non-secret configuration belongs in `VITE_*` variables, because Vite embeds them in the browser bundle. Never place database passwords, service-role keys, storage secrets, or JWT secrets in frontend environment variables.

## Testing and Checks

### Backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

The suite currently has **55 tests**. It verifies:

- Application metadata, health endpoint behavior, JSON error envelopes, and CORS.
- Database URL normalization and Supabase pooler/SSL detection.
- Models, tables, columns, indexes, and constraints for all five tables.
- Migration `0001` plus `0002`: `upgrade head`, `alembic check` for drift, `downgrade base`, and re-`upgrade`.
- Registration, login, refresh rotation, reuse detection, logout, and current-user behavior.
- Expired, tampered, wrong-issuer/audience, disabled-account, and revoked-session rejection.
- Role authorization helpers and fail-closed unknown-role handling.
- Login/registration rate limiting and `Retry-After` behavior.
- Production authentication configuration validators.
- Auth logging that does not include passwords, tokens, or email addresses.

Database tests start an **embedded PostgreSQL** instance in a temporary directory and never contact Supabase or read `DATABASE_URL`.

### Frontend

```powershell
cd frontend
npm run typecheck
npm run lint
npm run build
```

All three commands pass. `npm run build` runs the TypeScript project build and the Vite production build.

## API Baseline

- **Health:** `GET /health` → `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`
- **Register:** `POST /api/v1/auth/register` → creates a Viewer and returns an access token
- **Login:** `POST /api/v1/auth/login` → returns an access token and sets the refresh cookie
- **Refresh:** `POST /api/v1/auth/refresh` → rotates the refresh session and returns a new access token
- **Logout:** `POST /api/v1/auth/logout` → revokes the current refresh session and returns 204
- **Current user:** `GET /api/v1/auth/me` → returns the authenticated user
- **Errors:** JSON envelope `{"error":{"code":"...","message":"...","details":"..."}}` where applicable.
- **CORS:** Loaded from `CORS_ALLOWED_ORIGINS`; production wildcards are rejected.
- **OpenAPI:** Enabled at `/docs` and `/openapi.json`.

No document, permission, or audit endpoints exist yet.

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
- Environment: `APP_ENV=production`, `LOG_LEVEL=INFO`, `DATABASE_URL`, `JWT_SECRET`, a real `CORS_ALLOWED_ORIGINS`, and the auth cookie/rate-limit settings in `render.yaml`. Render supplies `PORT`.
- Migrations are **not** run automatically. Run `alembic upgrade head` from a trusted shell with the production `DATABASE_URL` before or after deploying schema changes.

`render.yaml` configures `AUTH_COOKIE_SECURE=true` and `AUTH_COOKIE_SAMESITE=none` for cross-site Vercel → Render cookies. This configuration has **not** been deployed. Third-party cookie blocking, custom-domain requirements, and a shared rate limiter must be evaluated during deployment hardening.

Deployment requires access to the Vercel, Render, and Supabase accounts and has not been authorized or attempted.

## Security Principles

- **Backend is authoritative.** Hiding a UI control is not authorization; every request is verified server-side.
- **Deny by default.** Access requires explicit ownership, role, or permission grant.
- **Defense in depth.** Application checks, Supabase RLS (planned), private storage, and audit logging layer together.
- **Immutable audit history.** Audit records will be append-only and hash-chained; external checkpoints are planned to detect privileged tampering.
- **Secrets never touch source control.** Only `.env.example` templates with placeholders are committed.
- **Fail closed.** Production authentication settings reject missing secrets, insecure cookies, and wildcard CORS.
- **Restricted CORS.** Production CORS allows only configured origins; credentials are never combined with a wildcard.

See [THREATS.md](THREATS.md) for the full threat model.

## Current Limitations

- No document upload, download, search, storage integration, or permission endpoints.
- No audit writing, hash chain, or administrator activity views.
- RLS is not enabled; the backend uses a single privileged database role.
- The `0002` migration has not been applied to Supabase, and no deployment has been verified.
- Authentication rate limiting is in-memory and per process; a multi-instance deployment needs a shared store.
- There is no MFA, account-lockout policy, or idle-timeout mechanism.
- Cross-site refresh cookies require Secure/SameSite=None and may be affected by browser third-party cookie policies; this is untested in production.
- Auth CSRF protection is origin-based; a per-session CSRF token is not implemented.
- The backend health check is process-only.
- No production CSP or HSTS configuration yet (planned for Phase 10).

## Project Status

| Phase | Status |
|-------|--------|
| 0 — Requirements and Repository Foundation | Complete |
| 1 — Project Scaffold and Early Deployment | Complete — awaiting review |
| 2 — Database Schema and Migrations | Complete — awaiting review |
| 3 — Authentication and Roles | Complete — awaiting review |
| 4 — Private Storage and Validated Uploads | Not started (next) |
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

Never commit credentials, database passwords, service-role keys, access tokens, JWT secrets, or private keys. If a secret is exposed, treat it as compromised and rotate it immediately.
