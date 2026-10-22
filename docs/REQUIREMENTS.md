# TrustVault — Requirements Document

## 1. Problem Statement

Organizations need a secure, auditable document management system that enforces strict access control at every layer. TrustVault is a multi-tenant document vault where document owners control exactly who can read or edit their files, administrators oversee activity, and every action is recorded in a tamper-evident audit trail. The system must guarantee that backend enforcement — not frontend visibility — is the sole authority for access decisions.

## 2. Mandatory Requirements

### MR-1: Authentication with Role-Based Access

**Description:** The system must support two account roles: **Administrator** and **User**. Users authenticate with secure credentials. Document access is contextual: a user owns every document they upload and may receive per-document READ or EDIT access to other users' documents.

- Administrators manage accounts, review metadata for all active documents, view the global audit log, and access administrator areas. Administrator identity does not automatically grant document content access.
- Users can upload documents and thereby become their owner. Owners can organize, share, and manage their own documents.
- A user without ownership or an explicit READ/EDIT grant cannot access another user's document content or metadata.

**Phase:** 3 (authentication and role baseline), with document-level access enforced in Phases 5–8 and account administration added in the business-model correction.
**Verification:** Tests confirm registration always creates `USER`, role/status administration, last-admin protection, self-change denial, disabled-account rejection, session revocation, and document-level ownership/grant enforcement.

---

### MR-2: Document Upload, Organization, Search, and Management

**Description:** Every active authenticated user can upload documents, organize them into categories, search across documents they may access, and manage documents they own. File metadata (name, category, upload date, size, MIME type) is stored in the database. Actual file content is stored in private object storage.

**Phase:** 4 (Storage and Upload), 5 (Document Management and Search)
**Verification:** Phase 4 has integration tests for validated upload and metadata persistence. Phase 5 adds listing/search, metadata visibility/updates, streamed download, and soft deletion tests using a mocked storage adapter. A live private-bucket connectivity, upload, download, metadata, and delete smoke test passed.

---

### MR-3: Named-User, Per-Document READ and EDIT Permissions

**Description:** Document owners grant READ or EDIT access to specific named users on a per-document basis. Permissions are stored at the individual document-user level, not at group or role level. A user without explicit permission has no access.

**Phase:** 6 (Document Permissions and Revocation)
**Verification:** Phase 6 tests confirm owner-only grants, READ/EDIT capability boundaries, immediate post-revocation denial, grant-history retention, and shared-document listing. Phase 7 verifies grant, update, revoke, and denied-permission audit events.

---

### MR-4: Owner-Controlled Permission Grants and Revocation

**Description:** Only the document owner can grant or revoke permissions. Revocation is immediate: the target user loses access on the next request. Granting, updating, or revoking a permission creates an audit record in the same transaction.

**Phase:** 6 (Document Permissions and Revocation), 7 (Audit)
**Verification:** Phase 6 tests confirm immediate denial after revocation, owner-only management, cross-document permission-ID rejection, and retained grant history. Phase 7 tests confirm permission success/denial audit events.

---

### MR-5: Backend Enforcement Preventing Unauthorized Access

**Description:** The backend must independently verify authorization on every request involving document content or metadata. Frontend UI hiding is insufficient. Requests to read, download, update, or delete a document must be rejected with an appropriate HTTP status (403 or 404) if the requesting user lacks permission.

**Phase:** 5, 6, 8 (Security Tests)
**Verification:** Direct API tests bypassing the frontend; cross-user access denial tests; automated penetration-style tests.

---

### MR-6: Audit Records for All Significant Actions

**Description:** The system must create immutable audit records for:

- Document uploads
- Document downloads
- Document modifications
- Document deletions
- Permission grants
- Permission revocations
- Denied access attempts

Each record includes: timestamp, acting user, target document, action type, outcome (success or denied), and client metadata (IP address, user agent). Audit records must be tamper-evident with hash-chain integrity and independently verifiable checkpoints.

**Phase:** 7 (Audit Trail and Administrator Activity)
**Verification:** Integration tests confirming audit records are created for all listed events; hash chain integrity tests; tests confirming audit records cannot be modified through the API.

---

### MR-7: Search by Name, Owner, Category, and Date

**Description:** Users can search for documents they have permission to access. Search supports filtering by:

- Document name (partial match)
- Owner
- Category
- Upload date / date range

Search results must be filtered by the requesting user's permissions — a user must never see documents they are not authorized to access.

**Phase:** 5 (Document Management and Search)
**Verification:** Phase 5 tests cover name search, category/owner/date filters, sorting, pagination, and initial visibility scoping. Phase 6 tests extend scoping to explicitly shared documents and revoked/deleted exclusions.

