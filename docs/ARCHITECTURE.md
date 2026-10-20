# TrustVault — System Architecture

## 1. System Overview

TrustVault is a secure document vault consisting of four primary components: a React single-page application, a FastAPI backend API, a Supabase PostgreSQL database, and Wasabi S3-compatible private object storage. The backend API is intended to be the sole authorization enforcement point — all document access, permission checks, and audit logging will flow through it.

> **Implementation status (Phase 3):** authentication, database-backed roles, rotating refresh sessions, and the protected frontend routes are implemented and verified locally. Document storage, document APIs, permission endpoints, and the audit write path are **not** implemented. TrustVault has **no live deployment**, and migrations have **not** been applied to the Supabase project.

### Architecture Diagram

```mermaid
graph TB
    subgraph "Client Zone — Untrusted"
        Browser["User Browser"]
        ReactSPA["React SPA<br/>TypeScript + Vite<br/>Tailwind CSS + shadcn/ui<br/><i>Hosted on Vercel</i>"]
    end

    subgraph "API Zone — Trust Boundary"
        API["FastAPI Backend<br/>Python 3.13<br/>SQLAlchemy 2.x (sync)<br/><i>Hosted on Render</i>"]
        AuthMW["JWT Auth + Session Checks<br/>Phase 3"]
        PermCheck["Permission Checker — Phase 6"]
        AuditSvc["Audit Writer — Phase 7"]
        FileVal["File Validator — Phase 4"]
    end

    subgraph "Data Zone — Trusted"
        DB["Supabase PostgreSQL<br/>RLS planned, not enabled"]
        S3["Wasabi S3<br/>Private Bucket"]
    end

    Browser -->|"HTTPS"| ReactSPA
    ReactSPA -->|"HTTPS REST API<br/>Authorization: Bearer JWT (Phase 3)"| API
    API --- AuthMW
    API --- PermCheck
    API --- AuditSvc
    API --- FileVal
    API -->|"SQLAlchemy + psycopg 3"| DB
    API -->|"boto3 (Phase 4)"| S3

    style Browser fill:#f9f,stroke:#333
    style ReactSPA fill:#bbf,stroke:#333
    style API fill:#fda,stroke:#333
    style DB fill:#bfb,stroke:#333
    style S3 fill:#bfb,stroke:#333
```

### Key Principle

> **Hiding a frontend UI element is NOT authorization.** The backend must independently verify every request. If a button is hidden but the API endpoint is accessible, that is a security vulnerability.

---

## 2. Phase Status

| Phase | Area | State |
|-------|------|-------|
| 0 | Requirements, architecture, threat model, docs | Complete |
| 1 | Frontend/backend scaffold, health endpoint, CORS, tests | Complete |
| 2 | Database models, initial migration, connection module | Complete (verified locally) |
| 3 | Authentication, roles, refresh tokens | Complete (verified locally) |
| 4 | Wasabi storage, validated uploads, proxied downloads | Planned |
| 5 | Document management and search | Planned |
| 6 | Permissions and revocation | Planned |
| 7 | Audit write path, hash chain, admin activity | Planned |
| 8 | Security tests and threat-model verification | Planned |
| 9 | Complete frontend | Planned |
| 10 | Deployment hardening and end-to-end verification | Planned |
| 11 | Final submission and demo | Planned |

The implemented schema is documented in full in [DATABASE.md](DATABASE.md).

---

## 3. React Frontend Responsibilities

The React SPA runs entirely in the user's browser. It is responsible for:

- **Rendering the UI** — login, authenticated dashboard, role-gated administrator area, and future document, permission, and audit views.
- **Client-side routing** — single-page navigation via React Router.
- **Client-side form validation** — for user experience only. All validation is re-performed server-side.
- **API communication** — all data interactions go through the FastAPI backend via HTTPS REST calls using a centralized Axios client.
- **Token handling** — the access token is held in memory only; the rotating refresh token stays in an HttpOnly cookie. Axios sends credentials and retries an expired access token through one shared refresh request.
- **UI state management** — loading states, error messages, and user feedback.

