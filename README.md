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