---

### MR-8: File Upload Validation

**Description:** All uploaded files must be validated before storage:

- File size limits enforced
- MIME type / file extension allow-list enforced
- File content inspected to verify claimed type matches actual content (magic byte verification)
- Malicious file name patterns rejected (path traversal, null bytes, excessively long names)
- Files are stored with system-generated names; original names are metadata only

**Phase:** 4 (Private Storage and Validated Uploads) — implemented
**Verification:** Unit and integration tests cover each validation rule, invalid file uploads, generated storage keys, and safe metadata. Live Supabase Storage integration passed a private-bucket smoke test.

---

### MR-9: Administrator View of Document Activity and Permission Changes

**Description:** Administrators can view:

- All audit log entries
- Document activity summaries (uploads, downloads, changes per document)
- Permission change history per document
- User activity summaries

Administrators can also search accounts, inspect last-login/owned-document counts, change account roles or status with session revocation, and inspect each document's permission history. Administrators cannot modify or delete audit records through the application and do not receive private content automatically.

**Phase:** 7 (Audit Trail and Administrator Activity)
**Verification:** Phase 7 integration tests confirm administrator access to logs and integrity status, filtering/pagination, non-admin denial, and the absence of audit mutation endpoints. Aggregate document/user activity summaries and export are not implemented.

---

### MR-10: Automated Tests Proving Cross-User Access Denial

**Description:** The test suite must include explicit tests where:

- User A creates a document
- User B (with no permission) attempts to read, download, edit, and delete the document
- All four attempts are denied with appropriate HTTP status codes
- User A grants READ to User B; User B can read but not edit
- User A revokes READ; User B is immediately denied again
- All actions produce audit records

**Phase:** 8 (Security Tests and Threat-Model Verification — implemented)
**Verification:** Dedicated `backend/tests/test_security.py` cross-user suite; the full suite runs in `.github/workflows/backend-tests.yml` on backend pushes and pull requests.

---

## 3. Role Capabilities Matrix

| Capability                          | Administrator | User |
|-------------------------------------|:---:|:---:|
| View document metadata              | All active metadata | Own + shared |
| Upload documents                    | Yes | Yes |
| Delete own documents                | Yes | Yes |
| Delete others' documents            | No  | No  |
| Grant/revoke per-document access    | Own documents only | Own documents only |
| View audit logs                     | Yes | No  |
| Manage users/roles                  | Yes, excluding unsafe self-change | No  |
| Search documents                    | All metadata | Own + shared |
| Download documents                  | Explicit grant only | Own + shared grants |
| Edit documents                      | Explicit EDIT only | Own + shared EDIT |
| Modify audit records via API        | No  | No  |

**Authorization note:** administrator identity grants metadata oversight of all active documents, not content access, editing, deletion, or permission management. Administrators can manage permissions only for documents they own. Content and mutation capabilities come from ownership or an explicit READ/EDIT grant. This deliberately avoids treating administrator identity as automatic document-content authorization. The last active administrator cannot be demoted or disabled, and administrators cannot change their own role or status.

### Phase 3 Implementation Status (Verified Locally)

- **FA-1:** Registration, login, access tokens, and rotating refresh sessions are implemented. Public registration always creates a normal `USER`; administrator accounts require the provisioning CLI or an authorized administrator role change.
- **FA-2:** Passwords are stored only as bcrypt hashes. Tests verify hashing, verification, and password-length limits.
- **FA-3:** Partially met. Access tokens expire after 15 minutes and refresh sessions expire after 7 days by default, with rotation and reuse detection. A configurable **idle** timeout is not implemented.
- **FA-4:** Invalid credentials and disabled accounts return the same generic login error, and unknown accounts perform dummy bcrypt work.
- **Additional controls:** auth POSTs enforce an Origin allow-list; auth endpoints are rate limited in-process; logout, disablement, and reuse detection invalidate access through database session checks.
- **Not yet met:** MFA, account lockout, a shared multi-instance rate limiter, per-session CSRF tokens, and production deployment verification.

### Phase 4 Implementation Status (Verified Locally with Mocked Storage)

- **FA-5:** Implemented. Validated files are sent to a private Supabase Storage bucket via the backend only, with backend-generated storage keys and no direct/presigned URL exposure. The private-bucket policy and live upload/download/delete smoke test were verified in the current environment.
- **MR-2 upload portion:** Implemented for every active authenticated user, with category/description metadata persisted in PostgreSQL and ownership assigned to the uploader.
- **MR-8:** Implemented. Extension, declared MIME, magic-byte/signature, filename, empty-file, size, DOCX package, and TXT encoding checks are covered by tests. Files are not virus-scanned.
- **Role enforcement:** Anonymous callers are denied; document ownership is derived from the authenticated session, not client input.
- **Integrity:** The backend computes SHA-256; a database failure after upload triggers best-effort object deletion.