**The frontend NEVER:**
- Connects directly to the database.
- Connects directly to Wasabi S3.
- Makes authorization decisions. Frontend controls (disabled buttons, hidden menus) are UX convenience, not security.
- Stores secrets or API keys (other than the backend URL).

---

## 4. FastAPI Backend Responsibilities

The backend is the **intended sole enforcement point** for security. It is responsible for the following. Items marked *planned* are not implemented yet.

### Authentication (implemented — Phase 3)
- Public registration always creates a `VIEWER`; elevated roles are provisioned with `scripts/create_user.py`.
- Passwords are hashed with bcrypt (cost configurable; production default 12) with a 12-character minimum and 72-byte maximum. Unknown accounts perform dummy-hash work and return the same generic error.
- Login returns a short-lived HS256 JWT access token and sets an opaque rotating refresh token in an HttpOnly cookie scoped to `/api/v1/auth`.
- Refresh tokens are stored only as SHA-256 hashes and grouped by session family. Reuse of a rotated token revokes the whole family.
- Every protected request validates the JWT signature, issuer, audience, account status, and an active refresh-token family. Logout, disablement, and reuse detection therefore invalidate access immediately.
- Auth POSTs enforce an Origin allow-list, and login/registration use a bounded in-memory rate limiter (10 attempts per 60 seconds by default, client IP plus normalized email for login).
- `GET /api/v1/auth/me` returns the trusted database user; authorization uses the current database role, not the token's role claim.

### Authorization (planned — Phase 6)
- Every document request passes through a permission checker.
- The checker resolves access as: administrator → allowed; document owner → allowed; explicit active `READ`/`EDIT` grant → allowed; otherwise denied.
- Denials return 403 (without leaking document existence or metadata) and will create an `ACCESS_DENIED` audit event once Phase 7 exists.

### Document Operations (planned — Phases 4–5)
- Upload: validate file, store in Wasabi with a UUID-based key, create metadata.
- Download: verify permission, stream from Wasabi. Direct storage URLs are never exposed.
- List/Search: query PostgreSQL with permission filtering. `documents.name` has a `pg_trgm` index to support case-insensitive search in Phase 5.
- Update metadata and soft delete.

### Audit Logging (schema in Phase 2; write path planned — Phase 7)
- Persist an event for every significant action into `audit_events`.
- Maintain a hash chain using `previous_hash` and `event_hash`.
- Expose read-only query endpoints for administrators and document owners.
- Never expose UPDATE or DELETE endpoints for audit history.

### Database Access (implemented — Phase 2)
- SQLAlchemy 2.x models with a synchronous engine using the **psycopg 3** driver.
- Alembic migrations as the only DDL path (`backend/alembic/`).
- Lazy engine creation so importing the application does not require `DATABASE_URL`.
- Connection pooling configurable through `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`.

### Error Handling (implemented — Phase 1)
- Structured JSON error responses.
- Sensitive details (stack traces, SQL) are logged server-side and never returned to clients.
- Documented status codes: 400, 401, 403, 404, 409, 422, 429, 500, 503.

---

## 5. Database Architecture (Implemented)

The Phase 3 schema contains five tables. Full column, constraint, and index detail lives in [DATABASE.md](DATABASE.md).

| Table | Purpose |
|-------|---------|
| `users` | Accounts, hashed passwords, role, status, timestamps |
| `refresh_tokens` | Hashed opaque refresh tokens, rotation families, expiry, revocation |
| `documents` | Metadata: owner, name, category, description, storage key, MIME type, size, checksum, soft-delete timestamp |
| `document_permissions` | Per-user, per-document grant history (`READ`/`EDIT`) with revocation timestamps |
| `audit_events` | Append-oriented event records with action, outcome, JSONB details, and hash-chain columns |

### Design Decisions

