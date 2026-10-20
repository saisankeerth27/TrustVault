# TrustVault — Implementation Plan

This document defines the 12-phase incremental delivery plan (Phase 0 through Phase 11). Each phase produces reviewable, verified work and a meaningful Git commit. No phase begins until the previous phase is reviewed and approved.

## Phase Summary

| Phase | Title | Primary Requirement Coverage |
|-------|-------|------------------------------|
| 0 | Requirements and Repository Foundation | All (documentation baseline) |
| 1 | Project Scaffold and Early Deployment | Infrastructure |
| 2 | Database Schema and Migrations | MR-2, MR-3, MR-6 |
| 3 | Authentication and Roles | MR-1 |
| 4 | Private Storage and Validated Uploads | MR-2, MR-8 |
| 5 | Document Management and Search | MR-2, MR-5, MR-7 |
| 6 | Document Permissions and Revocation | MR-3, MR-4, MR-5 |
| 7 | Audit Trail and Administrator Activity | MR-6, MR-9 |
| 8 | Security Tests and Threat-Model Verification | MR-5, MR-10 |
| 9 | Complete Frontend | MR-2, MR-7, MR-9 |
| 10 | Deployment Hardening and End-to-End Verification | All (verification) |
| 11 | Final Submission and Demo | All (evidence) |

---

## Phase 0: Requirements and Repository Foundation

**Objectives**
Establish the complete requirements baseline, architecture, threat model, and repository documentation before writing application code. Ensure no application functionality is implemented prematurely.

**Deliverables**
- `docs/REQUIREMENTS.md` — problem statement, ten mandatory requirements, role matrix, acceptance criteria, security constraints, deployment requirements, traceability matrix.
- `docs/ARCHITECTURE.md` — component responsibilities, flows, security boundaries, environment variables, RLS planning, failure behavior.
- `docs/IMPLEMENTATION_PLAN.md` — this document.
- `THREATS.md` — assets, trust boundaries, threat actors, scenarios, mitigations, residual risks.
- `PROMPTS.md` — AI development activity log with reusable template.
- `README.md` — project overview, stack, security principles, links, status.
- `.gitignore` — excludes secrets, dependencies, and build artifacts.

**Dependencies**
- None.

**Acceptance Criteria**
- All ten company requirements are documented and traceable.
- Every requirement maps to an implementation phase and verification method.
- All 12 phases (0–11) are defined with objectives, deliverables, dependencies, acceptance criteria, tests, and commit messages.
- Threat model covers IDOR, unauthorized downloads, privilege escalation, revoked access, malicious uploads, path manipulation, unauthorized permission changes, audit tampering, metadata leakage, exposed credentials, weak RLS, session/token theft, brute force, and denial of service.
- README accurately states Phase 0 status and claims no unverified functionality.
- No application code, database schema, API endpoints, or frontend components exist.

**Tests**
- Manual documentation review.
- Internal link verification between documents.
- Secret scan of staged files.
- Verification that no future-phase functionality is present.

**Suggested Commit Message**
```
docs: define TrustVault requirements and architecture
```

---

## Phase 1: Project Scaffold and Early Deployment

**Status:** Partial — awaiting review. Local scaffold, build, startup, and health checks are verified; live Vercel/Render deployment was not performed and is deferred to Phase 10.

**Objectives**
Create the frontend and backend scaffolds, configure build tooling, and deploy empty shells to Vercel and Render to prove the deployment pipeline before feature work.

**Deliverables**
- `frontend/` — React + Vite + Tailwind CSS + shadcn/ui scaffold with a placeholder page (initially TypeScript; migrated to JavaScript/JSX in Phase 4).
- `backend/` — FastAPI application scaffold with `app/main.py`, `GET /health`, and settings management.
- `.env.example` files for both frontend and backend with placeholder values only.
- Vercel configuration for the frontend.
- Render configuration (`render.yaml` or dashboard settings) for the backend.
- Basic CI workflow (lint/build/test stubs) where feasible.

**Dependencies**
- Phase 0 approved.

**Acceptance Criteria**
- `npm run build` succeeds in `frontend/`.
- `uvicorn app.main:app` starts in `backend/`.
- `GET /health` returns 200 with a status payload.
- Frontend shell deploys to Vercel; backend shell deploys to Render.
- No secrets committed; `.env` excluded by `.gitignore`.

