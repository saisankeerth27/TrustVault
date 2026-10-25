# TrustVault — Simplified Overview

Live: https://trust-vault-six-ivory.vercel.app/

## What it is
TrustVault is a secure document vault for storing, sharing, and auditing documents. Backend enforces permissions; frontend never trusts client role.

## Stack
- Frontend: React + Vite (Vercel)
- Backend: FastAPI + Python (Render)
- DB: Supabase PostgreSQL
- Auth: Supabase Auth
- Storage: Supabase private bucket

## Quick start (local)
Backend:
```
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend:
```
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Env (minimum)
Backend: DATABASE_URL, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET, CORS_ALLOWED_ORIGINS, PASSWORD_RECOVERY_REDIRECT_URL
Frontend: VITE_API_BASE_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY

## Tests
Backend: `pytest` (all pass)
Frontend: `npm run lint`, `npm test`, `npm run build`

## Roles
- Document Owner: upload, share, delete, version control
- Viewer: read-only on shared docs
- Administrator: accounts + audit, no auto content access

## Key flows
- Signup -> email verify -> login
- Forgot password -> OTP -> new password -> dashboard
- Disable/enable users (no delete)
- Last login tracked after successful auth

## Live deploy checklist
- Render: set AUTH_COOKIE_SECURE=true, AUTH_COOKIE_SAMESITE=none, CORS_ALLOWED_ORIGINS=<vercel url>
- Vercel: set VITE_API_BASE_URL=<render url>
- Run alembic upgrade head on production DB

## Known limits
- Cross-site cookies untested in prod
- No MFA
- In-memory rate limiting
- Checkpoint is same-host file
