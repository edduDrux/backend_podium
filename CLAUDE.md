# Claude Context — Projeto Podium

## 1. Resumo do projeto

**Podium** é um backend em Python para uma plataforma imersiva de treinamento de oratória com VR + IA/LLM.

Objetivo do backend:

- receber e processar **documentos** da apresentação do usuário;
- receber **fala transcrita em segmentos** durante a apresentação;
- correlacionar o conteúdo do documento com a fala;
- gerar **perguntas contextuais** e, depois, **feedback de performance**;
- servir como **middleware** entre frontend/VR client e serviços cognitivos.

O usuário do projeto é iniciante em Python e VR, então as respostas devem priorizar:

- simplicidade;
- implementação incremental;
- código claro;
- poucas mudanças por etapa;
- foco em MVP funcional antes de sofisticação.

---

## 2. Escopo funcional do produto

### Entrada de documentos

O sistema deve aceitar:

- **PDF** como prioridade do MVP;
- suporte futuro para **PPTX** e **DOCX/DOCS**.

O texto extraído do documento será usado como **base de conhecimento** para perguntas contextualizadas.

### Entrada da apresentação

Durante a apresentação, o frontend/VR client enviará:

- idealmente **segmentos de texto transcritos** em tempo real;
- no futuro, também poderá enviar **áudio** para STT.

### Saída esperada

O backend deve:

- gerar perguntas sobre a apresentação;
- variar o estilo conforme o perfil de simulação;
- no futuro, gerar feedback de performance.

---

## 3. Perfis de simulação

Existem 4 perfis principais:

1. **Defesa Acadêmica**
   - foco em rigor técnico;
   - fundamentação;
   - profundidade conceitual;
   - estilo semelhante a banca de TCC.

2. **Ambiente Corporativo**
   - foco em pitch;
   - persuasão;
   - clareza;
   - gestão de tempo;
   - visão de negócio.

3. **Entrevista de Emprego**
   - foco em currículo;
   - experiência;
   - comportamento;
   - justificativas e exemplos.

4. **Auditório**
   - foco em pressão;
   - variedade de perguntas;
   - improviso;
   - exposição a perguntas mais amplas e imprevisíveis.

Esses perfis devem influenciar:

- tom;
- rigor;
- frequência de perguntas;
- follow-ups;
- intenções das perguntas.

---

## 4. Requisitos técnicos principais

### Requisitos de backend

- usar **Python**;
- usar **FastAPI**;
- usar **asyncio** sempre que fizer sentido;
- suportar crescimento futuro;
- manter arquitetura modular.

### Requisitos de UX / latência

- a geração de perguntas não deve quebrar a imersão;
- ideal de latência para pergunta: **3 a 5 segundos**;
- por isso o sistema deve preferir:
  - documento pré-processado antes da sessão;
  - fala recebida em segmentos curtos;
  - processamento assíncrono.

### Requisitos de IA

- usar prompts estruturados;
- reduzir alucinação;
- evitar repetição;
- basear perguntas em evidências do documento.

---

## 5. Arquitetura decidida para o MVP

### Stack principal

- **FastAPI** para API;
- **PostgreSQL** como banco principal;
- **Redis** para broker e Pub/Sub;
- **Celery** para tarefas assíncronas;
- **Docker Compose** para infraestrutura local;
- armazenamento local inicialmente para uploads;
- suporte futuro a MinIO/S3;
- busca textual com **Postgres Full-Text Search** no MVP;
- busca vetorial com **pgvector** no futuro.

### Estratégia do MVP

O MVP não começa com áudio em tempo real complexo.
A abordagem priorizada é:

1. usuário envia documento antes da apresentação;
2. backend extrai texto;
3. backend quebra em chunks;
4. backend cria sessão com perfil;
5. frontend envia **segmentos de texto** da apresentação;
6. backend gera perguntas com base nesses segmentos + chunks relevantes do documento.

---

## 6. Estrutura de pastas escolhida

```text
podium_backend/
  app/
    main.py
    core/
      config.py
      logging.py
      security.py
      database.py
    api/
      routes/
        documents.py
        sessions.py
        profiles.py
        websocket.py
      deps.py
    models/
      user.py
      document.py
      document_chunk.py
      session.py
      profile.py
      question.py
      transcript.py
    schemas/
      document.py
      chunk.py
      session.py
      profile.py
      question.py
      transcript.py
    services/
      storage_service.py
      document_service.py
      vector_service.py
      stt_service.py
      llm_service.py
      simulation_service.py
      analytics_service.py
      redis_service.py
    workers/
      celery_app.py
      tasks.py
    prompts/
      base.md
      profiles/
        academic.md
        corporate.md
        interview.md
        auditorium.md
    scripts/
      seed_profiles.py
      db_indexes.py
  tests/
  docker-compose.yml
  pyproject.toml
  .env

```