**Tests**
- Frontend production build test.
- Backend startup and import test.
- Health endpoint test via FastAPI `TestClient`.

**Suggested Commit Message**
```
feat: scaffold frontend and backend with early deployment
```

---

## Phase 2: Database Schema and Migrations

**Status:** Complete — awaiting review. Verified against an isolated local PostgreSQL instance. The migration has **not** been applied to the Supabase project.

**Objectives**
Design and implement the relational schema with SQLAlchemy 2.x models and an Alembic migration, plus a connection/session module. Document the RLS strategy without enabling policies before authentication exists.

**Deliverables**
- SQLAlchemy models: `users`, `documents`, `document_permissions`, `audit_events` (`docs/DATABASE.md`).
- Alembic configuration (`backend/alembic.ini`, `backend/alembic/env.py`) and the initial migration `0001_initial_schema`.
- Database connection/session module (`backend/app/db/`): URL normalization, lazy engine, session factory, FastAPI dependency.
- RLS strategy documented in `docs/ARCHITECTURE.md` and `docs/DATABASE.md`. Policy scripts are deferred because RLS policy design depends on the Phase 3 authentication model.
- `categories` and `refresh_tokens` tables were intentionally deferred at the end of Phase 2: category is a nullable column on `documents` for now, and refresh tokens were implemented in Phase 3.

**Dependencies**
- Phase 1 approved.

**Acceptance Criteria**
- `alembic upgrade head` applies cleanly against a fresh PostgreSQL database.
- `alembic downgrade base` reverts cleanly, and re-upgrading succeeds.
- `alembic check` reports no drift between the migration and the SQLAlchemy metadata.
- Foreign keys, check constraints, and partial unique indexes are enforced (for example, only one active permission per user/document pair).
- `audit_events` has no application-level update/delete path; deletion of users/documents nulls audit references instead of removing history.

**Tests**
- Migration upgrade/`alembic check`/downgrade/re-upgrade test against a fresh database.
- Model/schema validation tests for tables, columns, and indexes.
- Constraint tests: unique email, normalized email, valid owner FK, non-negative file size, internal storage key, valid permission values, duplicate active grant rejected, regrant after revocation preserves history, audit retention via `ON DELETE SET NULL`, JSON object enforcement, hash format validation.
- Database URL normalization and Supabase pooler/SSL detection tests.

**Suggested Commit Message**
```
feat(db): implement database schema and migrations
```

---

## Phase 3: Authentication and Roles

**Status:** Complete — awaiting review. Verified locally against an isolated PostgreSQL instance; no deployment or Supabase migration was performed.

**Objectives**
Implement registration, login, JWT issuance, rotating refresh sessions, logout, role enforcement, authentication rate limiting, and the frontend authentication experience.

**Deliverables**
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, and `GET /api/v1/auth/me`.
- bcrypt password hashing with a 12-character minimum and 72-byte maximum.
- Short-lived HS256 access JWTs with issuer/audience validation and opaque rotating refresh tokens stored as SHA-256 hashes.
- `refresh_tokens` model and migration `0002_add_refresh_tokens` with family-based reuse detection and revocation.
- Authentication dependencies that verify JWT claims, active user status, and an active refresh-token family on every protected request.
- Role dependencies for `ADMINISTRATOR`, `DOCUMENT_OWNER`, and `VIEWER`; fail-closed handling for unknown roles.
- Origin allow-list checks on auth POSTs, HttpOnly path-scoped refresh cookies, and configurable production cookie policy.
- In-memory login/registration rate limiting with `Retry-After`.
- Account provisioning CLI that never prints passwords or hashes; public registration creates Viewers only.
- Frontend in-memory access token, credentialed Axios client with shared refresh retry, auth provider, protected routes, role-gated admin route, forbidden state, login/logout UX, and current-user display.
- Updated `.env.example`, `render.yaml`, README, architecture, database, requirements, implementation plan, threat model, and PROMPTS log.

**Dependencies**
- Phase 2 approved.

