# Production deployment

The application is containerized and can run on Render, Fly.io, Railway, or another Docker host. The recommended low-cost setup is a managed PostgreSQL provider (Neon or Supabase) plus an API service and a static frontend site. Render's free Postgres tier expires and has no backups, so it is for testing only.

## Required production settings

- `DATABASE_URL`: managed PostgreSQL URL using the `postgresql+psycopg://` SQLAlchemy scheme.
- `JWT_SECRET`: at least 32 random characters. The API will not start without it. `render.yaml` generates one.
- `CORS_ORIGINS`: the exact HTTPS frontend origin, without a trailing slash.
- `ALLOW_REGISTRATION`: `false` (default). See "Creating your account".
- `ACCESS_TOKEN_TTL_MINUTES`: session length, default 720 (12 hours).
- `CLIENT_IP_HEADER` / `TRUSTED_PROXY_HOPS`: how to find the real client IP for rate limiting. `render.yaml` sets `CLIENT_IP_HEADER=CF-Connecting-IP`. After the first deploy, check a request log line: `client_ip` must show your own public IP, not a Render or Cloudflare address. Never set either when clients connect directly; both headers can be forged by clients.

`REQUIRE_AUTH` no longer exists; authentication is always required.

Migrations run automatically on every container start (`alembic upgrade head` in the backend Dockerfile), so no shell access is needed. They are idempotent. A database created by the old startup `create_all()` bootstrap is adopted automatically.

`render.yaml` contains the Docker API service. Create the frontend separately as a Render Static Site because the current Blueprint schema rejects the static-site service type. The database URL and frontend/API URLs are environment-specific and must be entered in the dashboard.

## Creating your account

Pick one:

1. **CLI (recommended):** from `backend/`, with `DATABASE_URL` pointing at the production database, run `python manage.py create-user --email you@example.com --name "Your Name"`.
2. **Existing data from the no-auth era:** run `python manage.py claim-local --email you@example.com --name "Your Name"`. It converts the old password-less `local@workos.dev` account into your login so its workspace and data stay yours.
3. **Temporary registration:** set `ALLOW_REGISTRATION=true`, register through the app, then set it back to `false` immediately.

## Release sequence

1. Create the managed PostgreSQL database and copy its pooled connection URL.
2. Create the API service from `render.yaml`; set `DATABASE_URL` and `CORS_ORIGINS`.
3. Deploy the API (migrations apply on start) and verify `/api/health` returns `{"status":"ok"}`.
4. Create your account (see above).
5. Create the frontend service and set `VITE_API_URL` to the API's HTTPS `/api` base URL.
6. Log in, create a project, create a work item, import a message, and verify all records survive a restart.
7. Configure the provider's daily database backup and perform a restore drill before storing anything you cannot lose.

No hosting provider can be provisioned from the repository alone; account ownership, billing, domain, and production secrets must be supplied by the owner.
