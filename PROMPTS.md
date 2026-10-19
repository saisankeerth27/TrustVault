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
- **Commit hash:** pending
- **GitHub link:** pending
- **Human review and decision:** Awaiting human review and Phase 2 approval. Phase 3 must not begin until approval is given.
