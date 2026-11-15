"""Database connection helpers and schema creation."""
import logging
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.config import DB_URL

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def get_engine() -> Engine:
    """Create and return a SQLAlchemy engine for the configured database."""
    return create_engine(DB_URL, pool_pre_ping=True, future=True)


def _split_statements(sql_text: str) -> list[str]:
    """Split a SQL script into individual statements, dropping comments."""
    lines = [ln for ln in sql_text.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def create_schema(engine: Engine) -> None:
    """Run sql/schema.sql against the database (idempotent for tables)."""
    statements = _split_statements(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        with engine.begin() as conn:
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                except SQLAlchemyError as exc:
                    # CREATE INDEX has no IF NOT EXISTS in MySQL; ignore duplicates
                    if "Duplicate key name" in str(exc):
                        logger.info("Index already exists, skipping.")
                    else:
                        raise
        logger.info("Schema created successfully.")
    except SQLAlchemyError:
        logger.exception("Failed to create schema")
        raise

def run_query(engine: Engine, sql: str, params: dict | None = None):
    """Run a read-only SQL query and return a pandas DataFrame."""
    import pandas as pd
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except SQLAlchemyError:
        logger.exception("Query failed")
        raise

    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    eng = get_engine()
    create_schema(eng)
    with eng.connect() as connection:
        tables = connection.execute(text("SHOW TABLES")).fetchall()
        print("Tables:", [t[0] for t in tables])

