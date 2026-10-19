# TrustVault — System Architecture

## 1. System Overview

TrustVault is a secure document vault consisting of four primary components: a React single-page application, a FastAPI backend API, a Supabase PostgreSQL database, and Wasabi S3-compatible private object storage. The backend API is intended to be the sole authorization enforcement point — all document access, permission checks, and audit logging will flow through it.

> **Implementation status (Phase 2):** the database schema, models, migrations, and connection module exist and are verified against an isolated PostgreSQL instance. Authentication, storage, document APIs, permission endpoints, and the audit write path are **not** implemented. Sections below label planned behavior explicitly. TrustVault has **no live deployment** and the migration has **not** been applied to the Supabase project.

### Architecture Diagram

```mermaid
graph TB
    subgraph "Client Zone — Untrusted"
        Browser["User Browser"]
        ReactSPA["React SPA<br/>TypeScript + Vite<br/>Tailwind CSS + shadcn/ui<br/><i>Hosted on Vercel</i>"]
    end

    subgraph "API Zone — Trust Boundary"
        API["FastAPI Backend<br/>Python 3.13<br/>SQLAlchemy 2.x (sync)<br/><i>Hosted on Render</i>"]
        AuthMW["JWT Auth Middleware — Phase 3"]
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
| 3 | Authentication, roles, refresh tokens | Planned |
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

- **Rendering the UI** — login, registration, document management, permission management, and audit log views.
- **Client-side routing** — single-page navigation via React Router.
- **Client-side form validation** — for user experience only. All validation is re-performed server-side.
- **API communication** — all data interactions go through the FastAPI backend via HTTPS REST calls using a centralized Axios client.
- **Token handling** — Phase 3 will store the access token securely (httpOnly cookie preferred, memory fallback) and attach it to requests.
- **UI state management** — loading states, error messages, and user feedback.

**The frontend NEVER:**
- Connects directly to the database.
- Connects directly to Wasabi S3.
- Makes authorization decisions. Frontend controls (disabled buttons, hidden menus) are UX convenience, not security.
- Stores secrets or API keys (other than the backend URL).

---

## 4. FastAPI Backend Responsibilities

The backend is the **intended sole enforcement point** for security. It is responsible for the following. Items marked *planned* are not implemented yet.

### Authentication (planned — Phase 3)
- Registration with password hashing (bcrypt).
- Login returning a JWT access token plus a rotating opaque refresh token.
- JWT validation dependency on protected endpoints.
- Rate limiting on authentication endpoints.

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

The Phase 2 schema contains four tables. Full column, constraint, and index detail lives in [DATABASE.md](DATABASE.md).

| Table | Purpose |
|-------|---------|
| `users` | Accounts, hashed passwords, role, status, timestamps |
| `documents` | Metadata: owner, name, category, description, storage key, MIME type, size, checksum, soft-delete timestamp |
| `document_permissions` | Per-user, per-document grant history (`READ`/`EDIT`) with revocation timestamps |
| `audit_events` | Append-oriented event records with action, outcome, JSONB details, and hash-chain columns |

### Design Decisions

- **UUID primary keys** generated by PostgreSQL `gen_random_uuid()`. UUIDs are not a security control; authorization never depends on ID secrecy.
- **Roles and statuses as constrained strings.** `users.role` is checked against `ADMINISTRATOR`, `DOCUMENT_OWNER`, `VIEWER`; `users.status` against `ACTIVE`, `DISABLED`. Constrained strings avoid the migration friction of native PostgreSQL enums while still being validated at the database. Python-side `StrEnum` values live in `app/models/enums.py`.
- **Email normalization.** `users.email` is stored lowercase and must already be lowercase (check constraint), with a unique constraint. Normalization happens before insert; the database guarantees no mixed-case duplicates.
- **Required `password_hash`.** Even though authentication arrives in Phase 3, the column is `NOT NULL`, so an account can never exist without a hashed credential.
- **Explicit owner FK.** `documents.owner_id` references `users.id` with `ON DELETE RESTRICT`; a user who owns documents cannot be deleted until ownership is transferred.
- **Internal storage keys only.** `documents.storage_key` is unique, must start with `documents/`, and must not contain a URL scheme, preventing accidental public-URL storage.
- **Required checksum.** `documents.checksum` is a required SHA-256 hex string for integrity checks in later phases.
- **Soft delete.** `documents.deleted_at` marks deletion without removing history; hard-delete and storage cleanup behavior is defined in Phase 5.
- **Permission history with a single active grant.** A partial unique index (`WHERE revoked_at IS NULL`) allows only one active grant per `(document_id, user_id)`. Revoking sets `revoked_at`; re-granting inserts a new row, preserving audit history. `granted_by` uses `ON DELETE SET NULL`.
- **Owner access is implicit.** Owners are not represented in `document_permissions`; ownership comes from `documents.owner_id`. The permissions table records grants to *other* users.
- **Audit retention by design.** `audit_events.actor_id` and `audit_events.document_id` use `ON DELETE SET NULL` so removing a user or document retains the event. The `action` column is intentionally unconstrained for extensibility; `outcome`, JSON-object details, and SHA-256 hash formats are constrained.

### Deferred Tables

`categories` and `refresh_tokens` are deferred. Category is a nullable `documents.category` column until Phase 5 decides whether a lookup table is warranted. Refresh tokens belong to the Phase 3 authentication design.

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

## 7. Authentication Flow (Planned — Phase 3)

```mermaid
sequenceDiagram
    participant U as User Browser
    participant F as React Frontend
    participant B as FastAPI Backend
    participant D as Supabase PostgreSQL

    U->>F: Enter credentials
    F->>B: POST /auth/login {email, password}
    B->>D: Query user by email
    D-->>B: User record (hashed password)
    B->>B: Verify password (bcrypt)
    alt Valid credentials
        B->>D: Create refresh token record
        B-->>F: 200 {access_token, refresh_token}
        F->>F: Store tokens securely
    else Invalid credentials
        B-->>F: 401 Invalid credentials
    end

    Note over F,B: Subsequent requests
    F->>B: GET /documents (Authorization: Bearer {jwt})
    B->>B: Validate JWT signature + expiration
    alt Valid JWT
        B->>B: Extract user_id, role from claims
        B->>B: Proceed to authorization check
    else Invalid/Expired JWT
        B-->>F: 401 Token expired
        F->>B: POST /auth/refresh {refresh_token}
        B->>D: Validate + rotate refresh token
        B-->>F: 200 {new_access_token, new_refresh_token}
    end
