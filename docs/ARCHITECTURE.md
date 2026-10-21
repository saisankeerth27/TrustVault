# TrustVault — System Architecture

## 1. System Overview

TrustVault is a secure document vault consisting of four primary components: a React single-page application, a FastAPI backend API, a Supabase PostgreSQL database, and Wasabi S3-compatible private object storage. The backend API is intended to be the sole authorization enforcement point — all document access, permission checks, and audit logging will flow through it.

> **Implementation status (Phase 8):** authentication, database-backed roles, rotating refresh sessions, the protected JavaScript frontend, a private validated upload pipeline, an authenticated document library, named-user READ/EDIT grants with immediate revocation, an append-only hash-chained audit trail with signed checkpoints and an administrator audit dashboard, and a threat-mapped security suite are implemented and verified locally. Storage tests use a mocked Wasabi adapter; **live Wasabi connectivity, download, and object-deletion behavior have not been verified**. TrustVault has **no live deployment**, and migrations have **not** been applied to the Supabase project.

### Architecture Diagram

```mermaid
graph TB
    subgraph "Client Zone — Untrusted"
        Browser["User Browser"]
        ReactSPA["React SPA<br/>JavaScript/JSX + Vite<br/>Tailwind CSS + shadcn/ui<br/><i>Hosted on Vercel</i>"]
    end

    subgraph "API Zone — Trust Boundary"
        API["FastAPI Backend<br/>Python 3.13<br/>SQLAlchemy 2.x (sync)<br/><i>Hosted on Render</i>"]
        AuthMW["JWT Auth + Session Checks<br/>Phase 3"]
        PermCheck["Centralized Access Checker<br/>Phase 6 — implemented"]
        AuditSvc["Audit Writer + Hash Chain<br/>Phase 7 — implemented"]
        FileVal["File Validator — Phase 4<br/>implemented"]
        DocMgmt["Document Library + Sharing<br/>Phases 5–6"]
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
    API --- DocMgmt
    API -->|"SQLAlchemy + psycopg 3"| DB
    API -->|"boto3 (mock-tested)"| S3

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
| 4 | Private Wasabi storage and validated uploads | Complete (verified locally with mocked storage; live Wasabi unverified) |
| 5 | Document listing, download proxy, management, and search | Complete (verified locally with mocked storage; live Wasabi unverified) |
| 6 | Named-user READ/EDIT permissions, sharing, immediate revocation | Complete (verified locally with mocked storage; live Wasabi unverified) |
| 7 | Audit write path, hash chain, signed checkpoint, admin activity | Complete (verified locally) |
| 8 | Security tests and threat-model verification | Complete (verified locally; awaiting review) |
| 9 | Complete frontend | Planned |
| 10 | Deployment hardening and end-to-end verification | Planned |
| 11 | Final submission and demo | Planned |

The implemented schema is documented in full in [DATABASE.md](DATABASE.md).

---

## 3. React Frontend Responsibilities

The React SPA runs entirely in the user's browser. It is responsible for:

- **Rendering the UI** — login, authenticated dashboard, document library/details, shared-with-me view, owner permission management, role-gated administrator area, and the administrator audit dashboard.
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

### Document Scoping (implemented — Phases 5–6)
- Owners can list/read their active documents and manage their own metadata, download, deletion, and sharing.
- Users with an active READ or EDIT grant can list/read the document; EDIT also permits metadata updates. Grants do not permit deletion or permission management.
- Administrators can list/read metadata for all active documents for oversight, but cannot download content, edit metadata, delete, or manage permissions unless the owner explicitly grants READ or EDIT.
- Inaccessible and missing IDs both return a generic 404 to limit enumeration. A caller who can see metadata but lacks the requested capability receives 403.
- No document content or storage key is returned in metadata responses.

### Explicit Permissions (implemented — Phase 6)
- Owner-only endpoints grant, list, update, and revoke named-user `READ`/`EDIT` access by recipient email.
- The centralized checker resolves ownership first, then the active grant, then administrator metadata oversight. There is no permission cache: each request reads current database state.
- Updates use revoke-and-regrant, so the prior level remains as history. Revocation is idempotent and effective on the recipient's next request.
- Denials create a typed audit denial event, and successful grant/update/revoke actions append chain events in the same transaction.

### Document Operations
**Upload (implemented — Phase 4):**
- `POST /api/v1/documents/upload` accepts multipart `file`, optional `category`, and optional `description`.
- Requires an active `ADMINISTRATOR` or `DOCUMENT_OWNER`. Ownership comes from the authenticated user; client-supplied owner, storage key, and checksum are ignored.
- Validates the extension, declared MIME type, content signature, filename, empty content, and size. DOCX OOXML structure and TXT encoding are checked. The checksum is computed by the backend.
- Stores with a generated key and commits metadata only after the object upload succeeds. A database failure triggers best-effort object deletion.

**Library, metadata, permissions, download, and soft delete (implemented — Phases 5–6):**
- `GET /api/v1/documents` supports name search, category/owner/date filters, sorting, and bounded pagination. Regular users see owned and actively shared documents; administrators see all active metadata. Name search uses the `pg_trgm` index; wildcard characters are escaped.
- `GET /api/v1/documents/shared-with-me` returns active non-deleted documents with an active grant for the caller, with bounded pagination and sorting.
- `GET /api/v1/documents/{id}` returns safe metadata and effective `access_level` for visible active documents.
- `PATCH /api/v1/documents/{id}` accepts only `name`, `category`, and `description`. Owners and EDIT recipients may update; READ recipients and metadata-only administrators receive 403.
- `GET /api/v1/documents/{id}/download` permits owners, READ recipients, and EDIT recipients, and proxies the private object with safe attachment and no-store headers.
- `DELETE /api/v1/documents/{id}` is owner-only and sets `deleted_at`; the Wasabi object is deleted best-effort after the database commit.
- Permission endpoints are owner-only: `GET/POST /documents/{id}/permissions` and `PATCH/DELETE /documents/{id}/permissions/{permission_id}`. Lists include revoked history.
- Successful and denied actions are written to the append-only audit trail. Mandatory success events share the business transaction; denial events are best-effort.

### Audit Logging (implemented — Phase 7)
- Append one event for each significant authentication, document, permission, and denial action into `audit_events`.
- Maintain a contiguous `chain_index`, previous-event hash, and SHA-256 `event_hash`.
- Expose read-only global-administrator query and integrity endpoints; do not expose admin or owner audit mutation endpoints.
- Never expose UPDATE or DELETE endpoints for audit history.

### Database Access (implemented — Phase 2)
- SQLAlchemy 2.x models with a synchronous engine using the **psycopg 3** driver.
- Alembic migrations as the only DDL path (`backend/alembic/`).
- Lazy engine creation so importing the application does not require `DATABASE_URL`.
- Connection pooling configurable through `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`.

### Error Handling (implemented — Phase 1)
- Structured JSON error responses.
- Sensitive details (stack traces, SQL) are logged server-side and never returned to clients.
- Documented status codes: 400, 401, 403, 404, 409, 411, 413, 415, 422, 429, 500, 503.

---

## 5. Database Architecture (Implemented)

The schema contains five tables. Migrations `0001`–`0003` establish the schema and audit chain sequence. Full column, constraint, and index detail lives in [DATABASE.md](DATABASE.md).

| Table | Purpose |
|-------|---------|
| `users` | Accounts, hashed passwords, role, status, timestamps |
| `refresh_tokens` | Hashed opaque refresh tokens, rotation families, expiry, revocation |
| `documents` | Metadata: owner, name, category, description, storage key, MIME type, size, checksum, soft-delete timestamp |
| `document_permissions` | Per-user, per-document grant history (`READ`/`EDIT`) with revocation timestamps |
| `audit_events` | Append-oriented event records with contiguous chain sequence, action, outcome, JSONB details, and hash-chain columns |

### Design Decisions

- **UUID primary keys** generated by PostgreSQL `gen_random_uuid()`. UUIDs are not a security control; authorization never depends on ID secrecy.
- **Roles and statuses as constrained strings.** `users.role` is checked against `ADMINISTRATOR`, `DOCUMENT_OWNER`, `VIEWER`; `users.status` against `ACTIVE`, `DISABLED`. Constrained strings avoid the migration friction of native PostgreSQL enums while still being validated at the database. Python-side `StrEnum` values live in `app/models/enums.py`.
- **Email normalization.** `users.email` is stored lowercase and must already be lowercase (check constraint), with a unique constraint. Normalization happens before insert; the database guarantees no mixed-case duplicates.
- **Required `password_hash`.** The column is `NOT NULL`; Phase 3 always stores a bcrypt hash, so an account can never exist without a credential.
- **Explicit owner FK.** `documents.owner_id` references `users.id` with `ON DELETE RESTRICT`; a user who owns documents cannot be deleted until ownership is transferred.
- **Internal storage keys only.** `documents.storage_key` is unique, must start with `documents/`, and must not contain a URL scheme. Phase 4 generates keys as `documents/{owner_uuid}/{random_uuid}.{ext}`; the user filename is metadata only.
- **Required checksum.** `documents.checksum` is a required SHA-256 hex string computed by the backend from the received bytes during upload.
- **Soft delete.** `documents.deleted_at` marks deletion without removing history; hard-delete and storage cleanup behavior is defined in Phase 5.
- **Permission history with a single active grant.** A partial unique index (`WHERE revoked_at IS NULL`) allows only one active grant per `(document_id, user_id)`. Revoking sets `revoked_at`; re-granting inserts a new row, preserving audit history. `granted_by` uses `ON DELETE SET NULL`.
- **Owner access is implicit.** Owners are not represented in `document_permissions`; ownership comes from `documents.owner_id`. The permissions table records grants to *other* users.
- **Audit retention by design.** `audit_events.actor_id` and `audit_events.document_id` use `ON DELETE SET NULL` so removing a user or document retains the event. The `action` column is intentionally unconstrained for extensibility; `outcome`, JSON-object details, and SHA-256 hash formats are constrained. A positive unique `chain_index` was added by migration `0003`.

### Deferred Tables

`categories` remains deferred. Category is a nullable `documents.category` column until Phase 5 decides whether a lookup table is warranted. `refresh_tokens` is now implemented by migration `0002`.

### Connection Management

`backend/app/db/session.py` provides a lazily created, cached engine and a `sessionmaker`. The module normalizes any `postgres://`/`postgresql://` URL to `postgresql+psycopg://`, sets `sslmode=require` for Supabase hosts, and disables psycopg server-side prepared statements when the Supabase transaction pooler (port 6543) is used. Pool defaults are `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`, and `pool_recycle=1800`.

