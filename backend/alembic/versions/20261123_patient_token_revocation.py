"""Store revocations for patient tokens until their original expiry."""
from alembic import context, op
import sqlalchemy as sa

revision = "20261123_patient_token_revoke"
down_revision = "20261123_mobile_otp_indexes"
branch_labels = None
depends_on = None


def upgrade():
    if context.is_offline_mode() or not sa.inspect(op.get_bind()).has_table("revoked_patient_tokens"):
        op.create_table(
            "revoked_patient_tokens",
            sa.Column("digest", sa.String(64), primary_key=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_revoked_patient_tokens_expires_at", "revoked_patient_tokens", ["expires_at"])


def downgrade():
    op.drop_table("revoked_patient_tokens")
