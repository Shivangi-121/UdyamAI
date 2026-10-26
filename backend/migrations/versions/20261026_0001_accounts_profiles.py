"""Add account authentication and merchant preferences.

Revision ID: 20261026_0001
Revises: 0002_proactive
"""
from alembic import op
import sqlalchemy as sa


revision = "20261026_0001"
down_revision = "0002_proactive"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "user_accounts" not in tables:
        op.create_table(
            "user_accounts",
            sa.Column("id", sa.String(length=80), primary_key=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("full_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("password_hash", sa.String(length=512), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "auth_sessions" not in tables:
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.String(length=80), primary_key=True),
            sa.Column("user_id", sa.String(length=80), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "password_reset_tokens" not in tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.String(length=80), primary_key=True),
            sa.Column("user_id", sa.String(length=80), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    for table, name, columns, unique in (
        ("user_accounts", "ix_user_accounts_email", ["email"], True),
        ("auth_sessions", "ix_auth_sessions_user_id", ["user_id"], False),
        ("auth_sessions", "ix_auth_sessions_refresh_token_hash", ["refresh_token_hash"], True),
        ("auth_sessions", "ix_auth_sessions_expires_at", ["expires_at"], False),
        ("password_reset_tokens", "ix_password_reset_tokens_user_id", ["user_id"], False),
        ("password_reset_tokens", "ix_password_reset_tokens_token_hash", ["token_hash"], True),
        ("password_reset_tokens", "ix_password_reset_tokens_expires_at", ["expires_at"], False),
    ):
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
        if name not in indexes:
            op.create_index(name, table, columns, unique=unique)

    merchant_columns = [
        sa.Column("owner_user_id", sa.String(length=80), nullable=True),
        sa.Column("business_model", sa.String(length=20), nullable=True),
        sa.Column("sales_channels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("business_stage", sa.String(length=30), nullable=True),
        sa.Column("sales_tracking", sa.String(length=20), nullable=True),
        sa.Column("business_size", sa.String(length=30), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("business_location", sa.String(length=120), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("preferred_language", sa.String(length=20), nullable=False, server_default="en"),
        sa.Column("response_detail", sa.String(length=20), nullable=False, server_default="balanced"),
        sa.Column("interaction_mode", sa.String(length=20), nullable=False, server_default="both"),
        sa.Column("theme", sa.String(length=20), nullable=False, server_default="system"),
        sa.Column("notifications", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("onboarding_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("onboarding_answers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]
    existing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("merchants")}
    missing_columns = [column for column in merchant_columns if column.name not in existing_columns]
    if missing_columns:
        with op.batch_alter_table("merchants") as batch:
            for column in missing_columns:
                batch.add_column(column)
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("merchants")}
    if "uq_merchants_owner_user_id" not in indexes:
        op.create_index("uq_merchants_owner_user_id", "merchants", ["owner_user_id"], unique=True)
    foreign_keys = {foreign_key.get("name") for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys("merchants")}
    if "fk_merchants_owner_user_id_user_accounts" not in foreign_keys:
        with op.batch_alter_table("merchants") as batch:
            batch.create_foreign_key(
                "fk_merchants_owner_user_id_user_accounts",
                "user_accounts",
                ["owner_user_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade():
    op.drop_index("uq_merchants_owner_user_id", table_name="merchants")
    for name in (
        "onboarding_completed",
        "onboarding_answers",
        "onboarding_step",
        "notifications",
        "theme",
        "interaction_mode",
        "response_detail",
        "preferred_language",
        "goals",
        "business_size",
        "business_stage",
        "sales_tracking",
        "business_location",
        "currency",
        "sales_channels",
        "business_model",
        "owner_user_id",
    ):
        op.drop_column("merchants", name)
    op.drop_index("ix_password_reset_tokens_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token_hash", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_refresh_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_user_accounts_email", table_name="user_accounts")
    op.drop_table("user_accounts")