- **UUID primary keys** generated by PostgreSQL `gen_random_uuid()`. UUIDs are not a security control; authorization never depends on ID secrecy.
- **Roles and statuses as constrained strings.** `users.role` is checked against `ADMINISTRATOR`, `DOCUMENT_OWNER`, `VIEWER`; `users.status` against `ACTIVE`, `DISABLED`. Constrained strings avoid the migration friction of native PostgreSQL enums while still being validated at the database. Python-side `StrEnum` values live in `app/models/enums.py`.
- **Email normalization.** `users.email` is stored lowercase and must already be lowercase (check constraint), with a unique constraint. Normalization happens before insert; the database guarantees no mixed-case duplicates.
- **Required `password_hash`.** The column is `NOT NULL`; Phase 3 always stores a bcrypt hash, so an account can never exist without a credential.
- **Explicit owner FK.** `documents.owner_id` references `users.id` with `ON DELETE RESTRICT`; a user who owns documents cannot be deleted until ownership is transferred.
- **Internal storage keys only.** `documents.storage_key` is unique, must start with `documents/`, and must not contain a URL scheme, preventing accidental public-URL storage.
- **Required checksum.** `documents.checksum` is a required SHA-256 hex string for integrity checks in later phases.
- **Soft delete.** `documents.deleted_at` marks deletion without removing history; hard-delete and storage cleanup behavior is defined in Phase 5.
- **Permission history with a single active grant.** A partial unique index (`WHERE revoked_at IS NULL`) allows only one active grant per `(document_id, user_id)`. Revoking sets `revoked_at`; re-granting inserts a new row, preserving audit history. `granted_by` uses `ON DELETE SET NULL`.
- **Owner access is implicit.** Owners are not represented in `document_permissions`; ownership comes from `documents.owner_id`. The permissions table records grants to *other* users.
- **Audit retention by design.** `audit_events.actor_id` and `audit_events.document_id` use `ON DELETE SET NULL` so removing a user or document retains the event. The `action` column is intentionally unconstrained for extensibility; `outcome`, JSON-object details, and SHA-256 hash formats are constrained.

### Deferred Tables

`categories` remains deferred. Category is a nullable `documents.category` column until Phase 5 decides whether a lookup table is warranted. `refresh_tokens` is now implemented by migration `0002`.

### Connection Management

`backend/app/db/session.py` provides a lazily created, cached engine and a `sessionmaker`. The module normalizes any `postgres://`/`postgresql://` URL to `postgresql+psycopg://`, sets `sslmode=require` for Supabase hosts, and disables psycopg server-side prepared statements when the Supabase transaction pooler (port 6543) is used. Pool defaults are `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`, and `pool_recycle=1800`.

The schema is applied only through Alembic. The initial migration `0001_initial_schema` creates the `pg_trgm` extension before its GIN index; downgrade drops the tables but leaves the shared extension installed.

---

## 6. Wasabi Private Storage Responsibilities (Planned — Phase 4)

Wasabi will provide S3-compatible object storage for document content.

- Bucket is **private** — no public access policy.
- All access goes through the FastAPI backend using `boto3`.
- `WASABI_ACCESS_KEY` and `WASABI_SECRET_KEY` are environment variables; they are never committed.

### File Organization

```
documents/
  {document_uuid}/
    {version}/
      {sanitized_filename}
```

Storage keys are system-generated UUID paths; the user-supplied filename is metadata only.

### Access Pattern

1. **Upload:** backend validates → `put_object()` → records the storage key.
2. **Download:** backend verifies permission → `get_object()` and streams. Presigned URLs, if used at all, must be very short-lived and are not part of the initial design.
3. **Delete:** backend verifies ownership → deletes from Wasabi → updates metadata.

The frontend **never** receives a direct Wasabi URL.

---

## 7. Authentication Flow (Implemented — Phase 3)

