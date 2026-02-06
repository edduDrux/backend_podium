import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.profile import SimulationProfile


PROFILES = [
    {
        "key": "academic",
        "name": "Academic",
        "description": "Simulação com foco em rigor acadêmico e profundidade técnica.",
        "config": {
            "rigor_level": 5,
            "tone": "formal",
            "max_questions_per_minute": 3,
            "follow_up_probability": 0.75,
            "intents": ["validate_methodology", "test_concepts", "challenge_assumptions"],
        },
    },
    {
        "key": "corporate",
        "name": "Corporate",
        "description": "Simulação com foco em pitch, persuasão e gestão de tempo.",
        "config": {
            "rigor_level": 3,
            "tone": "objective",
            "max_questions_per_minute": 4,
            "follow_up_probability": 0.55,
            "intents": ["assess_business_value", "evaluate_clarity", "pressure_timeboxing"],
        },
    },
    {
        "key": "interview",
        "name": "Interview",
        "description": "Simulação com foco em currículo, experiência prática e comportamental.",
        "config": {
            "rigor_level": 4,
            "tone": "conversational",
            "max_questions_per_minute": 3,
            "follow_up_probability": 0.65,
            "intents": ["probe_resume", "behavioral_assessment", "verify_impact"],
        },
    },
    {
        "key": "auditorium",
        "name": "Auditorium",
        "description": "Simulação com pressão de plateia e perguntas diversificadas.",
        "config": {
            "rigor_level": 4,
            "tone": "dynamic",
            "max_questions_per_minute": 5,
            "follow_up_probability": 0.7,
            "intents": ["stress_test", "diverse_questions", "manage_interruptions"],
        },
    },
]


async def seed_profiles() -> None:
    async with AsyncSessionLocal() as session:
        for profile_data in PROFILES:
            stmt = select(SimulationProfile).where(SimulationProfile.key == profile_data["key"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is None:
                session.add(SimulationProfile(**profile_data))

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_profiles())