### Phase 5 Implementation Status (Verified Locally with Mocked Storage)

- **MR-2:** Implemented for owner-managed documents: list/search/filter/sort/paginate metadata, inspect details, update mutable metadata, download content, and soft delete. A live private-bucket smoke test passed.
- **MR-5:** Document endpoints enforce authentication, current role, and ownership server-side; metadata visibility for administrators does not grant content or owner-only actions. Missing/inaccessible IDs return generic 404 responses.
- **MR-7:** Name (partial, literal wildcards), owner ID, category, and created-date filters are implemented with pagination and allow-listed sorting. Results are owner/grant-scoped; administrators can review all active metadata.
- **FA-6 / FA-7 / FA-8:** Metadata is queryable/filterable; deletion marks `deleted_at` and attempts object cleanup; search results are scoped. At Phase 5 completion, per-document sharing scoping was not implemented.
- **Integrity / privacy:** Downloads are proxied through the authenticated backend with safe attachment headers and no storage key or presigned URL. Name search escapes SQL wildcard characters; sort fields are allow-listed.
- **Not yet met at Phase 5 completion:** explicit READ/EDIT grants, immediate revocation, audit events for view/download/edit/delete, live bucket verification, malware scanning, and deployment.

### Phase 6 Implementation Status (Verified Locally with Mocked Storage)

- **MR-3:** Implemented. Owners grant READ/EDIT to named active accounts by email; owner access is implicit. Grant/list/update/revoke endpoints are owner-only and reject forged recipient/grantor fields.
- **MR-4:** Implemented except audit persistence. Same-level grants are idempotent, conflicts return 409, level updates retain history, revocation is idempotent, and access is rechecked from the database on every request.
- **MR-5:** Document detail, edit, download, delete, and permission endpoints use centralized authorization with 404 for missing/unrelated resources and 403 for visible-but-insufficient capability. Metadata-only administrators are denied content access.
- **MR-7:** Regular listing includes owned and actively shared documents; `/shared-with-me` excludes revoked grants and deleted documents. Administrators retain metadata oversight.
- **Frontend:** Access-level badges, a shared-documents route, and an owner-only permission-management page with grant, update, revoke confirmation, and history are implemented.
- **Not yet met at Phase 6 completion:** permission/document audit events, live bucket verification, malware scanning, RLS, and deployment.

### Phase 7 Implementation Status (Verified Locally with Mocked Storage)

- **MR-6:** Implemented for authentication, upload, metadata update, download, delete, permission grant/update/revoke, and denied access. Each event records timestamp, actor, optional document, action, outcome, request ID, direct client IP, and user-agent. Details are sanitized and bounded.
- **MR-6 integrity:** Events use a contiguous chain index, previous-event hash, canonical SHA-256 hashing, and a PostgreSQL advisory transaction lock. HMAC-SHA256 signed checkpoint files detect changes relative to the last trusted checkpoint, and checkpoint creation refuses invalid or backward replacements. Events appended after the latest checkpoint and then deleted are not detectable by that checkpoint.
- **MR-4 audit:** Successful grants/updates/revocations append audit events in the protected transaction; denial events are best-effort so they cannot alter the denial outcome.
- **MR-9:** Global administrators can query all audit events with actor, document, action, outcome, and UTC date filters, plus read chain/checkpoint integrity. There is no audit modification/deletion endpoint.
- **FA-14:** Implemented for state-changing actions; idempotent no-op requests do not duplicate state-change events. Login failures and authorization denials are recorded.
- **FA-15 / FA-16:** Implemented for the checkpoint-covered prefix; verification detects modified, reordered, and removed events at or before the latest checkpoint, and no API exposes audit mutation. Tail deletions after the latest checkpoint require independent checkpoint publication.
- **FA-17:** Partially met. Querying, filtering, and pagination are implemented; CSV/JSON export is not.
- **MR-9 summaries:** Aggregate document/user activity summaries are not implemented. Administrators can derive detail views through filters and the existing permission history.
- **Administrator UI:** `/admin/audit` provides filters, pagination, event details, and an integrity panel. Owner-scoped audit views are intentionally not part of the Phase 7 policy.
- **Not yet met / unverified:** independent immutable checkpoint storage and scheduled publication, audit export and aggregate summaries, deployment, RLS, and malware scanning. Live private-bucket storage and the current Supabase migration were verified locally.

