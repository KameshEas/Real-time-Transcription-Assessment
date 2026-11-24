# Hinglish Live Transcribe

Real-time speech-to-text for Hindi-English code-mixed speech. Next.js frontend, FastAPI backend, Postgres.
All AI runs through managed APIs (Sarvam for STT/TTS, Groq for script conversion). No model is hosted here.


## Layout

```
backend/    FastAPI, Clean Architecture + DDD contexts (src/hinglish/<context>/{domain,application,infrastructure,interface})
frontend/   Next.js App Router, Feature-Sliced Design (src/{app,widgets,features,entities,shared})
docs/adr/   Architecture decision records
```

## Quick start

```bash
cp .env.example .env          # then add SARVAM_API_KEY and GROQ_API_KEY

# Everything in containers
docker compose up --build     # frontend :3000, backend :8000, postgres :5432

# Or run locally
cd backend  && uv sync && uv run uvicorn hinglish.main:app --reload   # http://localhost:8000/api/docs
cd frontend && npm install && npm run dev                              # http://localhost:3000
```

## Checks

| | Command |
|---|---|
| Backend lint / format | `uv run ruff check . && uv run ruff format --check .` |
| Backend types | `uv run mypy` |
| Layer rules | `uv run lint-imports` (also runs inside `pytest`) |
| Backend tests | `uv run pytest` |
| Frontend lint (incl. FSD boundaries) | `npm run lint` |
| Frontend types / build | `npm run typecheck && npm run build` |
| Regenerate API types | `npm run gen:api` (backend must be running) |

## Scaling topology

`docker compose --profile scale up` adds Redis and a separate worker container (`APP_ROLES=worker`) to show the Stage 1 setup.
