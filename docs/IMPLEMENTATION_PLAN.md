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

**Status:** Complete — awaiting review. Verified locally; no live deployment was performed.

**Objectives**
Create the frontend and backend scaffolds, configure build tooling, and deploy empty shells to Vercel and Render to prove the deployment pipeline before feature work.

**Deliverables**
- `frontend/` — React + TypeScript + Vite + Tailwind CSS + shadcn/ui scaffold with a placeholder page.
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

**Objectives**
Design and implement the relational schema with SQLAlchemy 2.x models and Alembic migrations. Prepare RLS policy scripts.

**Deliverables**
- SQLAlchemy models: `users`, `documents`, `document_permissions`, `audit_logs`, `categories`, `refresh_tokens`.
- Alembic configuration and initial migration.
- RLS policy SQL scripts (applied in later phases/deployment).
- Database connection/session management module.

**Dependencies**
- Phase 1 approved.

**Acceptance Criteria**
- `alembic upgrade head` applies cleanly against a fresh database.
- `alembic downgrade base` reverts cleanly.
- Schema matches the architecture document (tables, keys, constraints, indexes).
- Foreign keys and uniqueness constraints enforced (e.g., one permission per user/document pair).
- Audit log table has no application-level update/delete path.

**Tests**
- Migration up/down test.
- Model/schema validation test.
- Constraint tests (duplicate permission rejected, cascade behavior verified).

**Suggested Commit Message**
```
feat: implement database schema and Alembic migrations
```

---

## Phase 3: Authentication and Roles

**Objectives**
Implement registration, login, JWT issuance, refresh token rotation, logout, role extraction, and authentication rate limiting.

**Deliverables**
- `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`.
- Password hashing with bcrypt.
- JWT access tokens with short TTL and opaque rotating refresh tokens.
- Authentication middleware/dependency.
- Role-based dependency helpers.
- Rate limiting on auth endpoints.

**Dependencies**
- Phase 2 approved.

**Acceptance Criteria**
- Registration stores only hashed passwords.
- Login returns valid access and refresh tokens.
- Expired or tampered JWTs are rejected with 401.
- Refresh token rotation invalidates the previous refresh token.
- Role is encoded and validated on protected endpoints.
- Auth endpoints are rate limited.

**Tests**
- Unit tests for password hashing and verification.
- Integration tests for register, login, refresh, logout.
- Expired/tampered token rejection tests.
- Rate limit behavior test.
- Role extraction test.

**Suggested Commit Message**
```
feat: implement authentication with JWT and role-based access
```

---

## Phase 4: Private Storage and Validated Uploads

**Objectives**
Integrate private Wasabi S3 storage and implement validated uploads with backend-proxied downloads.

**Deliverables**
- Wasabi S3 client wrapper using `boto3`.
- Upload endpoint with validation (size, MIME allow-list, magic-byte check, filename sanitization).
- UUID-based storage key generation.
- Download proxy endpoint with permission placeholder from Phase 3 roles.
- Metadata creation and rollback on storage failure.
- Audit hooks scaffolded for upload/download (fully implemented in Phase 7).

**Dependencies**
- Phase 3 approved.

**Acceptance Criteria**
- Valid files upload to Wasabi and metadata is recorded.
- Invalid type/size/filename uploads are rejected with no partial records.
- Downloads are proxied through the backend; no direct S3 URL is exposed.
- Storage failures return 503 and leave no orphan metadata.

**Tests**
- Unit tests for every validation rule.
- Integration tests for upload/download (mockable S3).
- Test that API responses contain no presigned or direct storage URLs.
- Failure-path tests for S3 errors.

**Suggested Commit Message**
```
feat: implement validated file uploads with Wasabi storage
```

---

## Phase 5: Document Management and Search

**Objectives**
Implement document listing, metadata editing, categorization, deletion, and permission-scoped search.

**Deliverables**
- Document CRUD endpoints.
- Category management.
- Search endpoint with filters: name, owner, category, date range.
- Pagination and sorting.
- Permission scoping so users only see accessible documents (owner/admin/placeholder grants until Phase 6).

**Dependencies**
- Phase 4 approved.

**Acceptance Criteria**
- Users can list, update, and delete documents they are entitled to manage.
- Search respects permission scoping and supports all four filter dimensions.
- Pagination and sorting behave correctly.
- Deletion removes storage objects and updates metadata consistently.

**Tests**
- Integration tests for CRUD.
- Search filter tests for each dimension.
- Permission-scoping tests for search results.
- Pagination boundary tests.

**Suggested Commit Message**
```
feat: implement document management and search
```

---

## Phase 6: Document Permissions and Revocation

**Objectives**
Implement per-document, per-user READ/EDIT grants with owner/admin control and immediate revocation enforced on every endpoint.

**Deliverables**
- Permission grant endpoint.
- Permission revocation endpoint.
- Permission listing endpoint.
- Reusable authorization dependency used by all document endpoints.
- Immediate-effect enforcement (no stale permission caching).

**Dependencies**
- Phase 5 approved.

**Acceptance Criteria**
- Owners (and admins) can grant READ or EDIT to named users.
- EDIT implies READ.
- Only owners/admins can manage permissions; others receive 403.
- Revocation takes effect on the very next request.
- All document endpoints enforce permissions independently of the frontend.

**Tests**
- Grant/revoke integration tests.
- Immediate revocation test.
- Non-owner permission-management denial tests.
- Cross-user access tests for read/edit.

**Suggested Commit Message**
```
feat: implement per-document permissions with immediate revocation
```

---

## Phase 7: Audit Trail and Administrator Activity

**Objectives**
Implement immutable audit logging with hash-chain integrity and administrator/owner audit query views.

**Deliverables**
- Audit service used by all significant actions.
- Hash chain (`previous_hash`, `record_hash`) with verification utility.
- Audit records for uploads, downloads, views, edits, deletions, permission grants/revocations, and denied attempts.
- Admin audit query endpoints with filtering (event type, user, document, date).
- Owner-scoped audit views for their own documents.
- Documentation of external checkpoint limitations.

**Dependencies**
- Phase 6 approved.

**Acceptance Criteria**
- Every significant action produces exactly one correctly typed audit record.
- Hash chain verifies successfully and detects a simulated tamper.
- No API endpoint permits audit modification or deletion.
- Admins can query and filter all audit events; owners can see activity for their documents only.
- Denied access attempts are recorded.

**Tests**
- Per-event-type audit creation tests.
- Hash chain integrity and tamper-detection tests.
- Audit immutability tests via API.
- Admin/owner query scoping tests.

**Suggested Commit Message**
```
feat: implement audit trail with hash-chain integrity
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
- Permission management UI (grant/revoke for owners; admin overrides).
- Audit log viewer for admins and owners.
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
- TypeScript typecheck and production build.
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
