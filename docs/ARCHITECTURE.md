# TrustVault — System Architecture

## 1. System Overview

TrustVault is a secure document vault consisting of four primary components: a React single-page application, a FastAPI backend API, a Supabase PostgreSQL database, and Wasabi S3-compatible private object storage. The backend API is the sole authorization enforcement point — all document access, permission checks, and audit logging flow through it.

### Architecture Diagram

```mermaid
graph TB
    subgraph "Client Zone — Untrusted"
        Browser["User Browser"]
        ReactSPA["React SPA<br/>TypeScript + Vite<br/>Tailwind CSS + shadcn/ui<br/><i>Hosted on Vercel</i>"]
    end

    subgraph "API Zone — Trust Boundary"
        API["FastAPI Backend<br/>Python 3.11+<br/>SQLAlchemy 2.x<br/><i>Hosted on Render</i>"]
        AuthMW["JWT Auth Middleware"]
        PermCheck["Permission Checker"]
        AuditSvc["Audit Service"]
        FileVal["File Validator"]
    end

    subgraph "Data Zone — Trusted"
        DB["Supabase PostgreSQL<br/>RLS Enabled"]
        S3["Wasabi S3<br/>Private Bucket"]
    end

    Browser -->|"HTTPS"| ReactSPA
    ReactSPA -->|"HTTPS REST API<br/>Authorization: Bearer JWT"| API
    API --- AuthMW
    API --- PermCheck
    API --- AuditSvc
    API --- FileVal
    API -->|"SQLAlchemy<br/>asyncpg"| DB
    API -->|"boto3<br/>S3 SDK"| S3

    style Browser fill:#f9f,stroke:#333
    style ReactSPA fill:#bbf,stroke:#333
    style API fill:#fda,stroke:#333
    style DB fill:#bfb,stroke:#333
    style S3 fill:#bfb,stroke:#333
```

### Key Principle

> **Hiding a frontend UI element is NOT authorization.** The backend must independently verify every request. If a button is hidden but the API endpoint is accessible, that is a security vulnerability.

---

## 2. React Frontend Responsibilities

The React SPA runs entirely in the user's browser. It is responsible for:

- **Rendering the UI** — login, registration, document management, permission management, and audit log views.
- **Client-side routing** — Single-page navigation via React Router.
- **Client-side form validation** — For user experience only. All validation is re-performed server-side.
- **API communication** — All data interactions go through the FastAPI backend via HTTPS REST calls.
- **JWT management** — Stores the access token securely (httpOnly cookie preferred; falls back to memory). Attaches the JWT to every API request.
- **UI state management** — Loading states, error messages, and user feedback.

**The frontend NEVER:**
- Connects directly to the database.
- Connects directly to Wasabi S3.
- Makes authorization decisions. Frontend controls (disabled buttons, hidden menus) are UX convenience, not security.
- Stores secrets or API keys (other than the backend URL).

---

## 3. FastAPI Backend Responsibilities

The backend is the **sole enforcement point** for security. It is responsible for:

### Authentication
- User registration with password hashing (bcrypt).
- Login with credential verification, returning JWT access token + refresh token.
- JWT validation middleware on all protected endpoints.
- Refresh token rotation (old refresh token invalidated on use).
- Rate limiting on `/auth/login` and `/auth/register`.

### Authorization
- Every request to a document endpoint passes through the permission checker.
- The permission checker queries `document_permissions` to verify the requesting user has the required level (READ or EDIT) for the target document.
- Administrators have implicit access to all documents.
- Document owners have implicit full access to their own documents.
- If authorization fails → 403 Forbidden response + denied-access audit record.

### Document Operations
- Upload: receive file, validate (type, size, filename), store in Wasabi S3 with UUID key, create metadata record in PostgreSQL.
- Download: verify permission, fetch from Wasabi S3, stream to client. Never expose direct S3 URLs.
- List/Search: query PostgreSQL with permission filtering. Users only see documents they can access.
- Update metadata: verify ownership/permission, update record.
- Delete: verify ownership, remove from S3, mark as deleted in metadata.

