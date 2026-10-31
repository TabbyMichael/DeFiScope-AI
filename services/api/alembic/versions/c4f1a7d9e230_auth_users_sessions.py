"""auth: users + auth_sessions (roadmap #17)

Adds the local identity tables that back authentication. Sessions store only the
SHA-256 of the opaque token, so a database leak cannot be replayed as a valid
credential; revocation is a DELETE rather than a token expiry wait.

Revision ID: c4f1a7d9e230
Revises: a1c7e9b204f8
Create Date: 2026-10-30 15:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f1a7d9e230"
down_revision: str | None = "a1c7e9b204f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USERS = "users"
_SESSIONS = "auth_sessions"


def upgrade() -> None:
    op.create_table(
        _USERS,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="viewer"),
        sa.Column("team", sa.String(), nullable=True),
        sa.Column("clearance", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("allowed_categories", sa.JSON(), nullable=True),
        sa.Column("allowed_chains", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), _USERS, ["email"], unique=True)

    op.create_table(
        _SESSIONS,
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), _SESSIONS, ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name=_SESSIONS)
    op.drop_table(_SESSIONS)
    op.drop_index(op.f("ix_users_email"), table_name=_USERS)
    op.drop_table(_USERS)
