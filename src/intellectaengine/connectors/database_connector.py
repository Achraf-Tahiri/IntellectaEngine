"""Headless SQLite validation and schema discovery using the execution policy."""

import logging

from intellectaengine.core.sql_policy import SAMPLE_DB, SQLitePolicy

logger = logging.getLogger(__name__)


class DatabaseConnector:
    @classmethod
    def validate_uri(cls, db_uri: str) -> tuple[bool, str]:
        try:
            tables = cls.get_table_names(db_uri)
            return True, f"✅ Connection successful ({len(tables)} tables found)."
        except Exception:
            logger.warning("Database connection validation failed")
            return (
                False,
                "⚠️ Database connection failed. Use the sample or an approved existing SQLite file.",
            )

    @staticmethod
    def get_table_names(db_uri: str) -> list[str]:
        # Errors propagate: an empty inventory must mean a valid empty database.
        return sorted(SQLitePolicy().schema(db_uri))

    @staticmethod
    def get_schema_summary(db_uri: str) -> str:
        return (
            ";\n".join(SQLitePolicy().schema(db_uri).values()) or "No tables found in the database."
        )

    @staticmethod
    def is_sample_db(db_uri: str) -> bool:
        return db_uri.strip() == SAMPLE_DB
