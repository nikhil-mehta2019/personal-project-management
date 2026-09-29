# Development notes

## How a work item is created

1. The React form collects title, project, type, priority, status, and optional context.
2. `src/api/client.ts` sends `POST /api/work-items`.
3. FastAPI validates the request with `WorkIn`.
4. The API confirms the project belongs to the current workspace.
5. SQLAlchemy writes the work item and its initial `Created` activity in one transaction.
6. PostgreSQL stores the durable record.

## Why activities are separate

Work-item fields represent current state. Activities represent history. A status update changes the work item and appends an activity so the past cannot be overwritten by the latest state.

## Why projects are foreign keys

Work items store `project_id`, not a copied project name. Renaming a project therefore does not rewrite historical work records.

## Local development

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/api/health
```

Frontend: `http://localhost:5173`  
API: `http://localhost:8000/docs`

## Safe release sequence

1. Run backend tests and frontend build.
2. Run `alembic upgrade head` against the target database.
3. Deploy the API.
4. Verify `/api/health`.
5. Deploy the static frontend with `VITE_API_URL` set.
6. Run the smoke workflow: create project → create work item → add activity → refresh → verify persistence.

Do not use `Base.metadata.create_all()` as the production migration mechanism. It remains only as a development bootstrap until the deployment command is fully Alembic-driven.

## Email and WhatsApp message capture

The first message workflow is manual and reviewable:

1. Paste the complete email or WhatsApp message.
2. Call `POST /api/message-imports/analyze`.
3. Review the suggested title, type, priority, tags, and sender.
4. If project or sender is unknown, ask the user to select/enter them.
5. Call `POST /api/message-imports/commit` with `confirm: true`.

Commit creates the work item, an initial activity, and a communication containing the complete original message. No external mailbox or WhatsApp integration is required for this flow.
