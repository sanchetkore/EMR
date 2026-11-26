"""Create patient mobile tables and retain appointment reasons.

Existing installations may already have mobile tables from initial setup.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261117_patient_release'
down_revision = '0bc173deee7b'
branch_labels = None
depends_on = None


def upgrade():
    from app.models.mobile import (
        MobileDeviceToken, MobileOtp, MobileBloodPickup,
        MobilePatientAlert, MobilePaymentRecord,
    )
    bind = op.get_bind()
    for model in (MobileDeviceToken, MobileOtp, MobileBloodPickup, MobilePatientAlert, MobilePaymentRecord):
        model.__table__.create(bind, checkfirst=True)
    columns = {column['name'] for column in sa.inspect(bind).get_columns('appointments')}
    if 'reason_for_visit' not in columns:
        op.add_column('appointments', sa.Column('reason_for_visit', sa.Text(), nullable=True))


def downgrade():
    # Patient records may predate this migration; retain them on rollback.
    # The additive appointment column is also safe for the previous application.
    pass
