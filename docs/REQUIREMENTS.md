# TrustVault — Requirements Document

## 1. Problem Statement

Organizations need a secure, auditable document management system that enforces strict access control at every layer. TrustVault is a multi-tenant document vault where document owners control exactly who can read or edit their files, administrators oversee activity, and every action is recorded in a tamper-evident audit trail. The system must guarantee that backend enforcement — not frontend visibility — is the sole authority for access decisions.

## 2. Mandatory Requirements

### MR-1: Authentication with Role-Based Access

**Description:** The system must support three distinct roles: **Administrator**, **Document Owner**, and **Viewer**. Users authenticate with secure credentials. Role assignment determines the scope of permitted actions.

- Administrators can review metadata for all active documents, view audit logs once Phase 7 is implemented, and manage users. Administrator identity does not automatically grant document content access.
- Document Owners can upload, organize, share, and manage their own documents.
- Viewers can only access documents explicitly shared with them.

**Phase:** 3 (authentication and role baseline), with role-specific document access enforced in Phases 5–8.
**Verification:** Phase 3 tests confirm registration role assignment, role dependencies, disabled-account rejection, and session enforcement. Document-level role tests arrive with document endpoints.

---

### MR-2: Document Upload, Organization, Search, and Management

**Description:** Authenticated users with the Owner role can upload documents, organize them into categories, search across their documents, and perform CRUD operations. File metadata (name, category, upload date, size, MIME type) is stored in the database. Actual file content is stored in private object storage.

**Phase:** 4 (Storage and Upload), 5 (Document Management and Search)
**Verification:** Phase 4 has integration tests for validated upload and metadata persistence. Phase 5 adds listing/search, metadata visibility/updates, streamed download, and soft deletion tests using a mocked storage adapter. Live Wasabi connectivity, download, and object deletion remain unverified.

---

### MR-3: Named-User, Per-Document READ and EDIT Permissions

**Description:** Document owners grant READ or EDIT access to specific named users on a per-document basis. Permissions are stored at the individual document-user level, not at group or role level. A user without explicit permission has no access.

**Phase:** 6 (Document Permissions and Revocation)
**Verification:** Phase 6 tests confirm owner-only grants, READ/EDIT capability boundaries, immediate post-revocation denial, grant-history retention, and shared-document listing. Audit event creation remains Phase 7.

---

### MR-4: Owner-Controlled Permission Grants and Revocation

**Description:** Only the document owner can grant or revoke permissions. Revocation is immediate: the target user loses access on the next request. Granting, updating, or revoking a permission must create an audit record once the Phase 7 audit writer exists.

**Phase:** 6 (Document Permissions and Revocation)
**Verification:** Phase 6 tests confirm immediate denial after revocation, owner-only management, cross-document permission-ID rejection, and retained grant history. Audit record creation is verified in Phase 7.

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
**Verification:** Unit and integration tests cover each validation rule, invalid file uploads, generated storage keys, and safe metadata. Live Wasabi integration remains unverified.

---

### MR-9: Administrator View of Document Activity and Permission Changes

**Description:** Administrators can view:

- All audit log entries
- Document activity summaries (uploads, downloads, changes per document)
- Permission change history per document
- User activity summaries

Administrators cannot modify or delete audit records through the application.

**Phase:** 7 (Audit Trail and Administrator Activity)
**Verification:** Integration tests confirming administrator access to logs; tests confirming administrators cannot delete audit records via API.

---

### MR-10: Automated Tests Proving Cross-User Access Denial

**Description:** The test suite must include explicit tests where:

- User A creates a document
- User B (with no permission) attempts to read, download, edit, and delete the document
- All four attempts are denied with appropriate HTTP status codes
- User A grants READ to User B; User B can read but not edit
- User A revokes READ; User B is immediately denied again
- All actions produce audit records

**Phase:** 8 (Security Tests and Threat-Model Verification)
**Verification:** Dedicated cross-user access test suite; CI integration.

---

## 3. Role Capabilities Matrix

| Capability                          | Administrator | Document Owner | Viewer |
|-------------------------------------|:---:|:---:|:---:|
| View document metadata              | All active | Own + shared | Shared only |
| Upload documents                    | Yes | Yes | No |
| Delete own documents                | Yes | Yes | No |
| Delete others' documents            | No  | No  | No |
| Grant/revoke per-document access    | Own documents only | Own only | No |
| View audit logs                     | Yes (Phase 7) | Own docs only (Phase 7) | No |
| Manage users/roles                  | Yes | No  | No |
| Search documents                    | All metadata | Own + shared | Shared only |
| Download documents                  | Explicit grant only | Own + shared grants | Shared grants only |
| Edit documents                      | Explicit EDIT only | Own + shared EDIT | Shared EDIT only |
| Modify audit records via API        | No  | No  | No  |

**Phase 6 authorization note:** administrator identity grants metadata oversight of all active documents, not content access, editing, deletion, or permission management. Administrators can manage permissions only for documents they own. Content and mutation capabilities come from ownership or an explicit READ/EDIT grant. This deliberately avoids treating administrator identity as automatic document-content authorization.

### Phase 3 Implementation Status (Verified Locally)

