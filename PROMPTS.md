# PROMPTS.md — AI Development Activity Log

This file records genuine AI-assisted development activity for TrustVault. Each entry documents the date, phase, objective, instructions given to the AI agent, artifacts produced, verification performed, issues found, corrections, commit information, and human review decision.

**Rules**
- Entries must be truthful. Never fabricate prompts, results, commits, or history.
- The project must eventually contain at least five genuine entries, including at least two involving authorization/access control and audit integrity.
- Commit hashes and links are added only after verification.

---

## Entry Template

```
### YYYY-MM-DD — Phase N: <Short Title>

- **Date and phase:** YYYY-MM-DD — Phase N (<title>)
- **Objective:** <what this session set out to accomplish>
- **Prompt / instruction summary:** <the prompt or a fair summary of the instructions given to the AI agent>
- **Files or code produced:** <list of files created or changed, with a short description of each>
- **Tests and verification performed:** <commands run and results; note any checks skipped and why>
- **Issues discovered:** <problems found during the session>
- **Corrections made:** <how issues were resolved>
- **Commit hash:** <actual hash, or "pending">
- **GitHub link:** <actual link, or "pending">
- **Human review and decision:** <approved / changes requested / notes>
```

---

## 2026-10-19 — Phase 0: Requirements, Architecture, and Repository Documentation

