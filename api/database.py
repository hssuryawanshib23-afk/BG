from __future__ import annotations

import json
import os
import sqlite3
import shutil
import uuid
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
DATABASE_DIRECTORY = PROJECT_DIRECTORY / "data"
DATABASE_PATH = Path(os.environ.get("BRAINGAIN_DATABASE_PATH", str(DATABASE_DIRECTORY / "braingain.sqlite3")))
CURRENT_SCHEMA_TABLES = {
    "admins",
    "subjects",
    "chapters",
    "topics",
    "concepts",
    "ai_import_batches",
    "ai_import_batch_questions",
    "question_items",
    "question_revisions",
    "question_revision_options",
    "question_revision_numeric_answers",
    "question_revision_match_sets",
    "question_revision_match_left_items",
    "question_revision_match_right_items",
    "tests",
    "test_question_revisions",
    "attempts",
    "attempt_answers",
}
LEGACY_SCHEMA_TABLES = {
    "question_bank_imports",
    "questions",
    "question_options",
    "test_questions",
    "attempt_answer_options",
}


def build_connection() -> sqlite3.Connection:
    DATABASE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def build_identifier() -> str:
    return str(uuid.uuid4())


def build_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def build_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def parse_json_text(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        return value
    return json.loads(value)


def convert_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def convert_rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [convert_row_to_dict(row) or {} for row in rows]


def insert_admin_activity_log(
    connection: sqlite3.Connection,
    admin_id: str,
    action_type: str,
    entity_type: str,
    entity_id: str | None,
    summary: str,
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO admin_activity_logs (
            id, admin_id, action_type, entity_type, entity_id, summary, details, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            build_identifier(),
            admin_id,
            action_type,
            entity_type,
            entity_id,
            summary,
            build_json_text(details) if details is not None else None,
            build_timestamp(),
        ),
    )


def list_existing_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def rollover_legacy_database_if_needed() -> None:
    if not DATABASE_PATH.exists():
        return
    with build_connection() as connection:
        existing_tables = list_existing_tables(connection)
    if not existing_tables or CURRENT_SCHEMA_TABLES.issubset(existing_tables):
        return
    if not (existing_tables & LEGACY_SCHEMA_TABLES):
        return
    backup_name = f"{DATABASE_PATH.stem}.legacy-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}{DATABASE_PATH.suffix}"
    backup_path = DATABASE_PATH.with_name(backup_name)
    shutil.move(str(DATABASE_PATH), str(backup_path))


def initialize_database() -> None:
    rollover_legacy_database_if_needed()
    with build_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subjects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                grade INTEGER NOT NULL,
                board TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, grade, board)
            );

            CREATE TABLE IF NOT EXISTS chapters (
                id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                chapter_number INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(subject_id, chapter_number),
                UNIQUE(subject_id, name)
            );

            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(chapter_id, name),
                UNIQUE(chapter_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS concepts (
                id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                source_concept_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(topic_id, name),
                UNIQUE(topic_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS textbook_documents (
                id TEXT PRIMARY KEY,
                chapter_id TEXT REFERENCES chapters(id) ON DELETE SET NULL,
                source_file_name TEXT NOT NULL,
                source_file_path TEXT NOT NULL,
                uploaded_by_admin_id TEXT NOT NULL REFERENCES admins(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS extraction_runs (
                id TEXT PRIMARY KEY,
                textbook_document_id TEXT NOT NULL REFERENCES textbook_documents(id) ON DELETE CASCADE,
                manifest_file_path TEXT NOT NULL,
                figure_review_manifest_file_path TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS extracted_assets (
                id TEXT PRIMARY KEY,
                extraction_run_id TEXT NOT NULL REFERENCES extraction_runs(id) ON DELETE CASCADE,
                chapter_id TEXT REFERENCES chapters(id) ON DELETE SET NULL,
                asset_type TEXT NOT NULL,
                page_number INTEGER,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                caption_text TEXT,
                bounding_box TEXT,
                text_density REAL,
                non_text_density REAL,
                review_status TEXT,
                reviewed_by_admin_id TEXT REFERENCES admins(id),
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_import_batches (
                id TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                source_file_path TEXT NOT NULL,
                uploaded_by_admin_id TEXT NOT NULL REFERENCES admins(id),
                subject_id TEXT REFERENCES subjects(id) ON DELETE SET NULL,
                chapter_id TEXT REFERENCES chapters(id) ON DELETE SET NULL,
                topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
                status TEXT NOT NULL,
                validation_summary TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                normalized_payload TEXT,
                materialized_question_count INTEGER NOT NULL DEFAULT 0,
                published_question_count INTEGER NOT NULL DEFAULT 0,
                approved_by_admin_id TEXT REFERENCES admins(id),
                approved_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_import_batch_questions (
                id TEXT PRIMARY KEY,
                ai_import_batch_id TEXT NOT NULL REFERENCES ai_import_batches(id) ON DELETE CASCADE,
                source_question_id TEXT,
                concept_name TEXT,
                question_text_preview TEXT NOT NULL,
                format TEXT,
                validation_status TEXT NOT NULL,
                validation_errors TEXT,
                question_item_id TEXT,
                question_revision_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS question_items (
                id TEXT PRIMARY KEY,
                concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                source_question_id TEXT,
                origin_type TEXT NOT NULL,
                ai_import_batch_id TEXT REFERENCES ai_import_batches(id) ON DELETE SET NULL,
                created_by_admin_id TEXT NOT NULL REFERENCES admins(id),
                current_draft_revision_id TEXT,
                current_published_revision_id TEXT,
                lifecycle_status TEXT NOT NULL DEFAULT 'draft',
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(concept_id, source_question_id)
            );

            CREATE TABLE IF NOT EXISTS question_revisions (
                id TEXT PRIMARY KEY,
                question_item_id TEXT NOT NULL REFERENCES question_items(id) ON DELETE CASCADE,
                revision_number INTEGER NOT NULL,
                parent_revision_id TEXT REFERENCES question_revisions(id) ON DELETE SET NULL,
                created_by_admin_id TEXT NOT NULL REFERENCES admins(id),
                format TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                type TEXT NOT NULL,
                text TEXT NOT NULL,
                explanation TEXT,
                image_asset_id TEXT REFERENCES extracted_assets(id) ON DELETE SET NULL,
                answer_type TEXT NOT NULL,
                answer_payload TEXT NOT NULL,
                scoring_payload TEXT NOT NULL,
                revision_status TEXT NOT NULL,
                published_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(question_item_id, revision_number)
            );

            CREATE TABLE IF NOT EXISTS question_revision_options (
                id TEXT PRIMARY KEY,
                question_revision_id TEXT NOT NULL REFERENCES question_revisions(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                text TEXT NOT NULL,
                is_correct INTEGER NOT NULL DEFAULT 0,
                display_order INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(question_revision_id, label),
                UNIQUE(question_revision_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS question_revision_numeric_answers (
                id TEXT PRIMARY KEY,
                question_revision_id TEXT NOT NULL UNIQUE REFERENCES question_revisions(id) ON DELETE CASCADE,
                exact_value REAL NOT NULL,
                tolerance REAL NOT NULL,
                unit TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS question_revision_match_sets (
                id TEXT PRIMARY KEY,
                question_revision_id TEXT NOT NULL UNIQUE REFERENCES question_revisions(id) ON DELETE CASCADE,
                a_heading TEXT NOT NULL,
                b_heading TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS question_revision_match_left_items (
                id TEXT PRIMARY KEY,
                match_set_id TEXT NOT NULL REFERENCES question_revision_match_sets(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                text TEXT NOT NULL,
                matches_right_label TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(match_set_id, label),
                UNIQUE(match_set_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS question_revision_match_right_items (
                id TEXT PRIMARY KEY,
                match_set_id TEXT NOT NULL REFERENCES question_revision_match_sets(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                text TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(match_set_id, label),
                UNIQUE(match_set_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS question_revision_figures (
                id TEXT PRIMARY KEY,
                question_revision_id TEXT NOT NULL REFERENCES question_revisions(id) ON DELETE CASCADE,
                extracted_asset_id TEXT NOT NULL REFERENCES extracted_assets(id) ON DELETE CASCADE,
                display_order INTEGER NOT NULL,
                is_primary INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(question_revision_id, extracted_asset_id),
                UNIQUE(question_revision_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                full_name TEXT NOT NULL,
                roll_number TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tests (
                id TEXT PRIMARY KEY,
                created_by_admin_id TEXT NOT NULL REFERENCES admins(id),
                title TEXT NOT NULL,
                subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                chapter_id TEXT REFERENCES chapters(id) ON DELETE SET NULL,
                topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                question_count INTEGER NOT NULL,
                hard_question_count INTEGER NOT NULL,
                is_custom_practice_template INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS test_question_revisions (
                id TEXT PRIMARY KEY,
                test_id TEXT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
                question_item_id TEXT NOT NULL REFERENCES question_items(id) ON DELETE CASCADE,
                question_revision_id TEXT NOT NULL REFERENCES question_revisions(id) ON DELETE CASCADE,
                display_order INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(test_id, question_item_id),
                UNIQUE(test_id, display_order)
            );

            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_by_admin_id TEXT NOT NULL REFERENCES admins(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(created_by_admin_id, name)
            );

            CREATE TABLE IF NOT EXISTS batch_students (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                UNIQUE(batch_id, student_id)
            );

            CREATE TABLE IF NOT EXISTS assignments (
                id TEXT PRIMARY KEY,
                test_id TEXT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
                assigned_by_admin_id TEXT NOT NULL REFERENCES admins(id),
                student_id TEXT REFERENCES students(id) ON DELETE CASCADE,
                batch_id TEXT REFERENCES batches(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                published_at TEXT,
                due_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY,
                test_id TEXT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
                assignment_id TEXT REFERENCES assignments(id) ON DELETE SET NULL,
                student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                score REAL,
                correct_answer_count INTEGER,
                wrong_answer_count INTEGER,
                started_at TEXT,
                submitted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempt_answers (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                test_question_revision_id TEXT NOT NULL REFERENCES test_question_revisions(id) ON DELETE CASCADE,
                question_revision_id TEXT NOT NULL REFERENCES question_revisions(id) ON DELETE CASCADE,
                answer_data TEXT NOT NULL,
                is_correct INTEGER,
                selected_option_count INTEGER NOT NULL DEFAULT 0,
                earned_score REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(attempt_id, test_question_revision_id)
            );

            CREATE TABLE IF NOT EXISTS admin_activity_logs (
                id TEXT PRIMARY KEY,
                admin_id TEXT NOT NULL REFERENCES admins(id),
                action_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                summary TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_topics_chapter_status ON topics(chapter_id, status);
            CREATE INDEX IF NOT EXISTS idx_concepts_topic_status ON concepts(topic_id, status);
            CREATE INDEX IF NOT EXISTS idx_question_items_concept_status ON question_items(concept_id, lifecycle_status, is_deleted);
            CREATE INDEX IF NOT EXISTS idx_question_revisions_item_status ON question_revisions(question_item_id, revision_status);
            CREATE INDEX IF NOT EXISTS idx_question_revisions_filter ON question_revisions(format, difficulty, type, revision_status);
            CREATE INDEX IF NOT EXISTS idx_ai_import_batches_status ON ai_import_batches(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_test_question_revisions_test ON test_question_revisions(test_id, display_order);
            CREATE INDEX IF NOT EXISTS idx_attempt_answers_attempt ON attempt_answers(attempt_id);
            """
        )


def ensure_default_admin_exists() -> None:
    with build_connection() as connection:
        row = connection.execute("SELECT id FROM admins WHERE lower(email) = lower(?)", ("admin@braingain.local",)).fetchone()
        if row is not None:
            return
        now = build_timestamp()
        connection.execute(
            """
            INSERT INTO admins (id, email, full_name, password_hash, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_identifier(),
                "admin@braingain.local",
                "Demo Admin",
                "admin123",
                1,
                now,
                now,
            ),
        )