```mermaid
sequenceDiagram
    participant U as User Browser
    participant F as React Frontend
    participant B as FastAPI Backend
    participant D as Supabase PostgreSQL

    U->>F: Enter credentials
    F->>B: POST /api/v1/auth/login {email, password}
    B->>D: Query user by normalized email
    D-->>B: User record (bcrypt hash, role, status)
    B->>B: Verify password / dummy hash for unknown accounts
    alt Valid credentials
        B->>D: Create refresh-token family record (store SHA-256 hash)
        B-->>F: 200 {access_token, user} + HttpOnly refresh cookie
        F->>F: Keep access token in memory
    else Invalid credentials or disabled account
        B-->>F: 401 Invalid email or password
    end

    Note over F,B: Subsequent API requests
    F->>B: Authorization: Bearer {jwt} + refresh cookie
    B->>B: Verify signature, issuer, audience, type, expiry
    B->>D: Load user + active refresh session
    alt Valid and session active
        B->>B: Proceed using the current database role
    else Invalid, expired, revoked, or disabled
        B-->>F: 401
        F->>B: POST /api/v1/auth/refresh (cookie)
        B->>D: Validate + rotate refresh token
        B-->>F: 200 {new_access_token, user} + rotated cookie
    end
```

### Token Details (Implemented)

- **Access token:** HS256 JWT, 15-minute default lifetime, with `sub`, `role`, `sid`, `type=access`, `iat`, `nbf`, `exp`, and `jti`. Issuer and audience are validated.
- **Refresh token:** 256-bit opaque value, stored only as `sha256:<64 hex>`, 7-day default lifetime, single-use rotation within a family. Reuse revokes the family.
- **Cookie:** `trustvault_refresh`, `HttpOnly`, path `/api/v1/auth`, `SameSite`/`Secure` from configuration. Production requires Secure; cross-site Vercel/Render needs `SameSite=None`.
- **Password hashing:** bcrypt with configurable cost (default 12). Passwords must be 12–72 UTF-8 bytes.
- **Revocation:** access tokens are tied to the refresh-token family and checked against current session state on every protected request.

## 8. Per-Request Authentication and Authorization (Phase 3)

```mermaid
flowchart TD
    A[Incoming Protected Request] --> B{Bearer token present?}
    B -->|No| C[401 Unauthorized]
    B -->|Yes| D{JWT valid and type=access?}
    D -->|No| C
    D -->|Yes| E[Load user and refresh family from database]
    E --> F{User active and session active?}
    F -->|No| C
    F -->|Yes| G{Endpoint role requirement met?}
    G -->|No| H[403 Forbidden]
    G -->|Yes| I[Execute endpoint]
```

The backend verifies identity and session state on **every** protected request. Role checks use the current database value and fail closed for unknown roles. Document-level ownership and READ/EDIT grants are not implemented yet; those checks arrive with the document endpoints in Phases 5–6.

## 9. Upload and Download Flows (Planned — Phases 4–5)

### Upload

1. Client sends `POST /documents/upload` with multipart file plus metadata.
2. Backend validates the JWT and checks the caller is an owner or administrator.
3. File validation: size limit, MIME allow-list, magic-byte check, filename sanitization.
4. Backend generates a UUID storage key, uploads to Wasabi, and on success creates the `documents` row (checksum computed from the file bytes).
5. An audit event (`DOCUMENT_UPLOAD`) is written.
6. Any failure leaves no partial database row and no orphan object.

### Download

1. Client sends `GET /documents/{id}/download`.
2. Backend validates the JWT, loads metadata, and checks ownership/role/grant.
3. Denied requests return 403 and, once Phase 7 exists, an `ACCESS_DENIED` event.
4. Backend fetches from Wasabi, streams with safe `Content-Type` and `Content-Disposition`, and records `DOCUMENT_DOWNLOAD`.

---

## 10. Permission Granting and Immediate Revocation (Schema now; endpoints Phase 6)

### Granting

1. Owner sends `POST /documents/{id}/permissions` with `{user_id, level: "READ"|"EDIT"}`.
2. Backend verifies the caller is the document owner (or administrator).
3. Backend inserts a `document_permissions` row (a regrant after revocation inserts a new row; history is preserved by the partial unique index).
4. Backend writes `PERMISSION_GRANTED`.

### Revoking

1. Owner sends `DELETE /documents/{id}/permissions/{user_id}`.
2. Backend verifies the caller is the document owner (or administrator).
3. Backend sets `revoked_at` on the active row.
4. Backend writes `PERMISSION_REVOKED`.
5. **Revocation is immediate** — the next request from the revoked user receives 403.

### Critical Notes

