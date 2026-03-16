# Prompts de Execução — Podium Backend Tasks

Cada bloco abaixo é um prompt independente para Claude Code.
Execute **um bloco por vez**, na ordem indicada.
Após cada bloco, rode os testes (`python -m pytest tests/`) antes de continuar.

---

## Task 1 — Segurança no Upload de Arquivos

```
Contexto: projeto Podium, backend FastAPI. Arquivo alvo: app/services/storage_service.py

Leia o arquivo atual e faça as seguintes mudanças:

1. Adicionar constantes no topo:
   MAX_PDF_SIZE = 100 * 1024 * 1024   # 100MB
   MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50MB
   ALLOWED_EXTENSIONS = {"pdf", "pptx", "docx", "wav", "mp3", "mp4", "webm", "ogg"}

2. Modificar a função save_upload_file para:
   a. Extrair a extensão do filename e checar contra ALLOWED_EXTENSIONS — se inválida, levantar HTTPException(415, "Tipo de arquivo não suportado")
   b. Determinar o limite de tamanho baseado na extensão: AUDIO_EXTENSIONS = {"wav","mp3","mp4","webm","ogg"}, resto usa MAX_PDF_SIZE
   c. Antes de salvar, verificar o tamanho enquanto lê os chunks:
      total = 0
      while chunk := await file.read(1024 * 1024):
          total += len(chunk)
          if total > max_size:
              raise HTTPException(413, "Arquivo muito grande")
          f.write(chunk)

Não alterar nenhum outro arquivo. Não criar arquivos novos.
Ao final, mostrar o arquivo completo modificado.
```

---

## Task 2 — Corrigir Bug no LLM Service

```
Contexto: projeto Podium, backend FastAPI. Arquivo alvo: app/services/llm_service.py

Leia o arquivo atual e faça as seguintes correções:

1. Bug no parsing de markdown fence (procure pelo bloco que detecta "```"):
   - Linha que usa .startswith("```") para a última linha deve usar == "```" ao invés de startswith
   - Motivo: startswith("```") seria verdade para "```json" também, causando perda do conteúdo

2. Consistência na truncação de texto:
   - Procure por [:500] e [:1000] — padronizar para [:1000] em todo o arquivo

3. Validação da resposta OpenAI antes de acessar choices:
   - Antes de `data["choices"][0]["message"]["content"]`, adicionar:
     if not data.get("choices") or len(data["choices"]) == 0:
         raise ValueError("Resposta OpenAI sem choices")

4. Retry simples em _call_openai e _call_gemini:
   - Encapsular a chamada httpx em um loop de até 2 tentativas
   - Retry apenas em status 429 ou 503
   - Esperar 2 segundos entre tentativas (await asyncio.sleep(2))

Não alterar nenhum outro arquivo. Não criar arquivos novos.
Ao final, mostrar o arquivo completo modificado.
```

---

## Task 3 — Corrigir Redis Service

```
Contexto: projeto Podium, backend FastAPI. Arquivos alvo: app/services/redis_service.py e app/main.py

Leia ambos os arquivos e faça as seguintes mudanças:

Em app/services/redis_service.py:
1. Manter o padrão singleton mas adicionar try/except em publish_session_event:
   - Se Redis não estiver disponível, logar warning (import logging; logger = logging.getLogger(__name__))
   - Não deixar a exceção propagar — publish é best-effort
2. Adicionar função close_redis() que fecha a conexão se existir:
   def close_redis():
       global _redis_client
       if _redis_client is not None:
           _redis_client.close()
           _redis_client = None

Em app/main.py:
1. Verificar se já existe lifespan ou on_shutdown — se sim, adicionar close_redis() nele
2. Se não existir, adicionar:
   from contextlib import asynccontextmanager
   @asynccontextmanager
   async def lifespan(app):
       yield
       from app.services.redis_service import close_redis
       close_redis()

   E passar lifespan=lifespan no app = FastAPI(...)

Em app/api/routes/websocket.py:
- Verificar se o finally block já tem pubsub.unsubscribe() — se não tiver, adicionar

Não alterar outros arquivos.
```

---

## Task 4 — Adicionar Enums de Status

```
Contexto: projeto Podium, backend FastAPI.

Leia os arquivos: app/models/document.py, app/models/session.py, app/models/question.py, app/schemas/document.py, app/schemas/session.py, app/schemas/question.py

Crie o arquivo app/core/enums.py com:

from enum import Enum

class DocumentStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    CHUNKED = "CHUNKED"
    FAILED = "FAILED"
    READY = "READY"

class SessionStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"

class QuestionDifficulty(int, Enum):
    VERY_EASY = 1
    EASY = 2
    MEDIUM = 3
    HARD = 4
    VERY_HARD = 5

