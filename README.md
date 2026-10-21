# TrustVault

TrustVault is a secure, multi-tenant document vault that lets organizations store, organize, share, and audit access to sensitive documents. The design enforces named-user, per-document READ and EDIT permissions in the backend, records significant actions in a tamper-evident audit trail, and gives administrators visibility into document activity.

> **Status: Phase 8 — Security tests and threat-model verification implemented and verified locally (awaiting review).**
> Phases 0–8 are implemented: documentation, the frontend/backend scaffold, the verified PostgreSQL schema, database-backed authentication and roles, a private validated upload pipeline, an authenticated document library, owner-managed READ/EDIT sharing with immediate revocation, and an append-only hash-chained audit trail with a signed checkpoint and administrator audit dashboard. Phase 8 adds a 40-case threat-mapped security suite covering cross-user denial, privilege escalation, audit mutation attempts, upload attacks, token abuse, and rate limits. Storage behavior is tested with a mocked Wasabi adapter; **live Wasabi bucket connectivity, download, and object-deletion behavior were not verified** because no storage credentials were supplied. There is no live deployment, and migrations have **not** been applied to the Supabase project.

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
│   │   │   ├── 0002_add_refresh_tokens.py
│   │   │   └── 0003_add_audit_chain_index.py
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── app/
│   │   ├── api/            # Health, auth, document, and administrator audit routers
│   │   ├── core/           # Settings, security, request context, rate limiting, logging, errors
│   │   ├── db/             # Base, URL helpers, engine/session management
│   │   ├── models/         # SQLAlchemy models and enums
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # Auth, validation, storage, documents, permissions, audit
│   │   └── main.py         # FastAPI application factory
│   ├── scripts/            # Account, storage connectivity, and audit integrity CLIs
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
│   │   ├── components/     # Layout, guards, upload, access badge, and UI primitives
│   │   ├── lib/            # Shared utilities, roles, access levels, audit labels, formatting
│   │   ├── pages/          # Login, dashboard, library, shared, details, permissions, audit, admin
│   │   └── services/       # Axios client plus auth, document, permission, and audit API functions
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

To enable signed external audit checkpoints, also configure both checkpoint settings in `backend/.env`; either both or neither must be set:

```env
AUDIT_CHECKPOINT_SIGNING_KEY=generate-a-random-secret-of-at-least-32-characters
AUDIT_CHECKPOINT_PATH=C:/TrustVault/checkpoints/audit-checkpoint.json
```

The path must be absolute. This same-host file is a tamper-detection control, not an independent immutable store. Apply migrations:

```powershell
alembic upgrade head
```

Check the bucket connection without printing credentials. The check requires bucket-level `HeadBucket`/list permission:

```powershell
python -m scripts.check_storage
```

Verify the audit hash chain, or write a signed checkpoint after the chain verifies:

```powershell
python -m scripts.audit_integrity
python -m scripts.audit_integrity --create-checkpoint
```

The command exits `0` for a verified chain or successfully written checkpoint, `1` when attention is required, and `2` for configuration errors. It never prints the signing key.

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
| `/documents` | Searchable document library with filters, pagination, and upload for Owner/Admin | Any signed-in user; includes owned and directly shared documents |
| `/shared-with-me` | Documents with an active READ/EDIT grant for the signed-in user | Any signed-in user |
| `/documents/:documentId` | Access-aware metadata details and download/edit/delete/manage actions | Any signed-in user with metadata visibility |
| `/documents/:documentId/permissions` | Owner-only grant, level update, revocation, and grant history | Document owner only |
| `/admin/audit` | Audit event search/filter/pagination and integrity verification | `ADMINISTRATOR` only |
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

## Document Management, Permissions, and Downloads

Phases 5–6 implement the authenticated document library and named-user sharing:

