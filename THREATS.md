# TrustVault — Threat Model

This threat model documents the assets TrustVault protects, the trust boundaries it enforces, the actors who may attempt to compromise it, the attack scenarios it must resist, and the mitigations and residual risks associated with each.

> **Current authentication status:** Supabase Auth is implemented in source but has not been deployed or verified against live SMTP/provider settings. TrustVault roles remain database-authoritative. Authenticated sessions are managed by Supabase; the SPA stores the SDK session in tab-scoped `sessionStorage`, and the recovery access token is held in a short-lived, scoped HttpOnly cookie. Migration `0009` irreversibly clears legacy password hashes and revokes old refresh tokens. Treat historical phase notes below as contemporaneous reports where they conflict with this current status.

---

## 1. Assets

| Asset | Description | Sensitivity |
|-------|-------------|-------------|
| Document contents | Files stored in a private Supabase Storage bucket | Critical |
| Document metadata | Names, owners, categories, timestamps | High |
| Permission grants | Which users may read or edit which documents | High |
| User credentials and sessions | Credentials managed by Supabase Auth; browser session/access tokens | Critical |
| Supabase project signing keys | Provider-managed signing keys used for Auth tokens | Critical |
| Audit records | Tamper-evident history of all actions | High |
| Audit checkpoint signing key | HMAC key used to sign the audit chain head | Critical |
| Service credentials | Supabase service role key, Supabase Storage keys, database URL | Critical |
| User identities and roles | Account and role assignments | Medium–High |

---

## 2. Trust Boundaries

```mermaid
graph TB
    subgraph "Untrusted: Client"
        U["Browser / Frontend<br/>(user-controlled, can be modified)"]
    end
    subgraph "Trusted: Server"
        API["FastAPI Backend<br/>(authorization enforcement point)"]
    end
    subgraph "Trusted: Data Services"
        DB["Supabase PostgreSQL"]
        S3["Supabase Storage Private Bucket"]
    end
    U -->|"Boundary 1: HTTPS/API<br/>untrusted input"| API
    API -->|"Boundary 2: least-privilege DB access"| DB
    API -->|"Boundary 3: private storage access"| S3
```

**Boundary 1 — Client to API.** All client input is untrusted. The frontend can be modified, bypassed, or replaced by an attacker with browser devtools or a direct HTTP client. Every request must be independently authorized by the backend.

**Boundary 2 — API to Database.** The backend connects with elevated credentials. Any bug in authorization or query construction can expose data. RLS provides a secondary barrier.

**Boundary 3 — API to Storage.** Storage is private. Clients never receive direct storage URLs. All file access is mediated and authorized by the backend.

**Boundary 4 — Operators/Administrators.** A privileged database or infrastructure administrator has capabilities that the application cannot fully constrain. This boundary is addressed through audit checkpointing and separation of duties where feasible.

---

## 3. Threat Actors

| Actor | Capability | Motivation |
|-------|------------|------------|
| Unauthenticated external attacker | Can send arbitrary HTTP requests; no credentials | Data theft, disruption |
| Authenticated low-privilege user | Valid normal account with no administrator role | Access documents beyond ownership or grants |
| Malicious document owner | Can upload and grant permissions on own documents | Excessive sharing, concealment |
| Compromised account holder | Valid credentials stolen or coerced | Impersonation, data exfiltration |
| Insider with database access | Direct database or infrastructure access | Alter or hide audit trails, exfiltrate data |
| Automated bot / scanner | High-volume requests | Brute force, denial of service |

---

## 4. Attack Scenarios, Mitigations, and Verification

### 4.1 Insecure Direct Object Reference (IDOR)

**Scenario:** A user guesses or enumerates document IDs and requests documents they were never granted access to.

**Mitigation:** Phase 6 document endpoints resolve visibility from ownership and active grants on every request. Regular users see owned plus actively shared documents; administrators may read all active metadata. Edit, download, delete, and permission management are separately checked. IDs are UUIDs (hard to enumerate but not relied upon for security), and inaccessible/missing IDs return the same generic 404.

**Verification:** Phase 5 tests established generic 404 IDOR denial. Phase 6 adds grant-based tests for unrelated documents, cross-document permission IDs, anonymous callers, and revoked access.

**Residual Risk:** Low. UUIDs reduce discoverability but authorization does not depend on secrecy of IDs.

---

### 4.2 Unauthorized Downloads

**Scenario:** A user attempts to download a document via a direct link, guessed storage key, or API manipulation.

**Mitigation:** The bucket is intended to be private. Uploads never return a direct or presigned URL or the storage key. The download proxy authorizes OWNER, EDIT, or READ capability from current database state before reading from storage and streams the body without exposing the key or a direct URL. Storage-not-found and configuration/operation failures return generic responses. Successful downloads append `DOCUMENT_DOWNLOAD`; denied attempts append `DOCUMENT_DOWNLOAD_DENIED` best-effort.

**Verification:** Phase 5–7 tests assert owner/READ/EDIT download permissions, generic 404 denial for unrelated users and ungranted administrators, immediate post-revocation denial, safe attachment/no-store headers, header-injection resistance, no storage-key leakage, and success/denial audit events.

