"""add scraper provenance fields to ratings

Revision ID: 001
Revises:
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ratings", sa.Column("citing_author", sa.String(255), nullable=True))
    op.add_column("ratings", sa.Column("is_multi_target", sa.Boolean(), nullable=False,
                                       server_default="false"))
    op.add_column("ratings", sa.Column("source_doi", sa.String(255), nullable=True))
    op.add_column("ratings", sa.Column("source_url", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("ratings", "source_url")
    op.drop_column("ratings", "source_doi")
    op.drop_column("ratings", "is_multi_target")
    op.drop_column("ratings", "citing_author")
