"""Persist onboarding answers and sales tracking preference.

Revision ID: 20261026_0003
Revises: 20261026_0002
"""
import sqlalchemy as sa
from alembic import op


revision = "20261026_0003"
down_revision = "20261026_0002"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("merchants")}
    if "sales_tracking" not in columns:
        op.add_column("merchants", sa.Column("sales_tracking", sa.String(length=20), nullable=True))
    if "onboarding_answers" not in columns:
        op.add_column(
            "merchants",
            sa.Column("onboarding_answers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("merchants")}
    if "onboarding_answers" in columns:
        op.drop_column("merchants", "onboarding_answers")
    if "sales_tracking" in columns:
        op.drop_column("merchants", "sales_tracking")