- **FA-1:** Registration, login, access tokens, and rotating refresh sessions are implemented. Public registration always creates a Viewer; elevated roles require the provisioning CLI.
- **FA-2:** Passwords are stored only as bcrypt hashes. Tests verify hashing, verification, and password-length limits.
- **FA-3:** Partially met. Access tokens expire after 15 minutes and refresh sessions expire after 7 days by default, with rotation and reuse detection. A configurable **idle** timeout is not implemented.
- **FA-4:** Invalid credentials and disabled accounts return the same generic login error, and unknown accounts perform dummy bcrypt work.
- **Additional controls:** auth POSTs enforce an Origin allow-list; auth endpoints are rate limited in-process; logout, disablement, and reuse detection invalidate access through database session checks.
- **Not yet met:** MFA, account lockout, a shared multi-instance rate limiter, per-session CSRF tokens, and production deployment verification.

### Phase 4 Implementation Status (Verified Locally with Mocked Storage)

- **FA-5:** Implemented. Validated files are sent to a private Wasabi bucket via the backend only, with backend-generated storage keys and no direct/presigned URL exposure. The bucket policy and live connectivity have **not** been verified.
- **MR-2 upload portion:** Implemented for Owner/Admin, with category/description metadata persisted in PostgreSQL.
- **MR-8:** Implemented. Extension, declared MIME, magic-byte/signature, filename, empty-file, size, DOCX package, and TXT encoding checks are covered by tests. Files are not virus-scanned.
- **Role enforcement:** Viewers and anonymous callers are denied; Owner/Admin ownership is derived from the authenticated session, not client input.
- **Integrity:** The backend computes SHA-256; a database failure after upload triggers best-effort object deletion.

### Phase 5 Implementation Status (Verified Locally with Mocked Storage)

- **MR-2:** Implemented for owner-managed documents: list/search/filter/sort/paginate metadata, inspect details, update mutable metadata, download content, and soft delete. Live Wasabi behavior remains unverified.
- **MR-5:** Document endpoints enforce authentication, current role, and ownership server-side; metadata visibility for administrators does not grant content or owner-only actions. Missing/inaccessible IDs return generic 404 responses.
- **MR-7:** Name (partial, literal wildcards), owner ID, category, and created-date filters are implemented with pagination and allow-listed sorting. Results are owner-scoped; administrators can review all active metadata; viewers see none.
- **FA-6 / FA-7 / FA-8:** Metadata is queryable/filterable; deletion marks `deleted_at` and attempts object cleanup; search results are scoped. At Phase 5 completion, per-document sharing scoping was not implemented.
- **Integrity / privacy:** Downloads are proxied through the authenticated backend with safe attachment headers and no storage key or presigned URL. Name search escapes SQL wildcard characters; sort fields are allow-listed.
- **Not yet met at Phase 5 completion:** explicit READ/EDIT grants, immediate revocation, audit events for view/download/edit/delete, live bucket verification, malware scanning, and deployment.

### Phase 6 Implementation Status (Verified Locally with Mocked Storage)

- **MR-3:** Implemented. Owners grant READ/EDIT to named active accounts by email; owner access is implicit. Grant/list/update/revoke endpoints are owner-only and reject forged recipient/grantor fields.
- **MR-4:** Implemented except audit persistence. Same-level grants are idempotent, conflicts return 409, level updates retain history, revocation is idempotent, and access is rechecked from the database on every request.
- **MR-5:** Document detail, edit, download, delete, and permission endpoints use centralized authorization with 404 for missing/unrelated resources and 403 for visible-but-insufficient capability. Metadata-only administrators are denied content access.
- **MR-7:** Regular listing includes owned and actively shared documents; `/shared-with-me` excludes revoked grants and deleted documents. Administrators retain metadata oversight.
- **Frontend:** Access-level badges, a shared-documents route, and an owner-only permission-management page with grant, update, revoke confirmation, and history are implemented.
- **Not yet met:** permission/document audit events, live bucket verification, malware scanning, RLS, and deployment.

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
- FA-13: Permission changes are recorded in the audit trail once the Phase 7 audit writer is implemented. The permission history table already retains grant/revoke rows.

### Audit
- FA-14: Every action listed in MR-6 produces exactly one audit record.
- FA-15: Audit records form a verifiable hash chain.
- FA-16: No API endpoint allows modification or deletion of audit records.
- FA-17: Administrators can query, filter, and export audit data.

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
| Object Storage  | Wasabi     | S3-compatible, private buckets             |
| DNS/TLS         | Provider defaults | HTTPS enforced                       |

## 7. Requirement Traceability Matrix

| Req ID | Requirement                                    | Implementation Phase | Verification Method                          |
|--------|------------------------------------------------|:--------------------:|----------------------------------------------|
| MR-1   | Authentication with roles                      | Phase 3              | Unit + integration tests for role endpoints  |
| MR-2   | Document upload, organization, search, mgmt    | Phase 4 (upload), 5  | Upload/library/CRUD/search tests pass with mocked storage; live Wasabi unverified |
| MR-3   | Named-user per-document READ/EDIT permissions  | Phase 6 (implemented) | Permission grant/deny integration tests pass |
| MR-4   | Owner-controlled grant and revocation          | Phase 6 (implemented); audit Phase 7 | Immediate revocation and history tests pass |
| MR-5   | Backend enforcement of authorization           | Phase 5, 6, 8        | Direct API tests bypassing frontend          |
| MR-6   | Audit records for all significant actions      | Phase 7              | Event-driven audit creation tests            |
| MR-7   | Search by name, owner, category, date          | Phase 5              | Filtered search tests with permission scoping|
| MR-8   | File upload validation                         | Phase 4              | Implemented; validation/unit tests pass      |
| MR-9   | Administrator activity and permission views    | Phase 7              | Admin endpoint access + restriction tests    |
| MR-10  | Automated cross-user access denial tests       | Phase 8              | Dedicated cross-user test suite              |

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