- No caching layer may serve stale permission data; checks always read current database state.
- **Files already downloaded before revocation cannot be recalled.** This is a documented limitation.
- `EDIT` implies `READ`. Only owners and administrators manage permissions; viewers cannot re-share.

---

## 11. Audit Model and Integrity Protection (Schema now; write path Phase 7)

### Event Actions

`app/models/enums.py` defines the known actions: `USER_REGISTERED`, `USER_LOGIN`, `USER_LOGIN_FAILED`, `DOCUMENT_UPLOAD`, `DOCUMENT_DOWNLOAD`, `DOCUMENT_VIEW`, `DOCUMENT_EDIT`, `DOCUMENT_DELETE`, `PERMISSION_GRANTED`, `PERMISSION_REVOKED`, and `ACCESS_DENIED`. The database column is unconstrained so later phases can add actions without a migration.

### Record Structure (`audit_events`)

| Column | Meaning |
|--------|---------|
| `id` | UUID primary key |
| `actor_id` | Acting user (nullable, `ON DELETE SET NULL`) |
| `document_id` | Target document (nullable, `ON DELETE SET NULL`) |
| `action` | Event action (extensible string) |
| `outcome` | `SUCCESS`, `DENIED`, or `FAILURE` |
| `occurred_at` | Server-side UTC timestamp |
| `request_id` | Optional correlation id |
| `details` | JSONB object with event-specific data |
| `previous_hash` | SHA-256 of the previous event (nullable for the first event) |
| `event_hash` | SHA-256 of this event |

### Hash Chain

Once the Phase 7 writer exists, each event will include the SHA-256 of the previous event, forming a tamper-evident chain verified by recomputation.

### Limitations of a Same-Database Hash Chain

A hash chain stored in the same database it protects does **not** fully protect against a privileged database administrator: an attacker could modify a record and recompute subsequent hashes so the local chain still verifies. Planned mitigation: independently controlled, periodically signed checkpoints published to an external append-only store, compared during verification. This does not make tampering impossible, only detectable.

### Application Enforcement

- The application will never issue `UPDATE` or `DELETE` on `audit_events`.
- No API exposes audit modification.
- A database immutability trigger is deliberately **not** added in Phase 2 because it would conflict with the `ON DELETE SET NULL` retention foreign keys. Phase 7 will revisit enforcement alongside the write path.

---

## 12. Deployment Architecture

```mermaid
graph LR
    subgraph "Vercel"
        FE["React SPA<br/>npm run build → dist/"]
    end

    subgraph "Render"
        BE["FastAPI<br/>uvicorn app.main:app"]
    end

    subgraph "Supabase"
        PG["PostgreSQL<br/>RLS planned"]
    end

    subgraph "Wasabi"
        WS["S3 Private Bucket"]
    end

    FE -->|"HTTPS API"| BE
    BE -->|"psycopg 3"| PG
    BE -->|"boto3 (Phase 4)"| WS
```

| Provider | Component | Configuration |
|----------|-----------|---------------|
| Vercel | Frontend | Build `npm run build`, output `dist/`, env `VITE_API_BASE_URL` |
| Render | Backend | Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, env below |
| Supabase | Database | Connection via `DATABASE_URL`; migrations applied manually with Alembic |
| Wasabi | Storage | Private bucket, server-side access only via `boto3` |

No deployment or migration has been performed. Render does not run migrations automatically; `alembic upgrade head` is a deliberate manual step.

---

## 13. Required Environment Variables

All values below are **placeholders**. Real credentials are configured in each provider's dashboard and never committed.

### Backend (Render)

```env
# Database (direct connection, port 5432, for migrations; transaction pooler 6543 also supported)
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# Authentication (Phase 3, implemented)
JWT_SECRET=replace-me
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Wasabi S3 (Phase 4)
WASABI_ACCESS_KEY=your-wasabi-access-key
WASABI_SECRET_KEY=your-wasabi-secret-key
WASABI_BUCKET=trustvault-documents
WASABI_ENDPOINT=https://s3.wasabisys.com
WASABI_REGION=us-east-1

# CORS and app
CORS_ALLOWED_ORIGINS=https://your-app.vercel.app
APP_ENV=production
LOG_LEVEL=INFO
```

