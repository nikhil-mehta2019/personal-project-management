# Production security checklist

## Done (covered by `backend/tests/test_api.py`)

- [x] Authentication always required; no anonymous or default-workspace fallback
- [x] API refuses to start or issue tokens without a strong `JWT_SECRET`
- [x] Tokens expire (`ACCESS_TOKEN_TTL_MINUTES`) and can be revoked (`POST /api/auth/logout`, `manage.py revoke-sessions`)
- [x] Deactivated users are locked out immediately
- [x] Public registration closed by default (`ALLOW_REGISTRATION=false`)
- [x] CORS runs before auth, so preflights succeed and 401/429 responses reach the frontend
- [x] Argon2 password hashing
- [x] Workspace membership checked on every authenticated request; cross-workspace reads and writes return 404
- [x] Alembic is the only schema owner; migrations are frozen, tested for drift, and run on container start
- [x] Security response headers and request IDs; structured request/error logs
- [x] PostgreSQL foreign keys; backup and restore scripts

## Owner actions

- [ ] Set the exact production HTTPS CORS origin
- [ ] Configure managed PostgreSQL daily backups and retention
- [ ] Verify restore into a separate database
- [ ] Configure HTTPS/custom domain and provider access controls
- [ ] Create your account via `manage.py`, or claim the legacy local account

## Next hardening pass (P1)

- [ ] Validate that contact and assignee IDs belong to the current workspace
- [ ] Make the activity history server-written only (no client-forged "Status changed"/"Created")
- [ ] Race-free, per-workspace work-item numbering
- [ ] Rate limiting that uses the real client IP behind Render's proxy
- [ ] Complete migration of Daily Journal, Contacts, Reports, and remaining local prototype state