The schema is applied only through Alembic. The initial migration `0001_initial_schema` creates the `pg_trgm` extension before its GIN index; downgrade drops the tables but leaves the shared extension installed.

---

## 6. Wasabi Private Storage Responsibilities (Implemented — Phase 4)

Wasabi provides S3-compatible object storage for document content.

- Bucket is **private**; no public access policy or direct frontend access.
- All access goes through the FastAPI backend using `boto3`.
- Server-side settings are `WASABI_ENDPOINT_URL`, `WASABI_REGION`, `WASABI_BUCKET_NAME`, `WASABI_ACCESS_KEY_ID`, and `WASABI_SECRET_ACCESS_KEY`. They are never committed or exposed to Vite.
- The client is configured for the Wasabi endpoint with path-style addressing. Missing configuration maps to 503; storage errors are logged without credentials or internal detail.
- `python -m scripts.check_storage` performs a safe `head_bucket` check for operators.

### File Organization

```
documents/
  {owner_uuid}/
    {random_uuid}.{ext}
```

Storage keys are system-generated; the user-supplied filename is metadata only. The random UUID prevents collisions and does not encode authorization.

### Access Pattern

1. **Upload (implemented):** backend validates → `put_object()` → commits the `documents` row. If the commit fails, the backend attempts `delete_object()`.
2. **Download (implemented):** backend verifies ownership → `get_object()` and streams the body. Presigned URLs are not part of the design.
3. **Delete (implemented):** backend verifies ownership → commits `deleted_at` → attempts `delete_object()`. Cleanup failure is logged and leaves the metadata soft-deleted.

