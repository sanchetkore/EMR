"""Index mobile OTP windows and normalized patient phone lookups."""
from alembic import op
import sqlalchemy as sa

revision = "20261123_mobile_otp_indexes"
down_revision = "20261123_prescription_duration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_mobile_otps_phone_created", "mobile_otps", ["phone_number", "created_at"])
    op.create_index(
        "ix_mobile_otps_unused_phone_id",
        "mobile_otps",
        ["phone_number", "id"],
        postgresql_where=sa.text("is_used IS FALSE"),
        sqlite_where=sa.text("is_used IS 0"),
    )
    op.create_index(
        "ix_patients_normalized_phone",
        "patients",
        [sa.text("replace(replace(replace(replace(replace(contact_number, ' ', ''), '-', ''), '+', ''), '(', ''), ')', '')")],
    )


def downgrade():
    op.drop_index("ix_patients_normalized_phone", table_name="patients")
    op.drop_index("ix_mobile_otps_unused_phone_id", table_name="mobile_otps")
    op.drop_index("ix_mobile_otps_phone_created", table_name="mobile_otps")
