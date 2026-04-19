from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from api.database import CURRENT_SCHEMA_TABLES
from api.database import DBConnection
from api.database import build_connection
from api.database import get_database_backend
from api.database import initialize_database


TABLE_COPY_ORDER = [
    "admins",
    "subjects",
    "chapters",
    "topics",
    "concepts",
    "students",
    "textbook_documents",
    "extraction_runs",
    "extracted_assets",
    "ai_import_batches",
    "ai_import_batch_questions",
    "question_items",
    "question_revisions",
    "question_revision_options",
    "question_revision_numeric_answers",
    "question_revision_match_sets",
    "question_revision_match_left_items",
    "question_revision_match_right_items",
    "question_revision_figures",
    "tests",
    "test_question_revisions",
    "batches",
    "batch_students",
    "assignments",
    "attempts",
    "attempt_answers",
    "admin_activity_logs",
]


def build_sqlite_source_connection(source_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(source_path)
    connection.row_factory = sqlite3.Row
    return connection


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def copy_table(source_connection: sqlite3.Connection, target_connection: DBConnection, table_name: str) -> None:
    column_rows = source_connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not column_rows:
        return
    column_names = [str(row["name"]) for row in column_rows]
    quoted_columns = ", ".join(quote_identifier(name) for name in column_names)
    placeholders = ", ".join("?" for _ in column_names)
    rows = source_connection.execute(f"SELECT {quoted_columns} FROM {quote_identifier(table_name)}").fetchall()
    for row in rows:
        target_connection.execute(
            f"INSERT INTO {quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})",
            tuple(row[column_name] for column_name in column_names),
        )


def main() -> None:
    source_path_text = os.environ.get("SOURCE_SQLITE_PATH", "").strip()
    if not source_path_text:
        raise SystemExit("Set SOURCE_SQLITE_PATH to the existing SQLite file.")
    source_path = Path(source_path_text)
    if not source_path.exists():
        raise SystemExit(f"SQLite file not found: {source_path}")
    if get_database_backend() != "postgres":
        raise SystemExit("Set DATABASE_URL to the target Postgres database before running this migration.")

    initialize_database()
    with build_sqlite_source_connection(source_path) as source_connection:
        with build_connection() as target_connection:
            for table_name in TABLE_COPY_ORDER:
                if table_name not in CURRENT_SCHEMA_TABLES:
                    continue
                copy_table(source_connection, target_connection, table_name)
    print("SQLite to Postgres migration complete.")


if __name__ == "__main__":
    main()
