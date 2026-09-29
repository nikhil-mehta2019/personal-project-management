# Production security checklist

- [x] JWT authentication enabled by default in Compose
- [x] Argon2 password hashing
- [x] Workspace membership checked on every authenticated request
- [x] CORS allowlist is environment-configured
- [x] Security response headers and request IDs
- [x] Structured request/error logs
- [x] Login/API rate limiting
- [x] PostgreSQL foreign keys and Alembic migrations
- [x] Backup and restore scripts
- [ ] Set a unique production JWT secret in the hosting provider
- [ ] Set the exact production HTTPS CORS origin
- [ ] Configure managed PostgreSQL daily backups and retention
- [ ] Verify restore into a separate database
- [ ] Configure HTTPS/custom domain and provider access controls
- [ ] Remove any demo/local accounts before inviting users
- [ ] Complete migration of Daily Journal, Contacts, Reports, and remaining local prototype state