- **Date and phase:** 2026-10-19 — Phase 0 (Requirements and Repository Foundation)
- **Objective:** Establish the Phase 0 documentation baseline for TrustVault: requirements, architecture, implementation plan, threat model, README, and this AI activity log. Inspect the repository and Git state, and prepare a safe Phase 0 commit. No application functionality to be implemented.
- **Prompt / instruction summary:** The human provided a master prompt instructing the AI agent to act as a senior architect, Forward Deployed Engineer, security engineer, and AI-assisted development engineer. The agent was directed to build TrustVault across 12 phases (0–11), each producing reviewable work, verification, a meaningful Git commit, and a push, then stopping for human approval. Phase 0 scope was restricted to documentation only: inspect the repository, create `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `THREATS.md`, `PROMPTS.md`, and `README.md`; cover all ten mandatory requirements; document the technology stack (React/TypeScript/Vite/Tailwind/shadcn/ui, FastAPI, Supabase PostgreSQL, SQLAlchemy/Alembic, Wasabi, Vercel, Render); maintain strict secret-handling rules; and prepare the commit `docs: define TrustVault requirements and architecture`.
- **Files or code produced:**
  - `docs/REQUIREMENTS.md` — problem statement, ten mandatory requirements (MR-1 through MR-10), role capability matrix, acceptance criteria, security constraints, deployment requirements, and a requirement traceability matrix.
  - `docs/ARCHITECTURE.md` — component responsibilities, Mermaid diagrams, authentication and authorization flows, upload/download flows, permission revocation, audit integrity and its limitations, deployment architecture, placeholder environment variables, RLS planning, and failure behavior.
  - `docs/IMPLEMENTATION_PLAN.md` — all 12 phases (0–11) with objectives, deliverables, dependencies, acceptance criteria, tests, and suggested commit messages.
  - `THREATS.md` — assets, trust boundaries, threat actors, 14 attack scenarios with mitigations and verification, and residual risks (including the limitation of a same-database hash chain and the irreversibility of downloaded copies).
  - `PROMPTS.md` — this file, containing a reusable template and this genuine initial entry.
  - `README.md` — project overview, stack, architecture summary, security principles, document links, deployment destinations, setup direction, and Phase 0 status.
  - `.gitignore` — excludes secrets, dependencies, build artifacts, and local environment files.
- **Tests and verification performed:** Documentation-only phase. Automated application tests are not applicable because no application code, database schema, or API exists in Phase 0. Performed manual checks: confirmed all ten requirements are present and traceable; confirmed all 12 phases are documented; confirmed required threat topics are covered; verified README reflects Phase 0 status and claims no unverified functionality; verified internal documentation links; reviewed the full Git diff; scanned staged files for secrets; confirmed `.env` files are excluded and only placeholders appear in documentation.
- **Issues discovered:** The initial local Git repository had been initialized at the user's home directory (`C:\Users\23jr1`) rather than inside the project folder, which caused Git to track the entire home directory. No remote was configured at the project level, and the project directory was empty. Additionally, the human's prompt included live-looking credentials; these were not used, and the human was advised to rotate them.
- **Corrections made:** Initialized a dedicated Git repository inside the project directory, set the branch to `main`, and configured the `origin` remote to the supplied GitHub repository (verified credential-free). Confirmed the remote repository was empty before planning any push. Ensured documentation uses placeholders only and no credentials were referenced or staged.
- **Commit hash:** `87cea0ee21f5606871ba0183e3602ffd94974a35`
- **GitHub link:** https://github.com/saisankeerth27/TrustVault/commit/87cea0ee21f5606871ba0183e3602ffd94974a35
- **Human review and decision:** Awaiting human review and Phase 0 approval. Phase 1 must not begin until approval is given.

---

## 2026-10-19 — Phase 1: Application Scaffold, Tooling, Tests, and Deployment Preparation

- **Date and phase:** 2026-10-19 — Phase 1 (Project Scaffold and Early Deployment)
- **Objective:** Build the initial React/TypeScript/Vite frontend and FastAPI backend skeletons, establish development tooling and automated checks, prepare Vercel and Render configuration, and verify everything locally without implementing future-phase functionality.
- **Prompt / instruction summary:** The human approved Phase 1 and provided a master prompt instructing the AI agent to act as a senior full-stack, FastAPI, React/TypeScript, DevOps, and application security engineer. Scope: create the frontend skeleton with React Router, Axios, Tailwind, shadcn/ui, React Hook Form, and Zod; create placeholder Login, Dashboard, Documents, and Not Found pages; centralize the Axios client behind `VITE_API_BASE_URL`; create a FastAPI skeleton with `GET /health`, CORS from settings, and OpenAPI docs; pin reproducible backend dependencies; add pytest tests for health, secret exposure, unknown routes, docs, and CORS; update documentation; and prepare Vercel/Render configuration. Explicitly excluded: database schema, authentication, documents, storage, permissions, audit persistence, and fake security features. Commit message: `chore: scaffold TrustVault application`.
- **Files or code produced:**
  - Frontend: Vite React/TypeScript scaffold under `frontend/`; Tailwind CSS v4 with the Vite plugin and shadcn/ui configuration (`components.json`, `cn`, Button/Card/Input primitives); React Router routes for `/login`, `/dashboard`, `/documents`, a root redirect, and a 404 page; centralized Axios client with configuration guard and consistent error extraction; React Hook Form + Zod login placeholder; responsive layout and branding; `vercel.json` SPA rewrites; `.env.example`.
  - Backend: FastAPI application factory under `backend/app/` with `main.py`, `api/`, `core/`, `schemas/`, and `services/`; `GET /health` (process-only); settings via pydantic-settings; environment-driven CORS that rejects wildcards outside development; JSON error envelope for HTTP and validation errors; OpenAPI enabled; pinned `requirements.txt` / `requirements-dev.txt`; `.env.example`; `pytest.ini`.
  - Tests: 7 backend tests across `tests/test_health.py` and `tests/test_cors.py`.
  - Deployment: `render.yaml` for Render; Vercel configuration in `frontend/vercel.json`.
  - Documentation: updated `README.md`, `docs/IMPLEMENTATION_PLAN.md` (Phase 1 status only), `THREATS.md` (verified Phase 1 notes), and this entry.
- **Tests and verification performed:**
  - `npm run typecheck` — passed.
  - `npm run lint` (oxlint) — 0 warnings, 0 errors after restructuring button variants.
  - `npm run build` — passed (TypeScript project build plus Vite production build).
  - `pytest` — 7 passed. A Starlette deprecation warning recommends `httpx2`; it did not fail any test and was not hidden.
  - Clean-environment check — created a temporary virtual environment outside the repository, installed `requirements-dev.txt`, and ran `pytest`: 7 passed.
  - Live process check — started Uvicorn on `127.0.0.1:8123`; `/health` returned `{"status":"ok","service":"TrustVault API","version":"0.1.0"}`, and `/docs` and `/openapi.json` returned HTTP 200.
  - Not performed: Vercel/Render deployment (no deployment authorization or credentials were provided), database/storage checks (not implemented), and cross-user authorization tests (authentication does not exist).
- **Issues discovered:**
  - `@hookform/resolvers` v6 introduced an npm peer-dependency conflict involving `effect` and Zod. The dependency was removed rather than forcing an incompatible tree; the login placeholder validates with Zod `safeParse` and React Hook Form `setError`.
  - TypeScript 7 removed the `baseUrl` compiler option, which broke the initial path alias configuration.
  - Oxlint warned that `button.tsx` exported both a component and the `buttonVariants` constant, which affects React Fast Refresh.
  - Starlette 1.9 emits a deprecation warning about using `httpx` with its TestClient.
- **Corrections made:**
  - Removed `@hookform/resolvers` and implemented explicit Zod validation in the login placeholder.
  - Removed `baseUrl` and kept `paths` relative to `tsconfig.app.json`, which TypeScript 7 supports.
  - Moved `buttonVariants` into `button-variants.ts` and updated consumers; lint now reports zero warnings.
  - Left the Starlette warning visible and reported it rather than suppressing it or weakening tests.
- **Commit hash:** `73bb4c5862305f24158aa41792f183a7d170eb2b`
- **GitHub link:** https://github.com/saisankeerth27/TrustVault/commit/73bb4c5862305f24158aa41792f183a7d170eb2b
- **Human review and decision:** Awaiting human review and Phase 1 approval. Phase 2 must not begin until approval is given.

---

## 2026-10-19 — Phase 2: Database Schema, Models, and Migrations

- **Date and phase:** 2026-10-19 — Phase 2 (Database Schema and Migrations)
- **Objective:** Design and implement the TrustVault PostgreSQL schema with SQLAlchemy 2.x models, an Alembic initial migration, and a connection/session module; verify the schema and migrations against a real database; document the data model and RLS strategy without enabling policies before authentication exists.
- **Prompt / instruction summary:** The human approved Phase 2 and provided a master prompt instructing the AI agent to act as a senior database engineer and application security engineer. Scope: create models for users, documents, permissions, and the audit trail; configure Alembic; enforce foreign keys, uniqueness, and check constraints; add a database session module that is safe for a Supabase pooler; document deletion, permission-history, and RLS strategy honestly; add tests; update documentation; and commit with `feat(db): implement database schema and migrations`. Explicit constraints: do not fabricate a Supabase migration, do not commit credentials, do not enable RLS policies without an authentication model, and do not claim unverified functionality.
- **Files or code produced:**
  - `backend/app/db/__init__.py`, `base.py`, `url.py`, `session.py` — declarative base, URL normalization (`postgresql+psycopg`), Supabase pooler/SSL detection, and a lazy cached engine plus FastAPI session dependency.
  - `backend/app/models/enums.py`, `user.py`, `document.py`, `document_permission.py`, `audit_event.py` — four tables with UUID keys, check constraints, foreign keys, partial unique indexes, and a `pg_trgm` GIN index on document names.
  - `backend/app/core/config.py` — added `database_url`, `db_pool_size`, `db_max_overflow`, and empty-to-`None` handling for `DATABASE_URL`.
  - `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_initial_schema.py` — Alembic configuration with no stored credentials, model-aware metadata, and a reviewed initial migration that creates `pg_trgm` before its index.
  - `backend/tests/conftest.py`, `db_helpers.py`, `factories.py`, `test_models.py`, `test_schema_constraints.py`, `test_migrations.py`, `test_db_url.py` — an ephemeral `embedded-postgres` fixture, model tests, constraint tests, and a full migration upgrade/`alembic check`/downgrade/re-upgrade test.
  - `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/.env.example`, `render.yaml` — pinned SQLAlchemy, Alembic, psycopg, and embedded-postgres; documented `DATABASE_URL` and pool settings; declared `DATABASE_URL` as a dashboard secret on Render.
  - `docs/DATABASE.md` (new), plus updates to `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `THREATS.md`, and `README.md`.
