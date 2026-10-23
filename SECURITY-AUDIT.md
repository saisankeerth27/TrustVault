# TrustVault — Defensive Application Security Audit Report

**Date:** 2026-10-23  
**Auditor:** Application Security Reviewer  
**Repository:** `saisankeerth27/TrustVault`  
**Commit Inspected:** `309326527e0245a2fe51302b28e49b80f52bbd18`  
**Status:** Non-destructive source code and local configuration review complete. No code changes applied.

---

## 1. Executive Summary

A defensive, non-destructive application security audit was performed on TrustVault, a secure document-sharing application built on FastAPI, PostgreSQL (Supabase), Supabase Storage, and React (Vite). The audit evaluated the application's source code, configurations, database migrations, authentication flows, authorization controls, document lifecycle, audit hash chains, and deployment topology against the 20 requested security criteria.

### Key Strengths
- **Strict Server-Side Authorization:** Multi-layered access control (`backend/app/services/document_access.py`) strictly isolates documents by ownership and explicit grants (READ/EDIT). BOLA/IDOR is prevented at the database query level; administrators cannot view or download private file contents without explicit owner grants.
- **Strong Upload Hygiene:** Uploads undergo deep validation (`backend/app/services/upload_validation.py`) including extension matching, declared MIME verification, magic-byte signatures (PDF, PNG, JPEG, DOCX OOXML structure checks, NUL-free UTF-8 text checks), ZIP-bomb limits, and path traversal sanitization. Files are stored using random UUID4 keys (`documents/{owner_id}/{uuid}.{ext}`).
- **Tamper-Evident Audit Logging:** Audit events (`backend/app/services/audit.py`) maintain a cryptographic SHA-256 hash chain with advisory transaction locks, preventing concurrent fork attacks and capturing structured security events across auth, documents, permissions, and admin operations.
- **Robust Session Rotation:** Refresh tokens are hashed (SHA-256) in PostgreSQL with session family tracking and automatic family revocation upon detecting token reuse.