- `GET /api/v1/documents` accepts `q`, `category`, `owner_id`, `created_from`, `created_to`, `page`, `page_size`, `sort_by`, and `order`. Search is name-based, category filtering is case-insensitive, date filters are inclusive UTC calendar days, and pagination is bounded to 100 items.
- Owners can list/read their active documents. Viewers and other owners also see documents with an active grant. Administrators can discover and review metadata for all active documents, but content access still requires an explicit grant.
- `GET /api/v1/documents/shared-with-me` returns only active non-deleted documents with an active grant for the caller, with bounded pagination and allow-listed sorting. Responses use `Cache-Control: no-store`.
- `GET /api/v1/documents/{id}` returns safe metadata plus the caller's `access_level`: `OWNER`, `EDIT`, `READ`, or `ADMINISTRATOR`. Inaccessible and missing IDs return the same generic 404.
- `PATCH /api/v1/documents/{id}` permits only `name`, `category`, and `description`. Owners and EDIT recipients may update; READ recipients and metadata-only administrators receive 403. Protected fields are rejected.
- `GET /api/v1/documents/{id}/download` streams the private object through the backend for owners, READ recipients, and EDIT recipients. It sets a safe attachment filename, `Content-Length`, `Cache-Control: private, no-store`, and `X-Content-Type-Options: nosniff`; it never returns a storage key or presigned URL.
- `DELETE /api/v1/documents/{id}` is owner-only. It marks `deleted_at`, removes the document from normal reads, then attempts best-effort Wasabi cleanup. Metadata is retained for history.
- Upload remains `POST /api/v1/documents/upload` for active Owners and Administrators, with backend-decided ownership, generated keys, validated content, and a server-computed SHA-256 checksum.
- Owners manage sharing with `GET/POST /api/v1/documents/{id}/permissions` and `PATCH/DELETE /api/v1/documents/{id}/permissions/{permission_id}`. Grants target an active registered account by normalized email and accept only `READ` or `EDIT`.
- A same-level grant is idempotent (`200`); a different active level returns `409`. Level changes revoke the existing row and insert a replacement, retaining history. Revocation is idempotent (`204`) and takes effect on the recipient's next request.
- Permission management is owner-only. Administrators do not gain owner or sharing powers. Permission lists include active and revoked rows, with `total` and `active_total`.
- Successful document, permission, registration, login, and logout actions append audit events in the same database transaction as the protected change. Denials are recorded best-effort so an audit failure cannot turn an authorization denial into a success.

The frontend provides a searchable/filterable library, a "Shared with me" view, access-level badges, an upload panel, an access-aware details page, and an owner-only sharing page with grant, level update, revoke confirmation, and history. Administrator metadata review remains read-only.

Storage behavior is verified with a mocked adapter. **Live Wasabi bucket policy, connectivity, download, and object deletion were not verified** because no credentials were supplied. The bucket must remain private.

## Audit Trail and Integrity

- The audit writer records authentication, upload, metadata update, download, delete, permission grant/update/revoke, and their denial outcomes. Read-only audit views and integrity checks are not themselves audited.
- Events are appended under a PostgreSQL advisory transaction lock with a contiguous `chain_index`, `previous_hash`, and SHA-256 `event_hash`. The hashed payload is canonical JSON with a versioned schema and UTC microsecond timestamps.
- State-changing success events share the protected business transaction: an audit write failure rolls back the change and returns a generic error. Denial events use a best-effort commit and never block the intended 403/404 response.
- Details are sanitized. Passwords, tokens, cookies, authorization headers, document content, session IDs, and other sensitive keys are rejected; request ID, direct socket client IP, and a length-limited user-agent are attached automatically when available.
- `GET /api/v1/admin/audit-events` supports filtering by actor ID, document ID, action, outcome, and inclusive UTC date range, with newest-first pagination. `GET /api/v1/admin/audit-integrity` verifies both the chain and the signed checkpoint.
- Both audit endpoints are global-administrator-only. There is no owner-scoped audit view or audit mutation endpoint in Phase 7.
- The signed checkpoint binds the current chain head with HMAC-SHA256 and is written atomically by `python -m scripts.audit_integrity --create-checkpoint`. It detects database tampering only relative to the last trusted checkpoint; it does not prevent a privileged attacker from deleting both the database changes and the same-host checkpoint file.
- The audit dashboard at `/admin/audit` provides filters, event detail expansion, pagination, and an integrity panel showing `VERIFIED`, stale/missing checkpoint, or invalid-chain states.

## Database

The schema has five tables — `users`, `refresh_tokens`, `documents`, `document_permissions`, and `audit_events` — with UUID primary keys, enforced checks, foreign keys, partial unique indexes, and a `pg_trgm` index for document name search. Phase 7 adds migration `0003` for the audit chain sequence. Highlighted decisions:

- Roles and statuses are constrained strings; no native PostgreSQL enums.
- Emails are stored lowercased and uniquely constrained.
- Refresh tokens are stored only as SHA-256 hashes, grouped by session family, with expiry and revocation timestamps.
- Document permissions keep a full grant/revoke history with a partial unique index allowing only one active grant per user/document pair.
- Audit events reference users and documents with `ON DELETE SET NULL` so history survives deletion.
- Audit events use a positive, unique `chain_index` populated in migration `0003`; the application appends the hash chain and does not expose update/delete endpoints.
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
| `AUDIT_CHECKPOINT_SIGNING_KEY` | HMAC key for signed audit checkpoints; at least 32 characters, set with the path | No (both checkpoint settings optional) |
| `AUDIT_CHECKPOINT_PATH` | Absolute path for the signed checkpoint file; configure both or neither | No (both checkpoint settings optional) |
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