## 7. Estado atual do projeto

### Já implementado

O projeto já tem a base abaixo funcionando:

#### Documentos

- upload de PDF;
- armazenamento local do arquivo;
- persistência do documento no Postgres;
- `GET` de documento por id.

#### Processamento assíncrono

- Celery configurado;
- Redis como broker;
- task de processamento do documento;
- extração de texto do PDF via `pypdf`.

#### Texto extraído

- o texto extraído já é salvo em `Document.extracted_text`.

#### Chunking

- o texto já é quebrado em chunks;
- chunks são persistidos na tabela `document_chunks`.

#### Busca

- endpoint para listar chunks do documento;
- endpoint para buscar chunks relevantes com Postgres Full-Text Search.

### Status atuais usados

Status de documento já utilizados:

- `QUEUED`
- `PROCESSING`
- `EXTRACTED`
- `CHUNKED`
- `FAILED`

**Observação:**

- no fluxo atual, após chunking o documento pode ser considerado pronto;
- pode haver uso futuro de `READY` como alias semântico de “pronto para sessão”.

---

## 8. Fluxo de dados do MVP

### Fluxo 1 — Ingestão de documento

1. cliente envia PDF;
2. API salva arquivo;
3. API cria registro `Document`;
4. API enfileira task Celery;
5. worker:
   - extrai texto;
   - salva em `extracted_text`;
   - gera chunks;
   - salva chunks;
   - marca documento como `CHUNKED`.

### Fluxo 2 — Sessão de simulação

1. cliente escolhe um documento já processado;
2. cliente escolhe um perfil;
3. backend cria `Session(status="READY")`.

### Fluxo 3 — Segmentos da apresentação

1. frontend envia `TranscriptSegment`;
2. backend salva segmento;
3. se necessário, muda sessão para `RUNNING`;
4. backend gera pergunta baseada em:
   - texto do segmento;
   - chunks relevantes do documento;
   - perfil da sessão;
   - histórico recente.

### Fluxo 4 — Entrega em tempo real

1. pergunta é salva;
2. evento é publicado no Redis;
3. WebSocket da sessão recebe e repassa ao cliente VR.

---

## 9. Modelos de domínio esperados

### Document

**Campos esperados:**

- `id`
- `filename`
- `content_type`
- `storage_path`
- `status`
- `extracted_text`
- `created_at`

### DocumentChunk

**Campos esperados:**

- `id`
- `document_id`
- `chunk_index`
- `content`
- `created_at`

### SimulationProfile

**Campos esperados:**

- `id`
- `key`
- `name`
- `description`
- `config`
- `created_at`

### Session

**Campos esperados:**

- `id`
- `document_id`
- `profile_id`
- `status`
- `created_at`

**Status esperados:**

- `READY`
- `RUNNING`
- `FINISHED`
- `FAILED`

### TranscriptSegment

**Campos esperados:**

- `id`
- `session_id`
- `text`
- `start_ms`
- `end_ms`
- `created_at`

### Question

**Campos esperados:**

- `id`
- `session_id`
- `question_text`
- `intent`
- `difficulty`
- `evidence_chunk_ids`
- `created_at`

---

## 10. Endpoints já existentes ou previstos

### Documents

**Já existem ou devem existir:**

- `POST /documents`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/text`
- `GET /documents/{document_id}/chunks`
- `GET /documents/{document_id}/search?q=...`

### Profiles

**Devem existir:**

- `GET /profiles`
- `GET /profiles/{profile_id}`

### Sessions

**Devem existir:**

- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/segments`
- `GET /sessions/{session_id}/segments`
- `GET /sessions/{session_id}/questions`

### WebSocket

**Deve existir:**

- `WS /sessions/{session_id}/live`

---

## 11. Regras de negócio importantes

### Documento

- no MVP, apenas `application/pdf`;
- sessão só pode ser criada se o documento estiver processado;
- considerar documento pronto quando status estiver em `CHUNKED` ou `READY`.

### Segmentos

- segmentos são preferidos em vez de áudio bruto para reduzir latência;
- primeiro segmento pode mudar a sessão de `READY` para `RUNNING`.

### Perguntas

- devem ser baseadas no documento;
- devem evitar repetição;
- devem respeitar o perfil;
- devem ter `evidence_chunk_ids` quando possível;
- quando não houver chunk relevante, gerar pergunta genérica baseada no segmento.

### Anti-spam

Devem existir guardrails simples:

- cooldown entre perguntas;
- limite de perguntas por minuto;
- evitar duplicatas triviais.

---

## 12. Estratégia de RAG do MVP

### Versão atual

O MVP usa:

- chunks persistidos no Postgres;
- Full-Text Search com:
  - `to_tsvector('portuguese', content)`
  - `plainto_tsquery('portuguese', q)`
  - `ts_rank_cd(...)`

