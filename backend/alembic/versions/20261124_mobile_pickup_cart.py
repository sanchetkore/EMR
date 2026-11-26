"""Store reusable home pickup combos and allow multi-test bookings."""
from alembic import op
import sqlalchemy as sa

revision = "20261124_mobile_pickup_cart"
down_revision = "20261123_patient_token_revoke"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mobile_pickup_combos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("test_codes", sa.JSON(), nullable=False),
    )
    op.create_index("ix_mobile_pickup_combos_patient_id", "mobile_pickup_combos", ["patient_id"])
    with op.batch_alter_table("mobile_blood_pickups") as batch:
        batch.alter_column("test_codes", existing_type=sa.String(255), type_=sa.Text())


def downgrade():
    # Keep the widened column so multi-test bookings remain readable.
    op.drop_table("mobile_pickup_combos")