The frontend **never** receives a direct or presigned Wasabi URL. The live bucket policy has not been verified.

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
- **CORS/origin:** exact-origin CORS with credentials (no wildcard) and Origin allow-list checks on auth POSTs; there is no per-session CSRF token.
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

The backend verifies identity and session state on **every** protected request. Role checks use the current database value and fail closed for unknown roles. Phase 6 document routes resolve the accessible set from ownership and active grants: regular users see owned plus shared documents; administrators may read all active metadata. Content and edit capabilities are separately checked against the centralized access policy. Missing/unrelated documents return a generic 404; visible-but-insufficient operations return 403.

## 9. Upload, Library, Download, and Sharing Flows (Implemented — Phases 4–6)

### Upload (implemented)

1. Client sends `POST /api/v1/documents/upload` with multipart `file`, optional `category`, and optional `description`.
2. Backend validates the JWT/session and requires an active owner or administrator role.
3. File validation: size limit with a pre-routing `Content-Length` check before body parsing or authentication (413), required length for uploads (411), extension/MIME allow-list, magic-byte/signature check, filename safety including Unicode format controls, empty-file rejection, DOCX structure and expansion limits, and TXT encoding.
4. Backend computes SHA-256, generates `documents/{owner_uuid}/{random_uuid}.{ext}`, uploads to Wasabi, then commits the `documents` row.
5. The response contains safe metadata only; it excludes `storage_key` and all credentials.
6. If storage fails, no database row is created and the response is a generic 503. If the database commit fails after upload, object deletion is attempted and a generic 500 is returned. Cleanup is best-effort, not transactional.
7. `DOCUMENT_UPLOAD` is appended in the same transaction as the metadata row; a failed audit write rolls back the row and returns a generic 500.

### Library, metadata update, and deletion (implemented — Phases 5–6)

1. Client sends `GET /api/v1/documents` with optional search/filter/sort/page parameters.
2. Backend builds the visible scope from ownership and active grants (or all active metadata for administrators), then applies literal escaped name search, category/owner/date filters, a stable sort, and bounded pagination.
3. Missing and inaccessible document IDs both return a generic 404. Visible documents with insufficient capability return 403.
4. `PATCH` accepts only mutable metadata; owners and EDIT recipients may update, while READ recipients and metadata-only administrators are denied. Protected storage and integrity fields are rejected with 422.
5. `DELETE` is owner-only and commits `deleted_at` first, then attempts Wasabi object deletion. The object cleanup is best-effort and not part of the database transaction.
6. `DOCUMENT_METADATA_UPDATE` and `DOCUMENT_DELETE` share the protected transaction. Denials append typed denial events best-effort and preserve the intended 403/404.

