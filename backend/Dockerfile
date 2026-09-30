FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Migrations run on every start (idempotent). Render's free tier has no shell, so this is the
# only reliable place to apply them. The API refuses to start without a valid JWT_SECRET.
CMD ["sh","-c","alembic -c alembic.ini upgrade head && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