class QuestionIntent(str, Enum):
    CLARIFICATION = "clarification"
    DEEP_DIVE = "deep_dive"
    CHALLENGE = "challenge"
    PRACTICAL = "practical"
    GENERIC = "generic"

Depois, nos modelos SQLAlchemy:
- Document.status: tipo String (manter) mas importar DocumentStatus para usar como default
- Session.status: tipo String (manter) mas importar SessionStatus

Nos schemas Pydantic (document.py, session.py, question.py):
- Campos status devem usar os Enums como tipo ao invés de str

Nos workers/tasks.py e api/routes/sessions.py:
- Substituir strings literais como "READY", "RUNNING", "CHUNKED" pelos enums:
  SessionStatus.READY, SessionStatus.RUNNING, DocumentStatus.CHUNKED, etc.

Verificar que os imports estão corretos em cada arquivo modificado.
Ao final listar todos os arquivos modificados.
```

---

## Task 5 — Refatorar Tasks Celery

```
Contexto: projeto Podium. Arquivo alvo principal: app/workers/tasks.py

Leia app/workers/tasks.py e app/services/llm_service.py

Problemas a corrigir:

1. DEDUPLICAÇÃO DE CÓDIGO — a task generate_session_feedback chama OpenAI/Gemini diretamente.
   Isso duplica o código de llm_service.py. Corrigir:
   - Criar um novo arquivo app/prompts/feedback.md com o prompt de feedback:
     "Você é um avaliador de oratória. Analise a sessão abaixo e gere um feedback construtivo..."
   - Na task generate_session_feedback, substituir as chamadas diretas à OpenAI/Gemini por:
     from app.services.llm_service import generate_question
     (ou criar uma função generate_text_response no llm_service para uso geral)

2. TRANSCRIPT SUMMARY — linha que faz " ".join(s.text for s in segments):
   - Substituir por " | ".join(s.text for s in segments)[:3000]

3. asyncio.run() — verificar se as tasks que usam asyncio.run(_async_fn()) funcionam no pool=solo
   - Se sim, documentar com comentário: "# pool=solo no Windows suporta asyncio.run()"
   - Se não, investigar e corrigir

Não remover nenhuma funcionalidade existente.
Ao final mostrar as seções modificadas.
```

---

## Task 6 — Melhorar Detecção de Duplicatas

```
Contexto: projeto Podium. Arquivo alvo: app/workers/tasks.py

Leia o arquivo e encontre a função _is_similar_question_text.

Problema: substring matching é agressivo demais.
Exemplo: "Por quê?" detecta como duplicata de "Por que isso é importante?"

Substituir por:

import difflib

def _is_similar_question_text(a: str, b: str) -> bool:
    """Retorna True se as perguntas forem similares demais (> 75% de semelhança)."""
    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)
    if a_norm == b_norm:
        return True
    ratio = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
    return ratio > 0.75

Também na função generate_question_for_segment, encontre onde o cooldown é verificado:
- Se usa hardcoded 15, substituir por:
  cooldown = session.profile.config.get("cooldown_seconds", 15) if session.profile else 15
  if (now_utc - created_at).total_seconds() < cooldown:

Verificar se session.profile está sendo carregado com selectinload ou equivalente, se não, adicionar:
  from sqlalchemy.orm import selectinload
  e adicionar .options(selectinload(Session.profile)) na query de session.

Não alterar outros arquivos. Mostrar as funções modificadas ao final.
```

---

## Task 7 — Error Handlers e Logging

```
Contexto: projeto Podium. Arquivos alvo: app/core/logging.py, app/main.py, app/services/simulation_service.py

1. Em app/core/logging.py (atualmente vazio), adicionar:

import logging
import sys

def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

2. Em app/main.py:
   - Importar e chamar setup_logging() antes de criar o app
   - Adicionar handler de exceção genérico:

   from fastapi import Request
   from fastapi.responses import JSONResponse

   @app.exception_handler(Exception)
   async def generic_exception_handler(request: Request, exc: Exception):
       import logging
       logging.getLogger("podium").error(f"Erro não tratado: {exc}", exc_info=True)
       return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor"})

3. Em app/services/simulation_service.py:
   - Adicionar logger = logging.getLogger(__name__) no topo
   - No bloco except genérico (onde silenciosamente usa stub), mudar para:
     logger.warning(f"LLM falhou, usando stub. Erro: {exc}")

4. Em app/services/llm_service.py:
   - Adicionar logger = logging.getLogger(__name__) no topo
   - Logar quando retry é acionado: logger.warning(f"Retry {attempt}/2 após erro {status}")

