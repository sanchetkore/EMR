"""Remember patient profiles verified for a phone number."""
from alembic import op
import sqlalchemy as sa

revision = "20261118_mobile_patient_links"
down_revision = "20261117_patient_release"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("mobile_patient_links",
                    sa.Column("phone", sa.String(32), primary_key=True),
                    sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), primary_key=True))


def downgrade():
    op.drop_table("mobile_patient_links")
