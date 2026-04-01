# Podium — Backend (Python)

Backend do projeto **Podium**: simulador de apresentações com geração de perguntas em tempo real via LLM, desenvolvido como TCC em Ciência da Computação.

O sistema recebe segmentos de transcrição de fala durante uma apresentação e, em resposta, gera perguntas contextuais baseadas no conteúdo do documento carregado e no perfil de simulação escolhido. As perguntas são entregues ao cliente via WebSocket em tempo real.

---

## Arquitetura

```
Cliente (VR/Web)
      │
      ├── HTTP (REST)  ──▶  FastAPI  ──▶  PostgreSQL (pgvector)
      │                         │
      └── WebSocket  ◀──  Redis Pub/Sub
                                │
                          Celery Worker
                         (geração de perguntas)
```

**Fluxo principal:**
1. Upload de documento PDF → extração de texto + chunking + embeddings (Celery)
2. Criação de sessão (documento + perfil de simulação)
3. Envio de segmentos de transcrição em tempo real → dispara task Celery
4. Celery faz busca semântica via pgvector (cosine similarity), gera pergunta via LLM e publica no Redis
5. WebSocket entrega a pergunta ao cliente

---

## Stack

| Camada | Tecnologia |
|---|---|
| Framework | FastAPI + Uvicorn |
| Banco de dados | PostgreSQL 17 + pgvector (async via asyncpg) |
| Busca semântica | pgvector (cosine similarity) com FTS como fallback |
| Embeddings | OpenAI text-embedding-3-small (1536 dims) |
| LLM | OpenAI GPT-4o-mini (padrão, configurável via `LLM_MODEL`) / Gemini Flash (fallback) |
| Fila / Cache | Redis 7 |
| Worker assíncrono | Celery |
| ORM | SQLAlchemy 2.0 (async) |
| Autenticação | JWT (HS256) via python-jose + bcrypt |
| Containerização | Docker Compose |
| Runtime | Python 3.10+ |

---

## Pré-requisitos

- Python 3.10+
- Docker e Docker Compose
- `pip` (ou `uv`)

---

## Setup

### 1. Clone e ambiente virtual

```bash
git clone <url-do-repo>
cd backend_podium

python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
```

### 2. Instale as depend��ncias

```bash
pip install -e .
```

### 3. Configure as variáveis de ambiente

Copie o exemplo e preencha com seus valores:

```bash
cp .env.example .env
```

Variáveis principais:

| Variável | Descrição | Padrão |
|---|---|---|
| `DATABASE_URL` | URL do PostgreSQL (asyncpg) | — |
| `REDIS_URL` | URL do Redis | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | Chave da OpenAI (embeddings + LLM + STT) | — |
| `GOOGLE_API_KEY` | Chave do Google (Gemini, fallback) | — |
| `LLM_MODEL` | Modelo LLM para geração de perguntas | `gpt-4o-mini` |
| `JWT_SECRET` | Segredo para assinatura JWT | `change-me-in-production` |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `JWT_EXPIRE_MINUTES` | Validade do token em minutos | `1440` (24h) |

### 4. Suba os serviços de infraestrutura

```bash
docker-compose up -d
```

Isso inicia (com healthchecks):
- PostgreSQL 17 + pgvector → `localhost:5433`
- Redis 7 → `localhost:6379`

### 5. Aplique as migrations

```bash
alembic upgrade head
```

### 6. Popule os perfis de simulação

```bash
python -m app.scripts.seed_profiles
```

Isso insere os 4 perfis padrão no banco: **Academic**, **Corporate**, **Interview**, **Auditorium**.

---

## Rodando a aplicação

Você precisa de **dois processos** rodando em paralelo:

**Terminal 1 — API (FastAPI)**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Worker (Celery)**
```bash
celery -A app.workers.celery_app worker --loglevel=info --pool=solo  # Windows
celery -A app.workers.celery_app worker --loglevel=info              # Linux/macOS
```

A API estará disponível em `http://localhost:8000`.
Documentação interativa: `http://localhost:8000/docs`

---

## Endpoints

