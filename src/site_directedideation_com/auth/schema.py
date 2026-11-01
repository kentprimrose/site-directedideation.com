"""Initial authentication schema. Apply explicitly during provisioning."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()
accounts = Table(
    "auth_accounts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(254), nullable=False),
    Column("verified", Boolean, nullable=False, default=False),
    Column("password_hash", String(255)),
    UniqueConstraint("email", name="uq_auth_email"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)
tokens = Table(
    "auth_tokens",
    metadata,
    Column("digest", String(64), primary_key=True),
    Column(
        "account_id",
        Integer,
        ForeignKey("auth_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("purpose", String(16), nullable=False),
    Column("expires_at", BigInteger, nullable=False),
    Column("consumed_at", BigInteger),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)


def upgrade(engine):
    """Apply the initial schema to an empty database; use managed migrations later."""
    metadata.create_all(engine)