**Residual Risk:** Low after the bucket policy is verified. The live Supabase Storage private policy and download behavior have **not** been verified. Files already downloaded before a revocation cannot be recalled — see 4.4.

---

### 4.3 Privilege Escalation

**Scenario:** A normal user attempts to act as a document owner or administrator by tampering with JWT claims, role fields in requests, or permission endpoints.

**Mitigation:** FastAPI verifies the bearer token with Supabase Auth, then binds the verified provider UUID/email to the TrustVault user row. Roles are read from the database and never trusted from provider metadata or client-supplied fields. Permission-management endpoints require document ownership; administrator status does not grant sharing or content access. Admin account endpoints reject self role/status changes and protect the last active administrator.

**Verification:** Tests attempt role manipulation via JWT tampering and request body injection and assert denial. Phase 7 tests confirm authorization denials append best-effort denial audit events.

**Residual Risk:** Low, provided provider credentials remain protected and the database role store is not compromised.

---

### 4.4 Access After Revocation

**Scenario:** A user whose permission was revoked attempts to continue accessing the document (e.g., relying on cached tokens or client state).

**Mitigation:** Permissions are checked on every request against current database state. No permission caching serves stale data. Revocation is immediate. The issued access token authorizes identity, not document access.

**Verification:** Phase 6 tests grant access, confirm success, revoke, then immediately assert 404 for detail/download/edit because the user no longer has any access, and confirm shared listings exclude the revoked document.

**Residual Risk:** **Downloaded copies cannot be recalled.** Once a user has downloaded a file, revocation cannot remove it from their device. This is inherent to all document-sharing systems and must be communicated to users.

---

### 4.5 Malicious Uploads

**Scenario:** A user uploads malware, an executable disguised as an allowed type, a polyglot file, or a zip bomb.

**Mitigation (implemented for upload/download):** Enforce a 10 MiB default size limit, including a pre-routing `Content-Length` check before body parsing or authentication, an extension and MIME allow-list, magic-byte/signature verification, filename validation, empty-file rejection, DOCX OOXML member limits, and NUL-free UTF-8 TXT validation. Executable types are not allowed. The backend computes the checksum, generates the storage key, and stores files privately. Uploaded content is never executed or rendered server-side. Downloads are forced as attachments with `nosniff` and no-store headers. Malware scanning remains future work.

**Verification:** Unit tests cover each validation rule, including DOCX member-count/uncompressed-size limits and Unicode format-control filenames. Integration tests cover mismatched extensions/content, missing content types, unsafe names, empty files, malformed multipart, unauthenticated oversized requests (413), chunked uploads without `Content-Length` (411), anonymous denial, storage failure, and metadata-failure cleanup.

**Residual Risk:** Medium without antivirus scanning. Signature checks are not a malware scanner and can be bypassed by a valid but malicious document. A zero-day in a viewed document format is outside the application's control. Recommend adding scanning in a later phase.

---

### 4.6 Path Manipulation

**Scenario:** A crafted filename such as `../../etc/passwd` or a null-byte injection manipulates storage paths or local filesystem writes.

**Mitigation (implemented for upload):** The application never uses client filenames as filesystem or storage paths. Phase 4 creates `documents/{owner_uuid}/{random_uuid}.{ext}` from server-side values. Path separators, NUL/control characters, Unicode format controls (including bidi overrides), and names over 255 characters are rejected; the original name is metadata only.

**Verification:** Tests assert rejection of traversal/NUL/control-character/bidi-format filenames and verify generated storage keys do not contain the user filename.

**Residual Risk:** Low.

---

### 4.7 Unauthorized Permission Changes

**Scenario:** A user or unrelated account grants themselves or others access to a document they do not own.

**Mitigation:** Permission endpoints require the caller to be the document owner. The recipient must be an active registered account, owner self-grants are rejected, client-supplied grantor/recipient IDs are rejected, and permission IDs must belong to the requested document. Successful changes and denied attempts append audit events.

**Verification:** Phase 6 tests attempt grants/list/update/revoke as unrelated owners, administrators, READ/EDIT recipients, and anonymous callers, and assert 403/404 denial without mutation. Phase 7 tests confirm permission success and denial audit records.

**Residual Risk:** Low.

---

### 4.8 Audit Tampering

**Scenario:** An attacker or privileged insider modifies or deletes audit records to hide unauthorized activity.

**Mitigation:** Audit writes are append-only at the application layer, with no UPDATE/DELETE endpoints. Events have a contiguous `chain_index`, previous-event hash, and canonical SHA-256 `event_hash`; verification detects modified, reordered, and removed events at or before the latest checkpoint. An HMAC-SHA256 signed checkpoint binds the chain head, and `scripts/audit_integrity.py` verifies or creates it. Checkpoint creation refuses to replace an invalid checkpoint or move backward to an older chain head. Migration `0008` enables RLS and revokes table/sequence access from `PUBLIC`, `anon`, and `authenticated`; the backend's privileged database connection remains within the application trust boundary.