### Download (implemented)

1. Client sends `GET /api/v1/documents/{id}/download` with the in-memory bearer token.
2. Backend validates the JWT/session and resolves OWNER, EDIT, or READ capability from current database state.
3. Backend fetches from Wasabi and streams with the stored MIME type, `Content-Disposition: attachment`, `Content-Length`, `Cache-Control: private, no-store`, and `X-Content-Type-Options: nosniff`.
4. Storage not-found maps to 404; configuration/operation failures map to generic 503. No storage key or presigned URL is exposed.
5. A successful download appends `DOCUMENT_DOWNLOAD` in the request transaction; an authorization denial appends `DOCUMENT_DOWNLOAD_DENIED` best-effort.

### Shared-document listing (implemented)

1. Client sends `GET /api/v1/documents/shared-with-me`.
2. Backend joins active, non-revoked grants to active, non-deleted documents for the authenticated user.
3. Only safe metadata and the effective `access_level` are returned; administrator status alone does not add rows to this view.
4. Revoked and deleted documents disappear immediately. Responses are `Cache-Control: no-store`.

---

## 10. Permission Granting and Immediate Revocation (Implemented — Phase 6)

### Granting

1. Owner sends `POST /api/v1/documents/{id}/permissions` with `{email, permission: "READ"|"EDIT"}`.
2. Backend loads the active document and requires the `MANAGE_PERMISSIONS` capability, which only `OWNER` holds.
3. Backend normalizes the email, requires an active registered recipient, and rejects the owner as a recipient.
4. A new active grant returns 201. Repeating the same active level returns the existing row with 200. Requesting a different active level returns 409 and instructs the owner to update instead.
5. Regranting after revocation inserts a new row; the partial unique index preserves one active grant while retaining history.
6. A new grant appends `PERMISSION_GRANT` in the same transaction. Same-level no-ops do not create a duplicate state-change event.

### Updating

1. Owner sends `PATCH /api/v1/documents/{id}/permissions/{permission_id}` with the new `READ`/`EDIT` level.
2. Backend verifies ownership and that the active permission belongs to the document.
3. A changed level sets `revoked_at` on the existing row and inserts a replacement, returning the active replacement. An unchanged level returns the existing row.
4. A changed level appends `PERMISSION_UPDATE` in the same transaction; cross-document permission IDs return generic 404 and append `PERMISSION_CHANGE_DENIED` best-effort.

### Revoking

1. Owner sends `DELETE /api/v1/documents/{id}/permissions/{permission_id}`.
2. Backend verifies ownership and document scope, then sets `revoked_at` on the row.
3. Revocation is idempotent and returns 204. The row remains visible in permission history. An actual revocation appends `PERMISSION_REVOKE` in the same transaction.
4. **Revocation is immediate** — the next content or metadata request from the revoked user is denied.

### Capability Model

| Access level | Metadata | Read/download | Edit | Delete | Manage permissions |
|--------------|:--------:|:-------------:|:----:|:------:|:------------------:|
| `OWNER` | Yes | Yes | Yes | Yes | Yes |
| `EDIT` | Yes | Yes | Yes | No | No |
| `READ` | Yes | Yes | No | No | No |
| `ADMINISTRATOR` | Yes | No | No | No | No |

### Critical Notes

- No caching layer may serve stale permission data; checks always read current database state.
- **Files already downloaded before revocation cannot be recalled.** This is a documented limitation.
- `EDIT` implies `READ`. Only owners manage permissions; administrators do not gain owner powers.
- Audit writes are part of the mutation transaction for successful actions. A failed mandatory audit write rolls back the mutation; denial auditing is best-effort and cannot change the denial outcome.

---

## 11. Audit Model and Integrity Protection (Implemented — Phase 7)

### Event Actions

`app/models/enums.py` defines the known actions: `USER_REGISTERED`, `LOGIN_SUCCESS`, `LOGIN_FAILURE`, `LOGOUT`, `DOCUMENT_UPLOAD`, `DOCUMENT_METADATA_UPDATE`, `DOCUMENT_DOWNLOAD`, `DOCUMENT_DELETE`, `PERMISSION_GRANT`, `PERMISSION_UPDATE`, `PERMISSION_REVOKE`, `DOCUMENT_ACCESS_DENIED`, `DOCUMENT_UPLOAD_DENIED`, `DOCUMENT_DOWNLOAD_DENIED`, `DOCUMENT_EDIT_DENIED`, `DOCUMENT_DELETE_DENIED`, `PERMISSION_CHANGE_DENIED`, and `AUDIT_ACCESS_DENIED`. The database column remains unconstrained so later phases can add actions without a migration.

### Record Structure (`audit_events`)

