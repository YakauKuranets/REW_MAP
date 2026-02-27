from __future__ import annotations
import os, sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

config = context.config
db_uri = os.environ.get("DATABASE_URI") or os.environ.get("DATABASE_URL")
if db_uri:
    config.set_main_option("sqlalchemy.url", db_uri)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

def _get_target_metadata():
    global target_metadata
    if target_metadata is not None:
        return target_metadata
    from app import create_app
    from app.extensions import db
    app = create_app()
    with app.app_context():
        target_metadata = db.metadata
    return target_metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=_get_target_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=_get_target_metadata(),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