**Limitation and Residual Risk:** **A hash chain and same-host checkpoint do not fully protect against a privileged attacker.** An attacker with direct database access can rewrite records and subsequent hashes, and an attacker with host filesystem access can delete or replace the checkpoint. Events appended after the latest checkpoint and then deleted are not detectable by that checkpoint, so checkpoint cadence determines the exposure window. Detection depends on retaining a trusted checkpoint outside the attacker's control. TrustVault still needs independently controlled, scheduled checkpoint publication to an append-only external store before this risk is adequately mitigated.

**Verification:** Phase 7 tests confirm no API audit mutation path, detection of modified/middle-removed events, signed-checkpoint validation, staleness/truncation/signature failure handling, and mandatory-audit-write rollback. Phase 8 re-audit tests confirm checkpoint creation refuses to replace a newer or invalid checkpoint. Residual risk remains without independent checkpoint storage.

---

### 4.9 Metadata Leakage

**Scenario:** Error messages, search results, headers, or logs reveal document existence, ownership, or contents to unauthorized users.

**Mitigation:** Upload and document responses expose only safe metadata and never the storage key, URL, or credentials. Role denials, missing/inaccessible IDs, and storage failures return generic messages; internal storage errors are logged without credentials. Phase 5 download authorization occurs before any content headers are returned, and attachment filenames are encoded with control characters neutralized. Audit details reject sensitive keys, content, and payloads and are bounded.

**Verification:** Tests assert generic storage/persistence errors, secret-safe logs, metadata-only response fields, owner-only download denial, safe attachment encoding, no storage-key leakage, and audit metadata sanitization.

Administrator diagnostic identifiers are intentionally confined to administrator account and audit surfaces. The global audit table uses human-readable document names; request IDs, document IDs, event IDs/sequences, and actor/target IDs are exposed through the admin-only metadata dialog with copy actions. Normal document activity uses a separate allowlisted response and does not inherit global audit diagnostics.

**Residual Risk:** Low–Medium. Timing side channels and name leakage in shared contexts require ongoing review.

---

### 4.10 Exposed Credentials

**Scenario:** Secrets (database URL, service-role key, SMTP credentials, provider signing keys, or Auth sessions) are committed, logged, or exposed in client bundles.

**Mitigation:** Secrets live only in environment variables. `.env` files are gitignored; `.env.example` contains placeholders only. Supabase Storage credentials are server-side settings returned by the backend configuration, never `VITE_*` values. Storage errors and logs omit credentials and keys. Secret scanning is required before each commit. Credentials are rotated if exposure is suspected.

**Verification:** Phase 4 tests assert secret-safe storage logging; Phase 8 verifies internal storage/configuration failures do not echo credentials into API responses. Repository and frontend build-output secret scans remain required before each commit.

**Residual Risk:** Medium if operational discipline lapses. Any leaked credential must be treated as compromised and rotated immediately.

---

### 4.11 Weak RLS Policies

**Scenario:** Misconfigured Row-Level Security policies allow cross-tenant reads or writes, or privileged service credentials are used from the client.

**Mitigation:** Migration `0008` enables RLS without permissive policies (default deny) and revokes direct PostgREST table/sequence privileges for `PUBLIC`, `anon`, and `authenticated`. The backend uses a privileged database connection, so application-level authorization remains the primary control. Supabase service-role credentials remain server-side only.

**Verification:** Migration tests confirm RLS is enabled on application tables; the threat suite confirms application authorization and that the browser does not receive service-role credentials. Supabase dashboard role/grant state still requires deployment verification.

**Residual Risk:** Low–Medium. RLS mistakes are caught by application-level checks, but policy drift must be reviewed.

---

### 4.12 Session and Token Theft

**Scenario:** An attacker steals a Supabase Auth session via XSS, insecure browser storage, or network interception.

**Mitigation:** HTTPS in production. The Supabase SDK stores its session in tab-scoped `sessionStorage`; this reduces persistence across browser restarts but remains JavaScript-accessible and does not prevent XSS token theft. FastAPI verifies each access token with Supabase Auth and checks active status and current database roles. Recovery access tokens are isolated in an HttpOnly cookie scoped only to password update, with a ten-minute lifetime. A strong CSP remains planned.

**Verification:** Automated tests cover provider token verification behavior, verified-email requirements, disabled-account denial, recovery OTP/type and cookie scoping, expiration clearing, rate limits, and safe audit details. Live provider revocation behavior, browser storage behavior, SMTP, and deployed cookie policy are unverified.

**Residual Risk:** Medium. A stolen SDK session is JavaScript-readable until revoked or expired; use a restrictive CSP, review all DOM sinks, and verify provider session expiry/revocation settings.

---

### 4.13 Brute-Force and Credential Stuffing

**Scenario:** Automated attempts to guess passwords or replay leaked credentials.

**Mitigation:** Supabase Auth owns password verification and provider-side abuse limits. The recovery API also applies generic responses and process-local per-email/per-IP limits; multi-instance deployments need a shared limiter. Account lockout and MFA remain future work.

**Verification:** Rate-limit tests; generic error message tests; timing considerations reviewed.