| Column | Meaning |
|--------|---------|
| `id` | UUID primary key |
| `chain_index` | Positive, unique, contiguous append sequence |
| `actor_id` | Acting user (nullable, `ON DELETE SET NULL`) |
| `document_id` | Target document (nullable, `ON DELETE SET NULL`) |
| `action` | Event action (extensible string) |
| `outcome` | `SUCCESS`, `DENIED`, or `FAILURE` |
| `occurred_at` | Server-side UTC timestamp |
| `request_id` | Validated or generated correlation id |
| `details` | Sanitized JSONB object with event-specific and request metadata |
| `previous_hash` | SHA-256 of the previous event (null for the first event) |
| `event_hash` | SHA-256 of this event |

`details` automatically includes the validated request ID, direct socket client IP, and length-limited user-agent when available, plus an actor-name snapshot. Sensitive keys such as passwords, tokens, cookies, authorization headers, session IDs, content, and payloads are rejected. Metadata depth, item count, and total size are bounded.

### Hash Chain

The writer takes a PostgreSQL advisory transaction lock, reads the current chain head, and appends `chain_index + 1`. The hashed payload is canonical JSON with sorted keys, compact separators, UTF-8 encoding, and a versioned schema (`trustvault-audit-event-v1`). Verification recomputes every event hash, checks contiguous indexes, and checks each previous-hash link.

Successful protected mutations append the audit event in the same transaction; an audit failure raises a generic 500 and rolls back the business change. Authorization denials use a best-effort commit so audit unavailability never converts a denial into success.

### Administrator API and UI

- `GET /api/v1/admin/audit-events` filters by actor ID, document ID, action, outcome, and inclusive UTC date range, with newest-first pagination.
- `GET /api/v1/admin/audit-integrity` returns chain and checkpoint status.
- Both endpoints require a global `ADMINISTRATOR`. Non-admin access returns 403 and appends `AUDIT_ACCESS_DENIED` best-effort.
- `/admin/audit` provides filters, event detail expansion, pagination, and an integrity panel. There is no owner-scoped audit view, audit export, or audit mutation endpoint.
- Audit reads and integrity checks are not themselves audited.

### Signed Checkpoints

Checkpoint creation signs the schema, creation time, event count, last chain index, and last event hash with HMAC-SHA256 using `AUDIT_CHECKPOINT_SIGNING_KEY`. The file is written atomically to the absolute `AUDIT_CHECKPOINT_PATH` and never exposes the key. Creation refuses to replace an invalid checkpoint or move backward to an older chain head. Statuses are `VALID`, `STALE`, `MISSING`, `UNCONFIGURED`, `UNAVAILABLE`, and `INVALID`; the overall status distinguishes `VERIFIED`, valid-chain-with-stale/missing checkpoint, and invalid.

`python -m scripts.audit_integrity` verifies the chain and checkpoint; `--create-checkpoint` writes a new signed checkpoint after verifying the chain. Exit codes are `0` verified/written, `1` attention required, and `2` configuration error.

### Limitations of a Same-Database Hash Chain

A hash chain stored in the same database it protects does **not** fully protect against a privileged database administrator: an attacker could modify records and recompute subsequent hashes so the local chain still verifies. The signed checkpoint detects changes relative to the last trusted checkpoint, but a same-host checkpoint file can be deleted by the same attacker. Events appended after the latest checkpoint and then deleted are not detectable by that checkpoint, and concurrent checkpoint writers are not serialized. Run checkpoint creation as a single scheduled job. An independently controlled append-only checkpoint store and scheduled checkpoint publication are still required to make privileged tampering reliably detectable. This control does not make tampering impossible.

### Application Enforcement

- The application never issues `UPDATE` or `DELETE` on `audit_events`.
- No API exposes audit modification or deletion.
- A database immutability trigger is deliberately **not** added because it would conflict with the `ON DELETE SET NULL` retention foreign keys. The backend's single database role is not restricted from direct table changes; hash-chain and checkpoint verification provide detection, not prevention.

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
    BE -->|"boto3 (Phase 4, live unverified)"| WS
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

# Wasabi S3 (Phase 4, implemented; live connection unverified)
WASABI_ENDPOINT_URL=https://s3.us-east-1.wasabisys.com
WASABI_REGION=us-east-1
WASABI_BUCKET_NAME=trustvault-documents
WASABI_ACCESS_KEY_ID=your-wasabi-access-key-id
WASABI_SECRET_ACCESS_KEY=your-wasabi-secret-access-key
MAX_UPLOAD_SIZE_BYTES=10485760
ALLOWED_UPLOAD_EXTENSIONS=pdf,txt,docx,png,jpg,jpeg

# Signed audit checkpoint (optional; configure both or neither)
AUDIT_CHECKPOINT_SIGNING_KEY=replace-with-at-least-32-random-characters
AUDIT_CHECKPOINT_PATH=/absolute/persistent/path/audit-checkpoint.json

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

