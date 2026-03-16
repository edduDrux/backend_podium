"""
Testes do endpoint de documentos.
Upload de arquivo, extensão inválida e tamanho excedido.
"""
import io
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_upload_invalid_extension(client):
    """Arquivo .txt deve ser rejeitado (400 pelo content-type ou 415 pela extensão)."""
    file_data = b"conteudo qualquer"
    resp = await client.post(
        "/documents",
        files={"file": ("relatorio.txt", io.BytesIO(file_data), "text/plain")},
    )
    assert resp.status_code in (400, 415)


@pytest.mark.asyncio
async def test_upload_invalid_content_type(client):
    """Content-type não aceito deve retornar 400."""
    file_data = b"%PDF-fake"
    resp = await client.post(
        "/documents",
        files={"file": ("script.exe", io.BytesIO(file_data), "application/x-msdownload")},
    )
    # pode ser 400 (content-type) ou 415 (extensão) dependendo da ordem
    assert resp.status_code in (400, 415)


@pytest.mark.asyncio
async def test_get_document_not_found(client):
    """GET de documento inexistente deve retornar 404."""
    resp = await client.get("/documents/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_pdf_creates_document(client):
    """Upload de PDF válido deve criar documento com status QUEUED."""
    file_data = b"%PDF-1.4 minimal pdf content"
    with patch("app.api.routes.documents.extract_document_text") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/documents",
            files={"file": ("apresentacao.pdf", io.BytesIO(file_data), "application/pdf")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "apresentacao.pdf"
    assert data["status"] == "QUEUED"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_chunks_document_not_ready(client):
    """GET /chunks em documento QUEUED deve retornar 409."""
    file_data = b"%PDF-minimal"
    with patch("app.api.routes.documents.extract_document_text") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/documents",
            files={"file": ("doc.pdf", io.BytesIO(file_data), "application/pdf")},
        )
    doc_id = resp.json()["id"]

    resp = await client.get(f"/documents/{doc_id}/chunks")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_document_text_no_text(client):
    """GET /text em documento sem texto extraído deve retornar 409."""
    file_data = b"%PDF-minimal"
    with patch("app.api.routes.documents.extract_document_text") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/documents",
            files={"file": ("doc.pdf", io.BytesIO(file_data), "application/pdf")},
        )
    doc_id = resp.json()["id"]

    resp = await client.get(f"/documents/{doc_id}/text")
    assert resp.status_code == 409
