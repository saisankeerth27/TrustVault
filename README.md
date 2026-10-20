# TrustVault

TrustVault is a secure, multi-tenant document vault that will let organizations store, organize, share, and audit access to sensitive documents. The design enforces named-user, per-document READ and EDIT permissions in the backend, records significant actions in a tamper-evident audit trail, and gives administrators visibility into document activity.

> **Status: Phase 5 — Document management and search implemented and verified locally (awaiting review).**
> Phases 0–5 are implemented: documentation, the frontend/backend scaffold, the verified PostgreSQL schema, database-backed authentication and roles, a private validated upload pipeline, and an authenticated document library with search, filters, pagination, metadata review/editing, proxied downloads, and soft deletion. Storage behavior is tested with a mocked Wasabi adapter; **live Wasabi bucket connectivity, download, and object-deletion behavior were not verified** because no storage credentials were supplied. Per-document permissions and audit writing are **not** implemented yet. There is no live deployment, and migrations have **not** been applied to the Supabase project.

## Project Objective

Provide a document management system where authorization is guaranteed by the backend, not by hiding frontend controls. Document owners will decide exactly who can read or edit each document; viewers will see only what is shared with them; administrators will oversee activity and audit history.

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React, JavaScript/JSX, Vite, Tailwind CSS, shadcn/ui |
| Routing | React Router |
| HTTP client | Axios |
| Forms / validation | React Hook Form, Zod |
| Backend | Python, FastAPI |
| Database | Supabase PostgreSQL |
| ORM / migrations | SQLAlchemy 2.x (psycopg 3), Alembic |
| Authentication | bcrypt, PyJWT (HS256), rotating refresh tokens |
| Object storage | Wasabi private S3-compatible storage (`boto3`) |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| Testing | pytest, FastAPI TestClient, embedded-postgres, oxlint, Vite build |

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
│   │   ├── api/            # Health, auth, and document API routers
│   │   ├── core/           # Settings, security, rate limiting, logging, errors
│   │   ├── db/             # Base, URL helpers, engine/session management
│   │   ├── models/         # SQLAlchemy models and enums
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # Auth, validation, storage, document lifecycle
│   │   └── main.py         # FastAPI application factory
│   ├── scripts/            # Account provisioning and storage connectivity CLIs
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
│   │   ├── components/     # Layout, guards, upload panel, and UI primitives
│   │   ├── lib/            # Shared utilities, roles, and document formatting
│   │   ├── pages/          # Login, dashboard, library, details, admin, not found
│   │   └── services/       # Axios client, auth, and document API functions
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

Use the generated value for `JWT_SECRET` in `backend/.env`. Configure `DATABASE_URL` with the direct connection for migrations and fill the Wasabi settings in `backend/.env`:

```env
WASABI_ENDPOINT_URL=https://s3.us-east-1.wasabisys.com
WASABI_REGION=us-east-1
WASABI_BUCKET_NAME=your-private-bucket
WASABI_ACCESS_KEY_ID=your-access-key
WASABI_SECRET_ACCESS_KEY=your-secret-key
MAX_UPLOAD_SIZE_BYTES=10485760
ALLOWED_UPLOAD_EXTENSIONS=pdf,txt,docx,png,jpg,jpeg
```

Apply migrations:

```powershell
alembic upgrade head
```

Check the bucket connection without printing credentials. The check requires bucket-level `HeadBucket`/list permission:

```powershell
python -m scripts.check_storage
```

Start the API:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health endpoint: <http://127.0.0.1:8000/health>
- OpenAPI documentation: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

The health endpoint reports **process health only**. It does not check the database or object storage; use `python -m scripts.check_storage` for a server-side Wasabi connectivity check.

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
| `/documents` | Searchable document library with filters, pagination, and upload for Owner/Admin | Any signed-in user; results are authorization-scoped |
| `/documents/:documentId` | Metadata details, owner-only download/edit/delete, admin metadata review | Any signed-in user with metadata visibility |
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

## Document Management and Downloads

Phase 5 implements the authenticated document library:

