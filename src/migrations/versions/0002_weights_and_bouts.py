"""store measured weights and online bout results

Revision ID: 0002_weights_and_bouts
Revises: 0001_initial
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_weights_and_bouts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    participant_columns = {column["name"] for column in inspector.get_columns("participants")}
    if "actual_weight" not in participant_columns:
        op.add_column(
            "participants", sa.Column("actual_weight", sa.Numeric(6, 2), nullable=True)
        )

    weight_columns = {column["name"] for column in inspector.get_columns("weight_categories")}
    if "is_auto_grouped" not in weight_columns:
        op.add_column(
            "weight_categories",
            sa.Column("is_auto_grouped", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "needs_review" not in weight_columns:
        op.add_column(
            "weight_categories",
            sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if "bouts" not in inspector.get_table_names():
        op.create_table(
            "bouts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("round_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("stage", sa.String(length=32), nullable=False),
            sa.Column("group_name", sa.String(length=16), nullable=True),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("source_a", sa.String(length=64), nullable=True),
            sa.Column("source_b", sa.String(length=64), nullable=True),
            sa.Column("player_a_id", sa.Integer(), nullable=True),
            sa.Column("player_b_id", sa.Integer(), nullable=True),
            sa.Column("winner_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["player_a_id"], ["participants.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["player_b_id"], ["participants.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["winner_id"], ["participants.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("round_id", "key", name="uq_bout_round_key"),
        )
        op.create_index(op.f("ix_bouts_round_id"), "bouts", ["round_id"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "bouts" in inspector.get_table_names():
        op.drop_index(op.f("ix_bouts_round_id"), table_name="bouts")
        op.drop_table("bouts")
    weight_columns = {column["name"] for column in inspector.get_columns("weight_categories")}
    if "needs_review" in weight_columns:
        op.drop_column("weight_categories", "needs_review")
    if "is_auto_grouped" in weight_columns:
        op.drop_column("weight_categories", "is_auto_grouped")
    participant_columns = {column["name"] for column in inspector.get_columns("participants")}
    if "actual_weight" in participant_columns:
        op.drop_column("participants", "actual_weight")
