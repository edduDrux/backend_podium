"""add pgvector extension and vector embedding column

Revision ID: a1b2c3d4e5f6
Revises: 6bc9dfb22dd5
Create Date: 2026-04-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6bc9dfb22dd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable pgvector, convert embedding column to vector, add ivfflat index."""
    # 1. Habilita a extensão pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Remove a coluna embedding JSON antiga
    op.drop_column("document_chunks", "embedding")

    # 3. Adiciona a coluna embedding como vector(1536)
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN embedding vector(1536)"
    )

    # 4. Cria índice ivfflat para busca por cosine distance
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    """Reverte para coluna embedding JSON."""
    op.drop_index("ix_document_chunks_embedding", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding")
    op.add_column(
        "document_chunks", sa.Column("embedding", sa.JSON(), nullable=True)
    )
    op.execute("DROP EXTENSION IF EXISTS vector")
