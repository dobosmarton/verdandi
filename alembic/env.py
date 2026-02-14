"""Alembic environment configuration for Verdandi.

Uses Verdandi's ORM Base as target metadata and SQLite with
render_as_batch=True for ALTER TABLE compatibility.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from verdandi.db.orm import Base

# Alembic Config object (provides access to alembic.ini values)
config = context.config

# Set up Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url", "sqlite:///data/verdandi.db")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to the database)."""
    from verdandi.db.engine import create_db_engine

    # Get URL from alembic.ini (can be overridden via -x or set_main_option)
    url = config.get_main_option("sqlalchemy.url", "sqlite:///data/verdandi.db")

    # Extract path from SQLite URL for our engine factory
    # sqlite:///relative/path or sqlite:////absolute/path
    db_path = url.replace("sqlite:///", "", 1)
    connectable = create_db_engine(db_path)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