**Residual Risk:** Medium without MFA. Credential stuffing against reused passwords remains possible.

---

### 4.14 Denial of Service

**Scenario:** High-volume requests, large uploads, or expensive queries exhaust backend, database, or storage resources.

**Mitigation:** Authentication rate limiting, a 10 MiB default upload limit (configurable up to 100 MiB), pre-routing `Content-Length` rejection before body parsing or authentication, required `Content-Length` for uploads, DOCX member-count/uncompressed-size limits, future query pagination/request limits, timeouts on external calls, and provider-level protections (Render/Vercel/Supabase). Health checks and monitoring.

**Verification:** Tests cover unauthenticated oversized upload rejection (413), missing/duplicate/invalid `Content-Length` handling (411/400), DOCX member-count and uncompressed-size limits, and storage-free rejection. Load tests and pagination caps remain later work.

**Residual Risk:** Medium. Managed providers absorb much of this, but application-level floods require continued tuning.

---

### 4.15 Unsafe Administrator Account Changes

**Scenario:** An administrator disables or demotes the wrong account, locks out the last administrator, changes their own privileges, or leaves a disabled/role-changed user with a live session.

**Mitigation:** Administrator account endpoints require the current database `ADMINISTRATOR` role. Self role/status changes are rejected. The service refuses to remove the last active administrator. Status disablement and role changes revoke the target's active refresh-token families, so subsequent refresh and protected-request checks fail. Every change is audited with target-user/resource context.

**Verification:** `backend/tests/test_business_model.py` covers account administration, self-change denial, last-admin protection, session revocation, audit targeting, disabled-account denial, and metadata-only oversight.

**Residual Risk:** Low. A malicious administrator can still perform allowed account changes; audit records and separation-of-duties controls are the detective boundary. There is no four-eyes approval workflow.

---

### 4.16 Unauthorized Content Preview, Versioning, and Replacement

**Threat:** A user without ownership or a READ/EDIT grant attempts to preview, list history, download a historical version, replace content, or edit plain text. A malicious EDIT recipient attempts to overwrite a newer version or abuse preview/history to obtain raw storage access. A metadata-only administrator expects content access from role alone.

**Mitigation:** Preview, history, current/historical download, replacement, and text editing all use the centralized document access policy. READ may preview, view history, and download; EDIT adds replacement and text editing; administrators remain metadata-only unless explicitly granted. Replacement and text edits require `expected_version_number`, lock the document, and return 409 rather than overwrite newer content. Files are streamed only by the backend; storage keys and presigned URLs are never exposed. Newly uploaded objects are deleted best-effort if the transaction fails. Audit details record version numbers and sanitized metadata but never content, credentials, tokens, or secrets.

**Verification:** `backend/tests/test_document_versions.py` covers READ denial of writes, admin denial, authorized replacement/text edits, stale 409, unsupported MIME 415, missing resources, storage/audit failures, and cleanup. `frontend/src/pages/DocumentDetailsPage.test.jsx` and `AuditEventDetails.test.jsx` cover READ preview/history, EDIT replacement/text editing, and safe structured audit rendering.

**Residual Risk:** Low–Medium. Version rows are immutable in normal application flows, but there is no object-lock or WORM retention, so privileged storage operators can alter objects. A manual real-browser PDF/DOCX check remains outstanding.

---

## 5. Security Principles

1. **Backend is authoritative.** Frontend visibility is never authorization.
2. **Deny by default.** Access is granted only by explicit ownership, role, or permission grant.
3. **Least privilege.** Credentials and roles carry only the access they require.
4. **Defense in depth.** Application checks plus RLS plus private storage plus audit.
5. **Tamper-evident history.** Audit records are append-only at the application layer, hash-chained, and compared with a signed checkpoint. Independent checkpoint storage remains required for privileged-host resistance.
6. **Secrets never touch source control.**
7. **Fail closed.** External-service failures deny access rather than bypass checks.

---

## 6. Residual Risks Summary

| Risk | Severity | Notes / Future Work |
|------|----------|---------------------|
| Downloaded copies cannot be recalled after revocation | Inherent | Communicate to users; consider watermarking |
| Privileged DB/host attacker can rewrite local hash chain, delete events appended after the latest checkpoint, or delete the same-host checkpoint | High | Retain signed checkpoints in an independently controlled append-only store; schedule publication and run checkpoint creation as a single job |
| Malware in uploaded files | Medium | Add antivirus scanning; validation is not scanning |
| Live Supabase Storage bucket policy is checked in the current environment | Medium | Verify private policy, least-privilege keys, and upload/delete behavior before deployment |
| Upload object and metadata are not transactional | Low–Medium | Best-effort cleanup only; monitor orphans and add reconciliation |
| Soft-deleted metadata and historical version objects can outlive a failed cleanup | Low–Medium | Cleanup is best-effort after commit; log and reconcile private orphans |
| Historical versions are immutable only at the application layer | Low–Medium | Version rows cannot be updated through the API, but privileged storage/database operators can alter objects; add object-lock/WORM retention if required |
| Audit summaries/export and owner audit views absent | Low | Global admin detail filters work; add aggregate/export features only if required |
| Stolen access token valid until expiry | Medium | Short TTL; consider token binding |
| Credential stuffing without MFA | Medium | Evaluate MFA |
| Application-level DoS | Medium | Rate limits, provider protections |
| Direct client IP may be a proxy address | Low | Configure trusted proxy handling deliberately if deployment requires real client IPs |