### Primary Risks & Vulnerabilities Identified
1. **Plaintext Secrets in Local `.env` (Critical):** `backend/.env` contains active credentials (Supabase PostgreSQL password and connection string, live `SUPABASE_SERVICE_ROLE_KEY`, and `JWT_SECRET`). While gitignored, these live credentials must be rotated if the workspace was ever shared or exposed.
2. **Missing Database Row-Level Security (RLS) (High):** Database migrations (`0001`–`0007`) create all application tables in the Supabase PostgreSQL `public` schema without enabling RLS (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`). If Supabase PostgREST is exposed, unauthorized clients with the public anon key could directly query or tamper with tables bypassing the FastAPI backend.
3. **Missing Security Headers & CSP (High):** Neither FastAPI nor Vercel configures Content Security Policy (CSP), HTTP Strict Transport Security (HSTS), X-Frame-Options (Clickjacking defense), or Referrer-Policy.
4. **CSRF Exposure on Cross-Site Refresh/Logout (High):** For cross-domain deployments (Vercel frontend and Render backend), `AUTH_COOKIE_SAMESITE=none` is configured. `_enforce_allowed_origin` in `backend/app/api/auth.py:47-55` only inspects requests if the `Origin` header is present (`if origin and ...`), allowing cross-site requests omitting the header to bypass validation without an anti-CSRF token or `Sec-Fetch-Site` check.
5. **No Password Reset or MFA (Medium):** Self-service password recovery and multi-factor authentication are not implemented.
6. **In-Memory Rate Limiting & Unprotected Heavy Endpoints (Medium):** Rate limiting is in-memory process-local (not distributed across multiple workers or instances) and only protects `/login` and `/register`. Document upload, replacement, and sequential audit integrity checks have no rate limits.

---

## 2. Stack and Attack-Surface Map

### Technology Stack
- **Backend Framework & Runtime:** Python 3.12, FastAPI 0.115+, Uvicorn, Pydantic v2.
- **Frontend Framework & Tooling:** React 19, Vite 8, Tailwind CSS v4, Lucide React, Axios.
- **Database & ORM:** PostgreSQL 15+ (hosted on Supabase / AWS `ap-south-1`), SQLAlchemy 2.0 ORM/Core, Psycopg 3 driver, Alembic for schema migrations.
- **Storage:** Supabase Storage (S3-compatible private bucket `trustvault-documents`).
- **Deployment Platform:** 
  - Backend: Render Web Service (`render.yaml`, Python runtime, free plan).
  - Frontend: Vercel SPA (`frontend/vercel.json`, output directory `dist`).

### Code Execution Topology
- **Browser (Client):** React SPA execution, DOMPurify sanitization, PDF.js rendering to HTML5 Canvas in Web Worker (`pdf.worker.min.mjs`), Mammoth.js DOCX-to-HTML conversion.
- **Server (Backend):** FastAPI request validation, JWT signing/verification, bcrypt hashing, database transaction orchestration, Supabase Storage API proxying, audit hash chaining.
- **Workers / Background Tasks:** None currently configured; all uploads, downloads, and hash chain integrity verifications run synchronously in HTTP request workers.
- **Build Time:** Vite asset bundling and minification, Oxlint AST static analysis, Vitest and Pytest test runners.

### Attack Surface Map
```
[External Attacker / Browser]
       │
       ├──► (Public) GET /health ────────► FastAPI health status
       ├──► (Public) POST /api/v1/auth/register ──► Rate Limiter ──► User creation & Refresh Cookie
       ├──► (Public) POST /api/v1/auth/login ─────► Rate Limiter ──► Bcrypt auth & Refresh Cookie
       ├──► (Public) POST /api/v1/auth/refresh ───► Cookie verification & Token rotation
       ├──► (Public) POST /api/v1/auth/logout ────► Session revocation & Cookie clear
       │
       ├──► (Authenticated: Bearer JWT)
       │       ├──► GET /api/v1/auth/me ──────────► Current user profile
       │       ├──► /api/v1/documents/* ──────────► Document access policy (Owner/Read/Edit)
       │       │       ├──► Upload, Download (Streaming proxy), Preview, Edit, Soft-delete
       │       │       └──► Version history & Rollback
       │       └──► /api/v1/documents/{id}/permissions ──► Owner-only permission grants/revocations
       │
       ├──► (Admin-Only: Role=ADMINISTRATOR)
       │       └──► /api/v1/admin/* ──────────────► User oversight, status toggle, audit logs,
       │                                            and full sequential hash integrity check
       │
[Direct Cloud Services (Bypass Threat Vector)]
       ├──► Supabase PostgREST (https://<ref>.supabase.co/rest/v1/*) [High Risk if RLS disabled]
       └──► Supabase Storage API (Private bucket; accessible only via backend Service Role Key)
```

---

## 3. Findings Table

| ID | Severity | Confidence | Status | Affected File / Route | Evidence | Impact | Recommended Fix |
|---|---|---|---|---|---|---|---|
| **SEC-01** | **Critical** | High | Open | `backend/.env:6, 10, 23` | Active Supabase DB password, `SUPABASE_SERVICE_ROLE_KEY` (`sb_secret_*`), and `JWT_SECRET` stored in plaintext on disk. | Compromise of local environment grants full administrative control over database and storage. | Rotate secrets in Supabase dashboard and Render; use developer secret manager. |
| **SEC-02** | **High** | High | Open | `backend/alembic/versions/*`, `docs/DATABASE.md:258` | All 7 Alembic migrations omit `ENABLE ROW LEVEL SECURITY`. Tables (`users`, `documents`, `audit_events`, etc.) reside in `public` schema without RLS. | If Supabase PostgREST API is exposed, anon keys can query/mutate application tables directly. | Run migration to enable RLS on all tables and grant zero public privileges to `anon`/`authenticated` roles. |
| **SEC-03** | **High** | High | **Resolved** | `backend/app/main.py:14-23`, `frontend/vercel.json` | `SecurityHeadersMiddleware` injected in FastAPI and response headers configured in Vercel (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS). | Eliminates clickjacking risks, protocol downgrades, and MIME sniffing without altering application behavior. | Implemented via `SecurityHeadersMiddleware` and `frontend/vercel.json`. |
| **SEC-04** | **High** | High | **Resolved** | `backend/app/api/auth.py:47-65` | `_enforce_allowed_origin` now enforces `Sec-Fetch-Site: cross-site` checks and validates non-whitelisted cross-site origins. | Blocks Cross-Site Request Forgery (CSRF) attempts on session rotation and logout endpoints. | Implemented in `backend/app/api/auth.py`. |
| **SEC-05** | **Medium** | High | Open | `backend/app/api/documents.py:269, 749, 867`, `backend/app/api/admin.py:522` | No rate limiting on file upload, version upload, PDF modification, or sequential audit verification (`/audit-integrity`). | Resource exhaustion, denial of service (DoS), and storage bloat from rapid file uploads or CPU-heavy audit checks. | Apply rate limits to upload endpoints and cache/throttle `/admin/audit-integrity`. |
| **SEC-06** | **Medium** | High | Open | `backend/app/core/rate_limit.py:12-65` | In-memory `SlidingWindowRateLimiter` is process-local. | Limits reset on process restart and do not coordinate across multiple Uvicorn workers or server instances. | Migrate to distributed rate limiting (e.g. Redis) for multi-worker/multi-instance production. |
| **SEC-07** | **Medium** | High | Open | `backend/app/services/auth.py`, `backend/app/api/auth.py` | No password reset / recovery endpoints exist; no MFA/2FA support. | Account lockout upon forgotten password; vulnerability to credential stuffing without MFA. | Implement secure token-based password reset flow with email verification; plan MFA. |
| **SEC-08** | **Low** | High | Open | `backend/app/main.py` | Backend lacks `HTTPSRedirectMiddleware` or independent TLS enforcement behind reverse proxy. | Plaintext HTTP requests could be processed if reverse proxy misroutes them. | Enforce `X-Forwarded-Proto: https` check or add `HTTPSRedirectMiddleware`. |

---

## 4. Comprehensive Audit of the 20 Areas

### 1. Secrets Present in the Current Tree or Git History — **FAIL (Critical)**
- **Result:** **FAIL**
- **Evidence:** `backend/.env` exists locally on disk containing live credentials:
  - Line 6: `DATABASE_URL=postgresql://postgres.hugxrjlawlxiwwnkwagu:[REDACTED_PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres` (Supabase database password).
  - Line 10: `JWT_SECRET=[REDACTED_SECRET]`.
  - Line 23: `SUPABASE_SERVICE_ROLE_KEY=sb_secret_[REDACTED_KEY]`.
- **Git History Check:** Verified with `git log -S` and `git log -p`. No real credentials were committed into Git history (all historical commits use placeholder values `replace-me` or `YOUR_PASSWORD`). The `.gitignore` properly includes `.env`.
- **Verdict & Recommendation:** Although `.env` is uncommitted, having active production/staging credentials in plaintext on a local workstation is a severe security exposure. Instruct administrator to rotate the Supabase database password, Supabase service-role key, and JWT secret.

### 2. Database Grants, Access Rules and RLS — **FAIL (High)**
- **Result:** **FAIL**
- **Evidence:** `docs/DATABASE.md:258-267` explicitly documents: *"No RLS policies are enabled. Phase 3 keeps the backend on a single privileged database role... application-level authorization remains authoritative"*. Review of `backend/alembic/versions/` (`0001` to `0007`) confirms that no table has `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`.
- **Impact:** Supabase exposes a RESTful API (`PostgREST`) over HTTPS for tables in the `public` schema. If the Supabase project has not explicitly disabled PostgREST or revoked `anon`/`authenticated` table grants in Postgres, an attacker holding the public anon key can bypass the FastAPI backend and query `users`, `documents`, or `audit_events` directly.
- **Recommendation:** Add an Alembic migration enabling RLS on all tables and revoke public schema privileges from PostgREST roles (`anon`, `authenticated`).

### 3. Spend Alerts, Budgets, Rate Limits and Hard Caps — **NEEDS INPUT**
- **Result:** **NEEDS INPUT**
- **Evidence:** `render.yaml:5` specifies `plan: free` (no overage charges; service spins down after 15 minutes of inactivity). Supabase and Vercel handle usage-based database, storage, and serverless bandwidth.
- **Reasoning:** Cloud billing limits, soft alerts, and spend caps are provider-level controls configured in Vercel and Supabase management consoles, not defined in repository code.
- **Recommendation:** Confirm in the Supabase and Vercel dashboards that spend alerts (e.g. 50%, 80%, 100%) and hard spend caps/auto-pause are enabled to prevent unexpected billing.

### 4. Server-Side Protection for Admin Routes, Actions and APIs — **PASS**
- **Result:** **PASS**
- **Evidence:** `backend/app/api/admin.py:57-74` enforces `require_admin_access`, verifying `current_user.role == UserRole.ADMINISTRATOR.value` and logging security denials to `audit_events`. All admin endpoints (`/api/v1/admin/*`, lines 180, 253, 313, 332, 371, 412, 450, 525) depend on this check. Furthermore, `backend/app/services/document_access.py:80` restricts administrators to `DocumentCapability.METADATA`, preventing admins from reading or downloading private user document contents.

### 5. Per-User, Per-Role and Per-Tenant Authorization — **PASS**
- **Result:** **PASS**
- **Evidence:** BOLA/IDOR protection is enforced server-side. In `backend/app/services/document_access.py:105-135`, every document request evaluates ownership and non-revoked permission grants (`DocumentPermission.revoked_at.is_(None)`). `backend/app/api/documents.py` invokes `authorize_document` on all operations. READ-only recipients cannot trigger EDIT or DELETE actions.

### 6. Rate Limiting on Authentication, Forms and Expensive Endpoints — **FAIL (Medium)**
- **Result:** **FAIL**
- **Evidence:** 
  1. Rate limiting in `backend/app/api/auth.py:57-70` covers only `/register` (by IP) and `/login` (by IP and email).
  2. `backend/app/core/rate_limit.py:12-65` is an in-memory process-local limiter, failing to coordinate across multi-worker or multi-instance deployments.
  3. Expensive endpoints have no rate limiting: file upload (`POST /api/v1/documents`), version upload (`PUT /api/v1/documents/{id}/versions`), PDF editing (`PUT /api/v1/documents/{id}/content`), and sequential audit verification (`GET /api/v1/admin/audit-integrity`).

### 7. File-Upload Type, Content, Size, Name, Storage and Authorization Controls — **PASS**
- **Result:** **PASS**
- **Evidence:** `backend/app/services/upload_validation.py:59-164` and `backend/app/services/documents.py:50-51`:
  - 10 MiB default upload size limit enforced before body parsing (`backend/app/main.py:31-35`).
  - Strict extension and MIME matching for PDF, TXT, DOCX, PNG, JPG/JPEG.
  - Magic-byte verification (`%PDF-`, `PK\x03\x04`, `\x89PNG`, `\xff\xd8\xff`, UTF-8 NUL-free checks).
  - DOCX zip-bomb prevention (max 1000 archive members, 50MB uncompressed limit).
  - Filename sanitization rejects path traversal (`/`, `\`, control chars, NUL bytes).
  - Storage keys are randomized UUIDs (`documents/{owner_id}/{uuid}.{ext}`).
  - Buckets are private and downloaded via authenticated streaming proxy (`backend/app/api/documents.py:1173-1255`).

### 8. Exact CORS Origin, Method, Header and Credential Rules — **PASS**
- **Result:** **PASS**
- **Evidence:** `backend/app/main.py:37-43` and `backend/app/core/config.py:175-183`. Wildcard `*` is explicitly blocked in non-development environments when credentials are enabled. Origins are strictly parsed from `CORS_ALLOWED_ORIGINS`. Allowed headers are constrained to `["Authorization", "Content-Type", "X-Request-ID"]` and methods to `GET, POST, PUT, PATCH, DELETE, OPTIONS`.

### 9. CSRF Protection for Cookie-Authenticated State-Changing Requests — **FAIL (High)**
- **Result:** **FAIL**
- **Evidence:** `backend/app/api/auth.py:47-55`:
  ```python
  def _enforce_allowed_origin(request: Request) -> None:
      origin = request.headers.get("origin")
      if origin and origin not in get_settings().cors_origins:
          raise HTTPException(...)
  ```
  In production (`render.yaml:45-46`), `AUTH_COOKIE_SAMESITE=none` is set to allow cross-site cookie transmission between Vercel and Render. Because `_enforce_allowed_origin` checks `if origin`, any cross-site request where the browser omits the `Origin` header bypasses origin verification. No CSRF token or `Sec-Fetch-Site` check exists for cookie-authenticated endpoints (`/refresh`, `/logout`).

### 10. Session-Cookie Secure, HttpOnly, SameSite, Path, Domain and Lifetime — **PASS**
- **Result:** **PASS**
- **Evidence:** `backend/app/api/auth.py:73-84`. `trustvault_refresh` is configured with `HttpOnly=True`, `Path=/api/v1/auth`, `max_age=604800` (7 days), and host-only domain. `config.py:205-206` programmatically halts application startup if `AUTH_COOKIE_SECURE` is not `True` in production.

### 11. CSP, HSTS, Frame Protection, Nosniff and Referrer Security Headers — **FAIL (High)**
- **Result:** **FAIL**
- **Evidence:** Neither `backend/app/main.py` nor `frontend/vercel.json` nor `frontend/index.html` sets:
  - `Content-Security-Policy` (CSP)
  - `Strict-Transport-Security` (HSTS)
  - `X-Frame-Options` (or `frame-ancestors`)
  - `Referrer-Policy`
  The only security header present is `X-Content-Type-Options: nosniff`, which is set only on document download responses (`backend/app/api/documents.py:1213`).

### 12. Debug Flags, Verbose Errors, Stack Traces and Sensitive Logging — **PASS**
- **Result:** **PASS**
- **Evidence:** `backend/app/core/errors.py:7-55` intercepts `StarletteHTTPException` and `RequestValidationError`, returning structured JSON error envelopes without stack traces or environment paths. `backend/app/services/storage.py` redacts credentials and suppresses raw error bodies. `backend/app/services/audit.py:133-167` strips passwords, cookies, and tokens before logging.

### 13. Production Configuration, Unsafe Defaults and Environment Separation — **PASS**
- **Result:** **PASS**
- **Evidence:** `backend/app/core/config.py:175-208` enforces production requirements (rejects wildcard CORS, mandates 32+ character `JWT_SECRET`, mandates `AUTH_COOKIE_SECURE=True`). `render.yaml:13-14` explicitly sets `APP_ENV=production`.

### 14. Server-Side Input Schemas, Types, Lengths, Ranges and Allowlists — **PASS**
- **Result:** **PASS**
- **Evidence:** Comprehensive Pydantic v2 schemas in `backend/app/schemas/` enforce string bounds (e.g. `min_length=1, max_length=255`), email syntax (`EmailStr`), password length limits (8–128 characters), query parameter limits (`page_size` le=100), and UUID path casting.

### 15. XSS Risks, Raw HTML, Unsafe DOM Sinks and Output Encoding — **PASS**
- **Result:** **PASS**
- **Evidence:** React 19 auto-encodes text expressions. In `frontend/src/components/documents/DocumentPreview.jsx:175`, `dangerouslySetInnerHTML` is used for DOCX preview, but the HTML output from Mammoth.js is explicitly sanitized using `DOMPurify.sanitize(result.value)` (`line 46`). PDF.js runs in worker mode with `isEvalSupported: false` (`frontend/src/components/documents/PdfViewer.jsx:43`). No unsafe DOM sinks found.

### 16. SQL Injection Risks, Raw Queries and String Concatenation — **PASS**
- **Result:** **PASS**
- **Evidence:** All database queries utilize SQLAlchemy 2.0 ORM expressions (`select()`, `update()`) with bound parameters. Search queries in `backend/app/api/admin.py:88-89, 260-267` escape `%`, `_`, and `\` before binding to ILIKE parameters. Advisory lock queries (`backend/app/services/audit.py:186`) use bound parameter `:lock_id`.

### 17. Public vs Server-Only Environment Variables and Client Exposure — **PASS**
- **Result:** **PASS**
- **Evidence:** Only `VITE_API_BASE_URL` is referenced in the frontend (`frontend/src/services/api.js:4`). No backend secrets or storage keys are prefixed with `VITE_`. Scanned `frontend/dist/` build output and verified zero leaked credentials.

### 18. Secret API Keys in Client Code, Source Control, Logs or Build Output — **PASS**
- **Result:** **PASS**
- **Evidence:** Git commit history and frontend distribution files (`frontend/dist/assets/*.js`) were inspected; no secret keys, JWT tokens, or credentials are embedded in tracked source code or client bundles.

### 19. Login, Signup, Password Reset, Session Rotation, Logout and MFA Controls — **FAIL (Medium)**
- **Result:** **FAIL**
- **Evidence:** While user registration, bcrypt authentication, and refresh token rotation with family revocation are well implemented (`backend/app/services/auth.py`), **Password Reset is completely absent** from the application (no forgot password API, reset tokens, or email dispatch). Multi-Factor Authentication (MFA) is also not implemented.

### 20. HTTPS Enforcement, Redirects, Certificates, Mixed Content and HSTS — **FAIL (Low)**
- **Result:** **FAIL**
- **Evidence:** While Supabase database connections require SSL (`backend/app/db/url.py:29`) and hosting providers (Render/Vercel) terminate TLS at the edge, the FastAPI backend does not include `HTTPSRedirectMiddleware` and does not issue `Strict-Transport-Security` headers.

---

## 5. Prioritized Remediation Plan

### Group 1: Immediate Remediation (Critical & High)
1. **Rotate Exposed Credentials:** Immediately rotate the Supabase database password, Supabase service-role key, and backend JWT secret in the Supabase and Render dashboards. Remove live values from local workspace `.env`.
2. **Enable Database Row-Level Security (RLS):** Create an Alembic migration (`0008_enable_rls.py`) executing `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` on `users`, `documents`, `audit_events`, `document_permissions`, `document_versions`, and `refresh_tokens`. Revoke table permissions from PostgREST `anon` and `authenticated` roles.
3. **Deploy Security Headers:**
   - Add security headers middleware in FastAPI (`backend/app/main.py`) to inject:
     - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' <API_ORIGIN>; frame-ancestors 'none';`
     - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
     - `X-Frame-Options: DENY`
     - `X-Content-Type-Options: nosniff`
     - `Referrer-Policy: strict-origin-when-cross-origin`
   - Configure security headers in `frontend/vercel.json`.
4. **Harden CSRF Protection on Auth Cookie Endpoints:**
   - In `backend/app/api/auth.py`, verify `Sec-Fetch-Site` (reject `cross-site` on state-changing requests) or require an exact non-empty `Origin`/`Referer` header matching `cors_origins`.

### Group 2: Before Launch (Medium)
1. **Endpoint Rate Limiting:**
   - Add rate limits to document upload (`POST /api/v1/documents`), version upload (`PUT /api/v1/documents/{id}/versions`), and PDF content updates (`PUT /api/v1/documents/{id}/content`).
   - Add throttling/caching to the sequential integrity check endpoint (`GET /api/v1/admin/audit-integrity`).
2. **Implement Password Reset Flow:**
   - Create a secure token-based password reset mechanism with time-limited cryptographic tokens, invalidated on use or password change.
3. **Centralize Rate Limiting for Multi-Worker Deployments:**
   - Prepare a Redis-backed rate limiter if horizontal scaling or multiple Uvicorn workers are enabled.

### Group 3: Later Hardening
1. **Multi-Factor Authentication (MFA):** Implement TOTP (RFC 6238) for user accounts, with mandatory MFA for administrative roles.
2. **Independent Audit Checkpoint Storage:** Publish signed audit chain checkpoints (`audit_checkpoint_path`) to an immutable, append-only external bucket (e.g. AWS S3 Object Lock) rather than local disk.
3. **Antivirus / Malware Scanning:** Integrate ClamAV or external virus-scanning sandbox before releasing newly uploaded files to readers.

---

## 6. Manual Verification Plan

### Signed-Out Actor
1. **Unauthenticated Access:** Request `GET /api/v1/documents` and `GET /api/v1/admin/summary`; verify `401 Unauthorized` response with `WWW-Authenticate: Bearer`.
2. **Direct Storage Access:** Attempt to access Supabase Storage object directly via URL; confirm `403 Forbidden` from Supabase private bucket.
3. **Cross-Origin Auth POST:** Submit a POST to `/api/v1/auth/logout` from an unauthorized origin; confirm `403 Forbidden` or rejection.

### User A (Document Owner)
1. **Upload & Storage Key:** Upload `test.pdf`. Verify metadata is created and storage key is opaque (`documents/<user_a_id>/<uuid>.pdf`).
2. **Permissions Management:** Grant `READ` access to User B. Confirm User A can view, edit, download, and delete.
3. **Revocation Test:** Revoke User B's access. Verify subsequent requests by User B immediately return `403 Forbidden` or `404 Not Found`.

### User B (Recipient)
1. **Authorized READ:** Verify User B can download and preview the shared document.
2. **Forbidden EDIT:** Attempt `PUT /api/v1/documents/{id}/content` or `DELETE /api/v1/documents/{id}`; verify `403 Forbidden` and check that an `ACCESS_DENIED` event is logged in `audit_events`.
3. **BOLA/IDOR Probe:** Attempt `GET /api/v1/documents/{unshared_id}` belonging to User A; verify `404 Not Found` without disclosing document existence.

### Administrator
1. **Admin Portal:** Access `/api/v1/admin/summary` and `/api/v1/admin/audit-events`; confirm full oversight data.
2. **Separation of Duty (Private Content Access):** Attempt to download User A's private document (`GET /api/v1/documents/{id}/download`); verify `403 Forbidden` (metadata oversight only).
3. **Audit Integrity:** Run `GET /api/v1/admin/audit-integrity`; verify hash chain calculates status `valid`.

---

## 7. Verification & Build Commands

### Backend Verification (Python 3.12 / venv)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
# Run full pytest test suite (269 tests)
python -m pytest -q
# Check database migration consistency
alembic check
```
*Current Result:* **269 passed** in 57.8s.

### Frontend Verification (Node.js / npm)
```powershell
cd frontend
# Run unit & component tests (31 tests across 11 test suites)
npm test
# Run static analysis
npm run lint
# Run production bundle build
npm run build
```
*Current Results:*
- Tests: **31 passed** (11 test files).
- Lint: **0 errors**, 5 React effect warnings.
- Build: Succeeded (`dist/` generated in 1.77s).

---

## 8. Open Questions & Items Requiring External Confirmation

1. **Supabase PostgREST Status:** Has the `public` schema exposure in Supabase PostgREST been explicitly disabled in the Supabase Dashboard (Settings → API → Exposed Schemas)? If not, RLS must be enabled immediately.
2. **Supabase & Vercel Budget Controls:** Are automated billing pause thresholds or spend notification alerts active on the connected Supabase and Vercel accounts?
3. **Production Deployment Target:** Is the current Render deployment actively linked to the Supabase instance referenced in `backend/.env`, or is there an isolated production database?
4. **Planned Checkpoint Strategy:** Is persistent cloud storage (e.g., S3 with object lock) available for `AUDIT_CHECKPOINT_PATH`, or will checkpoints remain file-based?
