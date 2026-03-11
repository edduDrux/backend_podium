"""
Analytics Service — calcula métricas de uma sessão de simulação.
Não requer LLM. Apenas consultas SQL agregadas.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question
from app.models.transcript import TranscriptSegment


async def get_session_analytics(db: AsyncSession, session_id: int) -> dict:
    # Total de segmentos
    seg_stmt = select(func.count(TranscriptSegment.id)).where(
        TranscriptSegment.session_id == session_id
    )
    total_segments = int((await db.execute(seg_stmt)).scalar_one())

    # Total de perguntas geradas
    q_stmt = select(func.count(Question.id)).where(
        Question.session_id == session_id
    )
    total_questions = int((await db.execute(q_stmt)).scalar_one())

    # Distribuição por dificuldade
    diff_stmt = (
        select(Question.difficulty, func.count(Question.id).label("count"))
        .where(Question.session_id == session_id)
        .group_by(Question.difficulty)
        .order_by(Question.difficulty)
    )
    diff_rows = (await db.execute(diff_stmt)).all()
    difficulty_distribution = {str(row.difficulty): row.count for row in diff_rows}

    # Distribuição por intent
    intent_stmt = (
        select(Question.intent, func.count(Question.id).label("count"))
        .where(Question.session_id == session_id)
        .group_by(Question.intent)
        .order_by(Question.intent)
    )
    intent_rows = (await db.execute(intent_stmt)).all()
    intent_distribution = {row.intent: row.count for row in intent_rows}

    # Duração estimada (end_ms do último segmento)
    last_seg_stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.id.desc())
        .limit(1)
    )
    last_seg = (await db.execute(last_seg_stmt)).scalars().first()
    duration_ms: int | None = last_seg.end_ms if last_seg and last_seg.end_ms else None

    # Perguntas por minuto
    questions_per_minute: float | None = None
    if duration_ms and duration_ms > 0 and total_questions > 0:
        duration_min = duration_ms / 60_000
        questions_per_minute = round(total_questions / duration_min, 2)

    # Dificuldade média
    avg_difficulty: float | None = None
    if total_questions > 0:
        avg_stmt = select(func.avg(Question.difficulty)).where(
            Question.session_id == session_id
        )
        avg_difficulty = round(float((await db.execute(avg_stmt)).scalar_one()), 2)

    return {
        "session_id": session_id,
        "total_segments": total_segments,
        "total_questions": total_questions,
        "questions_per_minute": questions_per_minute,
        "duration_ms": duration_ms,
        "avg_difficulty": avg_difficulty,
        "difficulty_distribution": difficulty_distribution,
        "intent_distribution": intent_distribution,
    }