```

### Token Details (Planned)

- **Access token:** JWT, short-lived (15 minutes default), containing `user_id`, `role`, `exp`.
- **Refresh token:** opaque string stored in the database, longer-lived, single-use with rotation.
- **Password hashing:** bcrypt with a configurable work factor.

---

## 8. Per-Request Authorization Flow (Planned — Phase 6)

```mermaid
flowchart TD
    A[Incoming Request] --> B{JWT Present?}
    B -->|No| C[401 Unauthorized]
    B -->|Yes| D{JWT Valid?}
    D -->|No| C
    D -->|Yes| E[Extract user_id + role]
    E --> F{Is Admin?}
    F -->|Yes| G[Access Granted]
    F -->|No| H{Is Document Owner?}
    H -->|Yes| G
    H -->|No| I{Has Active Grant?}
    I -->|No| J[403 Forbidden + Audit]
    I -->|Yes| K{Permission Level Sufficient?}
    K -->|No| J
    K -->|Yes| G
    G --> L[Execute Operation + Audit]
```

The backend verifies access on **every** request; no cached authorization persists beyond an individual call.

---

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

# Authentication (Phase 3)
JWT_SECRET=your-random-jwt-secret-min-32-chars
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

RLS is defense-in-depth, not the primary control. **RLS is not enabled in Phase 2.** The backend currently connects with a single privileged role; there is no per-request database identity. Policy design depends on the Phase 3 authentication model (whether the backend keeps using a privileged role or assumes a per-user database role), so policies are deferred rather than shipped untested.

Planned policies:

| Table | Policy |
|-------|--------|
| `users` | Users can SELECT their own row; administrators can SELECT all |
| `documents` | SELECT allowed if owner, administrator, or holds a grant |
| `document_permissions` | Manageable only by document owner or administrator |
| `audit_events` | INSERT-only for the backend role; no UPDATE/DELETE |
| `refresh_tokens` (Phase 3) | Accessible only by the backend role |

**Important:** if the backend continues to use a privileged role, that role bypasses RLS by design, and application-level authorization remains authoritative. Phase 2 must not be described as having database-enforced access control.

---

## 15. Error Handling and External-Service Failure Behavior

| Scenario | Response | Behavior |
|----------|----------|----------|
| Wasabi S3 unreachable (Phase 4) | 503 Service Unavailable | Upload/download fails cleanly; no partial metadata |
| Supabase DB unreachable | 503 Service Unavailable | Requests fail; no silent fallback |
| JWT missing/expired/invalid (Phase 3) | 401 Unauthorized | Request rejected |
| Permission denied (Phase 6) | 403 Forbidden | Generic message; no metadata leaked; audit event once Phase 7 exists |
| Document not found | 404 Not Found | Generic message; no ownership information |
| File too large (Phase 4) | 413 Payload Too Large | Rejected before storage |
| Invalid file type (Phase 4) | 422 Unprocessable Entity | Rejected with allowed-types list |
| Rate limit exceeded (Phase 3) | 429 Too Many Requests | Client waits and retries |
| Unexpected server error | 500 Internal Server Error | Logged server-side; generic client message |

---

## 16. Health Check

`GET /health` currently reports **process health only**: `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`. It does **not** query PostgreSQL or Wasabi, and a test asserts that it exposes no configuration markers. Database and storage connectivity checks will be added when those integrations exist.
