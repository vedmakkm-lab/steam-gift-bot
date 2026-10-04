"""Начальная схема БД

Revision ID: 0001
Revises:
Create Date: 2026-10-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("free_claim_used", sa.Boolean(), nullable=False),
        sa.Column("extra_claims", sa.Integer(), nullable=False),
        sa.Column("extra_claims_used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_issue_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "steam_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("games", sa.Text(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("issues_count", sa.Integer(), nullable=False),
        sa.Column("last_issue_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_steam_accounts_login", "steam_accounts", ["login"], unique=False)

    op.create_table(
        "issue_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("account_login", sa.String(length=255), nullable=True),
        sa.Column("issue_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["steam_accounts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issue_history_telegram_id", "issue_history", ["telegram_id"], unique=False)
    op.create_index("ix_issue_history_created_at", "issue_history", ["created_at"], unique=False)

    op.create_table(
        "promos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("reward_type", sa.String(length=32), nullable=False),
        sa.Column("reward_amount", sa.Integer(), nullable=False),
        sa.Column("max_activations", sa.Integer(), nullable=True),
        sa.Column("activations_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_promos_code", "promos", ["code"], unique=True)

    op.create_table(
        "promo_uses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("promo_id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["promo_id"], ["promos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("promo_id", "telegram_id", name="uq_promo_uses_promo_user"),
    )
    op.create_index("ix_promo_uses_telegram_id", "promo_uses", ["telegram_id"], unique=False)

    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("charge_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_telegram_id", "payments", ["telegram_id"], unique=False)
    op.create_index("ix_payments_charge_id", "payments", ["charge_id"], unique=True)

    op.create_table(
        "ads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("button_text", sa.String(length=64), nullable=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bot_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("bot_settings")
    op.drop_table("ads")
    op.drop_index("ix_payments_charge_id", table_name="payments")
    op.drop_index("ix_payments_telegram_id", table_name="payments")
    op.drop_table("payments")
    op.drop_table("channels")
    op.drop_index("ix_promo_uses_telegram_id", table_name="promo_uses")
    op.drop_table("promo_uses")
    op.drop_index("ix_promos_code", table_name="promos")
    op.drop_table("promos")
    op.drop_index("ix_issue_history_created_at", table_name="issue_history")
    op.drop_index("ix_issue_history_telegram_id", table_name="issue_history")
    op.drop_table("issue_history")
    op.drop_index("ix_steam_accounts_login", table_name="steam_accounts")
    op.drop_table("steam_accounts")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
