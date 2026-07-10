# Authentication And User Session Plan

## Goal
Implement magic-link authentication so every persisted user action is associated to a user, and provide a login experience with database and source/article visibility.

## Scope
- Email-based magic-link login.
- Server-managed authenticated sessions.
- User-scoped investigator sessions and activity log.
- Login UI showing database state and article/source summaries.

## Phases

### 1) Data Model And Persistence
- Add tables for `users`, `auth_magic_links`, `auth_sessions`, and `user_activity`.
- Add `user_id` to `investigator_sessions` and enforce ownership in reads/writes.
- Add indices for token/session/activity lookup.

### 2) Auth Service Layer
- Create reusable auth service for:
  - email normalization/validation,
  - token generation and hashing,
  - magic-link issuing/consumption,
  - authenticated session issuing/resolution/revocation,
  - SMTP + development fallback delivery.

### 3) API Endpoints
- `POST /api/auth/request-link`
- `POST /api/auth/verify-link`
- `GET /api/auth/status`
- `GET /api/auth/login-metadata`
- `POST /api/auth/logout`

### 4) Route Protection And User Ownership
- Require auth for protected endpoints when auth is enabled.
- Scope session list/get/save by authenticated `user_id`.
- Reject cross-user access.

### 5) User Activity Association
- Log user activity for key actions:
  - chat sync/stream,
  - session list/get/save,
  - auth login/logout,
  - additional protected operations.

### 6) Login UI
- Add login gate with email input and request-link action.
- Show:
  - DB readiness,
  - total article count,
  - source breakdown,
  - latest sync timestamp.
- Handle magic-token verification from URL.

### 7) Testing
- Add auth flow tests for:
  - request/verify magic link,
  - cookie session issuance,
  - per-user session isolation.
- Keep current API/UI regression tests green.

## Verification Checklist
1. [x] Unauthenticated user sees login gate and metadata.
2. [x] Magic link can be requested and verified.
3. [x] Session cookie authenticates protected endpoints.
4. [x] User A cannot read User B session data.
5. [x] Activity records include associated `user_id`.
6. [x] Existing non-auth mode works when disabled.

## Completion Notes (2026-07-02)
- Added ownership guard for investigator sessions to prevent cross-user takeover of existing `session_id` values.
- Added explicit `/api/auth/logout` test coverage (session revocation + cookie expiry behavior).
- Added explicit cross-user session takeover test coverage.
- Verification run: `py -m pytest tests/test_webui_api.py -q` -> `42 passed`.
