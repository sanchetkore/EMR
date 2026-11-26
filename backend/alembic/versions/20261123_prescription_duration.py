"""Store the prescribed duration in days for each medicine."""
from alembic import op
import sqlalchemy as sa

revision = "20261123_prescription_duration"
down_revision = "20261118_mobile_patient_links"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("prescription_items", sa.Column("duration_days", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("prescription_items", "duration_days")
