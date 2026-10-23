# TrustVault

TrustVault is a secure, multi-tenant document vault that lets organizations store, organize, share, and audit access to sensitive documents. The design enforces named-user, per-document READ and EDIT permissions in the backend, records significant actions in a tamper-evident audit trail, and gives administrators visibility into document activity.

> **Status: Phase 11 — History Pagination, Safe Version Rollback, and Stale-Editor Protection Implemented.**
> All 269 backend tests and 23 frontend tests pass with Vite production build verified. The implementation adds:
> - **Secure PDF Preview**: Client-side rendering via Mozilla PDF.js (`pdfjs-dist`) with Vite web worker bundling. Documents are streamed through authenticated FastAPI endpoints with `Cache-Control: private, no-store` without exposing private object URLs or service secrets.
> - **In-Browser PDF Editing**: Authorized EDIT recipients can annotate PDFs with sticky text notes, typewriter free text, area highlights, and typed signatures. Annotations are embedded directly into the PDF binary via `pdf-lib` and saved as a new version with optimistic concurrency (`expected_version_number`).
> - **Owner-Only Version Deletion and Safe Rollback**: Owners can delete any version while at least one remains (`DELETE /api/v1/documents/{id}/versions/{version_number}`). Deleting the current version rolls the document back to the highest remaining version, updates the active storage pointer, cleans up private storage, and records rollback audit details; deleting the last version returns HTTP 400. A persistent version sequence prevents deleted numbers from being reused.
> - **Paginated History and Stale-Editor Protection**: Version history and owner activity are server-paginated five at a time, with owner routine preview/download events excluded from the activity timeline. Text and PDF editors become read-only after a 409 conflict and require close/reopen, preventing a refreshed-but-stale editor from overwriting a newer revision.
> - **Document Activity & Audit Integrity**: Document owners can inspect their document's paginated activity timeline (`GET /api/v1/documents/{id}/activity`), while administrators verify tamper-evident hash chains (`hash_schema: trustvault-audit-event-v1`) and signed HMAC-SHA256 checkpoints.

## Project Objective

Provide a document management system where authorization is guaranteed by the backend, not by hiding frontend controls. Every normal user owns the documents they upload and decides exactly who else can read or edit each document. Administrators manage accounts, oversee document metadata and audit history, and do not automatically receive access to private file content.

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React, JavaScript/JSX, Vite, Tailwind CSS, shadcn/ui |
| PDF Rendering & Editing | Mozilla PDF.js (`pdfjs-dist`), `pdf-lib` |
| Routing | React Router |
| HTTP client | Axios |
| Forms / validation | React Hook Form, Zod |
| Backend | Python, FastAPI |
| Database | Supabase PostgreSQL |
| ORM / migrations | SQLAlchemy 2.x (psycopg 3), Alembic |
| Authentication | bcrypt, PyJWT (HS256), rotating refresh tokens |
| Object storage | Supabase Storage private bucket (`httpx`) |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| Testing | pytest, FastAPI TestClient, embedded-postgres, oxlint, Vitest, Vite build |

## Repository Structure

```text
TrustVault/
├── backend/
│   ├── alembic/
│   │   ├── versions/
│   │   │   ├── 0001_initial_schema.py
│   │   │   ├── 0002_add_refresh_tokens.py
│   │   │   ├── 0003_add_audit_chain_index.py
│   │   │   ├── 0004_user_roles_and_login_tracking.py
│   │   │   └── 0005_document_versions.py
    0006_audit_hash_schema.py
    0007_version_sequence.py
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── app/
│   │   ├── api/            # Health, auth, document, and administrator routers
│   │   ├── core/           # Settings, security, request context, rate limiting, logging, errors
│   │   ├── db/             # Base, URL helpers, engine/session management
│   │   ├── models/         # SQLAlchemy models and enums
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # Auth, validation, storage, documents, permissions, admin, audit
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

Set `DATABASE_URL` to your Supabase connection string and generate a real `JWT_SECRET`. The direct database host (port 5432) is IPv6-only on some networks; if it is unreachable, use the **session pooler** on port 5432 with username `postgres.YOUR_PROJECT_REF`:

```env
DATABASE_URL=postgresql://postgres.YOUR_PROJECT_REF:YOUR_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
```


```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use the generated value for `JWT_SECRET` in `backend/.env`. Configure `DATABASE_URL` and a private Supabase Storage bucket in `backend/.env`:

