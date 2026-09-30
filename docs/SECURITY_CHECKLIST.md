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

## Done in the P1 pass

- [x] Contact and assignee references must belong to the current workspace (create, update, communications, message import)
- [x] System history events are server-written only; edits and project moves are recorded
- [x] Race-free, per-workspace work-item numbering (verified with concurrent creates on PostgreSQL)
- [x] Rate limiting keyed on the real client IP when configured; bounded memory
- [x] Message import matches senders exactly (no `%`/`_` wildcard matches)

## Owner verification

- [ ] After deploying, confirm `client_ip` in the request logs is your real IP

## Next (P2)

- [ ] Allowed values for status, type, priority, and source
- [ ] Size limits on text fields and request bodies
- [ ] Hide `/docs` and `/openapi.json` in production
- [ ] Complete migration of Daily Journal, Contacts, Reports, and remaining local prototype state