### Audit Logging
- Create an audit record for every significant action (see MR-6).
- Maintain hash-chain integrity (each record hashes the previous).
- Expose read-only query endpoints for administrators and document owners.
- Never expose UPDATE or DELETE endpoints for audit records.

### Database Access
- SQLAlchemy 2.x with async sessions via `asyncpg`.
- Alembic for schema migrations.
- Connection pooling configured for production load.

### Error Handling
- Returns structured JSON error responses.
- Sensitive details (stack traces, SQL queries) are logged server-side but never returned to the client.
- Appropriate HTTP status codes: 400, 401, 403, 404, 409, 422, 429, 500, 503.

---

## 4. Supabase PostgreSQL Responsibilities

### Schema

The database stores:

| Table                  | Purpose                                             |
|------------------------|-----------------------------------------------------|
| `users`                | User accounts, hashed passwords, roles              |
| `documents`            | Document metadata (name, category, owner, storage key, timestamps) |
| `document_permissions` | Per-user, per-document access grants (READ/EDIT)     |
| `audit_logs`           | Immutable event records with hash chain              |
| `categories`           | Document categorization                              |
| `refresh_tokens`       | Refresh token tracking for rotation                  |

### Row-Level Security (RLS)

RLS is a **defense-in-depth layer**, not the primary authorization mechanism. The primary authorization is enforced in FastAPI application logic.

Planned RLS policies:
- `users`: Users can read their own profile. Admins can read all.
- `documents`: Rows visible only if user is owner, admin, or has a permission grant.
- `document_permissions`: Rows manageable only by document owner or admin.
- `audit_logs`: INSERT only. No UPDATE or DELETE for any role including service role in application context.

**Important:** The backend connects with the Supabase service role key, which bypasses RLS. This is intentional — the backend enforces its own authorization logic. RLS provides a safety net against bugs or SQL injection.

### Migrations

Schema changes are managed exclusively through Alembic migrations. No manual DDL changes in production.

---

## 5. Wasabi Private Storage Responsibilities

Wasabi provides S3-compatible object storage for document file content.

### Configuration
- Bucket is **private** — no public access policy.
- All access goes through the FastAPI backend using `boto3`.
- Credentials (`WASABI_ACCESS_KEY`, `WASABI_SECRET_KEY`) are stored in environment variables on Render.

### File Organization
```
documents/
  {document_uuid}/
    {version}/
      {sanitized_filename}
```

Files are stored with system-generated UUID-based paths. The original user-supplied filename is stored in database metadata only.

### Access Pattern
1. **Upload:** Backend receives file → validates → uploads to Wasabi via `boto3.put_object()` → records storage key in database.
2. **Download:** Backend verifies user permission → fetches file from Wasabi via `boto3.get_object()` → streams to client. Alternatively, generates a short-lived presigned URL (valid for seconds, not minutes).
3. **Delete:** Backend verifies ownership → deletes from Wasabi → updates database metadata.

The frontend **never** receives a direct Wasabi URL.

---

## 6. Authentication Flow

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

### Token Details
- **Access token:** JWT, short-lived (15 minutes default). Contains `user_id`, `role`, `exp`.
- **Refresh token:** Opaque string, stored in database, longer-lived (7 days default). Single-use with rotation.
- **Password hashing:** bcrypt with configurable work factor.

---

## 7. Per-Request Authorization Flow

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
    H -->|No| I{Has Permission Grant?}
    I -->|No| J[403 Forbidden + Audit]
    I -->|Yes| K{Permission Level Sufficient?}
    K -->|No| J
    K -->|Yes| G
    G --> L[Execute Operation + Audit]