```env
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_STORAGE_BUCKET=trustvault-documents
SUPABASE_SERVICE_ROLE_KEY=your-server-side-secret-key
MAX_UPLOAD_SIZE_BYTES=10485760
ALLOWED_UPLOAD_EXTENSIONS=pdf,txt,docx,png,jpg,jpeg
```

Create the bucket in **Supabase Dashboard → Storage** and keep it private. Use a server-side secret/service-role key, never a `VITE_*` variable.

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

The health endpoint reports **process health only**. It does not check the database or object storage; use `python -m scripts.check_storage` for a server-side Supabase Storage connectivity and private-bucket check.

### 3. Provision an account

Public registration creates a normal **User** account. Create administrator accounts explicitly from `backend/`:

```powershell
python -m scripts.create_user --email admin@example.com --name "Admin User" --role ADMINISTRATOR
```

The script prompts for a password with `getpass`, or reads `TRUSTVAULT_USER_PASSWORD` if set. It never prints the password or hash. Administrator accounts must be provisioned this way; clients cannot request a role.

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
| `/login` | Login form and session bootstrap | Public |
| `/register` | User account registration with validation and automatic sign-in | Public |
| `/dashboard` | Live document, owned, and shared counts with recent permitted documents | Any signed-in user |
| `/documents` | Searchable document library with name/category/owner/date filters, sorting, and pagination | Any signed-in user; includes owned and directly shared documents |
| `/upload` | Dedicated validated upload page with progress feedback | Any signed-in active user |
| `/shared-with-me` | Documents with an active READ/EDIT grant for the signed-in user | Any signed-in user |
| `/documents/:documentId` | Access-aware metadata details and download/edit/delete/manage actions | Any signed-in user with metadata visibility |
| `/documents/:documentId/permissions` | Owner-only grant, level update, revocation, and grant history | Document owner only |
| `/admin/audit` | Audit event search/filter/pagination and integrity verification | `ADMINISTRATOR` only |
| `/admin` | Administrator account, summary, and document-metadata oversight | `ADMINISTRATOR` only |
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
- **RBAC:** `ADMINISTRATOR` and `USER`; document-level `OWNER`/`READ`/`EDIT` capabilities are contextual, and authorization reads the current database role rather than trusting a token claim.
- **CSRF mitigation:** Origin allow-list checks on auth POSTs, no wildcard CORS with credentials, and cookie scoping. This is an origin-based control, not a per-session CSRF token.
- **Rate limiting:** process-local sliding window, default 10 attempts per 60 seconds, keyed by client IP plus normalized email for login and by IP for registration. Multi-instance production deployments need a shared limiter.

Public registration always creates a `USER`. Use the CLI for `ADMINISTRATOR` accounts. Disabling an account or changing its role revokes its active refresh sessions immediately; successful logins record `last_login_at`.

## Document Management, Permissions, and Downloads

Phases 5–6 implement the authenticated document library and named-user sharing:

