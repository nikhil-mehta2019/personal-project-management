# Production deployment

The application is containerized and can run on Render, Fly.io, Railway, or another Docker host. The recommended low-cost setup is a managed PostgreSQL provider (Neon or Supabase) plus an API service and a static frontend site. Render's free Postgres tier expires and has no backups, so it is for testing only.

## Required production settings

- `DATABASE_URL`: managed PostgreSQL URL using the `postgresql+psycopg://` SQLAlchemy scheme.
- `JWT_SECRET`: a unique random value, never the development value.
- `REQUIRE_AUTH=true`.
- `CORS_ORIGINS`: the exact HTTPS frontend origin, without a trailing slash.
- Run `alembic -c alembic.ini upgrade head` as the release migration before starting application traffic.

`render.yaml` contains a Docker API service and a static frontend site. Render still requires the database URL and frontend/API URLs to be entered in the dashboard because they are environment-specific secrets.

## Release sequence

1. Create the managed PostgreSQL database and copy its pooled connection URL.
2. Create the API service from `render.yaml`; set `DATABASE_URL` and `CORS_ORIGINS`.
3. Deploy the API and verify `/api/health` returns `{"status":"ok"}`.
4. Run the migration command from the service shell: `alembic -c alembic.ini upgrade head`.
5. Create the frontend service and set `VITE_API_URL` to the API's HTTPS `/api` base URL.
6. Register a user, create a project, create a work item, import a message, and verify all records survive a restart.
7. Configure the provider's daily database backup and perform a restore drill before inviting real users.

No hosting provider can be provisioned from the repository alone; account ownership, billing, domain, and production secrets must be supplied by the owner.
