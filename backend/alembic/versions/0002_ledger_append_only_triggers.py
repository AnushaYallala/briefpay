"""ledger_entries append-only database triggers (GAP-08)

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger_entries "
            "BEGIN SELECT RAISE(ABORT, 'ledger_entries is append-only'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger_entries "
            "BEGIN SELECT RAISE(ABORT, 'ledger_entries is append-only'); END"
        )
    elif dialect == "postgresql":
        op.execute(
            "CREATE OR REPLACE FUNCTION forbid_ledger_mutation() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'ledger_entries is append-only'; END; $$ LANGUAGE plpgsql"
        )
        op.execute("DROP TRIGGER IF EXISTS ledger_no_update ON ledger_entries")
        op.execute(
            "CREATE TRIGGER ledger_no_update BEFORE UPDATE ON ledger_entries "
            "FOR EACH ROW EXECUTE FUNCTION forbid_ledger_mutation()"
        )
        op.execute("DROP TRIGGER IF EXISTS ledger_no_delete ON ledger_entries")
        op.execute(
            "CREATE TRIGGER ledger_no_delete BEFORE DELETE ON ledger_entries "
            "FOR EACH ROW EXECUTE FUNCTION forbid_ledger_mutation()"
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS ledger_no_update")
        op.execute("DROP TRIGGER IF EXISTS ledger_no_delete")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS ledger_no_update ON ledger_entries")
        op.execute("DROP TRIGGER IF EXISTS ledger_no_delete ON ledger_entries")
        op.execute("DROP FUNCTION IF EXISTS forbid_ledger_mutation()")