- `GET /api/v1/documents` accepts `q`, `category`, `owner_id`, `created_from`, `created_to`, `page`, `page_size`, `sort_by`, and `order`. Search is name-based, category filtering is case-insensitive, date filters are inclusive UTC calendar days, and pagination is bounded to 100 items.
- Users can list/read documents they own and documents shared with them by an active grant. Administrators can discover and review metadata for all active documents, but content access still requires ownership or an explicit grant.
- `GET /api/v1/documents/shared-with-me` returns only active non-deleted documents with an active grant for the caller, with bounded pagination and allow-listed sorting. Responses use `Cache-Control: no-store`.
- `GET /api/v1/documents/{id}` returns safe metadata plus the caller's `access_level`: `OWNER`, `EDIT`, `READ`, or `ADMINISTRATOR`. Inaccessible and missing IDs return the same generic 404.
- `PATCH /api/v1/documents/{id}` permits only `name`, `category`, and `description`. Owners and EDIT recipients may update; READ recipients and metadata-only administrators receive 403. Protected fields are rejected.
- `GET /api/v1/documents/{id}/download` streams the current private object through the backend for owners, READ recipients, and EDIT recipients. It sets a safe attachment filename, `Content-Length`, `Cache-Control: private, no-store`, and `X-Content-Type-Options: nosniff`; it never returns a storage key or presigned URL.
- `GET /api/v1/documents/{id}/preview` streams the current object inline for owners, READ recipients, and EDIT recipients with `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`. Administrators without a grant receive 403.
- `GET /api/v1/documents/{id}/versions` returns version metadata paginated five at a time by default, including the current version and page metadata; `GET /api/v1/documents/{id}/versions/{version_number}/download` streams a retained version. Neither exposes storage keys.
- `PUT /api/v1/documents/{id}/versions` accepts a validated multipart replacement for owners and EDIT recipients and requires `expected_version_number`; stale writes return 409 rather than overwriting newer content.
- `PUT /api/v1/documents/{id}/content` edits UTF-8 `text/plain` content as a new version for owners and EDIT recipients. Other MIME types return 415.
- `DELETE /api/v1/documents/{id}/versions/{version_number}` is owner-only. Deleting a historical version preserves the current pointer; deleting the current version rolls back to the highest remaining version. The final version cannot be deleted, and version numbers are never reused.
- `DELETE /api/v1/documents/{id}` is owner-only. It marks `deleted_at`, removes the document from normal reads, then attempts best-effort Supabase Storage cleanup for the current and historical version objects. Metadata is retained for history.
- `POST /api/v1/documents/upload` is available to every active authenticated user. Ownership is assigned to the uploader, with generated keys, validated content, and a server-computed SHA-256 checksum.
- Owners manage sharing with `GET/POST /api/v1/documents/{id}/permissions` and `PATCH/DELETE /api/v1/documents/{id}/permissions/{permission_id}`. Grants target an active registered account by normalized email and accept only `READ` or `EDIT`.
- A same-level grant is idempotent (`200`); a different active level returns `409`. Level changes revoke the existing row and insert a replacement, retaining history. Revocation is idempotent (`204`) and takes effect on the recipient's next request.
- Permission management is owner-only. Administrators do not gain owner or sharing powers. Permission lists include active and revoked rows, with `total` and `active_total`.
- Successful document, permission, registration, login, and logout actions append audit events in the same database transaction as the protected change. Denials are recorded best-effort so an audit failure cannot turn an authorization denial into a success.

The frontend provides registration and login, a live dashboard with permitted-document counts and recent activity, a searchable/filterable library with name, category, owner-ID, and date filters, sorting, and pagination; a "Shared with me" view; access-level badges; a dedicated upload page with validation and progress feedback; an access-aware details page with read-only metadata, preview, download, paginated version history, and paginated owner activity; and an owner-only sharing page with grant, level update, revoke confirmation, and history. Administrators get account management, summary counts, permission history, metadata oversight, and the audit viewer; administrator metadata and audit access remain read-only, and private content still requires ownership or an explicit grant. Desktop uses a sidebar navigation shell, while mobile uses a compact top bar and scrollable navigation.

Storage behavior is covered by a mocked adapter, and a **live private-bucket connectivity, upload, download, metadata, and delete smoke test has passed** against the configured Supabase project. The bucket must remain private.

## Secure PDF Preview, Annotation Editing, and Revisions