---

## 7. Phase 1 Implementation Notes (Verified)

These notes record what is actually implemented in the Phase 1 scaffold. Planned mitigations elsewhere in this document are not active yet.

- **CORS is configuration-driven.** Origins come from `CORS_ALLOWED_ORIGINS`; wildcards are rejected outside development. Automated tests confirm allowed origins receive CORS headers and untrusted origins do not.
- **The health endpoint exposes no configuration.** `GET /health` returns only `status`, `service`, and `version`. It performs a process-level check and does **not** query PostgreSQL or Supabase Storage. A test asserts that configuration markers are absent.
- **No authorization exists yet.** Authentication, document access, permissions, and audit persistence are not implemented in Phase 1. The threat mitigations that depend on them are planned, not verified.
- **No production security headers yet.** CSP and HSTS are planned for Phase 10 deployment hardening.

---

## 8. Phase 2 Implementation Notes (Verified)

These notes record what the Phase 2 schema does and does not enforce. Planned mitigations elsewhere remain planned unless listed here.

- **Schema constraints are enforced by PostgreSQL.** Unique, check, and partial-unique indexes are applied by the initial Alembic migration and exercised by tests against a real PostgreSQL instance. See `docs/DATABASE.md`.
- **RLS is not enabled.** The backend connects with a single privileged database role that bypasses Row-Level Security. Phase 3 keeps that model while adding application-level authentication and roles. Authorization is therefore **not** provided by the database, and TrustVault must not be described as RLS-complete.
- **Audit history is retained, not yet written.** `audit_events.actor_id` and `audit_events.document_id` use `ON DELETE SET NULL` so deleting a user or document preserves the event with its action and details. No application code writes audit rows yet (Phase 7), and the `event_hash`/`previous_hash` columns are not populated by any trust boundary yet.
- **Audit immutability is not database-enforced.** A database immutability trigger or revoke-based policy would conflict with the `ON DELETE SET NULL` foreign keys and with the application-level design, so it is deferred to Phase 7 alongside the write path and hash-chain verification.
- **Deletion semantics are deliberate.** `documents.owner_id` uses `ON DELETE RESTRICT`, `document_permissions` cascades from documents/users, and `documents.deleted_at` provides soft deletion. These choices are documented in `docs/DATABASE.md`.
- **Only sanitized placeholders are committed.** `backend/.env.example` contains placeholders; `DATABASE_URL` is supplied through the environment. No production connection string or credential is stored in the repository, and the Phase 2 migration was never run against production.

**Residual risk after Phase 2:** Medium, unchanged for authorization. The database is prepared but no access control path exists until Phase 3; database-level defense in depth is deferred.

---

## 9. Phase 3 Implementation Notes (Verified)

These notes record the authentication controls that are actually implemented. Planned document and audit controls remain planned.

- **Password storage:** bcrypt hashes only; cost is configurable (default 12). Passwords are limited to 12–72 UTF-8 bytes. Unknown accounts perform a dummy bcrypt verification to reduce timing-based enumeration.
- **Access tokens:** HS256 JWTs with issuer/audience, type, expiry, session, and role claims. The role claim is informational; authorization reads the current database role.
- **Refresh sessions:** 256-bit opaque tokens stored as SHA-256 hashes, grouped into families. Rotation marks the old token revoked and links the replacement; reuse revokes the family.
- **Immediate invalidation:** protected requests verify the user's active status and an active refresh family on every call. Logout, disablement, and reuse detection invalidate existing access tokens without waiting for JWT expiry.
- **Cookie and CSRF controls:** refresh cookie is HttpOnly with path `/api/v1/auth`; production requires Secure. Auth POSTs enforce an exact Origin allow-list. A per-session CSRF token is not implemented, and cross-site cookies remain dependent on browser policy.
- **Rate limiting:** in-memory and per process. It is not a shared limiter and can be bypassed by distributing requests across instances; production hardening must address this.
- **Account provisioning:** public registration always creates a normal `USER`. Administrator accounts require the server-side CLI or an authorized administrator role change; clients cannot request a role at registration.
- **Secret-free logging:** tests assert that auth logs do not include passwords, access tokens, refresh tokens, or email addresses. Alembic logging is configured with `disable_existing_loggers=False` so application loggers remain active.
- **Residual risks after Phase 3:** no MFA, no account lockout, no idle timeout, no per-session CSRF token, no shared rate limiter, and no deployed verification of cross-site cookies. Stolen access tokens remain valid only while the session stays active and the token stays unexpired (15 minutes by default).

---

## 10. Phase 4 Implementation Notes (Verified with Mocked Storage)

These notes record the upload/storage controls that are actually implemented. Downloads, permissions, and audit writes remain planned.

