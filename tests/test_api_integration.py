"""
Testes de integração end-to-end: fluxo completo de autenticação,
upload de documentos e criação de sessões.
"""
import io
import pytest
from unittest.mock import patch

from app.models.document import Document
from app.models.profile import SimulationProfile
from tests.conftest import _TestSessionLocal


@pytest.mark.asyncio
async def test_register_login_token_flow(client):
    """Registro → login → uso do token no /auth/me."""
    # 1. Registro
    resp = await client.post(
        "/auth/register",
        json={"email": "integ@podium.dev", "password": "senha_segura"},
    )
    assert resp.status_code == 201
    register_token = resp.json()["access_token"]

    # 2. Login com as mesmas credenciais
    resp = await client.post(
        "/auth/login",
        data={"username": "integ@podium.dev", "password": "senha_segura"},
    )
    assert resp.status_code == 200
    login_token = resp.json()["access_token"]
    assert login_token  # não vazio

    # 3. Usar o token do login para acessar /auth/me
    resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "integ@podium.dev"


@pytest.mark.asyncio
async def test_upload_pdf_with_valid_token(client, auth_headers):
    """Upload de PDF com token válido deve retornar 200."""
    file_data = b"%PDF-1.4 fake pdf content for integration test"
    with patch("app.api.routes.documents.extract_document_text") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/documents",
            files={"file": ("integ.pdf", io.BytesIO(file_data), "application/pdf")},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "integ.pdf"
    assert data["status"] == "QUEUED"
    assert data["user_id"] is not None


@pytest.mark.asyncio
async def test_upload_pdf_without_token(client):
    """Upload de PDF sem token deve retornar 401."""
    file_data = b"%PDF-1.4 fake pdf"
    resp = await client.post(
        "/documents",
        files={"file": ("doc.pdf", io.BytesIO(file_data), "application/pdf")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_session_with_ready_document(client, auth_headers):
    """Criar sessão com documento READY deve retornar 200 com status READY."""
    # Setup: cria documento com status READY e perfil diretamente no banco
    async with _TestSessionLocal() as db:
        doc = Document(
            filename="pronto.pdf",
            content_type="application/pdf",
            storage_path="/tmp/pronto.pdf",
            status="READY",
        )
        profile = SimulationProfile(
            key="integ_profile",
            name="Integration",
            description="Perfil para teste de integração",
            config={"max_questions_per_minute": 3},
        )
        db.add(doc)
        db.add(profile)
        await db.commit()
        await db.refresh(doc)
        await db.refresh(profile)
        doc_id = doc.id
        profile_id = profile.id

    resp = await client.post(
        "/sessions",
        json={"document_id": doc_id, "profile_id": profile_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "READY"
    assert data["document_id"] == doc_id
    assert data["profile_id"] == profile_id
    assert data["user_id"] is not None