### PDF Preview Architecture
- **Rendering engine:** Mozilla PDF.js (`pdfjs-dist` v6.x) built into Vite via dynamic worker bundling (`pdf.worker.min.mjs?url`).
- **Data flow:** PDF bytes are retrieved through the authenticated backend endpoint (`GET /api/v1/documents/{id}/preview`), converted to an `ArrayBuffer`, and rendered directly into HTML5 canvas elements.
- **Security controls:** `isEvalSupported: false` is configured on the PDF document loading task to prevent arbitrary code execution within the PDF context. The preview endpoint sets `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`. Private Supabase Storage object keys and signed URLs are never exposed to the client.
- **Controls & navigation:** Page-by-page navigation with keyboard/button controls, zoom scaling (from 80% to 200%), page-count indicators, and automatic resource disposal (`loadingTask.destroy()`, render task cancellation on unmount).

### In-Browser PDF Editing Capabilities
- **SDK & Licensing:** Implemented using open-source `pdf-lib` (MIT License) and `pdfjs-dist` (Apache 2.0 License). No proprietary or commercial license keys (such as Apryse WebViewer) are required.
- **Supported Operations:**
  - **Sticky Text Notes:** Place text note annotations anywhere on the canvas with author attribution and timestamp.
  - **Free Text (Typewriter):** Type custom text annotations directly onto the PDF document surface at exact coordinates.
  - **Area Highlights:** Click-and-drag translucent highlight boxes over specific document regions.
  - **Typed Signatures & Initials:** Insert stylized italicized signatures/initials at user-specified positions.
- **Limitations:**
  - Modification of pre-existing PDF font glyphs or body text streams is not supported without commercial font-substitution engines (e.g. Apryse WebViewer with commercial licensing).
  - TrustVault accurately represents this capability as client-side PDF binary annotation embedding rather than arbitrary document layout reflow.

### Revision Lifecycle & Concurrency
- When an authorized user with `EDIT` or `OWNER` permissions saves annotations, `pdf-lib` loads the original PDF binary in the browser, draws the requested annotations onto the corresponding PDF pages, and serializes the modified document into a valid binary PDF (`application/pdf`).
- The new revision is uploaded via `PUT /api/v1/documents/{id}/versions` with `expected_version_number`.
- If another editor committed a revision concurrently, the server rejects the request with HTTP 409 Conflict. The editor becomes stale and requires close/reopen; refreshing history alone is not sufficient because the in-memory draft could still overwrite a newer revision.
- Every revision takes the next persistent `next_version_number`, assigns a new unique storage key in private storage, computes a new SHA-256 checksum, logs a `DOCUMENT_VERSION_CREATED` audit event, and preserves the previous version. Deleted version numbers are never reused.
- PDF annotation coordinates are converted through the PDF.js page viewport so rotated pages retain correct placement; filenames are normalized, and text unsupported by standard PDF fonts is sanitized before embedding.

### Version Deletion and Rollback Policy
- Document owners can delete any version via `DELETE /api/v1/documents/{id}/versions/{version_number}`, provided at least one version remains.
- Deleting a non-current version leaves the current pointer unchanged. Deleting the current version rolls back to the highest-numbered remaining version and updates the document's active storage key, MIME type, size, and checksum.
- The last remaining version cannot be deleted and returns HTTP 400 Bad Request. This prevents a document from existing without usable content.
- When a version is deleted, its private Supabase Storage object is deleted, retained storage totals are recalculated, and a `DOCUMENT_VERSION_DELETE` audit event records whether a rollback occurred, the previous/current version numbers, and storage cleanup status.

## Administrator Account Management

- `GET /api/v1/admin/summary` returns account, role, document, and active-grant counts.
- `GET /api/v1/admin/users` and `GET /api/v1/admin/users/{id}` provide account search/filtering, timestamps, last login, owned-document count, and role/status detail.
- `PATCH /api/v1/admin/users/{id}/status` disables or reactivates an account; disablement and role changes revoke the target's active refresh sessions.
- `PATCH /api/v1/admin/users/{id}/role` switches between `USER` and `ADMINISTRATOR`.
- An administrator cannot change their own role or status, and the last active administrator cannot be disabled or demoted.
- `GET /api/v1/admin/documents/{id}/permissions` exposes permission history for oversight without granting file content.
- Every successful account change is audited with `target_user_id` and `resource_type`; denied account changes are also audited. Self-service deletion remains unavailable.

