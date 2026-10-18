"""store participant gender for demographic child grouping

Revision ID: 0003_participant_gender
Revises: 0002_weights_and_bouts
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_participant_gender"
down_revision = "0002_weights_and_bouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    participant_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("participants")
    }
    if "gender" not in participant_columns:
        op.add_column(
            "participants", sa.Column("gender", sa.String(length=16), nullable=True)
        )


def downgrade() -> None:
    participant_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("participants")
    }
    if "gender" in participant_columns:
        op.drop_column("participants", "gender")
