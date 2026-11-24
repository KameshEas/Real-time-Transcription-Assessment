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

## Database

Set `DATABASE_URL` in `.env` to any Postgres URL, pasted as the provider gives it (Supabase: the **Session pooler**
string; Neon and local work too). The backend switches it to the async driver and enables SSL for remote hosts.

```bash
cd backend
uv run alembic upgrade head        # create/upgrade tables (the Docker image does this on start)
```

No database handy? `PERSISTENCE_BACKEND=memory` runs everything in process (data is lost on restart).

Tests: `uv run pytest` always runs against the in-memory backend. Set `TEST_DATABASE_URL` to run the API and gateway
tests a second time against real Postgres, inside a throwaway schema built by the real migration and dropped
afterwards, so existing tables are never touched. CI does this with a Postgres service container.

## REST API (`/api/v1`, OpenAPI at `/api/docs`)

| Method | Path | Notes |
|---|---|---|
| POST | `/transcripts` | Typed note (`engine=manual`); optional `Idempotency-Key` |
| GET | `/transcripts?q=&engine=&from=&to=&cursor=&limit=` | Newest first, 20 per page, keyset cursor, full-text search |
| GET | `/transcripts/{id}` | Detail with segments and per-word language tags; `ETag` = version |
| PATCH | `/transcripts/{id}` | Rename; needs `If-Match` (428 without, 412 if stale) |
| PATCH | `/transcripts/{id}/segments/{seq}` | Edit text; sets `edited`, recomputes tags, `full_text`, `hindi_ratio` |
| DELETE | `/transcripts/{id}` | Soft delete; `?hard=true` deletes permanently |
| POST | `/transcripts/{id}:restore` | Undo a soft delete |
| GET | `/transcripts/{id}/export` | Plain-text download |

Errors are RFC 9457 Problem Details with a stable `code` (e.g. `VERSION_CONFLICT`, `TRANSCRIPT_NOT_FOUND`).
Recordings are saved by the realtime gateway: each final is written before it is shown, and a dropped connection
resumes the same transcript with numbering continued.

## Live transcription

Open http://localhost:3000/record, pick an output script and press **Start recording**.

```
browser mic ─► AudioWorklet (native rate → 16 kHz PCM16, 100 ms frames)
            ─► WS /ws/v1/transcribe (protocol v1) ─► Sarvam saaras:v4 realtime
            ◄─ partial / final / latency / limit / error / done
```

| Script | Sarvam `mode` | Final output example |
|---|---|---|
| Mixed | `codemix` | आज की meeting में हम next quarter का budget discuss करेंगे |
| Devanagari | `transcribe` | आज की मीटिंग में हम नेक्स्ट क्वार्टर का बजट डिस्कस करेंगे |
| Roman | `translit` | Aaj ki meeting mein hum next quarter ka budget discuss karenge |

Measured on Sarvam with `stream_type=fast`: first partial about 0.5–1.0 s after speech starts; the engine handshake
adds about 2 s before `ready`, and the browser buffers up to 5 s of audio meanwhile so no words are lost.

Protocol v1 (all JSON carries `"v": 1`; audio is binary):
- client → server: `start {engine, script}`, PCM16 frames, `stop`, `ping`
- server → client: `ready`, `partial`, `final {seq, text, language}`, `latency`, `limit`, `error {code, fatal, retryable}`, `done`, `pong`

Without a Sarvam key (or in tests), the `fake` engine returns a scripted transcript so the full flow still runs.

## Scaling topology

`docker compose --profile scale up` adds Redis and a separate worker container (`APP_ROLES=worker`) to show the Stage 1 setup.