## Audit Trail and Integrity

- The audit writer records authentication, account status/role changes, upload, metadata update, download, delete, permission grant/update/revoke, and their denial outcomes. Read-only audit views and integrity checks are not themselves audited.
- Events are appended under a PostgreSQL advisory transaction lock with a contiguous `chain_index`, `previous_hash`, and SHA-256 `event_hash`. The hashed payload is canonical JSON with a versioned schema and UTC microsecond timestamps.
- State-changing success events share the protected business transaction: an audit write failure rolls back the change and returns a generic error. Denial events use a best-effort commit and never block the intended 403/404 response.
- Details are sanitized. Passwords, tokens, cookies, authorization headers, document content, session IDs, and other sensitive keys are rejected; request ID, direct socket client IP, and a length-limited user-agent are attached automatically when available.
- `GET /api/v1/admin/audit-events` supports filtering by actor ID, target user ID, resource type, document ID, action, outcome, and inclusive UTC date range, with newest-first pagination. `GET /api/v1/admin/audit-integrity` verifies both the chain and the signed checkpoint.
- Both audit endpoints are global-administrator-only. There is no owner-scoped audit view or audit mutation endpoint in Phase 7.
- The signed checkpoint binds the current chain head with HMAC-SHA256 and is written atomically by `python -m scripts.audit_integrity --create-checkpoint`. Checkpoint creation refuses to replace an invalid or newer checkpoint. It detects database tampering only relative to the last trusted checkpoint; events appended after the latest checkpoint and then deleted are not detectable by that checkpoint, and it does not prevent a privileged attacker from deleting both the database changes and the same-host checkpoint file.
- The audit dashboard at `/admin/audit` provides filters, event detail expansion, pagination, and an integrity panel showing `VERIFIED`, stale/missing checkpoint, or invalid-chain states.

## Database

The schema has six tables — `users`, `refresh_tokens`, `documents`, `document_permissions`, `document_versions`, and `audit_events` — with UUID primary keys, enforced checks, foreign keys, partial unique indexes, and a `pg_trgm` index for document name search. Migration `0003` adds the audit chain sequence; `0004` adds `users.last_login_at`, migrates legacy roles, and adds role/status index support; `0005` adds content versions and backfills existing documents as version 1; `0006` versions the audit hash schema; `0007` adds `documents.next_version_number` and backfills it from the highest retained version. Highlighted decisions:

- Roles and statuses are constrained strings; no native PostgreSQL enums. The current role constraint allows only `ADMINISTRATOR` and `USER`.
- Emails are stored lowercased and uniquely constrained.
- Refresh tokens are stored only as SHA-256 hashes, grouped by session family, with expiry and revocation timestamps.
- Document permissions keep a full grant/revoke history with a partial unique index allowing only one active grant per user/document pair.
- Audit events reference users and documents with `ON DELETE SET NULL` so history survives deletion.
- Audit events use a positive, unique `chain_index` populated in migration `0003`; the application appends the hash chain and does not expose update/delete endpoints.
- Documents use soft deletion (`deleted_at`). Current-file columns remain denormalized for compatibility, while `document_versions` retains content history with one current version per document.
- `documents.next_version_number` is a persistent sequence so deleting a version cannot cause its number to be reused. Deleting the current version atomically moves the pointer and denormalized content columns to the highest remaining version.
- Version uniqueness is enforced on `(document_id, version_number)` and `storage_key`; a partial unique index permits exactly one current version, and `storage_key` is never returned by the API.

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
| `DATABASE_URL` | PostgreSQL/Supabase connection string; direct or session pooler (5432) for migrations, transaction pooler (6543) for runtime | Yes for database work |
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
| `SUPABASE_URL` | HTTPS Supabase project URL without a path | Yes for uploads |
| `SUPABASE_STORAGE_BUCKET` | Private Supabase Storage bucket name | Yes for uploads |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side secret or legacy service-role key | Yes for uploads |
| `MAX_UPLOAD_SIZE_BYTES` | Upload limit, 1–104,857,600 bytes | No (default `10485760`) |
| `ALLOWED_UPLOAD_EXTENSIONS` | Comma-separated extension allow-list | No (default `pdf,txt,docx,png,jpg,jpeg`) |

`CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173`. A wildcard is rejected outside `development`. Supabase Storage credentials are server-side only and must never be placed in `VITE_*` variables.

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

The suite currently has **269 tests**, including **46 threat-mapped security cases** in `backend/tests/test_security.py`, the business-model acceptance suite in `backend/tests/test_business_model.py`, the document-content/version suite in `backend/tests/test_document_versions.py`, and focused request-limit tests in `backend/tests/test_request_limits.py`. It verifies:

- Application metadata, health endpoint behavior, JSON error envelopes, and CORS.
- Database URL normalization and Supabase pooler/SSL detection.
- Models, tables, columns, indexes, and constraints for all six tables, including immutable version history and one-current/version uniqueness constraints.
- Migrations `0001`–`0007`: `upgrade head`, `alembic check` for drift, legacy-role data migration, version backfill/downgrade, persistent version-sequence backfill, `downgrade base`, and re-`upgrade`.
- Registration, login, refresh rotation, reuse detection, logout, and current-user behavior.
- Expired, tampered, wrong-issuer/audience/type, disabled-account, and revoked-session rejection.
- Role authorization helpers and fail-closed unknown-role handling.
- Login/registration rate limiting and `Retry-After` behavior.
- Production authentication configuration validators.
- Auth logging that does not include passwords, tokens, or email addresses.
- Upload validation for supported file types, MIME/signature mismatches, unsafe filenames, empty files, and oversized requests.
- Normal-user upload success with server-decided ownership, generated storage keys, computed SHA-256 checksums, and persisted metadata.
- Anonymous denial, storage failure mapping, database-failure object cleanup, and secret-safe errors/logs.
- Supabase Storage configuration validators, private-bucket enforcement, header handling, and safe storage error mapping without live network access.
- Document list authorization/scoping, name search with literal wildcard escaping, category/owner/date filters, sorting, pagination boundaries, and invalid query parameters.
- Owner/shared/metadata-only visibility, owner/EDIT updates, READ/administrator denial, protected-field rejection, and generic 404 IDOR behavior.
- Streamed download and inline-preview headers, UTF-8/header-injection-safe filenames, storage-not-found/storage-failure mapping, and READ/EDIT/owner access rules.
- Version listing pagination and deduplication, current/historical downloads, READ denial of writes, EDIT replacement and text editing, stale-write conflicts, plain-text-only enforcement, history retained across replacement, persistent version numbering after deletion, last-version rejection, current-version rollback, storage-failure rollback safety, and owner activity filtering/pagination.
- Soft deletion, list/detail exclusion, retained metadata, mocked object cleanup, cleanup-failure logging, and repeat/other-user delete denial.
- Owner-only permission grant/list/update/revoke, idempotent same-level grants, conflict handling, active/revoked history, retained revocation rows, and revoke-and-regrant behavior.
- Active excluded (disabled/missing) recipients, endpoint-forged identity rejection, owner self-grant conflict, and authenticated but unauthorized document manipulation.
- Shared-with-me filtering of revoked and soft-deleted documents, pagination/sorting, immediate post-revocation denial, access-level reporting, and metadata-only administrator behavior.
- Audit events for registration, login success/failure, logout, account status/role changes, uploads, metadata updates, downloads, deletes, permission changes, and denied operations.
- Administrator-only audit query access, filters, pagination, generic denial behavior, request-ID normalization, metadata/request-context sanitization, and denied audit access.
- Hash-chain verification, middle-event tampering/removal detection, signed-checkpoint success/staleness/truncation/signature failure, refusal to replace invalid/newer checkpoints, and mandatory-audit-write rollback behavior.
- Threat-model verification for IDOR, cross-user GET/download/edit/delete denial, grant/revoke audit coverage, forged role claims, administrator content boundaries, malicious uploads, malformed multipart, DOCX expansion limits, Unicode format-control filenames, path manipulation, audit API mutation attempts, metadata leakage, secret-safe failures, expired/tampered tokens, logout/disabled-account invalidation, brute-force limits, pre-authentication oversized uploads, and uploads without `Content-Length`.