- **Authorization:** `POST /api/v1/documents/upload` requires an active authenticated user; anonymous callers receive 401 and disabled accounts are rejected. Ownership is taken from the authenticated user, never client input.
- **Input validation:** Extension and declared-MIME allow-list, magic-byte/signature checks, empty-file rejection, 10 MiB default limit with pre-routing `Content-Length` rejection, filename length/control/Unicode-format/path-separator rejection, DOCX member count/uncompressed-size checks, and NUL-free UTF-8 TXT validation.
- **Key and checksum integrity:** Storage keys are generated from server-side UUIDs; the backend computes SHA-256 from received bytes and ignores client checksums. The user filename never becomes a path.
- **Private access:** No direct/presigned URL or storage key is returned to the client. The frontend never receives Supabase Storage credentials.
- **Failure behavior:** Missing/misconfigured storage or Supabase Storage failure returns generic 503 with no metadata row. A metadata commit failure after upload returns generic 500 and attempts best-effort object deletion.
- **Secret handling:** Storage errors are logged without credentials or internal details; configuration is server-side only. Tests assert secret-safe logging and responses.
- **Frontend migration:** TypeScript/TSX was removed in favor of JavaScript/JSX; lint and build pass.
- **Verification:** 107 backend tests passed at Phase 4 completion. Storage tests use a fake adapter. A later manual smoke test verified live private-bucket privacy, credentials, upload, download, metadata, and deletion.
- **Not implemented at Phase 4 completion:** Download/listing, permission grants, audit writes, malware scanning, RLS, and deployment.

---

## 11. Phase 5 Implementation Notes (Verified with Mocked Storage)

These notes record the document-management controls implemented at Phase 5 completion. Permission grants and audit writes were still planned at that point.

