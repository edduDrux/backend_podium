# Podium — Backend (Python)

Backend do projeto **Podium**: simulador de apresentações com geração de perguntas em tempo real via LLM, desenvolvido como TCC em Ciência da Computação.

O sistema recebe segmentos de transcrição de fala durante uma apresentação e, em resposta, gera perguntas contextuais baseadas no conteúdo do documento carregado e no perfil de simulação escolhido. As perguntas são entregues ao cliente via WebSocket em tempo real.

---

## Arquitetura

```
Cliente (VR/Web)
      │
      ├── HTTP (REST)  ──▶  FastAPI  ──▶  PostgreSQL
      │                         │
      └── WebSocket  ◀──  Redis Pub/Sub
                                │
                          Celery Worker
                         (geração de perguntas)
```

**Fluxo principal:**
1. Upload de documento PDF → extração de texto + chunking (Celery)
2. Criação de sessão (documento + perfil de simulação)
3. Envio de segmentos de transcrição em tempo real → dispara task Celery
4. Celery faz Full-Text Search no PostgreSQL, gera pergunta e publica no Redis
5. WebSocket entrega a pergunta ao cliente

---

## Stack

| Camada | Tecnologia |
|---|---|
| Framework | FastAPI + Uvicorn |
| Banco de dados | PostgreSQL 17 (async via asyncpg) |
| Fila / Cache | Redis 7 |
| Worker assíncrono | Celery |
| ORM | SQLAlchemy 2.0 (async) |
| Busca textual | PostgreSQL Full-Text Search |
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

### 2. Instale as dependências

```bash
pip install -e .
```

### 3. Configure as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto (ele está no `.gitignore` — nunca o commite):

```env
DATABASE_URL=postgresql+asyncpg://podium:podium@localhost:5433/podium
REDIS_URL=redis://localhost:6379/0
UPLOADS_DIR=./data/uploads
ENVIRONMENT=dev

# Integrações futuras (LLM / STT)
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
```

> **Atenção:** se usar o Docker Compose abaixo, o PostgreSQL fica exposto na porta **5433** do host. Ajuste `DATABASE_URL` para usar `5433`.

### 4. Suba os serviços de infraestrutura

```bash
docker-compose up -d
```

Isso inicia:
- PostgreSQL 17 → `localhost:5433`
- Redis 7 → `localhost:6379`

### 5. Popule os perfis de simulação

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
celery -A app.workers.celery_app worker --loglevel=info
```

A API estará disponível em `http://localhost:8000`.
Documentação interativa: `http://localhost:8000/docs`

---

## Endpoints

### Documentos (`/documents`)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/documents` | Upload de PDF (inicia extração assíncrona) |
| `GET` | `/documents/{id}` | Status e metadados do documento |
| `GET` | `/documents/{id}/text` | Texto extraído completo |
| `GET` | `/documents/{id}/chunks` | Lista os chunks de texto (paginado) |
| `GET` | `/documents/{id}/search?q=...` | Busca full-text nos chunks |

**Status do documento:** `QUEUED` → `PROCESSING` → `CHUNKED` → `READY` / `FAILED`

### Perfis de simulação (`/profiles`)

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/profiles` | Lista todos os perfis |
| `GET` | `/profiles/{id}` | Detalhe de um perfil |

### Sessões (`/sessions`)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/sessions` | Cria sessão (requer documento `CHUNKED` ou `READY`) |
| `GET` | `/sessions/{id}` | Status da sessão |
| `POST` | `/sessions/{id}/segments` | Envia segmento de transcrição |
| `GET` | `/sessions/{id}/segments` | Lista segmentos recebidos |
| `GET` | `/sessions/{id}/questions` | Lista perguntas geradas |

**Status da sessão:** `READY` → `RUNNING` (ao receber o primeiro segmento)

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
2. **Cooldown** — intervalo mínimo de 15s entre perguntas consecutivas
3. **Deduplicação** — detecta perguntas semanticamente repetidas antes de persistir

---

## Estrutura do projeto

```
app/
├── api/
│   ├── deps.py               # Dependências compartilhadas (DB session)
│   └── routes/
│       ├── documents.py
│       ├── profiles.py
│       ├── sessions.py
│       └── websocket.py
├── core/
│   ├── config.py             # Settings via pydantic-settings (.env)
│   ├── database.py           # Engine async + session factory
│   ├── logging.py
│   └── security.py
├── models/                   # SQLAlchemy ORM models
│   ├── document.py
│   ├── document_chunk.py
│   ├── profile.py
│   ├── question.py
│   ├── session.py
│   ├── transcript.py
│   └── user.py
├── schemas/                  # Pydantic schemas (request/response)
├── services/
│   ├── document_service.py   # Extração de texto e chunking
│   ├── llm_service.py        # Integração LLM (futuro)
│   ├── redis_service.py      # Pub/Sub helpers
│   ├── simulation_service.py # Geração de perguntas (stub/FTS)
│   ├── storage_service.py    # Persistência de arquivos
│   ├── stt_service.py        # Speech-to-Text (futuro)
│   └── vector_service.py     # Busca vetorial (futuro)
├── workers/
│   ├── celery_app.py         # Configuração do Celery
│   └── tasks.py              # Tasks: extração de doc + geração de perguntas
├── prompts/                  # Prompts por perfil (Markdown)
│   └── profiles/
│       ├── academic.md
│       ├── auditorium.md
│       ├── corporate.md
│       └── interview.md
├── scripts/
│   └── seed_profiles.py      # Popula perfis no banco
└── main.py                   # Entrypoint FastAPI
```

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
