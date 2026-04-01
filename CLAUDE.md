# Podium Backend

Python backend for a VR public-speaking training platform. Users upload documents,
practice presentations in VR, and receive AI-generated contextual questions in real time.

## Stack

- **API**: FastAPI + Pydantic v2, async everywhere
- **Database**: PostgreSQL 17 (pgvector image) via SQLAlchemy 2.0 async + asyncpg
- **Migrations**: Alembic (async, reads `DATABASE_URL` from `.env`)
- **Task queue**: Celery + Redis (broker + Pub/Sub)
- **Auth**: bcrypt + python-jose (JWT HS256, 24h expiry) — no passlib (Python 3.14)
- **Document parsing**: pypdf, python-pptx, python-docx
- **LLM**: OpenAI GPT-4o-mini (primary), Google Gemini 1.5 Flash (fallback), stub if neither configured
- **STT**: OpenAI Whisper API (`whisper-1`)
- **Tests**: pytest + pytest-asyncio + aiosqlite (SQLite in-memory), 28 tests passing

## Infrastructure

```bash
docker-compose up -d          # Postgres (port 5433) + Redis (port 6379)
alembic upgrade head
python -m app.scripts.seed_profiles
uvicorn app.main:app --reload                                        # Terminal 1
celery -A app.workers.celery_app worker --loglevel=info --pool=solo  # Terminal 2
python -m pytest tests/                                              # Tests
```

## Data Flow

### 1. Document ingestion
Client uploads PDF/PPTX/DOCX → `storage_service` saves file → `Document` created (status `QUEUED`)
→ Celery task `extract_document_text`: extracts text → chunks (1200 chars, 200 overlap)
→ optionally generates OpenAI embeddings (stored as JSON) → status becomes `CHUNKED`.

### 2. Session creation
Client picks a processed document + simulation profile → `POST /sessions` creates
`Session(status=READY)`. Document must be `CHUNKED` or `READY`.

### 3. Transcript segments
During the VR presentation, frontend sends text segments via `POST /sessions/{id}/segments`.
First segment flips session to `RUNNING`. Each segment fires Celery task
`generate_question_for_segment`.

### 4. Question generation
Task applies rate limiting + cooldown (per-profile config) + deduplication (SequenceMatcher > 0.75).
`simulation_service` retrieves top-5 chunks via Postgres FTS, loads profile-specific prompt,
calls `llm_service.generate_question()`. Falls back to template stub if no LLM key.

### 5. Real-time delivery
Question is saved to DB → published to Redis channel `session:{id}:events`
→ WebSocket at `/sessions/{id}/live` pushes to VR client.

### 6. Post-session
`POST /sessions/{id}/feedback` (202) fires Celery task that builds a coaching prompt from
all segments + questions, calls LLM, stores result in `session.feedback_text`.
`GET /sessions/{id}/analytics` returns pure-SQL metrics (no LLM).

## Simulation Profiles

Seeded via `python -m app.scripts.seed_profiles`. Each has a prompt file + config JSON.

| Key | Focus | Difficulty |
|-----|-------|-----------|
| `academic` | Rigor, methodology, theoretical depth (banca de TCC style) | 4-5 |
| `corporate` | ROI, value proposition, feasibility, risks | 3-4 |
| `interview` | Concrete evidence, measurable impact, self-awareness | 3-4 |
| `auditorium` | Diverse audience, unpredictable questions, improvisation | 3-5 |

## Endpoints

### No auth
- `GET /health`
- `POST /auth/register` — `{email, password}` → JWT
- `POST /auth/login` — OAuth2 form → JWT
- `POST /documents` — upload PDF/PPTX/DOCX
- `GET /documents/{id}`, `GET /documents/{id}/text`, `GET /documents/{id}/chunks`, `GET /documents/{id}/search?q=`
- `GET /profiles`, `GET /profiles/{id}`
- `WS /sessions/{id}/live`

### Requires Bearer token
- `GET /auth/me`
- `POST /sessions` — `{document_id, profile_id}`
- `GET /sessions/{id}`
- `POST /sessions/{id}/segments` — `{text, start_ms?, end_ms?}`
- `GET /sessions/{id}/segments`, `GET /sessions/{id}/questions`
- `POST /sessions/{id}/audio` — upload audio for STT (**note: auth missing on this endpoint**)
- `GET /sessions/{id}/analytics`
- `POST /sessions/{id}/feedback` (202), `GET /sessions/{id}/feedback`