Não alterar outros arquivos.
```

---

## Task 8 — Indexes de Performance

```
Contexto: projeto Podium. Arquivos alvo: todos os arquivos em app/models/

Leia os modelos: document.py, document_chunk.py, session.py, question.py, transcript.py

Adicionar os seguintes indexes via SQLAlchemy __table_args__:

Em Document:
  __table_args__ = (
      Index("ix_document_status", "status"),
  )

Em DocumentChunk:
  __table_args__ = (
      Index("ix_chunk_document_index", "document_id", "chunk_index"),
  )

Em Session:
  __table_args__ = (
      Index("ix_session_status", "status"),
  )

Em Question:
  __table_args__ = (
      Index("ix_question_session_created", "session_id", "created_at"),
  )

Em TranscriptSegment:
  __table_args__ = (
      Index("ix_transcript_session_created", "session_id", "created_at"),
  )

Verificar imports necessários: from sqlalchemy import Index

Depois criar a migration:
  alembic revision --autogenerate -m "add_performance_indexes"

Mostrar o conteúdo da migration gerada e confirmar que os indexes aparecem nela.
```

---

## Task 9 — Expandir Testes

```
Contexto: projeto Podium. Criar/editar arquivos em tests/

Leia tests/conftest.py e tests/test_sessions.py para entender o padrão de testes.

Criar tests/test_documents.py com:

1. test_upload_invalid_extension: POST /documents com arquivo .txt → deve retornar 415
2. test_upload_too_large: POST /documents com arquivo > 100MB simulado → deve retornar 413
   (mock o read do arquivo para simular tamanho grande)
3. test_get_document_not_found: GET /documents/99999 → deve retornar 404
4. test_get_chunks_empty: criar documento, GET /documents/{id}/chunks → deve retornar lista vazia

Criar tests/test_llm_service.py com:

1. test_parse_valid_json: chamar _parse_response com JSON direto → deve retornar dict correto
2. test_parse_markdown_wrapped: chamar _parse_response com "```json\n{...}\n```" → deve parsear
3. test_parse_invalid_fallback: chamar _parse_response com "texto inválido" → deve retornar fallback com question_text

Importar _parse_response diretamente: from app.services.llm_service import _parse_response

Criar tests/test_analytics.py com:

1. test_analytics_empty_session: criar sessão sem segmentos, GET /sessions/{id}/analytics
   → deve retornar total_segments=0, total_questions=0
2. test_analytics_with_data: criar sessão, adicionar segmentos mockados via DB, checar analytics

Usar o padrão de fixtures do conftest.py existente.
Ao final rodar: python -m pytest tests/ -v e mostrar resultado.
```

---

## Task 10 — Vincular User à Session

```
Contexto: projeto Podium. Arquivos alvo: app/models/session.py, app/api/routes/sessions.py, app/schemas/session.py

Esta task adiciona user_id à Session e enforça autenticação nas rotas de sessão.

1. Em app/models/session.py:
   - Adicionar campo: user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
   - Adicionar relationship se quiser: user: Mapped["User | None"] = relationship(back_populates=None)

2. Criar migration:
   alembic revision --autogenerate -m "add_user_id_to_session"

   Verificar que a migration tem ADD COLUMN user_id e o FK constraint correto.

3. Em app/schemas/session.py:
   - Adicionar user_id: int | None = None em SessionOut

4. Em app/api/routes/sessions.py:
   - Importar get_current_user de app.api.deps ou app.core.security
   - Adicionar current_user: User = Depends(get_current_user) nas seguintes rotas:
     * POST /sessions
     * GET /sessions/{session_id}
     * POST /sessions/{session_id}/segments
     * GET /sessions/{session_id}/segments
     * GET /sessions/{session_id}/questions
     * WS /sessions/{session_id}/live (se aplicável)
   - No POST /sessions, preencher: session.user_id = current_user.id
   - No GET /sessions/{session_id}, adicionar verificação:
     if session.user_id and session.user_id != current_user.id:
         raise HTTPException(403, "Acesso negado")

5. Atualizar tests/test_sessions.py para incluir token de autenticação nos requests
   (criar fixture create_user_and_token que registra usuário e pega JWT)

Listar todos os arquivos modificados ao final.
```

---

## Verificação Final

Após executar todas as tasks, rodar:

```bash
# Aplicar migrations
alembic upgrade head

# Subir serviços
docker-compose up -d
uvicorn app.main:app --reload

# Rodar todos os testes
python -m pytest tests/ -v --tb=short

# Checar endpoints principais
curl http://localhost:8000/health
curl http://localhost:8000/profiles
```

Resultado esperado: todos os testes passando, sem erros de import, API respondendo.