- **Tests and verification performed:**
  - `pytest` — 25 passed. This includes 7 Phase 1 tests and 18 Phase 2 tests (URL helpers, model metadata, database constraints, and the migration test).
  - Migration test ran against a fresh embedded PostgreSQL 18.6 database: `upgrade head`, `alembic check` (no model/migration drift), `downgrade base`, and a second `upgrade head` all succeeded. The test also asserts the `pg_trgm` extension and the GIN trigram index exist.
  - Constraint tests exercised real PostgreSQL errors rather than mocks: duplicate/normalized email, invalid owner FK, negative file size, URL-style storage key, invalid permission, duplicate active grant, regrant after revocation, audit retention after user/document deletion, non-object JSON details, and malformed hashes.
  - A direct TCP check to the configured Supabase host on port 5432 was not reachable, and no credential was introduced into the shell or repository. The migration was therefore **not** applied to Supabase, and this is stated in the docs.
  - Not performed: applying the migration to the Supabase project, RLS policy tests (no policies enabled), and authorization tests (authentication does not exist).
- **Issues discovered:**
  - The autogenerated migration did not create the `pg_trgm` extension, so the trigram index would have failed on a database where the extension is absent.
  - The initial Alembic URL resolution read `DATABASE_URL` before an explicitly configured URL, which would have prevented tests from targeting an isolated database without mutating the process environment.
  - Live-looking Supabase credentials appeared in the human's messages from an earlier phase; they were not used, and the human was again advised to rotate them.
  - `docs/ARCHITECTURE.md` described `asyncpg`, an `audit_logs` table, and enabled RLS, none of which matched the Phase 2 implementation.
