# Podium API — Documentação

**Base URL:** `http://127.0.0.1:8000`
**Docs interativas:** `http://127.0.0.1:8000/docs`

---

## Fluxo principal

```
1. [Auth]      Registrar / fazer login
2. [Documents] Enviar PDF → aguardar status CHUNKED
3. [Profiles]  Listar perfis → escolher um ID
4. [Sessions]  Criar sessão com document_id + profile_id
5. [Segments]  Enviar trechos da fala durante a apresentação
6. [WebSocket] Receber perguntas em tempo real
7. [Feedback]  Solicitar feedback ao final
```

---

## Auth

### `POST /auth/register`
Cria uma conta e retorna token JWT.

**Body (JSON):**
```json
{
  "email": "usuario@email.com",
  "password": "senha123"
}
```

**Resposta (201):**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### `POST /auth/login`
Login. Usa formato `form-data` (não JSON).

**Body (form-data):**
```
username = usuario@email.com
password = senha123
```

**Resposta (200):**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### `GET /auth/me`
Retorna o usuário logado.

**Header:** `Authorization: Bearer <token>`

**Resposta (200):**
```json
{
  "id": 1,
  "email": "usuario@email.com"
}
```

---

## Documents

### `POST /documents`
Envia um arquivo. Aceita PDF, PPTX, DOCX.

**Body (form-data):**
```
file = (arquivo)
```

**Resposta (200):**
```json
{
  "id": 6,
  "filename": "slides.pdf",
  "content_type": "application/pdf",
  "status": "QUEUED",
  "created_at": "2026-03-10T00:47:08Z"
}
```

> O processamento é assíncrono. O status evolui: `QUEUED → PROCESSING → CHUNKED`. Consulte o endpoint abaixo para saber quando está pronto.

---

### `GET /documents/{document_id}`
Retorna status e dados do documento.

**Resposta (200):**
```json
{
  "id": 6,
  "filename": "slides.pdf",
  "content_type": "application/pdf",
  "status": "CHUNKED",
  "created_at": "2026-03-10T00:47:08Z"
}
```

**Status possíveis:**

| Status | Significado |
|---|---|
| `QUEUED` | Na fila aguardando worker |
| `PROCESSING` | Worker extraindo texto |
| `CHUNKED` | Pronto para uso em sessões |
| `FAILED` | Falha no processamento |

---

### `GET /documents/{document_id}/text`
Retorna o texto extraído do documento (texto puro).

> Só funciona se status for `CHUNKED`.

---

### `GET /documents/{document_id}/chunks`
Lista os chunks (pedaços de texto) gerados do documento.

**Query params:**

| Param | Padrão | Descrição |
|---|---|---|
| `limit` | 20 | Máx. de chunks retornados (1–200) |
| `offset` | 0 | Paginação |

**Resposta (200):**
```json
[
  {
    "id": 1,
    "document_id": 6,
    "chunk_index": 0,
    "content": "Texto do trecho...",
    "created_at": "..."
  }
]
```

---

### `GET /documents/{document_id}/search?q=termo`
Busca chunks relevantes por texto (Full-Text Search em português).

**Query params:**

| Param | Descrição |
|---|---|
| `q` | Termo de busca (2–200 caracteres) |
| `limit` | Máx. de resultados (padrão: 5) |

**Resposta (200):**
```json
[
  {
    "rank": 0.85,
    "chunk": { "id": 3, "content": "..." }
  }
]
```

---

## Profiles

### `GET /profiles`
Lista os perfis de simulação disponíveis.

**Resposta (200):**
```json
[
  { "id": 1, "key": "academic",   "name": "Defesa Acadêmica",       "description": "..." },
  { "id": 2, "key": "corporate",  "name": "Ambiente Corporativo",    "description": "..." },
  { "id": 3, "key": "interview",  "name": "Entrevista de Emprego",   "description": "..." },
  { "id": 4, "key": "auditorium", "name": "Auditório",               "description": "..." }
]
```

---

### `GET /profiles/{profile_id}`
Retorna um perfil específico.

---

## Sessions

### `POST /sessions`
Cria uma sessão de simulação. O documento deve estar com status `CHUNKED`.

**Body (JSON):**
```json
{
  "document_id": 6,
  "profile_id": 1
}
```