### Autenticação (`/auth`)

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| `POST` | `/auth/register` | Cria conta e retorna JWT | Não |
| `POST` | `/auth/login` | Login (OAuth2 form) e retorna JWT | Não |
| `GET` | `/auth/me` | Dados do usuário autenticado | Sim |

**Exemplo de registro:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'
```

**Exemplo de login:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -d "username=user@example.com&password=secret123"
```

O token retornado deve ser enviado no header: `Authorization: Bearer <token>`

### Documentos (`/documents`)

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| `POST` | `/documents` | Upload de PDF/PPTX/DOCX (inicia extração assíncrona) | Sim |
| `GET` | `/documents/{id}` | Status e metadados do documento | Não |
| `GET` | `/documents/{id}/text` | Texto extraído completo | Não |
| `GET` | `/documents/{id}/chunks` | Lista os chunks de texto (paginado) | Não |
| `GET` | `/documents/{id}/search?q=...` | Busca full-text nos chunks | Não |

**Status do documento:** `QUEUED` → `PROCESSING` → `CHUNKED` → `READY` / `FAILED`

### Perfis de simulação (`/profiles`)

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| `GET` | `/profiles` | Lista todos os perfis | Não |
| `GET` | `/profiles/{id}` | Detalhe de um perfil | Não |

### Sessões (`/sessions`)

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| `POST` | `/sessions` | Cria sessão (requer documento `CHUNKED` ou `READY`) | Sim |
| `GET` | `/sessions/{id}` | Status da sessão | Sim |
| `POST` | `/sessions/{id}/segments` | Envia segmento de transcrição | Sim |
| `GET` | `/sessions/{id}/segments` | Lista segmentos recebidos | Sim |
| `GET` | `/sessions/{id}/questions` | Lista perguntas geradas | Sim |
| `POST` | `/sessions/{id}/audio` | Upload de áudio para STT (202) | Sim |
| `GET` | `/sessions/{id}/analytics` | Métricas da sessão | Sim |
| `POST` | `/sessions/{id}/feedback` | Solicita feedback via LLM (202) | Sim |
| `GET` | `/sessions/{id}/feedback` | Recupera feedback gerado | Sim |

**Status da sessão:** `READY` → `RUNNING` (ao receber o primeiro segmento) → `FINISHED`

### WebSocket

```
WS /sessions/{session_id}/live
```

Conecte para receber eventos em tempo real da sessão. Formato do evento:

```json
{
  "type": "question.created",
  "session_id": 1,
  "question": {
    "id": 42,
    "question_text": "Explique melhor: ...",
    "intent": "general",
    "difficulty": 3,
    "evidence_chunk_ids": [7, 12],
    "created_at": "2025-06-01T14:30:00Z"
  }
}
```

### Health check

```
GET /health  →  { "status": "ok" }
```

---

## Perfis de simulação

| Key | Nome | Foco | Perguntas/min |
|---|---|---|---|
| `academic` | Academic | Rigor acadêmico, validação metodológica | 3 |
| `corporate` | Corporate | Pitch, persuasão, gestão de tempo | 4 |
| `interview` | Interview | Currículo, experiência comportamental | 3 |
| `auditorium` | Auditorium | Pressão de plateia, diversidade de perguntas | 5 |

---

## Anti-spam na geração de perguntas

O worker aplica três camadas de proteção para evitar flood de perguntas:

1. **Rate limit** — respeita `max_questions_per_minute` configurado no perfil
2. **Cooldown** — intervalo mínimo configurável entre perguntas consecutivas
3. **Deduplicação** — detecta perguntas semanticamente repetidas (SequenceMatcher > 0.75)

---

## Testes

```bash
python -m pytest tests/
```

Os testes usam SQLite em memória via aiosqlite para isolamento completo.

---

## Comandos úteis

```bash
# Verificar logs do Celery em verbose
celery -A app.workers.celery_app worker --loglevel=debug

# Inspecionar workers ativos
celery -A app.workers.celery_app inspect active

# Parar containers
docker-compose down

# Derrubar containers e volumes (apaga dados do banco)
docker-compose down -v
```

---

*Desenvolvido por Eduardo Sartori — TCC Ciência da Computação (2025/2026)*