### Primary Authorization: Application Logic (Authentication, Documents, and Grants Implemented)

The FastAPI backend is the primary enforcement point. Every protected endpoint checks authentication and role. Phase 6 document endpoints resolve metadata visibility and content/edit/delete/share capabilities from current ownership and active grants. Missing/unrelated resources return 404; insufficient capability on a visible resource returns 403.

### Secondary Defense: Row-Level Security (Deferred)

RLS is defense-in-depth, not the primary control. **RLS is not enabled.** Phase 3 keeps the backend on a single privileged database role; authentication issues application-level identities, not per-request PostgreSQL identities. Because that role bypasses RLS, application authorization remains authoritative and policies are deferred until they can be tested meaningfully.

Planned policies:

| Table | Policy |
|-------|--------|
| `users` | Users can SELECT their own row; administrators can SELECT all |
| `documents` | SELECT allowed if owner, administrator, or holds a grant |
| `document_permissions` | Manageable only by the document owner |
| `audit_events` | INSERT-only for the backend role; no UPDATE/DELETE |
| `refresh_tokens` (Phase 3) | Accessible only by the backend role |

**Important:** because the backend uses a privileged role, that role bypasses RLS by design, and application-level authorization remains authoritative. TrustVault must not be described as having database-enforced access control.

---

## 15. Error Handling and External-Service Failure Behavior

| Scenario | Response | Behavior |
|----------|----------|----------|
| Wasabi unreachable or misconfigured (Phases 4–6) | 503 Service Unavailable | Upload fails with no metadata row; download fails without content; generic client message |
| Metadata commit fails after upload (Phase 4) | 500 Internal Server Error | Best-effort object deletion; generic client message |
| Object cleanup fails after soft delete (Phase 5) | 204 No Content | Metadata remains soft-deleted; cleanup failure logged for reconciliation |
| Object missing during download (Phase 5) | 404 Not Found | Generic unavailable message; no storage details |
| Supabase DB unreachable | 503 Service Unavailable | Requests fail; no silent fallback |
| JWT missing/expired/invalid, revoked session, or disabled account | 401 Unauthorized | Request rejected |
| Permission denied / wrong role or insufficient grant (Phases 4–7) | 403 Forbidden | Generic message; no document metadata leaked; denial audit event attempted best-effort |
| Mandatory audit write fails during a protected mutation (Phase 7) | 500 Internal Server Error | Business transaction rolls back; generic client message; no secret or chain details exposed |
| Audit integrity check fails | 200 with `INVALID` status | Administrator sees chain/checkpoint status; no automatic repair |
| Document not found | 404 Not Found | Generic message; no ownership information |
| File too large (Phase 4) | 413 Payload Too Large | Rejected before storage |
| Invalid/unsupported file type or signature (Phase 4) | 415 Unsupported Media Type | Rejected with a generic type message |
| Invalid upload metadata, empty file, or malformed filename (Phase 4) | 400/422 | Rejected before storage; details limited to validation feedback |
| Auth rate limit exceeded | 429 Too Many Requests | `Retry-After` returned; client waits and retries |
| Unexpected server error | 500 Internal Server Error | Logged server-side; generic client message |

---

## 16. Health Check

`GET /health` currently reports **process health only**: `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`. It does **not** query PostgreSQL or Wasabi, and a test asserts that it exposes no configuration markers. Storage operators can use `python -m scripts.check_storage`; audit operators can use `python -m scripts.audit_integrity`. Health integration remains deferred.

---

## 17. Phase 3 Implementation Notes (Verified)

- **Auth endpoints:** `register`, `login`, `refresh`, `logout`, and `me` are implemented under `/api/v1/auth`.
- **Session design:** access tokens stay in frontend memory; refresh tokens are hashed in PostgreSQL and rotated through an HttpOnly cookie. Family reuse detection revokes the family.
- **Immediate revocation:** protected requests check the user's status and active refresh family on every call, so logout/disablement takes effect without waiting for JWT expiry.
- **Role model:** `ADMINISTRATOR`, `DOCUMENT_OWNER`, and `VIEWER` are stored in PostgreSQL. Public registration creates Viewers only; elevated roles come from the provisioning CLI.
- **CSRF and CORS:** auth POSTs enforce an exact Origin allow-list, CORS never combines credentials with a wildcard, and the refresh cookie is path-scoped. A per-session CSRF token is not implemented.
- **Rate limiting:** an in-memory sliding window limits login/register attempts per process. A multi-instance deployment requires a shared store.
- **Tests:** 55 backend tests covered Phase 3 auth flows at the time; the suite now has 213 tests. It uses an ephemeral PostgreSQL instance.
- **Not implemented at Phase 3 completion:** document authorization, audit writes, RLS, MFA, account lockout, idle timeouts, and production deployment verification.

---

## 18. Phase 4 Implementation Notes (Verified with Mocked Storage)