**Acceptance Criteria**
- Registration stores only hashed passwords and always creates a Viewer.
- Login returns a valid access token and sets a rotating HttpOnly refresh cookie.
- Expired, tampered, wrong-issuer/audience, wrong-type, revoked-session, and disabled-account tokens are rejected with 401.
- Refresh rotation invalidates the previous token; reuse revokes the entire family.
- Logout revokes the session immediately, including existing access tokens.
- Role checks use the current database role and fail closed.
- Production settings reject a short/missing JWT secret, insecure cookies, invalid SameSite combinations, and wildcard CORS.
- Auth logs contain no passwords, tokens, or email addresses.
- Auth endpoints are rate limited.

**Tests**
- 55 backend tests total, including registration, login, refresh, rotation/reuse, logout, current user, expired/tampered tokens, disabled accounts, role dependencies, rate limits, production config validation, and log redaction.
- Full migration test applies `0001` and `0002`, runs `alembic check`, downgrades to base, and re-upgrades.
- At Phase 3 completion, frontend typecheck, lint, and build passed. The frontend was migrated to JavaScript/JSX in Phase 4, and typecheck no longer applies.
- Not tested: live Vercel/Render cookies, third-party cookie blocking, shared rate limiting, and Supabase migration.

**Suggested Commit Message**
```
feat(auth): implement authentication and roles
```

---

## Phase 4: Private Storage and Validated Uploads

**Status:** Complete - awaiting review. Verified locally with a mocked Wasabi adapter; live bucket connectivity/policy was **not** verified because no credentials were supplied.

**Objectives**
Integrate private Wasabi S3 storage and implement a validated secure upload path. Downloads are deferred to Phase 5 to keep Phase 4 reviewable.

**Deliverables**
- Wasabi S3 client wrapper using `boto3`, lazy/cached service creation, and safe errors.
- `POST /api/v1/documents/upload` with Owner/Admin role enforcement.
- Validation: size (10 MiB default), extension/MIME allow-list, magic-byte/signature checks, filename safety, empty-file rejection, DOCX package checks, and TXT encoding checks.
- Backend-generated `documents/{owner_uuid}/{random_uuid}.{ext}` keys and backend-computed SHA-256.
- Metadata creation, safe 201 response without storage keys, and best-effort object cleanup when metadata commit fails.
- Server-side storage settings, upload limits, connectivity CLI, and deployment templates.
- JavaScript/JSX frontend migration and an upload form for Owner/Admin.

**Dependencies**
- Phase 3 approved.

**Acceptance Criteria**
- Valid files pass validation, upload through the mocked storage adapter, and record metadata.
- Invalid type/size/filename/content uploads are rejected before storage.
- No direct/presigned storage URL or storage key is exposed to the client.
- Storage failures return 503 with no metadata row; database failures return 500 and attempt object cleanup.
- Live Wasabi behavior remains explicitly unverified.

**Tests**
- Unit tests for every validation rule and storage configuration.
- Integration tests for authorized/denied upload, metadata persistence, failure paths, and cleanup.
- Tests that responses and logs expose no storage key or secret.
- 107 backend tests pass; frontend lint/build pass.

**Suggested Commit Message**
```
feat(storage): implement secure document uploads
```

---

## Phase 5: Document Management and Search

**Status:** Complete — approved. Verified locally with a mocked Wasabi adapter; live download and object-deletion behavior was **not** verified because no credentials were supplied.

**Objectives**
Implement document listing, metadata editing, categorization, search, proxied download, and soft deletion with ownership/role scoping.

**Deliverables**
- `GET /api/v1/documents` with name search, category/owner/date filters, pagination, and allow-listed sorting.
- `GET /api/v1/documents/{id}` safe metadata details.
- `PATCH /api/v1/documents/{id}` for owner-only `name`, `category`, and `description` updates; protected fields rejected.
- `GET /api/v1/documents/{id}/download` as an owner-only backend proxy with safe attachment/no-store headers and no presigned URL.
- `DELETE /api/v1/documents/{id}` owner-only soft deletion with best-effort Wasabi object cleanup after commit.
- JavaScript/JSX library, filters, pagination, upload panel, and document details/edit/delete UI.
- Administrator metadata review across active documents without content or owner-only actions.

**Dependencies**
- Phase 4 approved.