- **Metadata scoping at Phase 5 completion:** Owners saw only their active documents; administrators could read active metadata across the library; users without a grant saw no other documents. Update, download, and delete required ownership. Inaccessible and missing IDs both return generic 404.
- **Query safety:** Name search is parameterized and escapes `\`, `%`, and `_` so user input cannot become a wildcard. Category/owner/date filters are parameterized; sort columns are an allow-list; page size is bounded.
- **Metadata integrity:** Only `name`, `category`, and `description` can be changed. Storage key, owner, MIME type, size, checksum, and timestamps are not client-updatable; extra fields are rejected.
- **Download:** The backend authorizes ownership before reading from private storage and streams the object. Responses set an attachment filename, `Content-Length`, `Cache-Control: private, no-store`, and `X-Content-Type-Options: nosniff`. Filenames are RFC 5987-encoded with sanitized ASCII fallbacks.
- **Deletion:** Soft deletion sets `deleted_at` and excludes the row from all normal reads. Supabase Storage cleanup happens after the database commit and is best-effort; failure is logged, and metadata is retained.
- **Failure handling:** Missing storage objects return generic 404; storage configuration/operation failures return generic 503. No storage key, URL, or credential is exposed to the client or logs.
- **Verification at Phase 5 completion:** 127 backend tests passed, including management authorization, filter/query safety, pagination, IDOR behavior, protected-field rejection, download headers/failures, soft delete, and cleanup failure. Frontend lint/build passed.
- **Not implemented at Phase 5 completion:** Explicit READ/EDIT grants, immediate revocation, audit events, live Supabase Storage download/delete verification, malware scanning, RLS, and deployment.

---

## 12. Phase 6 Implementation Notes (Verified with Mocked Storage)

These notes record the authorization controls actually implemented for named-user sharing. Audit writes and live storage verification were still outstanding at Phase 6 completion.

- **Central enforcement:** `app/services/document_access.py` resolves access from current ownership and active grants on every request and maps it to explicit metadata/read/edit/delete/manage capabilities. There is no authorization cache.
- **Grant management:** Only the document owner can list, grant, update, or revoke access. Recipients must be active registered users identified by normalized email. Same-level grants are idempotent; conflicting levels return 409; cross-document permission IDs return 404.
- **History:** Updates revoke the previous row and insert a replacement. Revocation is idempotent and retains the row. The partial unique index prevents multiple active grants.
- **Administrator boundary:** Administrators can read metadata for all active documents but receive no content, edit, delete, or permission-management capability unless they own the document or receive an explicit grant.
- **Shared listing:** /api/v1/documents/shared-with-me includes only active grants on active, non-deleted documents. The regular document list includes owned plus actively shared documents.
- **Revocation semantics:** After revocation, content and edit requests return generic 404 because the user no longer has document visibility. Downloaded copies remain outside the system's control.
- **Verification:** 146 backend tests pass at Phase 6 completion, including 19 Phase 6 tests for owner-only management, READ/EDIT/administrator boundaries, forged fields, idempotency/conflicts, history retention, immediate revocation, shared-list exclusions, and cross-document IDOR. Frontend lint/build pass.
- **Not implemented/verified at Phase 6 completion:** Audit event writes/views, live Supabase Storage behavior, malware scanning, RLS, and deployment.

---

## 13. Phase 7 Implementation Notes (Verified Locally with Mocked Storage)

These notes record the audit controls actually implemented. Live private-bucket storage passed its smoke test, and Supabase is at migration `0004` with no Alembic drift; deployment remains unverified.

- **Append-only writer:** `app/services/audit.py` sanitizes metadata and appends events under an advisory transaction lock with contiguous `chain_index`, `previous_hash`, and canonical SHA-256 `event_hash`.
- **Transactional semantics:** Mandatory audit events for successful state changes share the protected transaction; audit failure rolls back the change and returns generic 500. Denial events are best-effort and cannot change the 403/404 outcome.
- **Coverage:** registration, login success/failure, logout, upload, metadata update, download, delete, permission grant/update/revoke, and typed document/permission/audit-access denials.
- **Request metadata:** validated or generated request IDs are echoed; details include direct socket client IP and sanitized, length-limited user-agent. Sensitive keys and content are rejected, and metadata depth/size is bounded.
- **Integrity verification:** chain verification detects index gaps, previous-hash mismatches, and modified event hashes. HMAC-SHA256 signed checkpoints support valid/stale/missing/unconfigured/unavailable/invalid statuses.
- **Administrator boundary:** audit query and integrity endpoints are global-administrator-only; non-admin attempts are denied and audited. No API allows audit modification or deletion.
- **Verification:** 158 backend tests pass, including 12 Phase 7 tests for event coverage, admin authorization/filtering, tamper and middle-removal detection, checkpoint staleness/truncation/signature failure, audit-write rollback, metadata sanitization, and unsafe request IDs. Frontend lint/build pass.
- **Residual risk:** No independent immutable checkpoint store or scheduled checkpoint publication exists. A privileged attacker who controls both database and host filesystem can still alter history; the signed same-host checkpoint only detects changes relative to the last trusted copy. Audit exports, aggregate summaries, owner audit views, RLS, malware scanning, and deployment remain outstanding.

---

## 14. Phase 8 Verification Notes (Verified Locally)

The dedicated security suite is `backend/tests/test_security.py`; it contains 46 cases named after the threat sections below. The full 233-test backend suite passed locally with 90% statement coverage. A 2026-10-21 re-audit added pre-routing upload size enforcement, Unicode format-control rejection, checkpoint-monotonicity protection, and focused regressions for malformed multipart, DOCX expansion limits, disabled accounts, and forged audit roles. CI is configured in `.github/workflows/backend-tests.yml` but has not yet run remotely.

| Threat | Automated verification |
|--------|------------------------|
| 4.1 IDOR | `test_threat_4_1_cross_user_document_operations_are_denied` (GET, download, PATCH, DELETE), `test_threat_4_1_4_4_mr10_grant_read_then_revoke_is_immediate_and_audited`, `test_threat_4_1_guessed_and_missing_ids_are_indistinguishable` |
| 4.2 Unauthorized downloads | `test_threat_4_2_download_denial_precedes_storage_access`; existing cross-user and admin denial tests |
| 4.3 Privilege escalation | `test_threat_4_3_role_injection_is_rejected_at_registration`, `test_threat_4_3_forged_role_claim_cannot_escalate_upload`, `test_threat_4_3_4_8_forged_admin_claim_cannot_read_audit`, `test_threat_4_3_administrator_role_does_not_grant_content_or_sharing` |
| 4.4 Access after revocation | `test_threat_4_1_4_4_mr10_grant_read_then_revoke_is_immediate_and_audited`; existing immediate-revocation tests |
| 4.5 Malicious uploads | `test_threat_4_5_malicious_uploads_are_rejected_without_storage` (executable, missing/mismatched MIME, signature mismatch, HTML-as-PNG, empty, malformed DOCX), `test_threat_4_5_malformed_multipart_is_rejected_without_storage`, plus DOCX member/uncompressed-size unit tests |
| 4.6 Path manipulation | `test_threat_4_6_path_manipulation_filenames_are_rejected`, `test_threat_4_6_control_characters_cannot_reach_storage_keys`, `test_threat_4_6_storage_keys_never_use_client_filenames`, plus bidi-format filename validation |
| 4.7 Unauthorized permission changes | `test_threat_4_7_recipient_cannot_manage_permissions` plus existing owner-only grant tests |
| 4.8 Audit tampering | `test_threat_4_8_audit_api_rejects_mutation_methods` (POST/PUT/PATCH/DELETE on both audit endpoints), `test_threat_4_8_audit_api_has_no_event_mutation_route`, `test_threat_4_3_4_8_forged_admin_claim_cannot_read_audit`, `test_checkpoint_creation_refuses_to_replace_newer_checkpoint` |
| 4.9 Metadata leakage | `test_threat_4_9_denials_do_not_disclose_document_metadata`, `test_threat_4_1_guessed_and_missing_ids_are_indistinguishable` |
| 4.10 Exposed credentials | `test_threat_4_10_internal_failures_do_not_expose_credentials`; secret-safe logging and repository scan remain operational checks |
| 4.11 Weak RLS policies | `test_threat_4_11_application_authorization_is_authoritative_without_rls`; RLS is disabled and policy tests remain outstanding |
| 4.12 Session and token theft | `test_threat_4_12_expired_access_token_is_rejected`, `test_threat_4_12_tampered_access_token_is_rejected`, `test_threat_4_12_logout_invalidates_previously_stolen_access_token`, `test_threat_4_12_disabled_users_cannot_access_documents_or_audit` |
| 4.13 Brute force and credential stuffing | `test_threat_4_13_brute_force_is_rate_limited_without_disclosure` plus existing generic-error and registration-limit tests |
| 4.14 Denial of service | `test_threat_4_14_oversized_upload_is_rejected_before_storage`, `test_threat_4_14_oversized_upload_is_rejected_before_authentication`, `test_threat_4_14_upload_without_content_length_is_rejected`, and `test_request_limits.py` missing/invalid/duplicate/oversized header tests; DOCX expansion limits are unit-tested |

**Limitations:** The suite verifies implemented controls, not the absence of vulnerabilities. RLS, malware scanning, shared multi-instance rate limiting, MFA, and independent checkpoint storage remain unimplemented or unverified; deployment and a full browser walkthrough remain unverified. Events appended after the latest checkpoint and then deleted cannot be detected by that checkpoint. Checkpoint creation is not locked against concurrent writers; run it as a single scheduled job.

---

## 15. Document Content and Version-History Verification Notes (Verified Locally)

This phase added authorized previews, replacement uploads, plain-text editing, immutable version metadata, and safe structured audit rendering. Supabase is at migration `0005` with no Alembic drift; no deployment was performed.

- **Authorization:** Preview, version listing, historical/current downloads, replacement, and text editing use the centralized access policy. READ may preview/list/download history; EDIT adds replacement and text editing. Administrators without a grant receive 403 for content operations.
- **Concurrency and cleanup:** Replacement and text editing require the expected current version, lock the document row, recheck the pointer, and return 409 on stale writes. Newly uploaded objects are best-effort deleted if the transaction or audit write fails. Soft deletion attempts cleanup of current and historical objects.
- **Data exposure:** Responses stream content only through the backend with `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`. Storage keys, presigned URLs, file contents, and secrets are excluded from metadata and audit details.
- **Audit UI:** Administrator audit details are rendered as structured text and nested metadata without `dangerouslySetInnerHTML`; long values wrap and raw JSON is optional.
- **Verification:** The current suite has 269 backend tests passing with 88% statement coverage, including migration backfill/downgrade, version constraints, READ/admin denial, EDIT replacement/text editing, stale writes, storage/audit failures, and deletion cleanup. Frontend: 23 tests across 8 files, lint with warnings and no errors, and production build successful.
- **Residual risk:** Real-browser PDF iframe and DOCX fallback behavior still require manual verification. Version immutability is enforced by application behavior and database rows, not object-lock/WORM storage policy.

---

## 16. PDF Viewing, Annotation Editing, and Integrity Verification Notes (Verified Locally)

This phase added native PDF rendering via Mozilla PDF.js, in-browser PDF annotation editing via `pdf-lib`, optimistic versioning for PDF revisions, owner-only version deletion with current-version rollback, paginated document activity history for owners, stale-editor protection, and audit trail integrity hardening with schema versioning (`0006`). The repository migration head is `0007`; live Supabase migration state and drift were not re-verified in this local run.

- **Client-Side PDF Sandbox:** PDF.js is configured with `isEvalSupported: false` to eliminate arbitrary script evaluation within the PDF rendering worker. The PDF worker is bundled and served locally from Vite assets without external CDNs.
- **Streaming Authorization:** PDF bytes are streamed through authenticated backend endpoints with `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`. No private Supabase object URLs or service credentials are leaked to the browser.
- **In-Browser Annotation Security:** Annotations are drawn onto HTML5 canvas and embedded directly into the PDF binary using `pdf-lib` entirely in browser memory without sending document data to third-party APIs. Content changes are validated server-side as authentic PDFs and saved as new versions with optimistic concurrency (`expected_version_number`).
- **Owner-Only Version Deletion and Rollback:** Only the document owner can delete a version. At least one version must remain; deleting the final version returns HTTP 400. Deleting the current version rolls back to the highest remaining version and atomically updates the active storage pointer, MIME type, size, and checksum. Private storage objects are removed, retained totals recalculated, version numbers never reused, and audit events record rollback state without exposing storage keys.
- **History and Conflict Integrity:** Version history and owner activity are server-paginated with bounded page sizes and deterministic ordering. Owner routine preview/download events are excluded from the owner timeline without changing administrative audit queries. A 409 conflict marks text/PDF editors stale, disables further saves, and requires close/reopen, preventing a refreshed-but-stale draft from overwriting a newer revision.
- **Audit Trail Integrity Hardening:** Contiguous hash chain with versioned `hash_schema: trustvault-audit-event-v1`, deterministic JSON canonicalization, and HMAC-SHA256 signed checkpoints. Verified via automated tampering tests and the `/admin/audit` integrity dashboard.
- **Verification:** 269 backend tests pass with 88% statement coverage, 23 frontend tests pass across 8 files, and the Vite production build succeeds. Frontend lint reports warnings but no errors.
