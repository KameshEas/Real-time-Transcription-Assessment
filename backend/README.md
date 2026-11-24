# hinglish (backend)

FastAPI service for Hinglish Live Transcribe. See the root README.

- `uv run uvicorn hinglish.main:app --reload`: API + realtime gateway
- `uv run python -m hinglish.worker`: outbox worker
- `uv run pytest`: tests, including the import-linter architecture contracts