- **Frontend:** migrated from TypeScript/TSX to JavaScript/JSX, removed TypeScript dependencies and configs, and added an upload form. Owner/Admin users can select a file, choose a category, add a description, and see progress/errors/success metadata. Viewers see a restriction notice.
- **Upload endpoint:** `POST /api/v1/documents/upload`; requires `ADMINISTRATOR` or `DOCUMENT_OWNER`, enforces active sessions, and returns 201 with safe metadata.
- **Validation:** extension/MIME/signature allow-list, filename safety, empty-file rejection, 10 MiB default limit, DOCX package checks, and UTF-8 TXT checks. No antivirus scanning.
- **Metadata:** backend-generated owner, storage key, MIME type, byte size, and SHA-256 checksum; `documents` table only, no new migration.
- **Storage:** `boto3` S3 client with Wasabi endpoint and path-style addressing, lazy cached service, safe error classes, and no secret logging.
- **Consistency:** object first, metadata second; database failure attempts object deletion. No distributed transaction.
- **Tests at Phase 4 completion:** 107 backend tests passed, including upload authorization, validation, metadata, storage failure, persistence cleanup, config validation, and secret-safe logging. Frontend lint/build passed; storage tests use a fake adapter.
- **Not implemented/verified at Phase 4 completion:** live Wasabi bucket policy/connectivity, download/listing, permission grants, audit writes, RLS, and deployment.

---

## 19. Phase 5 Implementation Notes (Verified with Mocked Storage)

