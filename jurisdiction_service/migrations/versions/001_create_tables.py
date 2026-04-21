"""Create court_districts, users, geocoding_cache with PostGIS.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "court_districts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("court_code", sa.String(50), unique=True, nullable=False),
        sa.Column("court_name", sa.String(500), nullable=False),
        sa.Column("court_type", sa.String(50), nullable=False, server_default="мировой"),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("geometry", Geometry(geometry_type="POLYGON", srid=4326), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_court_districts_geometry", "court_districts", ["geometry"], postgresql_using="gist")
    op.create_index("ix_court_districts_court_code", "court_districts", ["court_code"])

    op.create_table(
        "geocoding_cache",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("address_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_geocoding_cache_address_hash", "geocoding_cache", ["address_hash"])

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("api_key", sa.String(100), unique=True, nullable=True),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_table("court_districts")
    op.drop_table("geocoding_cache")
    op.drop_table("users")
