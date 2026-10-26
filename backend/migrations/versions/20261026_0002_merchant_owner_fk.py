"""Ensure owned merchants reference their account.

Revision ID: 20261026_0002
Revises: 20261026_0001
"""
import sqlalchemy as sa
from alembic import op


revision = "20261026_0002"
down_revision = "20261026_0001"
branch_labels = None
depends_on = None


def upgrade():
    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys("merchants")
    }
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
    with op.batch_alter_table("merchants") as batch:
        batch.drop_constraint("fk_merchants_owner_user_id_user_accounts", type_="foreignkey")