**Acceptance Criteria**
- Owners can list, inspect, update, download, and delete their active documents.
- Administrators can list/inspect metadata for all active documents but cannot manage another owner's document.
- Viewers see no documents until Phase 6 grants exist.
- Search/filter/sort/pagination behave correctly and wildcard characters are treated literally.
- Unauthorized or missing documents return a generic 404; protected metadata cannot be changed.
- Downloads are authenticated and never expose storage keys or direct storage URLs.
- Deletion excludes metadata from normal reads and attempts object cleanup; cleanup failure is logged.

**Tests**
- 127 backend tests pass, covering listing/scoping, all filters, wildcard escaping, sorting, pagination validation, IDOR behavior, protected-field rejection, safe download headers/failures, soft deletion, and cleanup failure.
- Frontend lint/build pass; no TypeScript files remain.

**Suggested Commit Message**
```
feat(documents): implement document management and search
```

---

## Phase 6: Document Permissions and Revocation

**Status:** Complete — verified locally with 146 backend tests and frontend lint/build at Phase 6 completion; live Wasabi behavior remains unverified.

**Objectives**
Implement named-user, per-document READ/EDIT grants with owner-only management and immediate revocation enforced on every document endpoint.

**Deliverables**
- Document-scoped permission grant, list, update, and revoke endpoints.
- Shared-with-me listing endpoint.
- Reusable centralized access checker used by all document endpoints.
- Access-level reporting (`OWNER`, `EDIT`, `READ`, `ADMINISTRATOR`) in document responses.
- Revoke-and-regrant level changes with retained history.
- Immediate-effect enforcement (no stale permission caching).
- Frontend shared-documents view, access-level badges, and owner-only permission manager.

**Dependencies**
- Phase 5 approved.

**Acceptance Criteria**
- Owners grant READ or EDIT to active registered users by email and manage permissions only on their own documents.
- EDIT implies READ; READ/EDIT cannot delete or manage permissions.
- Administrators receive metadata oversight but no automatic content or mutation access.
- Same-level grants are idempotent; conflicts return 409; cross-document permission IDs return 404.
- Revocation takes effect on the very next request and remains visible as history.
- All document endpoints enforce permissions independently of the frontend.

**Tests**
- Grant/list/update/revoke integration tests, including history retention.
- Immediate revocation and regrant tests.
- Non-owner, cross-document, anonymous, and forged-identity denial tests.
- READ/EDIT/administrator capability boundary tests.
- Shared-listing exclusion tests for revoked and deleted documents.

**Suggested Commit Message**
```
feat(permissions): implement document access grants and revocation
```

---

## Phase 7: Audit Trail and Administrator Activity

**Status:** Complete — awaiting review. Verified locally with 158 backend tests and frontend lint/build; live Wasabi and Supabase/deployment behavior remain unverified.

**Objectives**
Implement an append-only, tamper-evident audit trail with hash-chain and signed-checkpoint verification and a global-administrator audit activity view.

**Deliverables**
- Audit service used by authentication, document, permission, and denial boundaries.
- Migration `0003` adding a positive, unique, contiguous `chain_index`.
- Hash chain over canonical JSON using `previous_hash` and `event_hash`, with a PostgreSQL advisory transaction lock.
- HMAC-SHA256 signed checkpoint creation and verification, plus `scripts/audit_integrity.py`.
- Audit records for registration, login success/failure, logout, upload, metadata update, download, delete, permission grant/update/revoke, and typed denials.
- Global-administrator audit query and integrity endpoints with actor/document/action/outcome/date filters and pagination.
- Administrator audit dashboard at `/admin/audit`.
- Request ID validation/generation and direct client IP/user-agent metadata.
- Documentation of same-host checkpoint limitations.

**Dependencies**
- Phase 6 approved.

**Acceptance Criteria**
- State-changing actions append correctly typed audit records in the protected transaction; denials are best-effort and preserve the denial outcome.
- Hash verification detects modified, reordered, removed, and truncated events.
- A valid signed checkpoint verifies; stale, truncated, malformed, or signature-invalid checkpoints are reported safely.
- No API endpoint permits audit modification or deletion.
- Only global administrators can query all audit events and integrity status.
- Audit metadata contains no sensitive values and remains bounded.
- Owner-scoped audit views and audit export are explicitly deferred.

**Tests**
- Per-event-type success and denial audit tests.
- Administrator authorization, filtering, pagination, and generic denial tests.
- Hash-chain tamper/removal and signed-checkpoint failure tests.
- Mandatory-audit rollback and best-effort-denial behavior tests.
- Metadata sanitization and request-ID safety tests.