### Phase 8 Implementation Status (Verified Locally)

- **MR-5 / MR-10:** Implemented in a dedicated 46-case security suite plus focused request-limit tests. User B is denied read, download, edit, and delete for User A's document; after a READ grant User B can read/download but not edit/delete; revocation restores immediate denial. Grant, revocation, and every denial are audited.
- **IDOR:** Unrelated existing UUIDs and random missing UUIDs return the same generic 404 body without document name, owner identity, checksum, or storage key.
- **Privilege escalation:** Registration role injection is rejected, a validly signed token with a forged administrator role claim cannot escalate a normal user, and administrator identity does not grant document content or sharing rights. These denials append audit records.
- **Audit tampering:** Every non-GET method against the audit collection and integrity endpoints returns 405, event-specific mutation paths return 404, and audit row counts remain unchanged.
- **Upload/path attacks:** Executable, content-mismatched, missing-content-type, empty, malformed-multipart, and malformed-document uploads are rejected before storage; traversal/absolute names return 400; control and Unicode format-control characters (including bidi overrides) cannot reach server-generated keys; DOCX member/uncompressed-size limits are tested.
- **Session/rate/DoS:** Expired and tampered access tokens return 401, logout and disabled accounts invalidate protected document/audit access, brute-force login attempts return 429 with `Retry-After`, pre-authentication oversized uploads return 413, uploads without `Content-Length` return 411, and invalid/duplicate lengths return 400.
- **Audit integrity:** Checkpoint creation refuses invalid or newer checkpoint replacement; forged administrator claims cannot read audit data; tail deletion after the latest checkpoint remains outside checkpoint detection.
- **Verification:** 233 backend tests pass locally with 90% statement coverage. A GitHub Actions workflow runs the suite with coverage, but remote CI execution has not yet been verified.
- **Not yet met / unverified:** RLS policy tests (RLS remains disabled; application authorization is the primary boundary), malware scanning, and deployment. A live private-bucket storage smoke test passed, and the current Supabase database is at migration `0003`.

### Phase 9 Implementation Status (Verified Locally)

- **MR-2 / MR-7:** The frontend exposes registration and login, a live access dashboard, a dedicated upload page with validation/progress feedback, a document library with name, category, exact owner-ID, and date filters plus sorting and pagination, document details, metadata editing, download, and owner-only deletion.
- **MR-9:** Administrators can reach the role-gated administrator area, account management, metadata/permission oversight, and audit viewer, including event filters, pagination, denied indicators, metadata details, and hash-chain/signed-checkpoint integrity verification.
- **MR-3 / MR-4:** Owners can grant, update, and revoke READ/EDIT access through the sharing page and review active grants and revoked history. Permission changes refresh immediately after the backend confirms them; no administrator override is presented.
- **UI quality:** Desktop uses a sidebar workspace shell and mobile uses labelled scrollable navigation. Forms validate input and surface bounded server error details. Major routes provide loading, error, empty, success, confirmation, forbidden, and not-found states.
- **Verification:** `npm run lint` reports 0 warnings/errors, `npm test` passes 10 Vitest/React Testing Library tests, and `npm run build` succeeds with the existing chunk-size warning.
- **Not yet met / unverified:** A browser-based manual walkthrough with live accounts remains outstanding. The live backend health, private Supabase Storage smoke test, and current Supabase migration were verified locally; RLS, malware scanning, and deployment remain unverified.

### Business-Model Correction Status (Verified Locally)

- **MR-1:** Replaced the legacy three-role model with `ADMINISTRATOR` and `USER`. Migration `0004` maps legacy `DOCUMENT_OWNER`/`VIEWER` accounts to `USER`, preserves administrators, adds `last_login_at`, and rebuilds role/status indexes.
- **MR-2:** Upload is available to every active user; ownership is assigned from the authenticated session.
- **MR-9:** Administrators can search/filter accounts, inspect detail/last login/owned-document counts, change roles or status, inspect document permission history, and review targeted audit events. Self role/status changes and removal of the last active administrator are rejected. Disablement and role changes revoke target sessions.
- **MR-6:** Account status/role changes audited with `target_user_id` and `resource_type` without changing the audit hash payload schema. Audit queries can filter target user and resource type.
- **Verification:** 233 backend tests and 10 frontend tests pass; frontend lint and production build pass.

---

## 4. Functional Acceptance Criteria