### Frontend (Vercel)

```env
VITE_API_BASE_URL=https://your-backend.onrender.com
```

Only non-secret configuration belongs in `VITE_*` variables, because Vite embeds them in the browser bundle.

---

## 14. Database Security and RLS Planning (Not Enabled)

### Primary Authorization: Application Logic (Planned)

The FastAPI backend is intended to be the primary enforcement point. Every endpoint will check authentication, role, and per-document permission.

### Secondary Defense: Row-Level Security (Deferred)

RLS is defense-in-depth, not the primary control. **RLS is not enabled.** Phase 3 keeps the backend on a single privileged database role; authentication issues application-level identities, not per-request PostgreSQL identities. Because that role bypasses RLS, application authorization remains authoritative and policies are deferred until they can be tested meaningfully.

Planned policies:

| Table | Policy |
|-------|--------|
| `users` | Users can SELECT their own row; administrators can SELECT all |
| `documents` | SELECT allowed if owner, administrator, or holds a grant |
| `document_permissions` | Manageable only by document owner or administrator |
| `audit_events` | INSERT-only for the backend role; no UPDATE/DELETE |
| `refresh_tokens` (Phase 3) | Accessible only by the backend role |

**Important:** because the backend uses a privileged role, that role bypasses RLS by design, and application-level authorization remains authoritative. TrustVault must not be described as having database-enforced access control.

---

## 15. Error Handling and External-Service Failure Behavior

| Scenario | Response | Behavior |
|----------|----------|----------|
| Wasabi S3 unreachable (Phase 4) | 503 Service Unavailable | Upload/download fails cleanly; no partial metadata |
| Supabase DB unreachable | 503 Service Unavailable | Requests fail; no silent fallback |
| JWT missing/expired/invalid, revoked session, or disabled account | 401 Unauthorized | Request rejected |
| Permission denied (Phase 6) | 403 Forbidden | Generic message; no metadata leaked; audit event once Phase 7 exists |
| Document not found | 404 Not Found | Generic message; no ownership information |
| File too large (Phase 4) | 413 Payload Too Large | Rejected before storage |
| Invalid file type (Phase 4) | 422 Unprocessable Entity | Rejected with allowed-types list |
| Auth rate limit exceeded | 429 Too Many Requests | `Retry-After` returned; client waits and retries |
| Unexpected server error | 500 Internal Server Error | Logged server-side; generic client message |

---

## 16. Health Check

`GET /health` currently reports **process health only**: `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`. It does **not** query PostgreSQL or Wasabi, and a test asserts that it exposes no configuration markers. Database and storage connectivity checks will be added when those integrations exist.

---

## 17. Phase 3 Implementation Notes (Verified)

- **Auth endpoints:** `register`, `login`, `refresh`, `logout`, and `me` are implemented under `/api/v1/auth`.
- **Session design:** access tokens stay in frontend memory; refresh tokens are hashed in PostgreSQL and rotated through an HttpOnly cookie. Family reuse detection revokes the family.
- **Immediate revocation:** protected requests check the user's status and active refresh family on every call, so logout/disablement takes effect without waiting for JWT expiry.
- **Role model:** `ADMINISTRATOR`, `DOCUMENT_OWNER`, and `VIEWER` are stored in PostgreSQL. Public registration creates Viewers only; elevated roles come from the provisioning CLI.
- **CSRF and CORS:** auth POSTs enforce an exact Origin allow-list, CORS never combines credentials with a wildcard, and the refresh cookie is path-scoped. A per-session CSRF token is not implemented.
- **Rate limiting:** an in-memory sliding window limits login/register attempts per process. A multi-instance deployment requires a shared store.
- **Tests:** 55 backend tests cover auth flows, rotation/reuse, disabled accounts, role dependencies, rate limits, production config validation, and secret-free logging. The suite uses an ephemeral PostgreSQL instance.
- **Not implemented:** document authorization, audit writes, RLS, MFA, account lockout, idle timeouts, and production deployment verification.