- **Corrections made:**
  - Added `CREATE EXTENSION IF NOT EXISTS pg_trgm` at the start of `upgrade()` and documented that `downgrade()` leaves the shared extension installed.
  - Changed `alembic/env.py` so an explicitly configured `sqlalchemy.url` takes precedence over the environment, letting tests use a disposable database.
  - Rewrote `docs/ARCHITECTURE.md` to describe the synchronous psycopg 3 implementation, the four real tables, the deferred `categories`/`refresh_tokens` tables, and the fact that RLS is not enabled; added `docs/DATABASE.md` for full schema detail.
  - Kept audit immutability out of the database on purpose (it would conflict with retention foreign keys), documenting the deferral to Phase 7.
  - Ensured only placeholder values were committed and no credential appears in any staged or generated file.
- **Commit hash:** `f85c6633154dc08af547e184dc9a31f56d914c10`
- **GitHub link:** https://github.com/saisankeerth27/TrustVault/commit/f85c6633154dc08af547e184dc9a31f56d914c10
- **Human review and decision:** Awaiting human review and Phase 2 approval. Phase 3 must not begin until approval is given.

---

## 2026-10-20 — Phase 3: Authentication, Roles, and Session Security

- **Date and phase:** 2026-10-20 — Phase 3 (Authentication and Roles)
- **Objective:** Implement database-backed authentication and role enforcement end to end, including secure password handling, short-lived access tokens, rotating refresh sessions, logout/revocation, auth rate limiting, account provisioning, real frontend login/logout/protected-state UX, tests, configuration, and documentation. Stop after one verified commit and push for human review before Phase 4.
- **Prompt / instruction summary:** The human approved Phase 3 and required: JWT access tokens plus opaque rotating refresh tokens stored as hashes; bcrypt password hashing with strong cost; registration, login, refresh, logout, and `GET /api/v1/auth/me`; all required role algorithms and deny-by-default role dependencies; `ADMINISTRATOR`, `DOCUMENT_OWNER`, and `VIEWER` names; public registration restricted to Viewer and elevated accounts created by a CLI; rate limiting; secure cookies/CSRF protections; security tests for expired/tampered tokens, revoked refresh tokens, and unauthorized role access; frontend login/logout/current-user/protected routes/forbidden state without implementing document APIs; production env/render docs; README/architecture/requirement/threat/PROMPTS updates; full verification. The prompt required exactly one final commit (`feat(auth): implement authentication and roles`), no intermediate commits or docs commit, one push, and stopping for approval before Phase 4.
- **Files or code produced:**
  - Backend auth core: `app/core/security.py` (bcrypt, JWT create/decode, refresh-token generation/hash/expiry), `app/core/rate_limit.py`, and auth settings/validators in `app/core/config.py`.
  - Data/service/auth API: `app/models/refresh_token.py`, `app/services/auth.py`, `app/schemas/auth.py`, `app/api/deps.py`, `app/api/auth.py`, plus router registration and app description updates.
  - Migration: `backend/alembic/versions/0002_add_refresh_tokens.py` with hashed tokens, families, self-reference, expiry/revocation, and indexes.
  - Provisioning: `backend/scripts/create_user.py` and `backend/scripts/__init__.py`; supports interactive password entry or `TRUSTVAULT_USER_PASSWORD`, refuses duplicates, and never prints secrets.
  - Tests: `tests/auth_helpers.py`, `test_auth.py`, `test_auth_roles.py`, `test_auth_rate_limit.py`, `test_auth_config.py`, updated `conftest.py`, `test_models.py`, and `test_migrations.py`.
  - Frontend: `src/auth/tokenStore.ts`, `src/auth/useAuth.ts`, `src/auth/AuthContext.tsx`, `src/services/auth.ts`, `src/types/auth.ts`, `src/lib/roles.ts`, `src/components/AuthLoadingScreen.tsx`, `ProtectedRoute.tsx`, `RequireRole.tsx`, `ForbiddenState.tsx`, `src/pages/AdminPage.tsx`; updated Axios client, router, layout, login, dashboard, documents, not-found, and page title.
  - Configuration/docs: `backend/.env.example`, `render.yaml`, `README.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/REQUIREMENTS.md`, `docs/IMPLEMENTATION_PLAN.md`, `THREATS.md`, and this entry.