### Versão futura

Quando necessário, evoluir para:

- embeddings;
- `pgvector`;
- recuperação semântica híbrida.

### Decisão importante

Não introduzir complexidade de embeddings cedo demais.

Primeiro consolidar:

- documentos;
- perfis;
- sessões;
- segmentos;
- perguntas em tempo real.

---

## 13. Ordem de implementação definida

A ordem correta decidida para o projeto é:

1. consolidar documentos + chunks + busca;
2. implementar profiles;
3. implementar sessions;
4. implementar transcript segments;
5. implementar questions com geração stub via Celery;
6. implementar Redis Pub/Sub + WebSocket;
7. adicionar guardrails de repetição e frequência;
8. só depois integrar LLM real;
9. depois feedback e analytics.

Essa ordem não deve ser invertida sem necessidade real.

---

## 14. Filosofia de implementação

### Prioridades

- primeiro funcionar;
- depois refinar;
- sempre preferir MVP demonstrável;
- evitar abstração excessiva cedo;
- manter código legível para iniciante.

### Decisões preferidas

- mudanças pequenas e incrementais;
- poucos arquivos por etapa;
- rotas claras;
- validações explícitas;
- respostas diretas;
- evitar refatoração ampla quando não necessária.

### Evitar

- reestruturar todo o projeto sem necessidade;
- introduzir autenticação cedo;
- introduzir Alembic cedo se o projeto ainda está em MVP;
- adicionar áudio complexo antes da pipeline de texto estar sólida;
- adicionar pgvector antes de sessões/perguntas funcionarem.

---

## 15. Como responder em futuras requisições

Ao responder sobre o projeto Podium:

1. assumir que este contexto já é conhecido;
2. evitar repetir a visão geral do projeto;
3. responder focando no próximo passo prático;
4. preferir:
   - lista curta de ações;
   - arquivos a criar/editar;
   - código pronto;
   - comandos exatos;
   - critérios de teste;
5. quando o pedido for para usar Codex/Claude Code:
   - gerar prompts completos;
   - em blocos separados;
   - com escopo específico;
   - sem explicações longas;
6. economizar tokens:
   - não repetir stack inteira;
   - não repetir estrutura de pastas inteira, salvo quando necessário;
   - não redefinir o produto do zero;
   - não explicar conceitos básicos já decididos.

---

## 16. Padrão esperado para sugestões de código

Quando sugerir código para o Podium:

- usar FastAPI;
- usar SQLAlchemy async;
- usar Pydantic v2;
- seguir o estilo já existente do projeto;
- respeitar `AsyncSession`, `Depends(get_db)` e `HTTPException`;
- usar nomes consistentes com os arquivos já escolhidos;
- não criar dependências desnecessárias.

### Quando gerar rotas

- usar `APIRouter`;
- `response_model` claro;
- validações com `Query` quando houver paginação e limites.

### Quando gerar tasks

- usar Celery;
- abrir `AsyncSessionLocal`;
- tratar erro sem quebrar o worker;
- retornar dict simples de resultado.

---

## 17. Contexto sobre o desenvolvedor

**Informações relevantes:**

- o autor do projeto é iniciante em Python;
- precisa de instruções muito práticas;
- já possui Postgres e Docker na máquina;
- já conseguiu subir API, Redis, Celery e fluxo de documento;
- já testou upload, extração e retorno do texto do PDF.

Portanto, as respostas devem:

- evitar jargão desnecessário;
- ser guiadas passo a passo;
- focar em implementação;
- assumir pouco conhecimento prévio;
- minimizar complexidade.

---

## 18. Próximos marcos do projeto

### MVP funcional demonstrável

O MVP será considerado demonstrável quando o sistema conseguir:

1. receber um PDF;
2. extrair e chunkar texto;
3. listar perfis;
4. criar sessão com documento + perfil;
5. receber segmentos de fala;
6. gerar perguntas automaticamente;
7. enviar perguntas por WebSocket.

### Pós-MVP

Depois disso:

- integrar LLM real;
- melhorar qualidade da pergunta;
- adicionar analytics;
- feedback final;
- suporte a PPTX/DOCX;
- embeddings com pgvector;
- ingestão de áudio com STT.

---

## 19. Resumo ultra-curto para reaproveitamento

**Podium** = backend FastAPI para treino de oratória com VR + IA.

### Estado atual

- upload PDF ok;
- Celery + Redis ok;
- extração de texto ok;
- chunks ok;
- busca FTS no Postgres ok.

### Próxima ordem

- profiles;
- sessions;
- transcript segments;
- questions stub;
- websocket;
- guardrails;
- LLM real.

### Sempre priorizar

- MVP incremental;
- baixo acoplamento;
- poucas mudanças por etapa;
- respostas práticas e econômicas em tokens.