The suite currently has **198 tests**, including **40 threat-mapped security cases** in `backend/tests/test_security.py`. It verifies:

- Application metadata, health endpoint behavior, JSON error envelopes, and CORS.
- Database URL normalization and Supabase pooler/SSL detection.
- Models, tables, columns, indexes, and constraints for all five tables.
- Migrations `0001`–`0003`: `upgrade head`, `alembic check` for drift, `downgrade base`, and re-`upgrade`.
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
- Owner/admin/viewer metadata visibility, owner/EDIT updates, READ/administrator denial, protected-field rejection, and generic 404 IDOR behavior.
- Streamed download headers, UTF-8/header-injection-safe attachment names, storage-not-found/storage-failure mapping, and READ/EDIT/owner access rules.
- Soft deletion, list/detail exclusion, retained metadata, mocked object cleanup, cleanup-failure logging, and repeat/other-user delete denial.
- Owner-only permission grant/list/update/revoke, idempotent same-level grants, conflict handling, active/revoked history, retained revocation rows, and revoke-and-regrant behavior.
- Active excluded (disabled/missing) recipients, endpoint-forged identity rejection, owner self-grant conflict, and authenticated but unauthorized document manipulation.
- Shared-with-me filtering of revoked and soft-deleted documents, pagination/sorting, immediate post-revocation denial, access-level reporting, and metadata-only administrator behavior.
- Audit events for registration, login success/failure, logout, uploads, metadata updates, downloads, deletes, permission changes, and denied operations.
- Administrator-only audit query access, filters, pagination, generic denial behavior, request-ID normalization, metadata/request-context sanitization, and denied audit access.
- Hash-chain verification, middle-event tampering/removal detection, signed-checkpoint success/staleness/truncation/signature failure, and mandatory-audit-write rollback behavior.
- Threat-model verification for IDOR, cross-user GET/download/edit/delete denial, grant/revoke audit coverage, forged role claims, administrator content boundaries, malicious uploads, path manipulation, audit API mutation attempts, metadata leakage, secret-safe failures, expired/tampered tokens, logout invalidation, brute-force limits, and oversized uploads.

Database tests start an **embedded PostgreSQL** instance in a temporary directory and never contact Supabase or read `DATABASE_URL`. Storage tests use a fake adapter; no test contacts Wasabi.

Coverage is generated separately from test success:

```powershell
pytest --cov=app --cov-report=term-missing
```

The verified local full-suite run passed **198 tests** with **89% coverage** across 2,130 statements and 410 branches. Authorization and document services are exercised at 77%–88%, the administrator audit API at 96%, and `app/api/deps.py`, `app/main.py`, and the error/schema modules at 100%. Coverage is a diagnostic, not proof of security.

The GitHub Actions workflow `.github/workflows/backend-tests.yml` runs the full backend suite with coverage on pushes and pull requests that change `backend/**`. Remote CI execution is not verified until the workflow runs on GitHub.

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
- **Details:** `GET /api/v1/documents/{id}` → safe metadata plus the caller's `access_level`
- **Shared with me:** `GET /api/v1/documents/shared-with-me` → active documents explicitly shared with the caller
- **Update:** `PATCH /api/v1/documents/{id}` → updates to `name`, `category`, and `description` for owners and EDIT recipients
- **Download:** `GET /api/v1/documents/{id}/download` → private object stream for owners, READ recipients, and EDIT recipients
- **Delete:** `DELETE /api/v1/documents/{id}` → owner-only soft deletion and best-effort object cleanup; returns 204
- **List permissions:** `GET /api/v1/documents/{id}/permissions` → owner-only active and revoked grant history
- **Grant permission:** `POST /api/v1/documents/{id}/permissions` → owner-only `READ`/`EDIT` grant; returns 201, or 200 for an idempotent same-level grant
- **Update permission:** `PATCH /api/v1/documents/{id}/permissions/{permission_id}` → revoke-and-regrant level change with retained history
- **Revoke permission:** `DELETE /api/v1/documents/{id}/permissions/{permission_id}` → idempotent immediate revocation; returns 204
- **List audit events:** `GET /api/v1/admin/audit-events` → administrator-only filtered/paginated audit history
- **Audit integrity:** `GET /api/v1/admin/audit-integrity` → administrator-only hash-chain and signed-checkpoint status
- **Errors:** JSON envelope `{"error":{"code":"...","message":"...","details":"..."}}` where applicable.
- **CORS:** Loaded from `CORS_ALLOWED_ORIGINS`; production wildcards are rejected.
- **OpenAPI:** Enabled at `/docs` and `/openapi.json`.