Database tests start an **embedded PostgreSQL** instance in a temporary directory and never contact Supabase or read `DATABASE_URL`. Storage tests use a fake HTTP client; no test contacts Supabase Storage.

Coverage is generated separately from test success:

```powershell
pytest --cov=app --cov-report=term-missing
```

The verified local full-suite run passed **269 tests with 88% statement coverage**. Coverage is a diagnostic, not proof of security.

The GitHub Actions workflow `.github/workflows/backend-tests.yml` runs the full backend suite with coverage on pushes and pull requests that change `backend/**`. Remote CI execution is not verified until the workflow runs on GitHub.

### Frontend

```powershell
cd frontend
npm run lint
npm test
npm run build
```

All three commands pass. The frontend is JavaScript/JSX only; `npm test` runs the Vitest/React Testing Library suite, and `npm run build` runs the Vite production build. The 23 automated tests across 8 files cover safe API error extraction, role-aware navigation, dashboard API-backed counts and failure handling, upload access for normal users, administrator account oversight/actions, structured audit metadata, READ-only previews/history, plain-text version edits, replacement uploads, version/activity pagination, current-version rollback, and stale-editor protection. A browser-based walkthrough with live accounts and deployment remain unverified.

## API Baseline

- **Health:** `GET /health` → `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`
- **Register:** `POST /api/v1/auth/register` → creates a User and returns an access token
- **Login:** `POST /api/v1/auth/login` → returns an access token and sets the refresh cookie
- **Refresh:** `POST /api/v1/auth/refresh` → rotates the refresh session and returns a new access token
- **Logout:** `POST /api/v1/auth/logout` → revokes the current refresh session and returns 204
- **Current user:** `GET /api/v1/auth/me` → returns the authenticated user
- **Upload:** `POST /api/v1/documents/upload` → validates and stores a document owned by the authenticated user and returns safe metadata (no storage key)
- **List/search:** `GET /api/v1/documents` → scoped, filtered, sorted, paginated metadata (`items`, `total`, `page`, `page_size`, `pages`, `has_next`, `has_previous`)
- **Details:** `GET /api/v1/documents/{id}` → safe metadata plus the caller's `access_level`
- **Shared with me:** `GET /api/v1/documents/shared-with-me` → active documents explicitly shared with the caller
- **Update:** `PATCH /api/v1/documents/{id}` → updates to `name`, `category`, and `description` for owners and EDIT recipients
- **Download:** `GET /api/v1/documents/{id}/download` → private object stream for owners, READ recipients, and EDIT recipients
- **Preview:** `GET /api/v1/documents/{id}/preview` → authorized inline content for owners, READ, and EDIT recipients
- **Versions:** `GET /api/v1/documents/{id}/versions` and `GET /api/v1/documents/{id}/versions/{version_number}/download` → safe history metadata and retained-version downloads
- **Replace version:** `PUT /api/v1/documents/{id}/versions` → owner/EDIT multipart replacement with optimistic version check
- **Edit text:** `PUT /api/v1/documents/{id}/content` → owner/EDIT plain-text edit that creates a new version
- **Delete:** `DELETE /api/v1/documents/{id}` → owner-only soft deletion and best-effort cleanup of every version object; returns 204
- **List permissions:** `GET /api/v1/documents/{id}/permissions` → owner-only active and revoked grant history
- **Grant permission:** `POST /api/v1/documents/{id}/permissions` → owner-only `READ`/`EDIT` grant; returns 201, or 200 for an idempotent same-level grant
- **Update permission:** `PATCH /api/v1/documents/{id}/permissions/{permission_id}` → revoke-and-regrant level change with retained history
- **Revoke permission:** `DELETE /api/v1/documents/{id}/permissions/{permission_id}` → idempotent immediate revocation; returns 204
- **Admin summary:** `GET /api/v1/admin/summary` → administrator-only account, role, document, and grant counts
- **Admin users:** `GET /api/v1/admin/users` and `GET /api/v1/admin/users/{id}` → administrator-only account search/detail
- **Admin status:** `PATCH /api/v1/admin/users/{id}/status` → disable/reactivate with session revocation and audit
- **Admin role:** `PATCH /api/v1/admin/users/{id}/role` → `USER`/`ADMINISTRATOR` change with session revocation and audit
- **Admin document permissions:** `GET /api/v1/admin/documents/{id}/permissions` → metadata-only permission oversight
- **List audit events:** `GET /api/v1/admin/audit-events` → administrator-only filtered/paginated audit history
- **Audit integrity:** `GET /api/v1/admin/audit-integrity` → administrator-only hash-chain and signed-checkpoint status
- **Errors:** JSON envelope `{"error":{"code":"...","message":"...","details":"..."}}` where applicable.
- **CORS:** Loaded from `CORS_ALLOWED_ORIGINS`; production wildcards are rejected.
- **OpenAPI:** Enabled at `/docs` and `/openapi.json`.

