"""Add idempotency keys for imported sales and expenses.

Revision ID: 20261026_0004
Revises: 20261026_0003
"""
from alembic import op
import sqlalchemy as sa


revision = "20261026_0004"
down_revision = "20261026_0003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for name, table in (
        ("ix_sales_merchant_date", "sales"),
        ("ix_expenses_merchant_date", "expenses"),
    ):
        indexes = {index["name"] for index in inspector.get_indexes(table)}
        if name not in indexes:
            op.create_index(name, table, ["merchant_id", "date"])
    for table, constraint in (
        ("sales", "uq_sales_merchant_import_fingerprint"),
        ("expenses", "uq_expenses_merchant_import_fingerprint"),
    ):
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        unique_constraints = {
            item.get("name")
            for item in sa.inspect(op.get_bind()).get_unique_constraints(table)
        }
        if "import_fingerprint" not in columns or constraint not in unique_constraints:
            with op.batch_alter_table(table) as batch:
                if "import_fingerprint" not in columns:
                    batch.add_column(sa.Column("import_fingerprint", sa.String(length=64), nullable=True))
                if constraint not in unique_constraints:
                    batch.create_unique_constraint(constraint, ["merchant_id", "import_fingerprint"])


def downgrade():
    for table, constraint in (
        ("expenses", "uq_expenses_merchant_import_fingerprint"),
        ("sales", "uq_sales_merchant_import_fingerprint"),
    ):
        inspector = sa.inspect(op.get_bind())
        columns = {column["name"] for column in inspector.get_columns(table)}
        constraints = {item.get("name") for item in inspector.get_unique_constraints(table)}
        if "import_fingerprint" in columns or constraint in constraints:
            with op.batch_alter_table(table) as batch:
                if constraint in constraints:
                    batch.drop_constraint(constraint, type_="unique")
                if "import_fingerprint" in columns:
                    batch.drop_column("import_fingerprint")
    for name, table in (
        ("ix_expenses_merchant_date", "expenses"),
        ("ix_sales_merchant_date", "sales"),
    ):
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
        if name in indexes:
            op.drop_index(name, table_name=table)
