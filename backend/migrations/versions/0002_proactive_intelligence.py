"""Add proactive insights, outcome tracking, and supplier lead times.

Revision ID: 0002_proactive
Revises: 0001_initial
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_proactive"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    if "supplier_lead_time_days" not in product_columns:
        op.add_column("products", sa.Column("supplier_lead_time_days", sa.Integer(), nullable=True))
    tables = set(inspector.get_table_names())
    if "business_insights" not in tables:
        op.create_table(
            "business_insights",
            sa.Column("id", sa.String(length=80), primary_key=True),
            sa.Column("merchant_id", sa.String(length=80), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fingerprint", sa.String(length=180), nullable=False),
            sa.Column("kind", sa.String(length=60), nullable=False),
            sa.Column("entity_id", sa.String(length=80), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("headline", sa.String(length=180), nullable=False),
            sa.Column("observed", sa.Text(), nullable=False),
            sa.Column("evidence", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("comparison_period", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("why_it_matters", sa.Text(), nullable=False),
            sa.Column("next_action", sa.String(length=250), nullable=False),
            sa.Column("confidence", sa.String(length=30), nullable=False),
            sa.Column("data_quality", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="unread"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("merchant_id", "fingerprint", name="uq_insight_merchant_fingerprint"),
        )
    insight_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("business_insights")}
    if "entity_id" not in insight_columns:
        op.add_column("business_insights", sa.Column("entity_id", sa.String(length=80), nullable=True))
    if "is_active" not in insight_columns:
        op.add_column("business_insights", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("business_insights")}
    if "ix_business_insights_merchant_id" not in indexes:
        op.create_index("ix_business_insights_merchant_id", "business_insights", ["merchant_id"])
    if "recommendation_outcomes" not in tables:
        op.create_table(
            "recommendation_outcomes",
            sa.Column("id", sa.String(length=80), primary_key=True),
            sa.Column("merchant_id", sa.String(length=80), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("insight_id", sa.String(length=80), sa.ForeignKey("business_insights.id", ondelete="SET NULL"), nullable=True),
            sa.Column("recommendation", sa.String(length=250), nullable=False),
            sa.Column("assumptions", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("selected_action", sa.String(length=500), nullable=False),
            sa.Column("baseline", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("observation_start", sa.Date(), nullable=False),
            sa.Column("observation_end", sa.Date(), nullable=True),
            sa.Column("actual_outcome", sa.Text(), nullable=True),
            sa.Column("fairly_comparable", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("recommendation_outcomes")}
    if "ix_recommendation_outcomes_merchant_id" not in indexes:
        op.create_index("ix_recommendation_outcomes_merchant_id", "recommendation_outcomes", ["merchant_id"])


def downgrade():
    op.drop_index("ix_recommendation_outcomes_merchant_id", table_name="recommendation_outcomes")
    op.drop_table("recommendation_outcomes")
    op.drop_index("ix_business_insights_merchant_id", table_name="business_insights")
    op.drop_table("business_insights")
    op.drop_column("products", "supplier_lead_time_days")