- **Tests and verification performed:**
  - `pytest` — **55 passed** after fixing the logging capture issue. Coverage includes registration, login, refresh rotation, family reuse revocation, logout, current user, expired/tampered/wrong-issuer/wrong-audience/wrong-type tokens, disabled accounts, role dependencies, rate limiting, production configuration validation, and log redaction.
  - The migration test applied `0001` and `0002`, ran `alembic check`, downgraded to base, and re-upgraded against an ephemeral PostgreSQL 18.6 instance.
  - `npm run typecheck` — passed.
  - `npm run lint` (oxlint) — 0 warnings, 0 errors after splitting the auth context/hook for Fast Refresh.
  - `npm run build` — passed (TypeScript plus Vite production build).
  - Not performed: Supabase migration, Vercel/Render deployment, live cross-site cookie verification, third-party cookie testing, and production rate-limiter testing. No credential was used or committed.
- **Issues discovered:**
  - The first full test run reported 54 passed and 1 failed: `test_auth_logs_do_not_contain_secrets_or_email` saw an empty `caplog`.
  - Instrumentation showed the `trustvault.auth` logger was disabled only after the Alembic test fixture ran. `alembic/env.py` called `fileConfig(config.config_file_name)` with the default `disable_existing_loggers=True`, disabling application loggers.
  - The frontend auth context initially exported both a component and a hook from one file, triggering an oxlint Fast Refresh warning.
  - Existing docs and HTML contained mojibake around some punctuation and a page-title separator.
- **Corrections made:**
  - Changed `alembic/env.py` to `fileConfig(config.config_file_name, disable_existing_loggers=False)` and re-ran the targeted test, then the full suite: 55 passed.
  - Split the auth context definition/hook into `useAuth.ts`, leaving `AuthContext.tsx` exporting only the provider; typecheck, lint, and build now pass cleanly.
  - Updated the page title and Phase 3 UI copy, removing stale Phase 1 placeholders.
  - Preserved the one-commit constraint: commit hash and GitHub link remain pending in this entry and are reported in the final response after the single commit is created.
- **Commit hash:** `c1892b8ae1589322f33689c21ab5fffad87b1d1b`
- **GitHub link:** https://github.com/saisankeerth27/TrustVault/commit/c1892b8ae1589322f33689c21ab5fffad87b1d1b
- **Human review and decision:** Approved; Phase 4 was authorized. Phase 5 must not begin until Phase 4 is reviewed and approved.

---

## 2026-10-20 - Phase 4: Private Storage and Validated Uploads