```

**Critical rule:** The backend verifies access on **every** request. There is no session-level or cached authorization that persists beyond individual API calls.

---

## 8. Upload Flow

1. Client sends `POST /documents/upload` with multipart file + metadata (name, category).
2. Backend middleware validates JWT → extracts user identity.
3. Backend checks: Is user an Owner or Administrator?
4. File validation:
   - File size within configured maximum (e.g., 50 MB).
   - MIME type on the allow-list (PDF, DOCX, XLSX, PNG, JPG, TXT, etc.).
   - Magic bytes match claimed MIME type.
   - Filename sanitized (no path traversal, null bytes, excessive length).
5. Backend generates UUID-based storage key.
6. Backend uploads file to Wasabi S3 via `boto3`.
7. On S3 success: backend creates `documents` record in PostgreSQL.
8. Backend creates audit record: `DOCUMENT_UPLOAD`.
9. Returns document metadata (id, name, category, created_at) to client.
10. On any failure: no partial records are left in database or S3.

---

## 9. Download Flow

1. Client sends `GET /documents/{id}/download`.
2. Backend validates JWT.
3. Backend queries document metadata from PostgreSQL.
4. Backend checks permission:
   - Admin → allowed.
   - Document owner → allowed.
   - User has READ or EDIT grant → allowed.
   - Otherwise → 403 + audit record (`ACCESS_DENIED`).
5. Backend fetches file from Wasabi S3 using the stored storage key.
6. Backend streams file to client with appropriate `Content-Type` and `Content-Disposition` headers.
7. Backend creates audit record: `DOCUMENT_DOWNLOAD`.

---

## 10. Permission Granting and Immediate Revocation

### Granting

1. Document owner sends `POST /documents/{id}/permissions` with `{user_id, level: "READ"|"EDIT"}`.
2. Backend verifies caller is the document owner (or admin).
3. Backend creates a `document_permissions` record.
4. Backend creates audit record: `PERMISSION_GRANTED`.
5. Target user can immediately access the document.

### Revoking

1. Document owner sends `DELETE /documents/{id}/permissions/{user_id}`.
2. Backend verifies caller is the document owner (or admin).
3. Backend deletes the `document_permissions` record.
4. Backend creates audit record: `PERMISSION_REVOKED`.
5. **Revocation is immediate** — the next request from the revoked user will receive 403.

### Critical Notes

- No caching layer may serve stale permission data. Permission checks always query the current database state.
- **Files already downloaded before revocation cannot be recalled.** Once a user has a local copy, revocation does not delete it. This is documented as a known limitation.
- EDIT permission includes READ capability. A user with EDIT can read, download, and modify.
- Only owners and admins can manage permissions. Viewers cannot re-share.

---

## 11. Audit Event Creation and Integrity Protection

### Event Types

| Event Type           | Trigger                          |
|----------------------|----------------------------------|
| `USER_REGISTERED`    | New user account created         |
| `USER_LOGIN`         | Successful login                 |
| `USER_LOGIN_FAILED`  | Failed login attempt             |
| `DOCUMENT_UPLOAD`    | Document uploaded                |
| `DOCUMENT_DOWNLOAD`  | Document downloaded              |
| `DOCUMENT_VIEW`      | Document metadata viewed         |
| `DOCUMENT_EDIT`      | Document metadata updated        |
| `DOCUMENT_DELETE`    | Document deleted                 |
| `PERMISSION_GRANTED` | Permission granted to user       |
| `PERMISSION_REVOKED` | Permission revoked from user     |
| `ACCESS_DENIED`      | Unauthorized access attempt      |

### Record Structure

Each audit record contains:
- `id` — UUID primary key
- `event_type` — One of the types above
- `user_id` — Acting user
- `document_id` — Target document (nullable for auth events)
- `target_user_id` — Affected user (for permission events)
- `timestamp` — Server-side UTC timestamp
- `ip_address` — Client IP
- `user_agent` — Client user agent string
- `details` — JSON field with event-specific data
- `previous_hash` — SHA-256 hash of the previous audit record
- `record_hash` — SHA-256 hash of this record's data fields

### Hash Chain

Each audit record includes the SHA-256 hash of the previous record, creating a tamper-evident chain. Verifying the chain means recomputing hashes sequentially and comparing.

### Limitations of Same-Database Hash Chain

A hash chain stored in the same database it protects does **not** fully protect against a privileged database administrator. An attacker with direct database access could:

1. Modify an audit record.
2. Recompute all subsequent hashes.
3. The chain would appear valid even though data was altered.

**Mitigation plan:** Implement independently controlled external checkpoints:
- Periodically compute a signed digest of the latest audit chain state.
- Publish the digest to an external, append-only store (e.g., an immutable cloud log or a separate system controlled by a different party).
- During verification, compare the local chain state against the external digest.

This does not make tampering impossible but makes it detectable.

### Application Enforcement

- The application never issues `UPDATE` or `DELETE` on `audit_logs`.
- No API endpoint exposes audit modification.
- RLS policies reinforce INSERT-only access.

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
        PG["PostgreSQL<br/>RLS Enabled"]
    end

    subgraph "Wasabi"
        WS["S3 Private Bucket"]
    end

    FE -->|"HTTPS API"| BE
    BE -->|"asyncpg"| PG
    BE -->|"boto3"| WS
```