- **API surface:** list/search, detail, metadata update, streamed download, and soft delete are implemented under `/api/v1/documents`; upload remains unchanged.
- **List query:** `q`, `category`, `owner_id`, `created_from`, `created_to`, `page`, `page_size`, `sort_by`, and `order`. Page size is 1–100; date filters are inclusive UTC days; sorting includes a stable document-ID tie-breaker.
- **Scope at Phase 5 completion:** owners saw/managed only their own active documents; administrators saw all active metadata but remained excluded from other owners' download/update/delete; viewers had no document access until Phase 6 grants.
- **Search safety:** name search uses parameterized `ILIKE` with escaped `\`, `%`, and `_`; sort columns are a fixed allow-list. The `pg_trgm` index supports partial name search.
- **Metadata update at Phase 5 completion:** only `name`, `category`, and `description` were accepted, and only the owner could update. Phase 6 extends updates to EDIT recipients. Extra/protected fields, blank names, empty patches, and null names return 422.
- **Download at Phase 5 completion:** owner-only backend proxy from Wasabi; no presigned URL or storage key. Attachment filenames are RFC 5987-encoded with an ASCII fallback, control characters are neutralized, and responses set no-store/nosniff headers.
- **Deletion:** soft deletion retains metadata and excludes the row from all normal reads. The Wasabi object is removed best-effort after commit; cleanup failure is logged but does not roll back deletion.
- **Frontend at Phase 5 completion:** `/documents` provides search/filter/sort/pagination and an upload panel; `/documents/:documentId` provides metadata, owner-only download/edit/delete, and read-only administrator review.
- **Tests:** 127 backend tests passed at Phase 5 completion, including management authorization, filters, pagination, IDOR behavior, protected fields, download headers/failures, soft deletion, and cleanup failure. Frontend lint/build passed.
- **Not implemented/verified at Phase 5 completion:** live Wasabi download/delete, per-document grants, audit writes, RLS, malware scanning, and deployment.

---

## 20. Phase 6 Implementation Notes (Verified with Mocked Storage)

- **Central policy:** `app/services/document_access.py` resolves `OWNER`, `EDIT`, `READ`, or `ADMINISTRATOR` from current ownership and active grants on every request. Capabilities are `METADATA`, `READ`, `EDIT`, `DELETE`, and `MANAGE_PERMISSIONS`.
- **API surface:** `GET /documents/shared-with-me` plus owner-only `GET/POST /documents/{id}/permissions` and `PATCH/DELETE /documents/{id}/permissions/{permission_id}`.
- **Access levels:** document responses now include a required `access_level`, allowing the frontend and API consumers to hide unavailable actions without making security decisions.
- **Grant semantics:** recipients must be active registered users identified by normalized email. Owner self-grants return 409. Same-level grants are idempotent with 200; conflicting levels return 409.
- **History:** level changes revoke the old row and insert a replacement; revocation is idempotent and retains the row. The existing partial unique index guarantees one active grant.
- **Listing:** regular document lists include owned and actively shared documents; the shared view excludes revoked grants and soft-deleted documents. Administrators retain all active metadata but gain no content rights by role.
- **Frontend:** access-level badges drive actions; owners get a sharing page with grant, update, revoke confirmation, and history. `/shared-with-me` lists direct shares. READ can download, EDIT can download and edit, and only OWNER can delete or manage access.
- **Tests:** 146 backend tests pass at Phase 6 completion (19 Phase 6 tests), covering role boundaries, owner-only management, idempotency/conflicts, forged identity fields, history retention, immediate revocation, shared listing exclusions, access levels, and metadata-only administrator behavior. Frontend lint/build pass.
- **Not implemented/verified at Phase 6 completion:** live Wasabi behavior, RLS, malware scanning, and deployment.

---

## 21. Phase 7 Implementation Notes (Verified Locally with Mocked Storage)

- **Audit writer:** `app/services/audit.py` sanitizes details, attaches validated request ID/direct client IP/user-agent context, takes an advisory transaction lock, and appends contiguous chain events with canonical SHA-256 hashes.
- **Migration:** `0003_add_audit_chain_index.py` adds nullable `chain_index`, deterministically backfills existing rows by `occurred_at, id`, then enforces `NOT NULL`, positive values, and uniqueness.
- **Event integration:** registration, login success/failure, logout, upload, metadata update, download, delete, grants, updates, revocations, and denial boundaries append typed events. Success writes share the protected transaction; denials use best-effort commits.
- **Integrity:** `app/services/audit_integrity.py` verifies chain continuity and hashes and validates HMAC-SHA256 signed checkpoint files. Checkpoint writing is atomic and uses an absolute path plus at least a 32-character secret.
- **Administrator surface:** global-admin-only `GET /api/v1/admin/audit-events` and `GET /api/v1/admin/audit-integrity`; no owner audit view, mutation endpoint, or export in this phase.
- **Request context:** `X-Request-ID` is validated or replaced with a 32-character UUID hex and echoed. Client IP uses the direct ASGI socket, not untrusted forwarded headers.
- **Frontend:** `/admin/audit` provides action/outcome/actor/document/date filters, pagination, detail expansion, denied indicators, and a chain/checkpoint integrity panel with refresh.
- **Tests:** 158 backend tests pass (12 Phase 7 tests), including event coverage, admin authorization/filtering, tamper/removal detection, checkpoint staleness/truncation/signature failure, mandatory-audit rollback, metadata sanitization, and request-ID safety. Frontend lint/build pass; the build retains the existing chunk-size warning.
- **Not implemented/verified:** live Wasabi behavior, live Supabase/deployment, scheduled independent checkpoint publication, audit export, owner-scoped audit views, RLS, and malware scanning.

---

## 22. Phase 8 Implementation Notes (Verified Locally)

- **Threat-mapped suite:** `backend/tests/test_security.py` contains 46 security cases named by threat-model section, plus focused request-limit tests in `backend/tests/test_request_limits.py`, covering every scenario in `THREATS.md`.
- **Cross-user denial:** User B is denied GET, download, edit/PATCH, and DELETE for User A's document without a grant. After a READ grant, User B can read and download but cannot edit or delete. Revocation restores immediate 404 denial for all four operations, and the grant/revoke/denial actions are audited.
- **Object-level authorization:** Existing-but-unrelated UUIDs and random missing UUIDs return the same generic 404 body, and denial responses omit document names, owner identity, storage keys, and checksums.
- **Privilege boundaries:** Registration rejects role injection, a validly signed token with a forged administrator role claim cannot escalate a Viewer, and administrator identity does not grant content, edit, delete, or permission-management access. Denials append the appropriate audit events.
- **Upload and path attacks:** Executable, MIME/signature-mismatched, missing-content-type, empty, malformed multipart, and broken-document uploads are rejected before storage. DOCX member-count and uncompressed-size limits are unit-tested. Traversal and absolute filenames return 400, control and Unicode format-control characters (including bidi overrides) cannot reach server-generated storage keys, and client filenames never become storage paths.
- **Audit tampering:** POST, PUT, PATCH, and DELETE against both administrator audit endpoints return 405; event-specific mutation paths return 404. Audit row counts and the latest event remain unchanged.
- **Token and brute-force defenses:** Expired and signature-tampered access tokens return 401, logout invalidates a previously issued access token through the active-session check, and the login limiter returns 429 with `Retry-After` without echoing the email or password.
- **Denial of service:** An unauthenticated oversized upload is rejected with 413 before request-body parsing or authentication, uploads without `Content-Length` return 411, and invalid/duplicate lengths return 400. DOCX expansion limits are tested.
- **Account status and audit role:** Disabled users are denied document and administrator audit endpoints, and a validly signed administrator role claim cannot read audit data when the database role is Viewer.
- **Coverage:** The full 213-test suite passes with 89% combined statement/branch coverage across 2,175 statements and 426 branches. Authorization and document services are at 77%-88%, the administrator audit API at 96%, and dependency, application, error, and audit-schema modules at 100%.
- **CI:** `.github/workflows/backend-tests.yml` runs the full suite and coverage on backend pushes and pull requests. The workflow has not yet run on GitHub.
- **Honest limitations:** RLS is still not enabled, so there are no database RLS policy tests; application-level authorization remains the primary boundary and is verified directly. Malware scanning, live Wasabi behavior, Supabase migration, and deployment remain outstanding. The security suite does not prove absence of vulnerabilities, and coverage is a diagnostic rather than a security guarantee.