**Resposta (200):**
```json
{
  "id": 1,
  "document_id": 6,
  "profile_id": 1,
  "status": "READY",
  "feedback_text": null,
  "created_at": "..."
}
```

**Status possíveis da sessão:**

| Status | Significado |
|---|---|
| `READY` | Criada, aguardando apresentação |
| `RUNNING` | Recebendo segmentos de fala |
| `FINISHED` | Feedback gerado, encerrada |
| `FAILED` | Erro |

---

### `GET /sessions/{session_id}`
Retorna dados da sessão.

---

### `POST /sessions/{session_id}/segments`
Envia um trecho da fala durante a apresentação. Dispara geração de pergunta automaticamente.

**Body (JSON):**
```json
{
  "text": "Meu projeto visa reduzir custos operacionais em 30% usando automação.",
  "start_ms": 0,
  "end_ms": 5000
}
```

> `start_ms` e `end_ms` são opcionais (tempo em milissegundos).

**Resposta (200):**
```json
{
  "id": 1,
  "session_id": 1,
  "text": "Meu projeto visa...",
  "start_ms": 0,
  "end_ms": 5000,
  "created_at": "..."
}
```

> O primeiro segmento muda a sessão de `READY` para `RUNNING`. A pergunta gerada chega via WebSocket.

---

### `GET /sessions/{session_id}/segments`
Lista os segmentos enviados na sessão.

**Query params:**

| Param | Padrão |
|---|---|
| `limit` | 50 (máx. 200) |

---

### `GET /sessions/{session_id}/questions`
Lista as perguntas geradas na sessão.

**Resposta (200):**
```json
[
  {
    "id": 1,
    "session_id": 1,
    "question_text": "Como você justifica a meta de 30%?",
    "intent": "clarification",
    "difficulty": "medium",
    "evidence_chunk_ids": [3, 7],
    "created_at": "..."
  }
]
```

---

### `POST /sessions/{session_id}/audio`
Envia áudio para transcrição automática via Whisper. Retorna `202` imediatamente — os segmentos aparecem assincronamente.

**Body (form-data):**
```
file = (arquivo .wav / .mp3 / .m4a / .webm)
```

> Requer `OPENAI_API_KEY` configurada.

---

### `GET /sessions/{session_id}/analytics`
Retorna métricas da sessão (número de segmentos, perguntas, duração, etc).

---

### `POST /sessions/{session_id}/feedback`
Enfileira a geração de feedback consolidado. Retorna `202` imediatamente.

> A sessão precisa estar em `RUNNING` (ter recebido segmentos).

---

### `GET /sessions/{session_id}/feedback`
Retorna o feedback gerado.

**Resposta (200):**
```json
{
  "session_id": 1,
  "status": "FINISHED",
  "feedback_text": "Pontos fortes: ..."
}
```

> Retorna `202` se o feedback ainda não estiver pronto.

---

## WebSocket

### `WS /sessions/{session_id}/live`
Conecte antes de enviar segmentos para receber perguntas em tempo real.

**Exemplo em JavaScript:**
```js
const ws = new WebSocket("ws://127.0.0.1:8000/sessions/1/live");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "question.created") {
    console.log("Pergunta:", data.question.question_text);
  }
};
```

**Payload recebido:**
```json
{
  "type": "question.created",
  "session_id": 1,
  "question": {
    "id": 5,
    "question_text": "Qual a principal evidência que suporta essa afirmação?",
    "intent": "evidence",
    "difficulty": "hard",
    "evidence_chunk_ids": [2, 8],
    "created_at": "..."
  }
}
```

---

## Regras de negócio (guardrails)

- Máximo **3 perguntas por minuto** por sessão (configurável por perfil)
- Cooldown de **15 segundos** entre perguntas
- Perguntas duplicadas são bloqueadas automaticamente
- Documento deve estar `CHUNKED` para criar sessão

---

## Erros comuns

| Código | Causa |
|---|---|
| `400` | Tipo de arquivo não suportado |
| `401` | Token ausente ou inválido |
| `404` | Recurso não encontrado |
| `409` | Documento ainda não processado / e-mail já cadastrado |
| `422` | Body inválido (campo faltando ou tipo errado) |