There are no audit mutation endpoints.

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
- Environment: `APP_ENV=production`, `LOG_LEVEL=INFO`, `DATABASE_URL`, `JWT_SECRET`, a real `CORS_ALLOWED_ORIGINS`, the auth cookie/rate-limit settings, the Wasabi/upload settings, and optional `AUDIT_CHECKPOINT_SIGNING_KEY`/`AUDIT_CHECKPOINT_PATH` in `render.yaml`. Render supplies `PORT`.
- The checkpoint path must be on persistent, access-controlled storage. A Render ephemeral filesystem is not suitable for durable checkpoint retention; use a persistent volume or external checkpoint store and run the CLI after deployment changes.
- Storage variables are marked `sync: false` in `render.yaml`; set them in the Render dashboard as secrets. Keep the bucket private and grant only the operations the API needs (`PutObject`, `GetObject`, `HeadBucket`, `DeleteObject`; listing only if you use the connectivity check).
- Migrations are **not** run automatically. Run `alembic upgrade head` from a trusted shell with the production `DATABASE_URL` before or after deploying schema changes.

`render.yaml` configures `AUTH_COOKIE_SECURE=true` and `AUTH_COOKIE_SAMESITE=none` for cross-site Vercel → Render cookies. This configuration has **not** been deployed. Third-party cookie blocking, custom-domain requirements, and a shared rate limiter must be evaluated during deployment hardening.

Deployment requires access to the Vercel, Render, and Supabase accounts and has not been authorized or attempted.

## Security Principles

- **Backend is authoritative.** Hiding a UI control is not authorization; every request is verified server-side.
- **Deny by default.** Access requires explicit ownership, role, or permission grant.
- **Defense in depth.** Application checks, Supabase RLS (planned), private storage, and append-only hash-chained audit events layer together.
- **Tamper evidence.** Audit records are append-only through the application, hash-chained, and compared with an HMAC-signed checkpoint. An independent immutable checkpoint store is still required to fully address a privileged same-host attacker.
- **Secrets never touch source control.** Only `.env.example` templates with placeholders are committed.
- **Fail closed.** Production authentication settings reject missing secrets, insecure cookies, and wildcard CORS.
- **Restricted CORS.** Production CORS allows only configured origins; credentials are never combined with a wildcard.

See [THREATS.md](THREATS.md) for the full threat model.

## Current Limitations

- Live Wasabi connectivity and bucket policy have not been verified; upload/download/delete tests use a mocked adapter.
- Audit history is append-only at the application layer, but database roles are not restricted from direct UPDATE/DELETE. The hash chain and signed checkpoint detect modifications only relative to a trusted checkpoint; the checkpoint is a same-host file, not an independent immutable store.
- The audit checkpoint is not written automatically on a schedule. Operators must run `python -m scripts.audit_integrity --create-checkpoint` and retain the signed file outside the application database.
- Audit exports (CSV/JSON download) and owner-scoped audit views are not implemented; audit query access is global-administrator-only.
- Client IP metadata uses the direct ASGI socket address, not a trusted `X-Forwarded-For` chain, so a reverse proxy may record the proxy address. Forwarded-header trust must be configured deliberately at deployment.
- Uploads are not virus-scanned; validation covers type/signature/size/structure only.
- Upload-to-database consistency is compensating, not transactional: a failed metadata commit triggers best-effort object deletion, which could itself fail.
- Soft deletion excludes metadata from normal reads but object cleanup occurs after commit; a cleanup failure can leave a private orphan object for later reconciliation.
- RLS is not enabled; the backend uses a single privileged database role.
- Migrations through `0003` have not been applied to Supabase, and no deployment has been verified.
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
| 2 — Database Schema and Migrations | Complete |
| 3 — Authentication and Roles | Complete |
| 4 — Private Storage and Validated Uploads | Complete |
| 5 — Document Management and Search | Complete |
| 6 — Document Permissions and Revocation | Complete |
| 7 — Audit Trail and Administrator Activity | Complete |
| 8 — Security Tests and Threat-Model Verification | Complete — awaiting review |
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
