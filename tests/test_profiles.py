import pytest

from app.models.profile import SimulationProfile
from tests.conftest import _TestSessionLocal


async def _seed():
    async with _TestSessionLocal() as db:
        db.add(SimulationProfile(
            key="academic", name="Academic",
            description="Banca", config={"max_questions_per_minute": 3},
        ))
        db.add(SimulationProfile(
            key="corporate", name="Corporate",
            description="Pitch", config={"max_questions_per_minute": 4},
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_list_profiles_empty(client):
    resp = await client.get("/profiles")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_profiles_after_seed(client):
    await _seed()
    resp = await client.get("/profiles")
    assert resp.status_code == 200
    keys = [p["key"] for p in resp.json()]
    assert "academic" in keys
    assert "corporate" in keys


@pytest.mark.asyncio
async def test_get_profile_not_found(client):
    resp = await client.get("/profiles/9999")
    assert resp.status_code == 404