- **Date and phase:** 2026-10-20 - Phase 4 (Private Storage and Validated Uploads)
- **Objective:** Implement a private, server-mediated Wasabi storage path and secure document upload endpoint; enforce upload validation, backend-decided ownership, generated storage keys, SHA-256 integrity metadata, role restrictions, safe errors, and failure cleanup; migrate the frontend to plain JavaScript/JSX; verify locally; update documentation; and stop after one commit and push for human review before Phase 5.
- **Prompt / instruction summary:** The human approved Phase 4 and required a README comparison against the actual repository; a JavaScript-only frontend with no TypeScript; a private Wasabi bucket accessed only by the backend; exact server-side Wasabi environment names; upload validation for extension, MIME, magic bytes, empty/oversized files, filenames, DOCX structure, and TXT encoding; generated keys and backend-computed checksums; Owner/Admin-only upload with Viewer denial; safe errors and no storage-key leakage; tests with mocked storage; mandatory docs updates; and exactly one final commit (`feat(storage): implement secure document uploads`) followed by one push. No live Wasabi credentials were supplied, so live integration was explicitly constrained to remain unverified.
- **Files or code produced:**
  - Storage configuration and service: `backend/app/core/config.py`, `backend/app/services/storage.py`, `backend/scripts/check_storage.py`, with lazy cached boto3 client, Wasabi endpoint/path-style setup, safe errors, and a `head_bucket` connectivity CLI.
  - Upload validation and persistence: `backend/app/services/upload_validation.py`, `backend/app/services/documents.py`, `backend/app/schemas/document.py`, and `backend/app/api/documents.py` for `POST /api/v1/documents/upload`.
  - Authorization/router wiring: `backend/app/api/router.py`, `backend/app/main.py`; upload restricted to active `ADMINISTRATOR`/`DOCUMENT_OWNER`, with ownership derived from the session.
  - Dependencies/config: `backend/requirements.txt` (`boto3==1.43.115`, `python-multipart==0.0.32`), `backend/.env.example`, and `render.yaml` with exact `WASABI_*`, upload-size, and extension settings.
  - Tests: `backend/tests/test_documents.py`, `test_upload_validation.py`, and `test_storage.py`, using a fake adapter and embedded PostgreSQL.
  - Frontend migration: renamed all `.tsx`/`.ts` application files to `.jsx`/`.js`; renamed `vite.config.ts` to `vite.config.js`; removed `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, and `src/types/`; updated `package.json`, `components.json`, and `index.html`; removed TypeScript and `@types/*` dependencies and the `typecheck` script.
  - Upload UI/API: `frontend/src/services/documents.js` and `frontend/src/pages/DocumentsPage.jsx` with file/category/description inputs, progress, errors, success metadata, and Viewer restriction.
  - Documentation: `README.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/REQUIREMENTS.md`, `docs/IMPLEMENTATION_PLAN.md`, `THREATS.md`, and this entry; Phase 3 commit details recorded above.
- **Tests and verification performed:**
  - `pytest` - **101 passed, 1 warning**. The warning is the Starlette/httpx deprecation. Tests cover upload authorization, role denial, owner derivation, generated keys, SHA-256 metadata, extension/MIME/signature validation, unsafe filenames, empty/oversized files, DOCX/TXT checks, storage failure mapping, metadata-failure cleanup, configuration validation, and secret-safe errors/logs.
  - Embedded PostgreSQL retained: migration upgrade/check/downgrade/re-upgrade and all prior auth/schema tests still pass.
  - `npm run lint` - 0 warnings, 0 errors after removing residual TypeScript references.
  - `npm run build` - Vite production build passed; no TypeScript project build remains.
  - Verified no application `.ts`/`.tsx` files or `tsconfig*.json` remain.
  - Not performed: live Wasabi connection/upload, bucket-policy verification, Supabase migration, deployment, or real end-to-end browser-to-Wasabi verification. No storage credential was supplied, used, or committed.
- **Issues discovered:**
  - The frontend was still TypeScript-based despite the Phase 4 JavaScript-only requirement, requiring a full file rename and removal of TypeScript tooling.
  - Existing README/docs described Wasabi as planned, listed only 55 tests, and used placeholder/incorrect Wasabi variable names and a storage-key layout that did not match the implementation.
  - Upload validation needed careful status mapping: invalid type/signature is 415, oversized is 413, and malformed input is 400/422.
  - Object upload followed by metadata commit is not atomic; cleanup cannot be guaranteed if object deletion fails.
  - No live Wasabi credentials/connectivity were available, so the master acceptance criterion for a real bucket upload cannot be claimed.
- **Corrections made:**
  - Migrated all frontend code to JavaScript/JSX and removed TypeScript configs, packages, and types; updated build/lint docs accordingly.
  - Implemented backend-generated `documents/{owner_uuid}/{random_uuid}.{ext}` keys, computed checksums, safe response schemas, and role-restricted upload.
  - Added failure-path cleanup and secret-safe logging, and documented the non-transactional residual risk.
  - Corrected all docs to distinguish **verified with mocked storage** from **live Wasabi unverified**, and updated test counts, routes, env names, key format, phases, threats, and limitations.
  - Preserved the one-commit constraint by updating docs before the single Phase 4 commit; commit hash remains pending until that commit is created.
- **Commit hash:** pending
- **GitHub link:** pending
- **Human review and decision:** Awaiting human review and Phase 4 approval. Phase 5 must not begin until approval is given.