### Authentication
- FA-1: Users can register, log in, and receive a secure session/token.
- FA-2: Passwords are never stored in plaintext.
- FA-3: Sessions expire after a configurable idle timeout.
- FA-4: Invalid credentials return a generic error (no user-enumeration leakage).

### Document Management
- FA-5: Uploaded files are stored in private object storage, not publicly accessible.
- FA-6: Document metadata is queryable and filterable.
- FA-7: Document deletion removes the file from storage and marks the metadata appropriately.
- FA-8: Search results are scoped to the requesting user's permissions.

### Permissions
- FA-9: A newly uploaded document's content is accessible only to the owner; administrators may see metadata but require an explicit grant for content.
- FA-10: Granting READ allows reading and downloading but not editing, deleting, re-sharing, or managing permissions.
- FA-11: Granting EDIT allows reading, downloading, and editing but not deleting, re-sharing, or managing permissions.
- FA-12: Revocation takes effect immediately.
- FA-13: Permission changes are recorded in the audit trail. The permission history table also retains grant/revoke rows.

### Audit
- FA-14: Every state-changing action listed in MR-6 produces one audit record; denied attempts and login failures are recorded separately. Idempotent no-ops do not create duplicate state-change events.
- FA-15: Audit records form a verifiable hash chain with a contiguous sequence and canonical hashes.
- FA-16: No API endpoint allows modification or deletion of audit records.
- FA-17: Partially met. Administrators can query, filter, and paginate audit data; export is not implemented.

### Security
- FA-18: Every document-access API endpoint checks authorization server-side.
- FA-19: Direct URL access to a stored file without valid authorization is denied.
- FA-20: File names in storage are system-generated UUIDs, not user-supplied names.
- FA-21: CORS, CSP, and other security headers are configured in production.

## 5. Security Constraints

- All communication over HTTPS in production.
- Secrets stored in environment variables, never in source code or Git.
- Database credentials use least-privilege accounts where possible.
- Supabase Row-Level Security (RLS) policies act as a secondary enforcement layer.
- File downloads are served through signed, time-limited presigned URLs or proxied through the backend — never through publicly accessible storage URLs.
- Input validation on all user-supplied data (names, search queries, file metadata).
- Rate limiting on authentication endpoints.
- CSRF protection on state-changing requests.

## 6. Deployment Requirements

| Component       | Provider   | Notes                                      |
|-----------------|------------|--------------------------------------------|
| Frontend        | Vercel     | React/JavaScript/JSX/Vite SPA              |
| Backend API     | Render     | FastAPI, Python 3.11+                      |
| Database        | Supabase   | PostgreSQL with RLS                        |
| Object Storage  | Supabase Storage     | private buckets             |
| DNS/TLS         | Provider defaults | HTTPS enforced                       |

## 7. Requirement Traceability Matrix

| Req ID | Requirement                                    | Implementation Phase | Verification Method                          |
|--------|------------------------------------------------|:--------------------:|----------------------------------------------|
| MR-1   | Authentication with roles                      | Phase 3              | Unit + integration tests for role endpoints  |
| MR-2   | Document upload, organization, search, mgmt    | Phase 4 (upload), 5  | Upload/library/CRUD/search tests pass with mocked storage plus live storage smoke test |
| MR-3   | Named-user per-document READ/EDIT permissions  | Phase 6 (implemented) | Permission grant/deny integration tests pass |
| MR-4   | Owner-controlled grant and revocation          | Phase 6, 7 (implemented) | Immediate revocation, history, and permission audit tests pass |
| MR-5   | Backend enforcement of authorization           | Phase 5, 6, 8        | Direct API and threat-mapped security tests bypassing frontend |
| MR-6   | Audit records for all significant actions      | Phase 7 (implemented) | Event-driven audit, chain integrity, and checkpoint tests pass |
| MR-7   | Search by name, owner, category, date          | Phase 5, 9          | Filtered search tests with permission scoping; library exposes name/category/owner/date filters |
| MR-8   | File upload validation                        | Phase 4              | Implemented; validation/unit tests pass      |
| MR-9   | Administrator activity and permission views    | Phase 7, 9, correction | Admin account management, summary counts, permission oversight, filtered audit viewer, and denial tests pass; export deferred |
| MR-10  | Automated cross-user access denial tests       | Phase 8 (implemented) | Dedicated 46-case security suite; full suite configured in CI |

## 8. Out of Scope for Phase 0

The following are explicitly **not** implemented in Phase 0:

- User registration or login endpoints
- Database tables or migrations
- File upload or download functionality
- Permission management APIs
- Audit logging code
- Frontend application components
- Deployment configuration

These will be addressed in Phases 1 through 11 as specified in the Implementation Plan.