- `GET /api/v1/documents` accepts `q`, `category`, `owner_id`, `created_from`, `created_to`, `page`, `page_size`, `sort_by`, and `order`. Search is name-based, category filtering is case-insensitive, date filters are inclusive UTC calendar days, and pagination is bounded to 100 items.
- `DOCUMENT_OWNER` accounts see only their own active documents. Administrators can discover and review metadata for all active documents, but download, edit, and delete remain owner-only. Viewers have no document access until Phase 6.
- `GET /api/v1/documents/{id}` returns safe metadata only; inaccessible and missing IDs return the same generic 404.
- `PATCH /api/v1/documents/{id}` permits only `name`, `category`, and `description`. Protected fields such as `owner_id`, `storage_key`, `mime_type`, and `checksum` are rejected.
- `GET /api/v1/documents/{id}/download` streams the private object through the backend. It authorizes the owner, sets an attachment filename, `Content-Length`, `Cache-Control: private, no-store`, and `X-Content-Type-Options: nosniff`; it never returns a storage key or presigned URL.
- `DELETE /api/v1/documents/{id}` marks `deleted_at` and removes the row from normal reads, then attempts to delete the Wasabi object. Metadata is retained for audit/history. Object cleanup is best-effort because it occurs after the database commit.
- Upload remains `POST /api/v1/documents/upload` for active Owners and Administrators, with backend-decided ownership, generated keys, validated content, and a server-computed SHA-256 checksum.
- No permission-grant endpoints and no audit-event writes exist yet. Successful download/update/delete requests are logged operationally, not written to `audit_events`.

The frontend provides a searchable/filterable library, pagination, an upload panel, and a details page with owner-only download/edit/delete actions. Administrator metadata review is read-only.

Storage behavior is verified with a mocked adapter. **Live Wasabi bucket policy, connectivity, download, and object deletion were not verified** because no credentials were supplied. The bucket must remain private.

## Database

The schema has five tables — `users`, `refresh_tokens`, `documents`, `document_permissions`, and `audit_events` — with UUID primary keys, enforced checks, foreign keys, partial unique indexes, and a `pg_trgm` index for document name search. Phase 5 writes metadata updates and the `deleted_at` soft-delete marker but adds no migration. Highlighted decisions:

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
| `WASABI_ENDPOINT_URL` | HTTPS endpoint for the bucket's Wasabi region | Yes for uploads |
| `WASABI_REGION` | Bucket region | Yes for uploads |
| `WASABI_BUCKET_NAME` | Private bucket name | Yes for uploads |
| `WASABI_ACCESS_KEY_ID` | Server-side Wasabi access key ID | Yes for uploads |
| `WASABI_SECRET_ACCESS_KEY` | Server-side Wasabi secret access key | Yes for uploads |
| `MAX_UPLOAD_SIZE_BYTES` | Upload limit, 1–104,857,600 bytes | No (default `10485760`) |
| `ALLOWED_UPLOAD_EXTENSIONS` | Comma-separated extension allow-list | No (default `pdf,txt,docx,png,jpg,jpeg`) |

`CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173`. A wildcard is rejected outside `development`. Wasabi credentials are server-side only and must never be placed in `VITE_*` variables.

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

The suite currently has **127 tests**. It verifies:

- Application metadata, health endpoint behavior, JSON error envelopes, and CORS.
- Database URL normalization and Supabase pooler/SSL detection.
- Models, tables, columns, indexes, and constraints for all five tables.
- Migration `0001` plus `0002`: `upgrade head`, `alembic check` for drift, `downgrade base`, and re-`upgrade`.
- Registration, login, refresh rotation, reuse detection, logout, and current-user behavior.
- Expired, tampered, wrong-issuer/audience/type, disabled-account, and revoked-session rejection.
- Role authorization helpers and fail-closed unknown-role handling.
- Login/registration rate limiting and `Retry-After` behavior.
- Production authentication configuration validators.
- Auth logging that does not include passwords, tokens, or email addresses.
- Upload validation for supported file types, MIME/signature mismatches, unsafe filenames, empty files, and oversized requests.
- Owner/Admin upload success with server-decided ownership, generated storage keys, computed SHA-256 checksums, and persisted metadata.
- Viewer and anonymous denial, storage failure mapping, database-failure object cleanup, and secret-safe errors/logs.
- Wasabi configuration validators and safe storage error mapping without live network access.
- Document list authorization/scoping, name search with literal wildcard escaping, category/owner/date filters, sorting, pagination boundaries, and invalid query parameters.
- Owner/admin/viewer metadata visibility, owner-only updates, protected-field rejection, and generic 404 IDOR behavior.
- Streamed download headers, UTF-8/header-injection-safe attachment names, storage-not-found/storage-failure mapping, and owner-only access.
- Soft deletion, list/detail exclusion, retained metadata, mocked object cleanup, cleanup-failure logging, and repeat/other-user delete denial.

