import pytest


@pytest.mark.asyncio
async def test_register_and_login(client):
    # Registro
    resp = await client.post("/auth/register", json={
        "email": "test@podium.dev",
        "password": "senha123"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Login
    resp = await client.post("/auth/login", data={
        "username": "test@podium.dev",
        "password": "senha123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_duplicate_register(client):
    await client.post("/auth/register", json={
        "email": "dup@podium.dev",
        "password": "abc"
    })
    resp = await client.post("/auth/register", json={
        "email": "dup@podium.dev",
        "password": "abc"
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "email": "wrong@podium.dev",
        "password": "certa"
    })
    resp = await client.post("/auth/login", data={
        "username": "wrong@podium.dev",
        "password": "errada"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