| Provider | Component | Configuration |
|----------|-----------|---------------|
| Vercel   | Frontend  | Build: `npm run build`, Output: `dist/`, Env: `VITE_API_URL` |
| Render   | Backend   | Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Env: see below |
| Supabase | Database  | Connection via `DATABASE_URL`, RLS policies applied via migrations |
| Wasabi   | Storage   | Private bucket, server-side access only via `boto3` |

---

## 13. Required Environment Variables

All values below are **placeholders**. Actual credentials must be configured in each hosting provider's dashboard and never committed to source control.

### Backend (Render)
```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres

# Authentication
JWT_SECRET=your-random-jwt-secret-min-32-chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Wasabi S3
WASABI_ACCESS_KEY=your-wasabi-access-key
WASABI_SECRET_KEY=your-wasabi-secret-key
WASABI_BUCKET=trustvault-documents
WASABI_ENDPOINT=https://s3.wasabisys.com
WASABI_REGION=us-east-1

# Supabase (for direct API use if needed)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# CORS
CORS_ORIGINS=https://your-app.vercel.app

# App
APP_ENV=production
LOG_LEVEL=info
MAX_UPLOAD_SIZE_MB=50
```

### Frontend (Vercel)
```env
VITE_API_URL=https://your-backend.onrender.com
```

---

## 14. Database Security and RLS Planning

### Primary Authorization: Application Logic

The FastAPI backend is the primary authorization enforcement point. Every endpoint checks:
1. Is the user authenticated? (JWT middleware)
2. Does the user have the required role? (role check)
3. Does the user have the required permission for this specific document? (permission check)

### Secondary Defense: Row-Level Security

RLS policies are configured as defense-in-depth:

| Table                  | Policy                                                    |
|------------------------|-----------------------------------------------------------|
| `users`                | Users can SELECT their own row. Admins can SELECT all.    |
| `documents`            | SELECT allowed if user is owner, admin, or has permission grant. |
| `document_permissions` | SELECT/INSERT/DELETE allowed only for document owner or admin. |
| `audit_logs`           | INSERT allowed for service role. No UPDATE/DELETE.        |
| `refresh_tokens`       | Accessible only by service role.                          |

### Service Role Key

The backend uses the Supabase service role key, which **bypasses RLS**. This is by design — the backend has its own authorization logic. RLS exists to catch bugs, not to be the primary gate.

---

## 15. Error Handling and External-Service Failure Behavior

| Scenario                          | Response              | Behavior                                    |
|-----------------------------------|-----------------------|---------------------------------------------|
| Wasabi S3 unreachable             | 503 Service Unavailable | Upload/download fails cleanly. No partial metadata created. |
| Supabase DB unreachable           | 503 Service Unavailable | All requests fail. No silent fallback.       |
| JWT missing                       | 401 Unauthorized      | Request rejected.                            |
| JWT expired                       | 401 Unauthorized      | Client should refresh token.                 |
| JWT invalid signature             | 401 Unauthorized      | Request rejected.                            |
| Permission denied                 | 403 Forbidden         | Audit record created. No document data leaked. |
| Document not found                | 404 Not Found         | Generic message. No ownership information leaked. |
| File too large                    | 413 Payload Too Large | Upload rejected before storage.              |
| Invalid file type                 | 422 Unprocessable Entity | Upload rejected with allowed-types list.   |
| Rate limit exceeded               | 429 Too Many Requests | Client must wait and retry.                  |
| Unexpected server error           | 500 Internal Server Error | Logged server-side. Generic message to client. |

### Health Check

`GET /health` returns the status of:
- Database connectivity
- Wasabi S3 connectivity
- Application uptime

This endpoint does not require authentication and is suitable for uptime monitoring.