Database tests start an **embedded PostgreSQL** instance in a temporary directory and never contact Supabase or read `DATABASE_URL`. Storage tests use a fake adapter; no test contacts Wasabi.

### Frontend

```powershell
cd frontend
npm run lint
npm run build
```

Both commands pass. The frontend is JavaScript/JSX only, and `npm run build` runs the Vite production build.

## API Baseline

- **Health:** `GET /health` → `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`
- **Register:** `POST /api/v1/auth/register` → creates a Viewer and returns an access token
- **Login:** `POST /api/v1/auth/login` → returns an access token and sets the refresh cookie
- **Refresh:** `POST /api/v1/auth/refresh` → rotates the refresh session and returns a new access token
- **Logout:** `POST /api/v1/auth/logout` → revokes the current refresh session and returns 204
- **Current user:** `GET /api/v1/auth/me` → returns the authenticated user
- **Upload:** `POST /api/v1/documents/upload` → validates and stores a document for an Owner/Admin and returns safe metadata (no storage key)
- **List/search:** `GET /api/v1/documents` → scoped, filtered, sorted, paginated metadata (`items`, `total`, `page`, `page_size`, `pages`, `has_next`, `has_previous`)
- **Details:** `GET /api/v1/documents/{id}` → safe metadata for the owner or an administrator
- **Update:** `PATCH /api/v1/documents/{id}` → owner-only updates to `name`, `category`, and `description`
- **Download:** `GET /api/v1/documents/{id}/download` → owner-only private object stream
- **Delete:** `DELETE /api/v1/documents/{id}` → owner-only soft deletion and best-effort object cleanup; returns 204
- **Errors:** JSON envelope `{"error":{"code":"...","message":"...","details":"..."}}` where applicable.
- **CORS:** Loaded from `CORS_ALLOWED_ORIGINS`; production wildcards are rejected.
- **OpenAPI:** Enabled at `/docs` and `/openapi.json`.

No permission-management or audit endpoints exist yet.

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
- Environment: `APP_ENV=production`, `LOG_LEVEL=INFO`, `DATABASE_URL`, `JWT_SECRET`, a real `CORS_ALLOWED_ORIGINS`, the auth cookie/rate-limit settings, and the Wasabi/upload settings in `render.yaml`. Render supplies `PORT`.
- Storage variables are marked `sync: false` in `render.yaml`; set them in the Render dashboard as secrets. Keep the bucket private and grant only the operations the API needs (`PutObject`, `GetObject`, `HeadBucket`, `DeleteObject`; listing only if you use the connectivity check).
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

- Live Wasabi connectivity and bucket policy have not been verified; upload/download/delete tests use a mocked adapter.
- Per-document READ/EDIT permissions, sharing, and revocation are not implemented; viewers currently see no documents.
- Uploads are not virus-scanned; validation covers type/signature/size/structure only.
- Upload-to-database consistency is compensating, not transactional: a failed metadata commit triggers best-effort object deletion, which could itself fail.
- Soft deletion excludes metadata from normal reads but object cleanup occurs after commit; a cleanup failure can leave a private orphan object for later reconciliation.
- No audit writing, hash chain, or administrator activity views; document management actions are not yet recorded in `audit_events`.
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
| 1 — Project Scaffold and Early Deployment | Partial — local scaffold complete; live deployment deferred to Phase 10 |
| 2 — Database Schema and Migrations | Complete — awaiting review |
| 3 — Authentication and Roles | Complete — awaiting review |
| 4 — Private Storage and Validated Uploads | Complete — awaiting review |
| 5 — Document Management and Search | Complete — awaiting review |
| 6 — Document Permissions and Revocation | Not started (next) |
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