**Suggested Commit Message**
```
feat(audit): implement protected audit trail
```

---

## Phase 8: Security Tests and Threat-Model Verification

**Objectives**
Build a dedicated security test suite proving each threat-model control and cross-user access denial.

**Deliverables**
- Security test suite mapped to `THREATS.md`.
- IDOR tests (object-level access via guessed/enumerated IDs).
- Privilege escalation tests.
- Cross-user access denial tests for GET, download, PUT, DELETE (MR-10).
- Audit tampering tests.
- Path traversal and malicious upload tests.
- Token theft/expiry and brute-force rate-limit tests.

**Dependencies**
- Phase 7 approved.

**Acceptance Criteria**
- Each threat in `THREATS.md` has at least one corresponding automated test.
- Cross-user denial is proven for all four operations.
- Privilege escalation attempts return 403 with audit records.
- Audit tampering through the API is impossible.
- At least 20 security-specific test cases exist.

**Tests**
- Full security suite executed in CI.
- Coverage report demonstrating authorization paths exercised.

**Suggested Commit Message**
```
test: add security test suite and threat-model verification
```

---

## Phase 9: Complete Frontend

**Objectives**
Deliver the full React frontend covering all user-facing capabilities with accessible, responsive UI.

**Deliverables**
- Login and registration pages.
- Document upload with validation feedback.
- Document list with search, filters, sorting, and pagination.
- Document detail and metadata editing.
- Permission management UI (grant/revoke for owners; no administrator override).
- Administrator audit viewer (Phase 7 provides the starting `/admin/audit` implementation; no owner audit view).
- Responsive layouts, loading/error/empty states.

**Dependencies**
- Phase 8 approved.

**Acceptance Criteria**
- All backend capabilities are reachable through the UI.
- Forms validate input and surface server errors clearly.
- Permission changes reflect immediately in the UI.
- Layouts are responsive on mobile and desktop.
- Frontend build succeeds with no type errors.

**Tests**
- JavaScript lint and production build.
- Manual UI walkthrough of each role.
- Component tests where applicable.

**Suggested Commit Message**
```
feat: implement complete React frontend
```

---

## Phase 10: Deployment Hardening and End-to-End Verification

**Objectives**
Harden production configuration and verify the full stack end to end.

**Deliverables**
- Production environment configuration for Vercel and Render.
- CORS locked to the production frontend origin.
- Security headers and HTTPS verification.
- Rate limiting verified in production configuration.
- End-to-end test suite against deployed services.
- Deployment and rollback checklist.

**Dependencies**
- Phase 9 approved.

**Acceptance Criteria**
- Frontend and backend communicate in production.
- CORS rejects unapproved origins.
- All automated tests pass against the deployed environment (or documented limitations reported).
- No secrets present in client bundles or repository.
- Health checks pass on both deployments.

**Tests**
- End-to-end tests across deployed services.
- Security header checks.
- CORS negative tests.
- Secret scan of frontend build output and repository.

**Suggested Commit Message**
```
ops: harden deployment and verify end-to-end
```

---

## Phase 11: Final Submission and Demo

**Objectives**
Finalize documentation and prepare evidence for submission and demo.

**Deliverables**
- Final `README.md` reflecting completed status.
- `PROMPTS.md` with at least five genuine entries, including at least two covering authorization/access control and audit integrity.
- Demo script and walkthrough.
- Final test results and requirement evidence.
- Updated threat model with residual risks.

**Dependencies**
- Phase 10 approved.

**Acceptance Criteria**
- All ten requirements are verified with test evidence.
- `PROMPTS.md` meets the minimum genuine-entry requirement.
- README claims match verified reality.
- Demo is runnable end to end.

**Tests**
- Full test suite run with recorded results.
- Documentation completeness check.

**Suggested Commit Message**
```
docs: finalize TrustVault for submission
```

---

## Cross-Phase Rules

1. Inspect repository state before beginning each phase.
2. Implement only the approved phase; never pre-build future functionality.
3. Run relevant tests and build checks before every commit.
4. Review the full diff and scan staged files for secrets.
5. Commit with a phase-specific message and push without force.
6. Stop for human review after each phase.
7. Record genuine activity in `PROMPTS.md`; never fabricate results.