## Models

| Model | Table | Key fields |
|-------|-------|-----------|
| `Document` | `documents` | filename, content_type, storage_path, status, extracted_text |
| `DocumentChunk` | `document_chunks` | document_id (FK), chunk_index, content, embedding (JSON) |
| `SimulationProfile` | `simulation_profiles` | key (unique), name, description, config (JSON) |
| `Session` | `sessions` | user_id (FK), document_id (FK), profile_id (FK), status, feedback_text |
| `TranscriptSegment` | `transcript_segments` | session_id (FK), text, start_ms, end_ms |
| `Question` | `questions` | session_id (FK), question_text, intent, difficulty, evidence_chunk_ids (JSON) |
| `User` | `users` | email (unique), hashed_password |

## Celery Tasks (`app/workers/tasks.py`)

| Task | Trigger |
|------|---------|
| `extract_document_text(document_id)` | Document upload |
| `generate_question_for_segment(session_id, segment_id)` | New transcript segment |
| `generate_session_feedback(session_id)` | `POST /sessions/{id}/feedback` |
| `process_audio_transcription(session_id, file_path, filename)` | `POST /sessions/{id}/audio` |

## What's Working

- Full document pipeline: upload → extract text (PDF/PPTX/DOCX) → chunk → index
- Postgres Full-Text Search for chunk retrieval
- Simulation profiles (CRUD + seed script)
- Sessions with auth (create, read, ownership check)
- Transcript segments (create, list, triggers question generation)
- LLM integration: OpenAI GPT-4o-mini + Gemini fallback + stub fallback
- Question generation with rate limiting, cooldown, deduplication
- Redis Pub/Sub + WebSocket for real-time question delivery
- Session feedback via LLM
- Session analytics (pure SQL metrics)
- Auth: register, login, JWT, protected session endpoints
- STT via Whisper API
- Embeddings generated and stored (JSON column)
- Prompt templates per profile (`app/prompts/`)
- 28 tests passing

## What's Not Working / Still TODO

### Bugs / schema issues
- **`sessions.user_id` missing from Alembic migrations**: model has it, but no migration adds the column. Fresh DB will break on session creation. Needs a new migration.
- **Empty no-op migration** (`6bc9dfb22dd5`): auto-generated with only `pass`.
- **`POST /sessions/{id}/audio` has no auth guard**: unlike all other session routes.
- **`app/api/deps.py` is empty**: auth dependency lives in `auth.py` instead.

### Not yet implemented
- **Vector similarity search in question generation**: embeddings are stored but `simulation_service` only uses Postgres FTS, not cosine similarity from `vector_service`.
- **Auth on document endpoints**: documents are fully public.
- **Auth on WebSocket**: no token verification on WS connections.
- **PPTX/DOCX extraction**: code exists in `document_service.py` but is untested and the upload route accepts these content types.
- **`aiosqlite` not in `pyproject.toml`**: needed by test suite but not declared as a dependency.

### Future roadmap
1. Fix Alembic migration for `sessions.user_id`
2. Wire vector similarity into question generation (hybrid FTS + cosine)
3. Add auth to document routes and WebSocket
4. Improve question quality and prompt engineering
5. Add pgvector extension for native vector ops
6. Support audio ingestion pipeline end-to-end (STT → segments → questions)
7. Add comprehensive analytics and feedback quality

## Code Conventions

- FastAPI + `APIRouter`, `response_model`, `Depends(get_db)`
- SQLAlchemy async: `AsyncSession`, `select()`, `await db.execute()`
- Celery tasks use `asyncio.run()` internally (Windows `--pool=solo`)
- Pydantic v2 schemas with `model_config = ConfigDict(from_attributes=True)`
- Enums in `app/core/enums.py`: `DocumentStatus`, `SessionStatus`, `QuestionIntent`, `QuestionDifficulty`
- Error handling: `HTTPException` with appropriate status codes
- Keep changes small and incremental — this is a learning project
