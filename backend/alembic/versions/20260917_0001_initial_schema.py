"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS = {
    "user_role": ("user", "moderator", "admin"),
    "auth_provider": ("email", "google"),
    "ticket_status": ("open", "pending_review", "assigned", "in_progress", "resolved", "closed"),
    "ticket_priority": ("low", "medium", "high", "urgent"),
    "otp_purpose": ("registration", "password_reset"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _ts(name: str, nullable: bool = False, default: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if default else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("role", _enum("user_role"), nullable=False),
        sa.Column("auth_provider", _enum("auth_provider"), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    # --- moderator_skills ---
    op.create_table(
        "moderator_skills",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("skill", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_moderator_skills_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_moderator_skills"),
        sa.UniqueConstraint("user_id", "skill", name="uq_moderator_skills_user_skill"),
    )
    op.create_index("ix_moderator_skills_user_id", "moderator_skills", ["user_id"])
    op.create_index("ix_moderator_skills_skill", "moderator_skills", ["skill"])

    # --- tickets ---
    op.create_table(
        "tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", _enum("ticket_status"), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("priority", _enum("ticket_priority"), nullable=True),
        sa.Column(
            "required_skills",
            postgresql.ARRAY(sa.String(64)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("ai_notes", sa.Text(), nullable=True),
        sa.Column("ai_model_used", sa.String(64), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("assigned_at", nullable=True, default=False),
        _ts("resolved_at", nullable=True, default=False),
        _ts("closed_at", nullable=True, default=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_tickets_created_by_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name="fk_tickets_assignee_id_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tickets"),
    )
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_created_by_id", "tickets", ["created_by_id"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_assignee_status", "tickets", ["assignee_id", "status"])
    op.create_index("ix_tickets_created_by_created_at", "tickets", ["created_by_id", "created_at"])
    op.create_index(
        "ix_tickets_title_trgm",
        "tickets",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    # --- ticket_comments ---
    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name="fk_ticket_comments_ticket_id_tickets",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_ticket_comments_author_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_comments"),
    )
    op.create_index("ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"])

    # --- otp_codes ---
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("purpose", _enum("otp_purpose"), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        _ts("expires_at", default=False),
        _ts("consumed_at", nullable=True, default=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_otp_codes"),
    )
    op.create_index(
        "ix_otp_codes_email_purpose_created_at", "otp_codes", ["email", "purpose", "created_at"]
    )

    # --- refresh_tokens ---
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        _ts("expires_at", default=False),
        _ts("revoked_at", nullable=True, default=False),
        sa.Column("replaced_by_id", sa.UUID(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name="fk_refresh_tokens_replaced_by_id_refresh_tokens",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # --- model_quota_state ---
    op.create_table(
        "model_quota_state",
        sa.Column("model_name", sa.String(64), nullable=False),
        _ts("exhausted_until", nullable=True, default=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("model_name", name="pk_model_quota_state"),
    )

    # --- sent_emails ---
    op.create_table(
        "sent_emails",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("template", sa.String(64), nullable=False),
        _ts("sent_at"),
        sa.PrimaryKeyConstraint("id", name="pk_sent_emails"),
        sa.UniqueConstraint("idempotency_key", name="uq_sent_emails_idempotency_key"),
    )
    op.create_index("ix_sent_emails_recipient", "sent_emails", ["recipient"])


def downgrade() -> None:
    for table in (
        "sent_emails",
        "model_quota_state",
        "refresh_tokens",
        "otp_codes",
        "ticket_comments",
        "tickets",
        "moderator_skills",
        "users",
    ):
        op.drop_table(table)

    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