There are no audit mutation endpoints.

## Deployment Preparation

No deployment has been performed or verified. The repository migration head is `0007`; the live Supabase migration state and drift were not re-verified during this local run.

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
- Environment: `APP_ENV=production`, `LOG_LEVEL=INFO`, `DATABASE_URL`, `JWT_SECRET`, a real `CORS_ALLOWED_ORIGINS`, the auth cookie/rate-limit settings, the Supabase Storage/upload settings, and optional `AUDIT_CHECKPOINT_SIGNING_KEY`/`AUDIT_CHECKPOINT_PATH` in `render.yaml`. Render supplies `PORT`.
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

- Live Supabase Storage connectivity and private-bucket behavior are verified only when `SUPABASE_SERVICE_ROLE_KEY` is configured; automated upload/download/delete tests use a fake HTTP client.
- Audit history is append-only at the application layer, but database roles are not restricted from direct UPDATE/DELETE. The hash chain and signed checkpoint detect modifications only relative to a trusted checkpoint; events appended after the latest checkpoint and then deleted are not detected by that checkpoint. The checkpoint is a same-host file, not an independent immutable store.
- The audit checkpoint is not written automatically on a schedule. Operators must run `python -m scripts.audit_integrity --create-checkpoint` and retain the signed file outside the application database.
- Audit exports (CSV/JSON download) and owner-scoped audit views are not implemented; audit query access is global-administrator-only.
- Client IP metadata uses the direct ASGI socket address, not a trusted `X-Forwarded-For` chain, so a reverse proxy may record the proxy address. Forwarded-header trust must be configured deliberately at deployment.
- Uploads are not virus-scanned; validation covers type/signature/size/structure only.
- Upload-to-database consistency is compensating, not transactional: a failed metadata commit triggers best-effort object deletion, which could itself fail.
- Soft deletion excludes metadata from normal reads but object cleanup occurs after commit; a cleanup failure can leave a private orphan object for later reconciliation.
- RLS is not enabled; the backend uses a single privileged database role.
- The repository migration head is `0007`; live Supabase migration state and `alembic check` were not re-verified, and no deployment has been verified.
- Version objects are immutable in normal application flows, but the backend has no object-lock or retention policy; a privileged storage operator could still alter or delete private content.
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
| 8 — Security Tests and Threat-Model Verification | Complete |
| 9 — Complete Frontend | Complete — awaiting review |
| 9.1 — Business-Model Correction | Complete — committed as `77af2dc` |
| 9.2 — Document Content, Previews, and Version History | Complete — pending review |
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
