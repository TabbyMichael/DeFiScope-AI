"""chat_chunks: ask-the-analyst RAG index (roadmap #8)

Creates the ``chat_chunks`` table that backs the grounded chat. The embedding
column is dialect-aware: pgvector's native ``Vector`` type on PostgreSQL (with
the extension enabled), plain ``JSON`` on SQLite so dev/tests need no pgvector.

Revision ID: a1c7e9b204f8
Revises: 7b3c9d21e4f0
Create Date: 2026-10-30 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.config import get_settings

# revision identifiers, used by Alembic.
revision: str = "a1c7e9b204f8"
down_revision: str | None = "7b3c9d21e4f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "chat_chunks"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        embedding = _pg_vector_type()
    else:
        embedding = sa.JSON()

    op.create_table(
        _TABLE,
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("doc_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("source_name", sa.String(), nullable=True),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("protocol_slug", sa.String(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("embedding", embedding, nullable=True),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index(op.f("ix_chat_chunks_doc_id"), _TABLE, ["doc_id"], unique=False)
    op.create_index(op.f("ix_chat_chunks_protocol_slug"), _TABLE, ["protocol_slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_chunks_protocol_slug"), table_name=_TABLE)
    op.drop_index(op.f("ix_chat_chunks_doc_id"), table_name=_TABLE)
    op.drop_table(_TABLE)


def _pg_vector_type():  # pragma: no cover - Postgres-only path
    from pgvector.sqlalchemy import Vector

    return Vector(get_settings().embedding_dimensions)
