# Work OS

A calm, personal Work & Issue Tracker designed around the complete history of a work item.

## Run the UI

```bash
npm install
npm run dev
```

The dashboard and work-item creation path now read/write through the FastAPI API. The remaining screens are being migrated incrementally; the local import utility preserves the previous browser prototype data during that transition.

## Docker

```bash
docker compose up --build
```

Frontend: `http://localhost:5173` · API docs: `http://localhost:8000/docs`.

## Architecture

- `src/` — React + TypeScript interface with dashboard, work list, timeline, projects, journal, reports, contacts, and quick add.
- `backend/` — FastAPI + SQLAlchemy workspace-scoped API and complete V1 relational model.
- `backend/alembic/` — migration environment and initial schema revision.
- `docker-compose.yml` — frontend, API, and durable Postgres volume.

The API models use UUID identifiers, indexed work-item fields, database-generated `WRK-YYYY-#####` numbers, and automatic creation activities. Its domain boundary keeps future communication importers and an `AIService` separate from the work-item model.

## API overview

- `GET/POST/PUT /api/projects`
- `PATCH /api/projects/{id}/archive`
- `PATCH /api/projects/{id}/restore`
- `GET /api/projects/{id}/work-items`
- `GET /api/projects/{id}/activity`
- `GET/POST/PUT /api/work-items`
- `PATCH /api/work-items/{id}/status`
- `GET/POST /api/work-items/{id}/activities`
- `GET/POST /api/work-items/{id}/communications`
- `GET/POST /api/contacts`
- `GET /api/reports/monthly`
- `GET /api/health`

## Database migrations

Set `DATABASE_URL`, then run:

```bash
alembic upgrade head
```

The development fallback can use SQLite, while Docker and deployment use PostgreSQL. The application retains a `create_all` bootstrap only for local development; Alembic is the production schema source of truth.

Authentication, frontend API migration, local-data import, XLSX export, and automated workspace-isolation tests remain in the next phases.

## Deployment checklist

1. Set `DATABASE_URL` to the managed PostgreSQL connection string.
2. Install backend dependencies and run `alembic upgrade head`.
3. Start the API with `uvicorn backend.main:app --host 0.0.0.0 --port 8000`.
4. Build the frontend with `npm run build` and deploy `dist/` as a static site.
5. Set `VITE_API_URL` to the public API base URL.
6. Run the local-data import utility once for any existing browser data.

Docker Desktop must be running before `docker compose up --build` can be used locally.
