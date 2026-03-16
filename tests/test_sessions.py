"""
Testes de sessões. A task Celery é mockada para evitar dependência de worker.
Todas as rotas de sessão requerem autenticação JWT.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch

from app.models.document import Document
from app.models.profile import SimulationProfile
from tests.conftest import _TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures de autenticação
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def auth_headers(client):
    """Registra um usuário e retorna headers com Bearer token."""
    resp = await client.post(
        "/auth/register",
        json={"email": "tester@example.com", "password": "senha123"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _setup_doc_and_profile(status: str = "CHUNKED"):
    async with _TestSessionLocal() as db:
        doc = Document(
            filename="test.pdf",
            content_type="application/pdf",
            storage_path="/tmp/test.pdf",
            status=status,
        )
        profile = SimulationProfile(
            key="test_p",
            name="Test",
            description="",
            config={"max_questions_per_minute": 5},
        )
        db.add(doc)
        db.add(profile)
        await db.commit()
        await db.refresh(doc)
        await db.refresh(profile)
        return doc.id, profile.id


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_session_requires_auth(client):
    """POST /sessions sem token deve retornar 401."""
    doc_id, profile_id = await _setup_doc_and_profile()
    resp = await client.post("/sessions", json={"document_id": doc_id, "profile_id": profile_id})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_session(client, auth_headers):
    doc_id, profile_id = await _setup_doc_and_profile()
    resp = await client.post(
        "/sessions",
        json={"document_id": doc_id, "profile_id": profile_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "READY"
    assert data["document_id"] == doc_id
    assert data["user_id"] is not None


@pytest.mark.asyncio
async def test_create_session_document_not_ready(client, auth_headers):
    doc_id, profile_id = await _setup_doc_and_profile(status="QUEUED")
    resp = await client.post(
        "/sessions",
        json={"document_id": doc_id, "profile_id": profile_id},
        headers=auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_session_document_not_found(client, auth_headers):
    async with _TestSessionLocal() as db:
        profile = SimulationProfile(
            key="prf_nf", name="T", description="", config={}
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        profile_id = profile.id

    resp = await client.post(
        "/sessions",
        json={"document_id": 9999, "profile_id": profile_id},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_not_found(client, auth_headers):
    resp = await client.get("/sessions/9999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_segment_triggers_task(client, auth_headers):
    doc_id, profile_id = await _setup_doc_and_profile()
    resp = await client.post(
        "/sessions",
        json={"document_id": doc_id, "profile_id": profile_id},
        headers=auth_headers,
    )
    session_id = resp.json()["id"]

    with patch("app.api.routes.sessions.generate_question_for_segment") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            f"/sessions/{session_id}/segments",
            json={
                "text": "Redes neurais convolucionais são usadas em visão computacional.",
                "start_ms": 0,
                "end_ms": 4000,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert mock_task.delay.called

    # Verifica que a sessão mudou para RUNNING
    resp = await client.get(f"/sessions/{session_id}", headers=auth_headers)
    assert resp.json()["status"] == "RUNNING"

    # Lista segmentos
    resp = await client.get(f"/sessions/{session_id}/segments", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_analytics_empty_session(client, auth_headers):
    doc_id, profile_id = await _setup_doc_and_profile()
    resp = await client.post(
        "/sessions",
        json={"document_id": doc_id, "profile_id": profile_id},
        headers=auth_headers,
    )
    session_id = resp.json()["id"]

    resp = await client.get(f"/sessions/{session_id}/analytics", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_segments"] == 0
    assert data["total_questions"] == 0
    assert data["questions_per_minute"] is None
