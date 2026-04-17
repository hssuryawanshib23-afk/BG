from __future__ import annotations

import json
import random
import shutil
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any
from typing import Literal

from fastapi import File
from fastapi import FastAPI
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

from .database import build_connection
from .database import build_identifier
from .database import build_json_text
from .database import build_timestamp
from .database import convert_row_to_dict
from .database import convert_rows_to_dicts
from .database import ensure_default_admin_exists
from .database import initialize_database
from .database import insert_admin_activity_log
from .database import parse_json_text
from .database import PROJECT_DIRECTORY
from .question_bank_import import BATCH_STATUS_VALUES
from .question_bank_import import QUESTION_DIFFICULTY_VALUES
from .question_bank_import import QUESTION_FORMAT_VALUES
from .question_bank_import import QUESTION_LIFECYCLE_VALUES
from .question_bank_import import QUESTION_TYPE_VALUES
from .question_bank_import import create_ai_import_batch
from .question_bank_import import delete_ai_import_batch_question
from .question_bank_import import get_ai_import_batch
from .question_bank_import import insert_ai_import_batch_question
from .question_bank_import import materialize_ai_import_batch
from .question_bank_import import update_ai_import_batch_question
from .question_bank_import import update_ai_import_batch_payload
from .question_bank_import import validate_question_bank_file


FIGURE_REVIEW_STATUS_VALUES = {"pending", "approved", "rejected"}
ATTEMPT_STATUS_VALUES = {"in_progress", "submitted", "evaluated"}
QUESTION_REVISION_STATUS_VALUES = {"draft", "published", "archived"}
DEFAULT_ATTEMPT_DURATION_MINUTES = 30
SECONDS_PER_QUESTION = 120
DEMO_CREDENTIALS = {
    "admin": {
        "username": "admin@braingain.local",
        "password": "admin123",
        "display_name": "Demo Admin",
        "redirect_path": "/admin",
    },
    "student": {
        "username": "student@braingain.local",
        "password": "student123",
        "display_name": "Demo Student",
        "redirect_path": "/student",
    },
}

app = FastAPI(title="BrainGain API")
WEB_DIRECTORY = PROJECT_DIRECTORY / "web"
UPLOAD_DIRECTORY = PROJECT_DIRECTORY / "data" / "uploads"
QUESTION_BANK_UPLOAD_DIRECTORY = UPLOAD_DIRECTORY / "question_banks"
FIGURE_IMPORT_UPLOAD_DIRECTORY = UPLOAD_DIRECTORY / "figure_imports"
QUESTION_IMAGE_UPLOAD_DIRECTORY = UPLOAD_DIRECTORY / "question_images"


class SubjectCreateRequest(BaseModel):
    name: str
    grade: int
    board: str


class ChapterCreateRequest(BaseModel):
    subject_id: str
    chapter_number: int
    name: str


class TopicCreateRequest(BaseModel):
    chapter_id: str
    name: str
    display_order: int


class ConceptCreateRequest(BaseModel):
    topic_id: str
    name: str
    display_order: int


class StudentEnsureRequest(BaseModel):
    full_name: str
    roll_number: str | None = None
    email: str | None = None


class DemoLoginRequest(BaseModel):
    role: Literal["admin", "student"]
    username: str
    password: str


class OptionInput(BaseModel):
    label: Literal["A", "B", "C", "D"]
    text: str
    is_correct: bool = False


class NumericAnswerInput(BaseModel):
    exact_value: float
    tolerance: float
    unit: str = ""


class MatchLeftItemInput(BaseModel):
    label: str
    text: str
    matches: str


class MatchRightItemInput(BaseModel):
    label: str
    text: str


class MatchColumnsInput(BaseModel):
    a_heading: str
    b_heading: str
    items_a: list[MatchLeftItemInput]
    items_b: list[MatchRightItemInput]


class OptionAnswerInput(BaseModel):
    type: Literal["option_labels"] = "option_labels"
    value: list[str]


class NumericTransportAnswerInput(BaseModel):
    type: Literal["numeric"] = "numeric"
    exact_value: float
    tolerance: float
    unit: str = ""


class PairAnswerInput(BaseModel):
    type: Literal["pairs"] = "pairs"
    value: dict[str, str]


class QuestionRevisionCreateRequest(BaseModel):
    concept_id: str
    created_by_admin_id: str
    source_question_id: str | None = None
    lifecycle_status: Literal["draft", "active", "disabled", "archived"] = "draft"
    format: Literal["mcq", "msq", "nat", "match"]
    difficulty: Literal["easy", "medium", "hard"]
    type: Literal["definition", "identification", "trap", "application", "comparison", "reasoning"]
    text: str
    image_asset_id: str | None = None
    options: list[OptionInput] = Field(default_factory=list)
    numeric_answer: NumericAnswerInput | None = None
    columns: MatchColumnsInput | None = None
    answer: OptionAnswerInput | NumericTransportAnswerInput | PairAnswerInput

    @model_validator(mode="after")
    def validate_shape(self) -> "QuestionRevisionCreateRequest":
        validate_question_request_shape(self.format, self.options, self.numeric_answer, self.columns, self.answer)
        return self


class QuestionRevisionUpdateRequest(BaseModel):
    updated_by_admin_id: str
    lifecycle_status: Literal["draft", "active", "disabled", "archived"] | None = None
    format: Literal["mcq", "msq", "nat", "match"]
    difficulty: Literal["easy", "medium", "hard"]
    type: Literal["definition", "identification", "trap", "application", "comparison", "reasoning"]
    text: str
    image_asset_id: str | None = None
    options: list[OptionInput] = Field(default_factory=list)
    numeric_answer: NumericAnswerInput | None = None
    columns: MatchColumnsInput | None = None
    answer: OptionAnswerInput | NumericTransportAnswerInput | PairAnswerInput

    @model_validator(mode="after")
    def validate_shape(self) -> "QuestionRevisionUpdateRequest":
        validate_question_request_shape(self.format, self.options, self.numeric_answer, self.columns, self.answer)
        return self


class PublishQuestionRevisionRequest(BaseModel):
    published_by_admin_id: str
    lifecycle_status: Literal["draft", "active", "disabled", "archived"] = "active"


class QuestionLifecycleUpdateRequest(BaseModel):
    updated_by_admin_id: str
    lifecycle_status: Literal["draft", "active", "disabled", "archived"]


class TestCreateRequest(BaseModel):
    created_by_admin_id: str
    title: str
    subject_id: str
    chapter_id: str | None = None
    topic_id: str | None = None
    concept_ids: list[str] = Field(default_factory=list)
    format_filters: list[Literal["mcq", "msq", "nat", "match"]] = Field(default_factory=list)
    difficulty_filters: list[Literal["easy", "medium", "hard"]] = Field(default_factory=list)
    type_filters: list[Literal["definition", "identification", "trap", "application", "comparison", "reasoning"]] = Field(default_factory=list)
    question_count: int
    hard_question_count: int | None = None
    is_custom_practice_template: bool = False
    selected_question_item_ids: list[str] = Field(default_factory=list)
    selected_question_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_selected_question_ids(self) -> "TestCreateRequest":
        if not self.selected_question_item_ids and self.selected_question_ids:
            self.selected_question_item_ids = list(self.selected_question_ids)
        return self


class AttemptStartRequest(BaseModel):
    test_id: str
    full_name: str
    roll_number: str | None = None
    email: str | None = None


class AttemptAnswerSubmission(BaseModel):
    test_question_revision_id: str
    option_labels: list[str] = Field(default_factory=list)
    numeric_value: float | None = None
    pair_mapping: dict[str, str] = Field(default_factory=dict)
    is_marked_for_review: bool = False
    has_visited: bool = True
    spent_seconds: int = Field(default=0, ge=0)


class AttemptAnswerUpdateRequest(BaseModel):
    option_labels: list[str] = Field(default_factory=list)
    numeric_value: float | None = None
    pair_mapping: dict[str, str] = Field(default_factory=dict)
    is_marked_for_review: bool = False
    has_visited: bool = True
    spent_seconds: int = Field(default=0, ge=0)


class AttemptSubmitRequest(BaseModel):
    answers: list[AttemptAnswerSubmission] = Field(default_factory=list)


class FigureReviewManifestImportRequest(BaseModel):
    chapter_id: str
    source_file_path: str
    manifest_file_path: str
    figure_review_manifest_file_path: str
    uploaded_by_admin_id: str


class FigureReviewUpdateRequest(BaseModel):
    review_status: Literal["pending", "approved", "rejected"]
    reviewed_by_admin_id: str


class QuestionBankValidationRequest(BaseModel):
    source_file_path: str


class AIImportBatchCreateRequest(BaseModel):
    source_file_path: str
    uploaded_by_admin_id: str


class AIImportBatchPayloadUpdateRequest(BaseModel):
    updated_by_admin_id: str
    payload_text: str


class AIImportBatchQuestionUpdateRequest(BaseModel):
    updated_by_admin_id: str
    concept_index: int
    question_index: int
    question: dict[str, Any]


class AIImportBatchQuestionInsertRequest(BaseModel):
    updated_by_admin_id: str
    concept_index: int
    insert_at_question_index: int
    question: dict[str, Any]


class AIImportBatchMaterializeRequest(BaseModel):
    approved_by_admin_id: str
    topic_id: str
    default_lifecycle_status: Literal["draft", "active", "disabled", "archived"] = "draft"
    auto_publish: bool = False


class LegacyQuestionBankImportRequest(BaseModel):
    source_file_path: str
    uploaded_by_admin_id: str
    default_status: Literal["draft", "active", "disabled"] = "draft"


class LegacyQuestionBankApproveRequest(BaseModel):
    approved_by_admin_id: str
    topic_id: str
    auto_publish: bool = False


class LegacyQuestionCreateRequest(BaseModel):
    topic_id: str
    created_by_admin_id: str
    text: str
    question_format: Literal["mcq", "msq", "nat", "match"]
    difficulty: Literal["easy", "medium", "hard"]
    type: Literal["definition", "identification", "trap", "application", "comparison", "reasoning"]
    status: Literal["draft", "active", "disabled", "archived"] = "draft"
    minimum_selection_count: int | None = None
    maximum_selection_count: int | None = None
    figure_ids: list[str] = Field(default_factory=list)
    options: list[OptionInput] = Field(default_factory=list)
    numeric_answer: NumericAnswerInput | None = None
    columns: MatchColumnsInput | None = None
    answer: OptionAnswerInput | NumericTransportAnswerInput | PairAnswerInput | None = None


class LegacyQuestionUpdateRequest(BaseModel):
    last_edited_by_admin_id: str
    text: str
    question_format: Literal["mcq", "msq", "nat", "match"]
    difficulty: Literal["easy", "medium", "hard"]
    type: Literal["definition", "identification", "trap", "application", "comparison", "reasoning"]
    status: Literal["draft", "active", "disabled", "archived"] = "draft"
    minimum_selection_count: int | None = None
    maximum_selection_count: int | None = None
    figure_ids: list[str] = Field(default_factory=list)
    options: list[OptionInput] = Field(default_factory=list)
    numeric_answer: NumericAnswerInput | None = None
    columns: MatchColumnsInput | None = None
    answer: OptionAnswerInput | NumericTransportAnswerInput | PairAnswerInput | None = None


@app.on_event("startup")
def handle_startup() -> None:
    initialize_database()
    ensure_default_admin_exists()


if WEB_DIRECTORY.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIRECTORY), name="static")


@app.get("/")
def get_login_application() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "login.html")


@app.get("/admin")
def get_admin_application() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "index.html")


@app.get("/student")
def get_student_application() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "student.html")


@app.get("/practice")
def get_student_practice_alias() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "student.html")


@app.get("/project-files/{file_path:path}")
def get_project_file(file_path: str) -> FileResponse:
    requested_path = (PROJECT_DIRECTORY / file_path).resolve()
    project_directory = PROJECT_DIRECTORY.resolve()
    if not str(requested_path).startswith(str(project_directory)):
        raise HTTPException(status_code=400, detail="File path is outside the project directory")
    if not requested_path.exists() or not requested_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(requested_path)


@app.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/demo-login")
def demo_login(request: DemoLoginRequest) -> dict[str, str]:
    credential = DEMO_CREDENTIALS.get(request.role)
    if credential is None:
        raise HTTPException(status_code=400, detail="Unsupported role")
    if request.username.strip().lower() != credential["username"] or request.password != credential["password"]:
        raise HTTPException(status_code=401, detail="Invalid demo credentials")
    return {
        "role": request.role,
        "display_name": credential["display_name"],
        "redirect_path": credential["redirect_path"],
    }


@app.get("/admins")
def list_admins() -> list[dict[str, object]]:
    with build_connection() as connection:
        rows = connection.execute(
            "SELECT id, email, full_name, is_active, created_at, updated_at FROM admins ORDER BY created_at"
        ).fetchall()
    return convert_rows_to_dicts(rows)


@app.post("/subjects")
def create_subject(request: SubjectCreateRequest) -> dict[str, object]:
    now = build_timestamp()
    subject_id = build_identifier()
    with build_connection() as connection:
        connection.execute(
            """
            INSERT INTO subjects (id, name, grade, board, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (subject_id, request.name.strip(), request.grade, request.board.strip(), "active", now, now),
        )
        row = connection.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    return convert_row_to_dict(row) or {}


@app.get("/subjects")
def list_subjects() -> list[dict[str, object]]:
    with build_connection() as connection:
        rows = connection.execute("SELECT * FROM subjects ORDER BY grade, name").fetchall()
    return convert_rows_to_dicts(rows)


@app.post("/chapters")
def create_chapter(request: ChapterCreateRequest) -> dict[str, object]:
    now = build_timestamp()
    chapter_id = build_identifier()
    with build_connection() as connection:
        ensure_subject_exists(connection, request.subject_id)
        connection.execute(
            """
            INSERT INTO chapters (id, subject_id, chapter_number, name, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (chapter_id, request.subject_id, request.chapter_number, request.name.strip(), "active", now, now),
        )
        row = connection.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return convert_row_to_dict(row) or {}


@app.get("/subjects/{subject_id}/chapters")
def list_chapters(subject_id: str) -> list[dict[str, object]]:
    with build_connection() as connection:
        ensure_subject_exists(connection, subject_id)
        rows = connection.execute(
            "SELECT * FROM chapters WHERE subject_id = ? ORDER BY chapter_number, name",
            (subject_id,),
        ).fetchall()
    return convert_rows_to_dicts(rows)


@app.post("/topics")
def create_topic(request: TopicCreateRequest) -> dict[str, object]:
    now = build_timestamp()
    topic_id = build_identifier()
    with build_connection() as connection:
        ensure_chapter_exists(connection, request.chapter_id)
        connection.execute(
            """
            INSERT INTO topics (id, chapter_id, name, display_order, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (topic_id, request.chapter_id, request.name.strip(), request.display_order, "active", now, now),
        )
        row = connection.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    return convert_row_to_dict(row) or {}


@app.get("/chapters/{chapter_id}/topics")
def list_topics(chapter_id: str) -> list[dict[str, object]]:
    with build_connection() as connection:
        ensure_chapter_exists(connection, chapter_id)
        rows = connection.execute(
            "SELECT * FROM topics WHERE chapter_id = ? ORDER BY display_order, name",
            (chapter_id,),
        ).fetchall()
    return convert_rows_to_dicts(rows)


@app.post("/concepts")
def create_concept(request: ConceptCreateRequest) -> dict[str, object]:
    now = build_timestamp()
    concept_id = build_identifier()
    with build_connection() as connection:
        ensure_topic_exists(connection, request.topic_id)
        connection.execute(
            """
            INSERT INTO concepts (id, topic_id, name, display_order, status, source_concept_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (concept_id, request.topic_id, request.name.strip(), request.display_order, "active", request.name.strip(), now, now),
        )
        row = connection.execute("SELECT * FROM concepts WHERE id = ?", (concept_id,)).fetchone()
    return convert_row_to_dict(row) or {}


@app.get("/topics/{topic_id}/concepts")
def list_concepts(topic_id: str) -> list[dict[str, object]]:
    with build_connection() as connection:
        ensure_topic_exists(connection, topic_id)
        rows = connection.execute(
            "SELECT * FROM concepts WHERE topic_id = ? ORDER BY display_order, name",
            (topic_id,),
        ).fetchall()
    return convert_rows_to_dicts(rows)


@app.post("/figure-review/import")
def import_figure_review_manifest(request: FigureReviewManifestImportRequest) -> dict[str, object]:
    manifest_path = normalize_project_file_path(request.figure_review_manifest_file_path)
    if not manifest_path.exists():
        raise HTTPException(status_code=400, detail="Figure review manifest file does not exist")
    review_items = load_json_file(manifest_path)
    now = build_timestamp()
    textbook_document_id = build_identifier()
    extraction_run_id = build_identifier()
    with build_connection() as connection:
        ensure_admin_exists(connection, request.uploaded_by_admin_id)
        ensure_chapter_exists(connection, request.chapter_id)
        manifest_data = load_json_file(normalize_project_file_path(request.manifest_file_path))
        source_file_path = str(normalize_project_file_path(str(manifest_data.get("source_file_path", request.source_file_path))))
        connection.execute(
            """
            INSERT INTO textbook_documents (id, chapter_id, source_file_name, source_file_path, uploaded_by_admin_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (textbook_document_id, request.chapter_id, Path(source_file_path).name, source_file_path, request.uploaded_by_admin_id, now, now),
        )
        connection.execute(
            """
            INSERT INTO extraction_runs (id, textbook_document_id, manifest_file_path, figure_review_manifest_file_path, started_at, finished_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (extraction_run_id, textbook_document_id, request.manifest_file_path, request.figure_review_manifest_file_path, now, now, now, now),
        )
        imported_count = 0
        for review_item in review_items:
            connection.execute(
                """
                INSERT INTO extracted_assets (
                    id, extraction_run_id, chapter_id, asset_type, page_number, name, file_path, caption_text,
                    bounding_box, text_density, non_text_density, review_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    chapter_id = excluded.chapter_id,
                    page_number = excluded.page_number,
                    name = excluded.name,
                    caption_text = excluded.caption_text,
                    bounding_box = excluded.bounding_box,
                    text_density = excluded.text_density,
                    non_text_density = excluded.non_text_density,
                    review_status = excluded.review_status,
                    updated_at = excluded.updated_at
                """,
                (
                    build_identifier(),
                    extraction_run_id,
                    request.chapter_id,
                    "figure_candidate",
                    review_item.get("page_number"),
                    review_item.get("figure_name"),
                    str(normalize_project_file_path(str(review_item.get("image_path")))),
                    review_item.get("caption_text"),
                    build_json_text(review_item.get("bounding_box")),
                    review_item.get("text_density"),
                    review_item.get("non_text_density"),
                    review_item.get("review_status", "pending"),
                    now,
                    now,
                ),
            )
            imported_count += 1
    return {"textbook_document_id": textbook_document_id, "extraction_run_id": extraction_run_id, "imported_asset_count": imported_count}


@app.post("/figure-review/import-upload")
async def import_figure_review_manifest_upload(
    chapter_id: str = Form(...),
    uploaded_by_admin_id: str = Form(...),
    manifest_file: UploadFile = File(...),
    figure_review_manifest_file: UploadFile = File(...),
) -> dict[str, object]:
    saved_manifest_path = await save_uploaded_file(manifest_file, FIGURE_IMPORT_UPLOAD_DIRECTORY)
    saved_review_manifest_path = await save_uploaded_file(figure_review_manifest_file, FIGURE_IMPORT_UPLOAD_DIRECTORY)
    manifest_data = load_json_file(saved_manifest_path)
    source_file_path = str(manifest_data.get("source_file_path", ""))
    return import_figure_review_manifest(
        FigureReviewManifestImportRequest(
            chapter_id=chapter_id,
            source_file_path=source_file_path,
            manifest_file_path=str(saved_manifest_path),
            figure_review_manifest_file_path=str(saved_review_manifest_path),
            uploaded_by_admin_id=uploaded_by_admin_id,
        )
    )


@app.get("/chapters/{chapter_id}/figure-candidates")
def list_figure_candidates(chapter_id: str, review_status: str | None = None) -> list[dict[str, object]]:
    with build_connection() as connection:
        ensure_chapter_exists(connection, chapter_id)
        query = "SELECT * FROM extracted_assets WHERE chapter_id = ?"
        parameters: list[object] = [chapter_id]
        if review_status:
            if review_status not in FIGURE_REVIEW_STATUS_VALUES:
                raise HTTPException(status_code=400, detail="Invalid review status")
            query += " AND review_status = ?"
            parameters.append(review_status)
        query += " ORDER BY page_number, name"
        rows = connection.execute(query, parameters).fetchall()
    return convert_rows_to_dicts(rows)


@app.patch("/extracted-assets/{asset_id}/review")
def review_extracted_asset(asset_id: str, request: FigureReviewUpdateRequest) -> dict[str, object]:
    now = build_timestamp()
    with build_connection() as connection:
        ensure_admin_exists(connection, request.reviewed_by_admin_id)
        asset_row = connection.execute("SELECT * FROM extracted_assets WHERE id = ?", (asset_id,)).fetchone()
        if asset_row is None:
            raise HTTPException(status_code=404, detail="Extracted asset not found")
        asset_type = "approved_figure" if request.review_status == "approved" else "figure_candidate"
        connection.execute(
            """
            UPDATE extracted_assets
            SET asset_type = ?, review_status = ?, reviewed_by_admin_id = ?, reviewed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (asset_type, request.review_status, request.reviewed_by_admin_id, now, now, asset_id),
        )
        row = connection.execute("SELECT * FROM extracted_assets WHERE id = ?", (asset_id,)).fetchone()
    return convert_row_to_dict(row) or {}


@app.get("/topics/{topic_id}/approved-figures")
def list_approved_figures(topic_id: str) -> list[dict[str, object]]:
    with build_connection() as connection:
        topic_row = connection.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if topic_row is None:
            raise HTTPException(status_code=404, detail="Topic not found")
        rows = connection.execute(
            """
            SELECT extracted_assets.*
            FROM extracted_assets
            WHERE extracted_assets.chapter_id = ? AND extracted_assets.asset_type = 'approved_figure' AND extracted_assets.review_status = 'approved'
            ORDER BY extracted_assets.page_number, extracted_assets.name
            """,
            (topic_row["chapter_id"],),
        ).fetchall()
    return convert_rows_to_dicts(rows)


@app.post("/topics/{topic_id}/question-images")
async def upload_question_image(
    topic_id: str,
    uploaded_by_admin_id: str = Form(...),
    image_file: UploadFile = File(...),
) -> dict[str, object]:
    if not image_file.content_type or not image_file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files can be attached to questions")
    saved_image_path = await save_uploaded_file(image_file, QUESTION_IMAGE_UPLOAD_DIRECTORY)
    now = build_timestamp()
    textbook_document_id = build_identifier()
    extraction_run_id = build_identifier()
    asset_id = build_identifier()
    with build_connection() as connection:
        ensure_admin_exists(connection, uploaded_by_admin_id)
        topic_row = connection.execute(
            """
            SELECT topics.id, topics.name, chapters.id AS chapter_id, chapters.name AS chapter_name
            FROM topics
            INNER JOIN chapters ON chapters.id = topics.chapter_id
            WHERE topics.id = ?
            """,
            (topic_id,),
        ).fetchone()
        if topic_row is None:
            raise HTTPException(status_code=404, detail="Topic not found")
        chapter_id = str(topic_row["chapter_id"])
        source_file_name = Path(image_file.filename or "question-image").name
        connection.execute(
            """
            INSERT INTO textbook_documents (id, chapter_id, source_file_name, source_file_path, uploaded_by_admin_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (textbook_document_id, chapter_id, source_file_name, str(saved_image_path), uploaded_by_admin_id, now, now),
        )
        connection.execute(
            """
            INSERT INTO extraction_runs (id, textbook_document_id, manifest_file_path, figure_review_manifest_file_path, started_at, finished_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (extraction_run_id, textbook_document_id, str(saved_image_path), None, now, now, now, now),
        )
        connection.execute(
            """
            INSERT INTO extracted_assets (
                id, extraction_run_id, chapter_id, asset_type, page_number, name, file_path, caption_text,
                bounding_box, text_density, non_text_density, review_status, reviewed_by_admin_id, reviewed_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                extraction_run_id,
                chapter_id,
                "approved_figure",
                None,
                source_file_name,
                str(saved_image_path),
                None,
                None,
                None,
                None,
                "approved",
                uploaded_by_admin_id,
                now,
                now,
                now,
            ),
        )
        insert_admin_activity_log(
            connection,
            uploaded_by_admin_id,
            action_type="question_image_uploaded",
            entity_type="extracted_asset",
            entity_id=asset_id,
            summary=f"Uploaded question image for topic {topic_row['name']}",
            details={"topic_id": topic_id, "chapter_id": chapter_id, "file_name": source_file_name},
        )
        row = connection.execute("SELECT * FROM extracted_assets WHERE id = ?", (asset_id,)).fetchone()
    return convert_row_to_dict(row) or {}


@app.post("/ai-import-batches")
def create_ai_import_batch_endpoint(request: AIImportBatchCreateRequest) -> dict[str, object]:
    with build_connection() as connection:
        ensure_admin_exists(connection, request.uploaded_by_admin_id)
        return create_ai_import_batch(connection, request.source_file_path, request.uploaded_by_admin_id)


@app.post("/ai-import-batches/upload")
async def create_ai_import_batch_upload(
    uploaded_by_admin_id: str = Form(...),
    json_file: UploadFile = File(...),
) -> dict[str, object]:
    saved_file_path = await save_uploaded_file(json_file, QUESTION_BANK_UPLOAD_DIRECTORY)
    return create_ai_import_batch_endpoint(
        AIImportBatchCreateRequest(
            source_file_path=str(saved_file_path),
            uploaded_by_admin_id=uploaded_by_admin_id,
        )
    )


@app.get("/ai-import-batches")
def list_ai_import_batches() -> list[dict[str, object]]:
    with build_connection() as connection:
        rows = connection.execute("SELECT * FROM ai_import_batches ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            data = convert_row_to_dict(row) or {}
            data["validation_summary"] = parse_json_text(data.get("validation_summary"), default={}) or {}
            results.append(data)
        return results


@app.get("/ai-import-batches/{batch_id}")
def get_ai_import_batch_endpoint(batch_id: str) -> dict[str, object]:
    with build_connection() as connection:
        return get_ai_import_batch(connection, batch_id)


@app.patch("/ai-import-batches/{batch_id}/payload")
def update_ai_import_batch_payload_endpoint(batch_id: str, request: AIImportBatchPayloadUpdateRequest) -> dict[str, object]:
    with build_connection() as connection:
        ensure_admin_exists(connection, request.updated_by_admin_id)
        return update_ai_import_batch_payload(connection, batch_id, request.updated_by_admin_id, request.payload_text)


@app.post("/ai-import-batches/{batch_id}/materialize")
def materialize_ai_import_batch_endpoint(batch_id: str, request: AIImportBatchMaterializeRequest) -> dict[str, object]:
    with build_connection() as connection:
        ensure_admin_exists(connection, request.approved_by_admin_id)
        ensure_topic_exists(connection, request.topic_id)
        return materialize_ai_import_batch(
            connection=connection,
            batch_id=batch_id,
            approved_by_admin_id=request.approved_by_admin_id,
            topic_id=request.topic_id,
            default_lifecycle_status=request.default_lifecycle_status,
            auto_publish=request.auto_publish,
        )


@app.post("/question-revisions")
def create_question_revision(request: QuestionRevisionCreateRequest) -> dict[str, object]:
    now = build_timestamp()
    question_item_id = build_identifier()
    revision_id = build_identifier()
    with build_connection() as connection:
        ensure_admin_exists(connection, request.created_by_admin_id)
        ensure_concept_exists(connection, request.concept_id)
        if request.image_asset_id:
            ensure_approved_figure_exists(connection, request.image_asset_id)
        connection.execute(
            """
            INSERT INTO question_items (
                id, concept_id, source_question_id, origin_type, ai_import_batch_id, created_by_admin_id,
                current_draft_revision_id, current_published_revision_id, lifecycle_status, is_deleted, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_item_id,
                request.concept_id,
                request.source_question_id,
                "manual",
                None,
                request.created_by_admin_id,
                revision_id,
                None,
                request.lifecycle_status,
                0,
                now,
                now,
            ),
        )
        store_revision(
            connection=connection,
            revision_id=revision_id,
            question_item_id=question_item_id,
            revision_number=1,
            parent_revision_id=None,
            created_by_admin_id=request.created_by_admin_id,
            revision_status="draft",
            question=question_request_to_payload(request),
            created_at=now,
        )
        insert_admin_activity_log(
            connection,
            request.created_by_admin_id,
            action_type="question_draft_created",
            entity_type="question_item",
            entity_id=question_item_id,
            summary=f"Created draft {request.format.upper()} question",
            details={"concept_id": request.concept_id},
        )
        return build_question_item_payload(connection, question_item_id, include_answers=True)


@app.post("/question-items/{question_item_id}/revisions")
def create_question_item_revision(question_item_id: str, request: QuestionRevisionUpdateRequest) -> dict[str, object]:
    now = build_timestamp()
    with build_connection() as connection:
        ensure_admin_exists(connection, request.updated_by_admin_id)
        item_row = connection.execute("SELECT * FROM question_items WHERE id = ? AND is_deleted = 0", (question_item_id,)).fetchone()
        if item_row is None:
            raise HTTPException(status_code=404, detail="Question item not found")
        if request.image_asset_id:
            ensure_approved_figure_exists(connection, request.image_asset_id)
        latest_row = connection.execute(
            """
            SELECT revision_number, id
            FROM question_revisions
            WHERE question_item_id = ?
            ORDER BY revision_number DESC
            LIMIT 1
            """,
            (question_item_id,),
        ).fetchone()
        next_revision_number = int(latest_row["revision_number"]) + 1 if latest_row else 1
        revision_id = build_identifier()
        store_revision(
            connection=connection,
            revision_id=revision_id,
            question_item_id=question_item_id,
            revision_number=next_revision_number,
            parent_revision_id=str(item_row["current_published_revision_id"] or item_row["current_draft_revision_id"] or ""),
            created_by_admin_id=request.updated_by_admin_id,
            revision_status="draft",
            question=question_update_to_payload(request),
            created_at=now,
        )
        lifecycle_status = request.lifecycle_status or str(item_row["lifecycle_status"])
        connection.execute(
            """
            UPDATE question_items
            SET current_draft_revision_id = ?, lifecycle_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (revision_id, lifecycle_status, now, question_item_id),
        )
        return build_question_item_payload(connection, question_item_id, include_answers=True)


@app.post("/question-revisions/{revision_id}/publish")
def publish_question_revision(revision_id: str, request: PublishQuestionRevisionRequest) -> dict[str, object]:
    now = build_timestamp()
    with build_connection() as connection:
        ensure_admin_exists(connection, request.published_by_admin_id)
        revision_row = connection.execute("SELECT * FROM question_revisions WHERE id = ?", (revision_id,)).fetchone()
        if revision_row is None:
            raise HTTPException(status_code=404, detail="Question revision not found")
        question_item_id = str(revision_row["question_item_id"])
        connection.execute(
            """
            UPDATE question_revisions
            SET revision_status = ?, published_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("published", now, now, revision_id),
        )
        connection.execute(
            """
            UPDATE question_items
            SET current_published_revision_id = ?, lifecycle_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (revision_id, request.lifecycle_status, now, question_item_id),
        )
        return build_question_item_payload(connection, question_item_id, include_answers=True)


@app.patch("/question-items/{question_item_id}/lifecycle")
def update_question_item_lifecycle(question_item_id: str, request: QuestionLifecycleUpdateRequest) -> dict[str, object]:
    now = build_timestamp()
    with build_connection() as connection:
        ensure_admin_exists(connection, request.updated_by_admin_id)
        connection.execute(
            """
            UPDATE question_items
            SET lifecycle_status = ?, updated_at = ?
            WHERE id = ? AND is_deleted = 0
            """,
            (request.lifecycle_status, now, question_item_id),
        )
        row = connection.execute("SELECT id FROM question_items WHERE id = ? AND is_deleted = 0", (question_item_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Question item not found")
        return build_question_item_payload(connection, question_item_id, include_answers=True)


@app.delete("/question-items/{question_item_id}")
def soft_delete_question_item(question_item_id: str, deleted_by_admin_id: str) -> dict[str, object]:
    now = build_timestamp()
    with build_connection() as connection:
        ensure_admin_exists(connection, deleted_by_admin_id)
        row = connection.execute("SELECT id FROM question_items WHERE id = ? AND is_deleted = 0", (question_item_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Question item not found")
        connection.execute(
            """
            UPDATE question_items
            SET is_deleted = 1, lifecycle_status = 'archived', updated_at = ?
            WHERE id = ?
            """,
            (now, question_item_id),
        )
    return {"deleted_question_item_id": question_item_id}


@app.get("/concepts/{concept_id}/questions")
def list_concept_questions(concept_id: str, include_answers: bool = True) -> list[dict[str, object]]:
    with build_connection() as connection:
        ensure_concept_exists(connection, concept_id)
        item_rows = connection.execute(
            """
            SELECT id
            FROM question_items
            WHERE concept_id = ? AND is_deleted = 0
            ORDER BY created_at
            """,
            (concept_id,),
        ).fetchall()
        return [build_question_item_payload(connection, str(row["id"]), include_answers=include_answers) for row in item_rows]


@app.get("/question-items/{question_item_id}")
def get_question_item(question_item_id: str) -> dict[str, object]:
    with build_connection() as connection:
        return build_question_item_payload(connection, question_item_id, include_answers=True)


@app.post("/questions")
def create_legacy_question(request: LegacyQuestionCreateRequest) -> dict[str, object]:
    with build_connection() as connection:
        concept_id = ensure_default_concept_for_topic(connection, request.topic_id)
    answer = build_legacy_question_answer(
        request.question_format,
        request.options,
        request.numeric_answer,
        request.columns,
        request.answer,
    )
    created_question = create_question_revision(
        QuestionRevisionCreateRequest(
            concept_id=concept_id,
            created_by_admin_id=request.created_by_admin_id,
            lifecycle_status=request.status,
            format=request.question_format,
            difficulty=request.difficulty,
            type=request.type,
            text=request.text,
            image_asset_id=request.figure_ids[0] if request.figure_ids else None,
            options=request.options,
            numeric_answer=request.numeric_answer,
            columns=request.columns,
            answer=answer,
        )
    )
    if request.status == "active" and created_question.get("current_draft_revision"):
        return publish_question_revision(
            str(created_question["current_draft_revision"]["id"]),
            PublishQuestionRevisionRequest(
                published_by_admin_id=request.created_by_admin_id,
                lifecycle_status=request.status,
            ),
        )
    return created_question


@app.patch("/questions/{question_item_id}")
def update_legacy_question(question_item_id: str, request: LegacyQuestionUpdateRequest) -> dict[str, object]:
    answer = build_legacy_question_answer(
        request.question_format,
        request.options,
        request.numeric_answer,
        request.columns,
        request.answer,
    )
    updated_question = create_question_item_revision(
        question_item_id,
        QuestionRevisionUpdateRequest(
            updated_by_admin_id=request.last_edited_by_admin_id,
            lifecycle_status=request.status,
            format=request.question_format,
            difficulty=request.difficulty,
            type=request.type,
            text=request.text,
            image_asset_id=request.figure_ids[0] if request.figure_ids else None,
            options=request.options,
            numeric_answer=request.numeric_answer,
            columns=request.columns,
            answer=answer,
        ),
    )
    if request.status == "active" and updated_question.get("current_draft_revision"):
        return publish_question_revision(
            str(updated_question["current_draft_revision"]["id"]),
            PublishQuestionRevisionRequest(
                published_by_admin_id=request.last_edited_by_admin_id,
                lifecycle_status=request.status,
            ),
        )
    return update_question_item_lifecycle(
        question_item_id,
        QuestionLifecycleUpdateRequest(
            updated_by_admin_id=request.last_edited_by_admin_id,
            lifecycle_status=request.status,
        ),
    )


@app.delete("/questions/{question_item_id}")
def delete_legacy_question(question_item_id: str, deleted_by_admin_id: str) -> dict[str, object]:
    return soft_delete_question_item(question_item_id, deleted_by_admin_id)


@app.get("/topics/{topic_id}/questions")
def list_topic_questions(topic_id: str, include_answers: bool = True) -> list[dict[str, object]]:
    with build_connection() as connection:
        ensure_topic_exists(connection, topic_id)
        item_rows = connection.execute(
            """
            SELECT question_items.id
            FROM question_items
            INNER JOIN concepts ON concepts.id = question_items.concept_id
            WHERE concepts.topic_id = ? AND question_items.is_deleted = 0
            ORDER BY concepts.display_order, question_items.created_at
            """,
            (topic_id,),
        ).fetchall()
        return [build_question_item_payload(connection, str(row["id"]), include_answers=include_answers) for row in item_rows]


@app.get("/subjects/{subject_id}/question-tree")
def get_subject_question_tree(subject_id: str) -> dict[str, object]:
    with build_connection() as connection:
        subject_row = connection.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        if subject_row is None:
            raise HTTPException(status_code=404, detail="Subject not found")
        chapter_rows = connection.execute(
            "SELECT id, chapter_number, name FROM chapters WHERE subject_id = ? ORDER BY chapter_number, name",
            (subject_id,),
        ).fetchall()
        chapters: list[dict[str, object]] = []
        total_question_count = 0
        total_active_question_count = 0
        for chapter_row in chapter_rows:
            topic_rows = connection.execute(
                "SELECT id, name, display_order FROM topics WHERE chapter_id = ? ORDER BY display_order, name",
                (chapter_row["id"],),
            ).fetchall()
            topics: list[dict[str, object]] = []
            chapter_question_count = 0
            chapter_active_question_count = 0
            for topic_row in topic_rows:
                concept_rows = connection.execute(
                    "SELECT id, name, display_order, status FROM concepts WHERE topic_id = ? ORDER BY display_order, name",
                    (topic_row["id"],),
                ).fetchall()
                concepts: list[dict[str, object]] = []
                topic_question_count = 0
                topic_active_question_count = 0
                for concept_row in concept_rows:
                    item_rows = connection.execute(
                        """
                        SELECT id, lifecycle_status, current_published_revision_id, current_draft_revision_id
                        FROM question_items
                        WHERE concept_id = ? AND is_deleted = 0
                        ORDER BY created_at
                        """,
                        (concept_row["id"],),
                    ).fetchall()
                    questions = []
                    concept_active_question_count = 0
                    for item_row in item_rows:
                        question_data = build_question_item_payload(connection, str(item_row["id"]), include_answers=False)
                        question_data["can_use_in_test"] = question_data["lifecycle_status"] == "active" and question_data["current_published_revision"] is not None
                        if question_data["can_use_in_test"]:
                            concept_active_question_count += 1
                        questions.append(question_data)
                    topic_question_count += len(questions)
                    topic_active_question_count += concept_active_question_count
                    concepts.append(
                        {
                            "id": str(concept_row["id"]),
                            "name": concept_row["name"],
                            "display_order": concept_row["display_order"],
                            "status": concept_row["status"],
                            "question_count": len(questions),
                            "active_question_count": concept_active_question_count,
                            "questions": questions,
                        }
                    )
                chapter_question_count += topic_question_count
                chapter_active_question_count += topic_active_question_count
                topics.append(
                    {
                        "id": str(topic_row["id"]),
                        "name": topic_row["name"],
                        "display_order": topic_row["display_order"],
                        "question_count": topic_question_count,
                        "active_question_count": topic_active_question_count,
                        "concepts": concepts,
                    }
                )
            total_question_count += chapter_question_count
            total_active_question_count += chapter_active_question_count
            chapters.append(
                {
                    "id": str(chapter_row["id"]),
                    "chapter_number": chapter_row["chapter_number"],
                    "name": chapter_row["name"],
                    "question_count": chapter_question_count,
                    "active_question_count": chapter_active_question_count,
                    "topics": topics,
                }
            )
    return {
        "subject": convert_row_to_dict(subject_row),
        "question_count": total_question_count,
        "active_question_count": total_active_question_count,
        "chapters": chapters,
    }


@app.post("/tests/generate")
def generate_test(request: TestCreateRequest) -> dict[str, object]:
    now = build_timestamp()
    test_id = build_identifier()
    with build_connection() as connection:
        ensure_admin_exists(connection, request.created_by_admin_id)
        ensure_subject_exists(connection, request.subject_id)
        resolved_chapter_id = request.chapter_id
        if resolved_chapter_id:
            ensure_chapter_exists(connection, resolved_chapter_id)
        if request.topic_id:
            topic_row = connection.execute("SELECT * FROM topics WHERE id = ?", (request.topic_id,)).fetchone()
            if topic_row is None:
                raise HTTPException(status_code=404, detail="Topic not found")
            resolved_chapter_id = str(topic_row["chapter_id"])
        manual_question_ids = list(dict.fromkeys([question_id for question_id in request.selected_question_item_ids if question_id]))
        if manual_question_ids:
            selected_rows = select_specific_question_items_for_test(
                connection=connection,
                subject_id=request.subject_id,
                chapter_id=resolved_chapter_id,
                topic_id=request.topic_id,
                concept_ids=request.concept_ids,
                question_item_ids=manual_question_ids,
            )
            actual_question_count = len(selected_rows)
            hard_question_count = sum(1 for row in selected_rows if str(row["difficulty"]) == "hard")
        else:
            if request.question_count < 1:
                raise HTTPException(status_code=400, detail="question_count must be at least 1")
            hard_question_count = request.hard_question_count
            if hard_question_count is None:
                hard_question_count = max(1, (request.question_count * 40 + 99) // 100)
            if hard_question_count * 100 < request.question_count * 40:
                raise HTTPException(status_code=400, detail="At least 40% of generated questions must be hard")
            selected_rows = select_question_items_for_test(
                connection=connection,
                subject_id=request.subject_id,
                chapter_id=resolved_chapter_id,
                topic_id=request.topic_id,
                concept_ids=request.concept_ids,
                format_filters=request.format_filters,
                difficulty_filters=request.difficulty_filters,
                type_filters=request.type_filters,
                question_count=request.question_count,
                hard_question_count=hard_question_count,
            )
            actual_question_count = request.question_count
        connection.execute(
            """
            INSERT INTO tests (
                id, created_by_admin_id, title, subject_id, chapter_id, topic_id, status, question_count,
                hard_question_count, is_custom_practice_template, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                test_id,
                request.created_by_admin_id,
                request.title.strip(),
                request.subject_id,
                resolved_chapter_id,
                request.topic_id,
                "published",
                actual_question_count,
                hard_question_count,
                1 if request.is_custom_practice_template else 0,
                now,
                now,
            ),
        )
        for display_order, row in enumerate(selected_rows, start=1):
            connection.execute(
                """
                INSERT INTO test_question_revisions (
                    id, test_id, question_item_id, question_revision_id, display_order, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (build_identifier(), test_id, str(row["question_item_id"]), str(row["question_revision_id"]), display_order, now),
            )
        return build_test_payload(connection, test_id, include_answers=True)


@app.get("/tests")
def list_tests(subject_id: str | None = None, chapter_id: str | None = None) -> list[dict[str, object]]:
    with build_connection() as connection:
        query = """
            SELECT
                tests.*,
                subjects.name AS subject_name,
                subjects.grade AS subject_grade,
                subjects.board AS subject_board,
                chapters.name AS chapter_name,
                chapters.chapter_number AS chapter_number,
                COUNT(DISTINCT test_question_revisions.question_revision_id) AS stored_question_count,
                COUNT(DISTINCT attempts.id) AS attempt_count
            FROM tests
            INNER JOIN subjects ON subjects.id = tests.subject_id
            LEFT JOIN chapters ON chapters.id = tests.chapter_id
            LEFT JOIN test_question_revisions ON test_question_revisions.test_id = tests.id
            LEFT JOIN attempts ON attempts.test_id = tests.id
        """
        clauses: list[str] = []
        parameters: list[object] = []
        if subject_id:
            clauses.append("tests.subject_id = ?")
            parameters.append(subject_id)
        if chapter_id:
            clauses.append("tests.chapter_id = ?")
            parameters.append(chapter_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " GROUP BY tests.id ORDER BY tests.created_at DESC"
        rows = connection.execute(query, parameters).fetchall()
    return convert_rows_to_dicts(rows)


@app.get("/tests/{test_id}")
def get_test(test_id: str) -> dict[str, object]:
    with build_connection() as connection:
        return build_test_payload(connection, test_id, include_answers=True)


@app.post("/students/ensure")
def ensure_student(request: StudentEnsureRequest) -> dict[str, object]:
    with build_connection() as connection:
        return get_or_create_student(connection, request.full_name, request.roll_number, request.email)


@app.post("/attempts/start")
def start_attempt(request: AttemptStartRequest) -> dict[str, object]:
    now = build_timestamp()
    attempt_id = build_identifier()
    with build_connection() as connection:
        test_data = build_test_payload(connection, request.test_id, include_answers=False)
        student = get_or_create_student(connection, request.full_name, request.roll_number, request.email)
        connection.execute(
            """
            INSERT INTO attempts (
                id, test_id, assignment_id, student_id, status, score, correct_answer_count, wrong_answer_count,
                started_at, submitted_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (attempt_id, request.test_id, None, student["id"], "in_progress", None, None, None, now, None, now, now),
        )
        for question in test_data["questions"]:
            upsert_attempt_answer_record(
                connection=connection,
                attempt_id=attempt_id,
                test_question_revision_id=str(question["test_question_revision_id"]),
                question_revision_id=str(question["id"]),
                answer_data=build_blank_attempt_answer_data(last_saved_at=now),
                is_correct=None,
                selected_option_count=0,
                earned_score=0.0,
                now=now,
            )
        return build_attempt_payload(connection, attempt_id, include_answers=False, include_results=False)


@app.get("/attempts/{attempt_id}")
def get_attempt(attempt_id: str) -> dict[str, object]:
    with build_connection() as connection:
        attempt_data = maybe_auto_submit_attempt(connection, attempt_id)
        if str(attempt_data["status"]) != "in_progress":
            return build_attempt_payload(connection, attempt_id, include_answers=True, include_results=True)
        return build_attempt_payload(connection, attempt_id, include_answers=False, include_results=False)


@app.put("/attempts/{attempt_id}/answers/{test_question_revision_id}")
def save_attempt_answer(
    attempt_id: str,
    test_question_revision_id: str,
    request: AttemptAnswerUpdateRequest,
) -> dict[str, object]:
    now = build_timestamp()
    with build_connection() as connection:
        attempt_data = maybe_auto_submit_attempt(connection, attempt_id)
        if str(attempt_data["status"]) != "in_progress":
            return build_attempt_payload(connection, attempt_id, include_answers=True, include_results=True)
        test_question_row = ensure_attempt_question_exists(connection, attempt_id, test_question_revision_id)
        existing_answer_row = connection.execute(
            """
            SELECT *
            FROM attempt_answers
            WHERE attempt_id = ? AND test_question_revision_id = ?
            """,
            (attempt_id, test_question_revision_id),
        ).fetchone()
        existing_answer_data = (
            parse_json_text(existing_answer_row["answer_data"], default={}) if existing_answer_row is not None else {}
        ) or {}
        answer_payload = normalize_attempt_answer(request, existing_answer_data=existing_answer_data)
        answer_payload["has_visited"] = bool(answer_payload.get("has_visited")) or attempt_answer_has_content(answer_payload)
        answer_payload["last_saved_at"] = now
        upsert_attempt_answer_record(
            connection=connection,
            attempt_id=attempt_id,
            test_question_revision_id=test_question_revision_id,
            question_revision_id=str(test_question_row["question_revision_id"]),
            answer_data=answer_payload,
            is_correct=None,
            selected_option_count=count_attempt_answer_selections(answer_payload),
            earned_score=0.0,
            now=now,
        )
        return build_attempt_payload(connection, attempt_id, include_answers=False, include_results=False)


@app.post("/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: str, request: AttemptSubmitRequest) -> dict[str, object]:
    with build_connection() as connection:
        maybe_auto_submit_attempt(connection, attempt_id)
        attempt_row = connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
        if attempt_row is None:
            raise HTTPException(status_code=404, detail="Attempt not found")
        if str(attempt_row["status"]) == "submitted":
            return build_attempt_payload(connection, attempt_id, include_answers=True, include_results=True)
        if str(attempt_row["status"]) != "in_progress":
            raise HTTPException(status_code=400, detail="Only in-progress attempts can be submitted")
        finalize_attempt_submission(connection, attempt_id, request.answers)
        return build_attempt_payload(connection, attempt_id, include_answers=True, include_results=True)


@app.get("/attempts/{attempt_id}/results")
def get_attempt_results(attempt_id: str) -> dict[str, object]:
    with build_connection() as connection:
        maybe_auto_submit_attempt(connection, attempt_id)
        attempt = build_attempt_payload(connection, attempt_id, include_answers=True, include_results=True)
        if attempt["status"] == "in_progress":
            raise HTTPException(status_code=400, detail="Attempt has not been submitted yet")
        return attempt


@app.get("/admin-activity")
def list_admin_activity() -> list[dict[str, object]]:
    with build_connection() as connection:
        rows = connection.execute(
            """
            SELECT admin_activity_logs.id, admin_activity_logs.admin_id, admins.full_name AS admin_name,
                   admin_activity_logs.action_type, admin_activity_logs.entity_type, admin_activity_logs.entity_id,
                   admin_activity_logs.summary, admin_activity_logs.details, admin_activity_logs.created_at
            FROM admin_activity_logs
            INNER JOIN admins ON admins.id = admin_activity_logs.admin_id
            ORDER BY admin_activity_logs.created_at DESC
            LIMIT 50
            """
        ).fetchall()
        results = []
        for row in rows:
            data = convert_row_to_dict(row) or {}
            data["details"] = parse_json_text(data.get("details"), default={}) or {}
            results.append(data)
        return results


@app.post("/question-banks/validate")
def validate_question_bank(request: QuestionBankValidationRequest) -> dict[str, object]:
    return validate_question_bank_file(request.source_file_path)


@app.post("/question-banks/validate-upload")
async def validate_question_bank_upload(json_file: UploadFile = File(...)) -> dict[str, object]:
    saved_file_path = await save_uploaded_file(json_file, QUESTION_BANK_UPLOAD_DIRECTORY)
    result = validate_question_bank_file(str(saved_file_path))
    result["uploaded_file_path"] = str(saved_file_path)
    return result


@app.post("/question-banks/import")
def import_question_bank(request: LegacyQuestionBankImportRequest) -> dict[str, object]:
    return create_ai_import_batch_endpoint(
        AIImportBatchCreateRequest(source_file_path=request.source_file_path, uploaded_by_admin_id=request.uploaded_by_admin_id)
    )


@app.post("/question-banks/import-upload")
async def import_question_bank_upload(
    uploaded_by_admin_id: str = Form(...),
    default_status: str = Form("draft"),
    json_file: UploadFile = File(...),
) -> dict[str, object]:
    del default_status
    saved_file_path = await save_uploaded_file(json_file, QUESTION_BANK_UPLOAD_DIRECTORY)
    return import_question_bank(LegacyQuestionBankImportRequest(source_file_path=str(saved_file_path), uploaded_by_admin_id=uploaded_by_admin_id))


@app.get("/question-banks/imports")
def list_question_bank_imports() -> list[dict[str, object]]:
    return list_ai_import_batches()


@app.get("/question-banks/imports/{question_bank_import_id}")
def get_question_bank_import_review(question_bank_import_id: str) -> dict[str, object]:
    return get_ai_import_batch_endpoint(question_bank_import_id)


@app.patch("/question-banks/imports/{question_bank_import_id}/payload")
def update_question_bank_import_review_payload(question_bank_import_id: str, request: AIImportBatchPayloadUpdateRequest) -> dict[str, object]:
    return update_ai_import_batch_payload_endpoint(question_bank_import_id, request)


@app.patch("/question-banks/imports/{question_bank_import_id}/questions")
def update_question_bank_import_review_question(
    question_bank_import_id: str,
    request: AIImportBatchQuestionUpdateRequest,
) -> dict[str, object]:
    with build_connection() as connection:
        ensure_admin_exists(connection, request.updated_by_admin_id)
        return update_ai_import_batch_question(
            connection,
            question_bank_import_id,
            request.updated_by_admin_id,
            request.concept_index,
            request.question_index,
            request.question,
        )


@app.post("/question-banks/imports/{question_bank_import_id}/questions")
def insert_question_bank_import_review_question(
    question_bank_import_id: str,
    request: AIImportBatchQuestionInsertRequest,
) -> dict[str, object]:
    with build_connection() as connection:
        ensure_admin_exists(connection, request.updated_by_admin_id)
        return insert_ai_import_batch_question(
            connection,
            question_bank_import_id,
            request.updated_by_admin_id,
            request.concept_index,
            request.insert_at_question_index,
            request.question,
        )


@app.delete("/question-banks/imports/{question_bank_import_id}/questions")
def delete_question_bank_import_review_question(
    question_bank_import_id: str,
    updated_by_admin_id: str,
    concept_index: int,
    question_index: int,
) -> dict[str, object]:
    with build_connection() as connection:
        ensure_admin_exists(connection, updated_by_admin_id)
        return delete_ai_import_batch_question(
            connection,
            question_bank_import_id,
            updated_by_admin_id,
            concept_index,
            question_index,
        )


@app.post("/question-banks/imports/{question_bank_import_id}/approve")
def approve_question_bank_import_review(question_bank_import_id: str, request: LegacyQuestionBankApproveRequest) -> dict[str, object]:
    return materialize_ai_import_batch_endpoint(
        question_bank_import_id,
        AIImportBatchMaterializeRequest(
            approved_by_admin_id=request.approved_by_admin_id,
            topic_id=request.topic_id,
            default_lifecycle_status="active" if request.auto_publish else "draft",
            auto_publish=request.auto_publish,
        ),
    )


def validate_question_request_shape(
    question_format: str,
    options: list[OptionInput],
    numeric_answer: NumericAnswerInput | None,
    columns: MatchColumnsInput | None,
    answer: OptionAnswerInput | NumericTransportAnswerInput | PairAnswerInput,
) -> None:
    if question_format not in QUESTION_FORMAT_VALUES:
        raise ValueError("Unsupported question format")
    if question_format in {"mcq", "msq"}:
        if len(options) != 4:
            raise ValueError("Each MCQ/MSQ revision must have exactly 4 options")
        labels = [option.label for option in options]
        if labels != ["A", "B", "C", "D"]:
            raise ValueError("Option labels must be A, B, C, D in order")
        if numeric_answer is not None or columns is not None:
            raise ValueError("MCQ/MSQ revisions cannot include numeric or match blocks")
        if answer.type != "option_labels":
            raise ValueError("MCQ/MSQ revisions must use option_labels answers")
        selected = {label.strip().upper() for label in answer.value}
        if question_format == "mcq" and len(selected) != 1:
            raise ValueError("MCQ revisions must have exactly one correct answer")
        if question_format == "msq" and len(selected) < 2:
            raise ValueError("MSQ revisions must have at least two correct answers")
        return
    if question_format == "nat":
        if options or columns is not None or numeric_answer is None:
            raise ValueError("NAT revisions require numeric_answer and forbid options/columns")
        if answer.type != "numeric":
            raise ValueError("NAT revisions must use numeric answers")
        return
    if question_format == "match":
        if options or numeric_answer is not None or columns is None:
            raise ValueError("Match revisions require columns and forbid options/numeric_answer")
        if answer.type != "pairs":
            raise ValueError("Match revisions must use pair answers")


def ensure_default_concept_for_topic(connection, topic_id: str) -> str:
    ensure_topic_exists(connection, topic_id)
    row = connection.execute(
        """
        SELECT id
        FROM concepts
        WHERE topic_id = ?
        ORDER BY display_order, name
        LIMIT 1
        """,
        (topic_id,),
    ).fetchone()
    if row is not None:
        return str(row["id"])
    concept_id = build_identifier()
    now = build_timestamp()
    connection.execute(
        """
        INSERT INTO concepts (id, topic_id, name, display_order, status, source_concept_key, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (concept_id, topic_id, "General", 1, "active", "default-general", now, now),
    )
    return concept_id


def build_legacy_option_answer(options: list[OptionInput]) -> OptionAnswerInput:
    return OptionAnswerInput(value=[option.label for option in options if option.is_correct])


def build_legacy_question_answer(
    question_format: str,
    options: list[OptionInput],
    numeric_answer: NumericAnswerInput | None,
    columns: MatchColumnsInput | None,
    provided_answer: OptionAnswerInput | NumericTransportAnswerInput | PairAnswerInput | None,
) -> OptionAnswerInput | NumericTransportAnswerInput | PairAnswerInput:
    if provided_answer is not None:
        return provided_answer
    if question_format in {"mcq", "msq"}:
        return build_legacy_option_answer(options)
    if question_format == "nat":
        if numeric_answer is None:
            raise HTTPException(status_code=400, detail="NAT questions require numeric_answer")
        return NumericTransportAnswerInput(
            exact_value=numeric_answer.exact_value,
            tolerance=numeric_answer.tolerance,
            unit=numeric_answer.unit,
        )
    if columns is None:
        raise HTTPException(status_code=400, detail="Match questions require columns")
    return PairAnswerInput(value={item.label: item.matches for item in columns.items_a})


def apply_legacy_question_aliases(item_data: dict[str, Any], include_answers: bool) -> dict[str, Any]:
    active_revision = item_data.get("current_published_revision") or item_data.get("current_draft_revision") or {}
    item_data["question_format"] = active_revision.get("format")
    item_data["text"] = active_revision.get("text")
    item_data["difficulty"] = active_revision.get("difficulty")
    item_data["type"] = active_revision.get("type")
    item_data["status"] = item_data.get("lifecycle_status")
    item_data["version"] = active_revision.get("revision_number")
    item_data["options"] = active_revision.get("options", [])
    item_data["numeric_answer"] = active_revision.get("numeric_answer")
    item_data["columns"] = active_revision.get("columns")
    item_data["figures"] = active_revision.get("figures", [])
    if active_revision.get("format") == "mcq":
        item_data["minimum_selection_count"] = 1
        item_data["maximum_selection_count"] = 1
    elif active_revision.get("format") == "msq":
        selected_count = len((active_revision.get("answer") or {}).get("value", [])) if include_answers else 2
        item_data["minimum_selection_count"] = max(1, selected_count)
        item_data["maximum_selection_count"] = max(item_data["minimum_selection_count"], 4)
    else:
        item_data["minimum_selection_count"] = 1
        item_data["maximum_selection_count"] = 1
    return item_data


def question_request_to_payload(request: QuestionRevisionCreateRequest) -> dict[str, Any]:
    payload = {
        "format": request.format,
        "difficulty": request.difficulty,
        "type": request.type,
        "text": request.text.strip(),
        "image": request.image_asset_id,
        "answer": request.answer.model_dump(),
    }
    if request.options:
        payload["options"] = [option.model_dump() for option in request.options]
    if request.numeric_answer:
        payload["numeric_answer"] = request.numeric_answer.model_dump()
    if request.columns:
        payload["columns"] = request.columns.model_dump()
    return payload


def question_update_to_payload(request: QuestionRevisionUpdateRequest) -> dict[str, Any]:
    payload = {
        "format": request.format,
        "difficulty": request.difficulty,
        "type": request.type,
        "text": request.text.strip(),
        "image": request.image_asset_id,
        "answer": request.answer.model_dump(),
    }
    if request.options:
        payload["options"] = [option.model_dump() for option in request.options]
    if request.numeric_answer:
        payload["numeric_answer"] = request.numeric_answer.model_dump()
    if request.columns:
        payload["columns"] = request.columns.model_dump()
    return payload


def store_revision(
    connection,
    revision_id: str,
    question_item_id: str,
    revision_number: int,
    parent_revision_id: str | None,
    created_by_admin_id: str,
    revision_status: str,
    question: dict[str, Any],
    created_at: str,
) -> None:
    answer_payload = question["answer"]
    scoring_payload = build_scoring_payload(question)
    connection.execute(
        """
        INSERT INTO question_revisions (
            id, question_item_id, revision_number, parent_revision_id, created_by_admin_id, format, difficulty, type,
            text, explanation, image_asset_id, answer_type, answer_payload, scoring_payload, revision_status,
            published_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            revision_id,
            question_item_id,
            revision_number,
            parent_revision_id or None,
            created_by_admin_id,
            question["format"],
            question["difficulty"],
            question["type"],
            question["text"],
            None,
            question.get("image"),
            answer_payload["type"],
            build_json_text(answer_payload),
            build_json_text(scoring_payload),
            revision_status,
            created_at if revision_status == "published" else None,
            created_at,
            created_at,
        ),
    )
    if question["format"] in {"mcq", "msq"}:
        correct_labels = {label.strip().upper() for label in answer_payload.get("value", [])}
        for display_order, option in enumerate(question.get("options", []), start=1):
            connection.execute(
                """
                INSERT INTO question_revision_options (
                    id, question_revision_id, label, text, is_correct, display_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    build_identifier(),
                    revision_id,
                    option["label"],
                    option["text"].strip(),
                    1 if option["label"] in correct_labels else 0,
                    display_order,
                    created_at,
                    created_at,
                ),
            )
        return
    if question["format"] == "nat":
        numeric_answer = answer_payload
        connection.execute(
            """
            INSERT INTO question_revision_numeric_answers (
                id, question_revision_id, exact_value, tolerance, unit, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_identifier(),
                revision_id,
                numeric_answer["exact_value"],
                numeric_answer["tolerance"],
                numeric_answer.get("unit", ""),
                created_at,
                created_at,
            ),
        )
        return
    if question["format"] == "match":
        columns = question["columns"]
        match_set_id = build_identifier()
        connection.execute(
            """
            INSERT INTO question_revision_match_sets (
                id, question_revision_id, a_heading, b_heading, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                match_set_id,
                revision_id,
                columns["a_heading"],
                columns["b_heading"],
                created_at,
                created_at,
            ),
        )
        for display_order, item in enumerate(columns["items_a"], start=1):
            connection.execute(
                """
                INSERT INTO question_revision_match_left_items (
                    id, match_set_id, label, text, matches_right_label, display_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    build_identifier(),
                    match_set_id,
                    item["label"],
                    item["text"],
                    item["matches"],
                    display_order,
                    created_at,
                    created_at,
                ),
            )
        for display_order, item in enumerate(columns["items_b"], start=1):
            connection.execute(
                """
                INSERT INTO question_revision_match_right_items (
                    id, match_set_id, label, text, display_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    build_identifier(),
                    match_set_id,
                    item["label"],
                    item["text"],
                    display_order,
                    created_at,
                    created_at,
                ),
            )


def build_scoring_payload(question: dict[str, Any]) -> dict[str, Any]:
    answer_payload = question["answer"]
    if question["format"] in {"mcq", "msq"}:
        return {"mode": "exact_option_set", "correct_labels": answer_payload["value"]}
    if question["format"] == "nat":
        return {
            "mode": "numeric_tolerance",
            "exact_value": answer_payload["exact_value"],
            "tolerance": answer_payload["tolerance"],
            "unit": answer_payload.get("unit", ""),
        }
    return {"mode": "exact_pairs", "pairs": answer_payload["value"]}


def build_question_revision_payload(connection, revision_id: str, include_answers: bool) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT question_revisions.*, concepts.id AS concept_id, concepts.name AS concept_name,
               topics.id AS topic_id, topics.name AS topic_name,
               chapters.id AS chapter_id, chapters.name AS chapter_name, chapters.chapter_number,
               subjects.id AS subject_id, subjects.name AS subject_name, subjects.grade AS subject_grade, subjects.board AS subject_board
        FROM question_revisions
        INNER JOIN question_items ON question_items.id = question_revisions.question_item_id
        INNER JOIN concepts ON concepts.id = question_items.concept_id
        INNER JOIN topics ON topics.id = concepts.topic_id
        INNER JOIN chapters ON chapters.id = topics.chapter_id
        INNER JOIN subjects ON subjects.id = chapters.subject_id
        WHERE question_revisions.id = ?
        """,
        (revision_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Question revision not found")
    data = convert_row_to_dict(row) or {}
    data["answer"] = parse_json_text(data.get("answer_payload"), default={}) or {}
    data["scoring"] = parse_json_text(data.get("scoring_payload"), default={}) or {}
    data.pop("answer_payload", None)
    data.pop("scoring_payload", None)
    if data["format"] in {"mcq", "msq"}:
        option_rows = connection.execute(
            """
            SELECT id, label, text, is_correct, display_order
            FROM question_revision_options
            WHERE question_revision_id = ?
            ORDER BY display_order
            """,
            (revision_id,),
        ).fetchall()
        options = []
        for option_row in option_rows:
            option_data = convert_row_to_dict(option_row) or {}
            if not include_answers:
                option_data.pop("is_correct", None)
            options.append(option_data)
        data["options"] = options
    elif data["format"] == "nat":
        numeric_row = connection.execute(
            """
            SELECT exact_value, tolerance, unit
            FROM question_revision_numeric_answers
            WHERE question_revision_id = ?
            """,
            (revision_id,),
        ).fetchone()
        if numeric_row is not None:
            numeric_data = convert_row_to_dict(numeric_row) or {}
            if not include_answers:
                numeric_data.pop("exact_value", None)
                numeric_data.pop("tolerance", None)
            data["numeric_answer"] = numeric_data
    elif data["format"] == "match":
        match_set_row = connection.execute(
            "SELECT * FROM question_revision_match_sets WHERE question_revision_id = ?",
            (revision_id,),
        ).fetchone()
        if match_set_row is not None:
            match_set_data = convert_row_to_dict(match_set_row) or {}
            left_rows = connection.execute(
                """
                SELECT label, text, matches_right_label, display_order
                FROM question_revision_match_left_items
                WHERE match_set_id = ?
                ORDER BY display_order
                """,
                (match_set_data["id"],),
            ).fetchall()
            right_rows = connection.execute(
                """
                SELECT label, text, display_order
                FROM question_revision_match_right_items
                WHERE match_set_id = ?
                ORDER BY display_order
                """,
                (match_set_data["id"],),
            ).fetchall()
            items_a = []
            for left_row in left_rows:
                left_data = convert_row_to_dict(left_row) or {}
                if include_answers:
                    left_data["matches"] = left_data.pop("matches_right_label")
                else:
                    left_data.pop("matches_right_label", None)
                items_a.append(left_data)
            data["columns"] = {
                "a_heading": match_set_data["a_heading"],
                "b_heading": match_set_data["b_heading"],
                "items_a": items_a,
                "items_b": convert_rows_to_dicts(right_rows),
            }
    data["figures"] = []
    if data.get("image_asset_id"):
        figure_row = connection.execute(
            """
            SELECT id, name, file_path, page_number, caption_text
            FROM extracted_assets
            WHERE id = ?
            """,
            (data["image_asset_id"],),
        ).fetchone()
        if figure_row is not None:
            data["figures"] = [convert_row_to_dict(figure_row) or {}]
    if not include_answers:
        data.pop("answer", None)
        data.pop("scoring", None)
    return data


def build_question_item_payload(connection, question_item_id: str, include_answers: bool) -> dict[str, Any]:
    item_row = connection.execute(
        """
        SELECT question_items.*, concepts.name AS concept_name, topics.id AS topic_id, topics.name AS topic_name
        FROM question_items
        INNER JOIN concepts ON concepts.id = question_items.concept_id
        INNER JOIN topics ON topics.id = concepts.topic_id
        WHERE question_items.id = ? AND question_items.is_deleted = 0
        """,
        (question_item_id,),
    ).fetchone()
    if item_row is None:
        raise HTTPException(status_code=404, detail="Question item not found")
    item_data = convert_row_to_dict(item_row) or {}
    if item_data.get("current_draft_revision_id"):
        item_data["current_draft_revision"] = build_question_revision_payload(connection, str(item_data["current_draft_revision_id"]), include_answers=include_answers)
    else:
        item_data["current_draft_revision"] = None
    if item_data.get("current_published_revision_id"):
        item_data["current_published_revision"] = build_question_revision_payload(connection, str(item_data["current_published_revision_id"]), include_answers=include_answers)
    else:
        item_data["current_published_revision"] = None
    revision_rows = connection.execute(
        """
        SELECT id
        FROM question_revisions
        WHERE question_item_id = ?
        ORDER BY revision_number DESC
        """,
        (question_item_id,),
    ).fetchall()
    item_data["revisions"] = [build_question_revision_payload(connection, str(row["id"]), include_answers=include_answers) for row in revision_rows]
    return apply_legacy_question_aliases(item_data, include_answers=include_answers)


def select_question_items_for_test(
    connection,
    subject_id: str,
    chapter_id: str | None,
    topic_id: str | None,
    concept_ids: list[str],
    format_filters: list[str],
    difficulty_filters: list[str],
    type_filters: list[str],
    question_count: int,
    hard_question_count: int,
) -> list[sqlite3.Row]:
    import sqlite3

    query = """
        SELECT
            question_items.id AS question_item_id,
            question_revisions.id AS question_revision_id,
            question_revisions.difficulty,
            question_revisions.format,
            question_revisions.type,
            chapters.id AS chapter_id,
            topics.id AS topic_id,
            concepts.id AS concept_id
        FROM question_items
        INNER JOIN question_revisions ON question_revisions.id = question_items.current_published_revision_id
        INNER JOIN concepts ON concepts.id = question_items.concept_id
        INNER JOIN topics ON topics.id = concepts.topic_id
        INNER JOIN chapters ON chapters.id = topics.chapter_id
        WHERE question_items.is_deleted = 0
          AND question_items.lifecycle_status = 'active'
          AND question_revisions.revision_status = 'published'
          AND chapters.subject_id = ?
    """
    parameters: list[object] = [subject_id]
    if chapter_id:
        query += " AND chapters.id = ?"
        parameters.append(chapter_id)
    if topic_id:
        query += " AND topics.id = ?"
        parameters.append(topic_id)
    if concept_ids:
        placeholders = ", ".join("?" for _ in concept_ids)
        query += f" AND concepts.id IN ({placeholders})"
        parameters.extend(concept_ids)
    if format_filters:
        placeholders = ", ".join("?" for _ in format_filters)
        query += f" AND question_revisions.format IN ({placeholders})"
        parameters.extend(format_filters)
    if difficulty_filters:
        placeholders = ", ".join("?" for _ in difficulty_filters)
        query += f" AND question_revisions.difficulty IN ({placeholders})"
        parameters.extend(difficulty_filters)
    if type_filters:
        placeholders = ", ".join("?" for _ in type_filters)
        query += f" AND question_revisions.type IN ({placeholders})"
        parameters.extend(type_filters)
    rows = connection.execute(query, parameters).fetchall()
    if len(rows) < question_count:
        raise HTTPException(status_code=400, detail="Not enough active published questions in the selected scope")
    hard_rows = [row for row in rows if str(row["difficulty"]) == "hard"]
    if len(hard_rows) < hard_question_count:
        raise HTTPException(status_code=400, detail="Not enough hard active published questions in the selected scope")
    random_generator = random.Random()
    random_generator.shuffle(hard_rows)
    selected_rows = hard_rows[:hard_question_count]
    selected_item_ids = {str(row["question_item_id"]) for row in selected_rows}
    remaining_rows = [row for row in rows if str(row["question_item_id"]) not in selected_item_ids]
    random_generator.shuffle(remaining_rows)
    selected_rows.extend(remaining_rows[: max(0, question_count - len(selected_rows))])
    random_generator.shuffle(selected_rows)
    return selected_rows


def select_specific_question_items_for_test(
    connection,
    subject_id: str,
    chapter_id: str | None,
    topic_id: str | None,
    concept_ids: list[str],
    question_item_ids: list[str],
) -> list[Any]:
    placeholders = ", ".join("?" for _ in question_item_ids)
    rows = connection.execute(
        f"""
        SELECT
            question_items.id AS question_item_id,
            question_items.lifecycle_status,
            question_revisions.id AS question_revision_id,
            question_revisions.difficulty,
            chapters.subject_id,
            chapters.id AS chapter_id,
            topics.id AS topic_id,
            concepts.id AS concept_id
        FROM question_items
        INNER JOIN question_revisions ON question_revisions.id = question_items.current_published_revision_id
        INNER JOIN concepts ON concepts.id = question_items.concept_id
        INNER JOIN topics ON topics.id = concepts.topic_id
        INNER JOIN chapters ON chapters.id = topics.chapter_id
        WHERE question_items.id IN ({placeholders}) AND question_items.is_deleted = 0
        """,
        question_item_ids,
    ).fetchall()
    if len(rows) != len(set(question_item_ids)):
        raise HTTPException(status_code=400, detail="One or more selected questions were not found")
    row_map = {str(row["question_item_id"]): row for row in rows}
    ordered_rows = []
    for question_item_id in question_item_ids:
        row = row_map.get(question_item_id)
        if row is None:
            raise HTTPException(status_code=400, detail="One or more selected questions were not found")
        if str(row["subject_id"]) != subject_id:
            raise HTTPException(status_code=400, detail="Selected questions must belong to the selected subject")
        if chapter_id and str(row["chapter_id"]) != chapter_id:
            raise HTTPException(status_code=400, detail="Selected questions must belong to the selected chapter")
        if topic_id and str(row["topic_id"]) != topic_id:
            raise HTTPException(status_code=400, detail="Selected questions must belong to the selected topic")
        if concept_ids and str(row["concept_id"]) not in set(concept_ids):
            raise HTTPException(status_code=400, detail="Selected questions must belong to the selected concepts")
        if str(row["lifecycle_status"]) != "active":
            raise HTTPException(status_code=400, detail="Only active published questions can be used in a test")
        ordered_rows.append(row)
    return ordered_rows


def build_test_payload(connection, test_id: str, include_answers: bool) -> dict[str, object]:
    test_row = connection.execute(
        """
        SELECT tests.*, subjects.name AS subject_name, subjects.grade AS subject_grade, subjects.board AS subject_board,
               chapters.name AS chapter_name, chapters.chapter_number
        FROM tests
        INNER JOIN subjects ON subjects.id = tests.subject_id
        LEFT JOIN chapters ON chapters.id = tests.chapter_id
        WHERE tests.id = ?
        """,
        (test_id,),
    ).fetchone()
    if test_row is None:
        raise HTTPException(status_code=404, detail="Test not found")
    test_data = convert_row_to_dict(test_row) or {}
    rows = connection.execute(
        """
        SELECT id, question_item_id, question_revision_id, display_order
        FROM test_question_revisions
        WHERE test_id = ?
        ORDER BY display_order
        """,
        (test_id,),
    ).fetchall()
    test_data["questions"] = []
    for row in rows:
        revision_payload = build_question_revision_payload(connection, str(row["question_revision_id"]), include_answers=include_answers)
        revision_payload["test_question_revision_id"] = str(row["id"])
        revision_payload["question_item_id"] = str(row["question_item_id"])
        revision_payload["display_order"] = row["display_order"]
        test_data["questions"].append(revision_payload)
    test_data["time_limit_minutes"] = calculate_attempt_duration_minutes(len(test_data["questions"]))
    return test_data


def build_attempt_payload(connection, attempt_id: str, include_answers: bool, include_results: bool) -> dict[str, object]:
    attempt_row = connection.execute(
        """
        SELECT attempts.*, students.full_name AS student_name, students.roll_number AS student_roll_number,
               students.email AS student_email, tests.title AS test_title
        FROM attempts
        INNER JOIN students ON students.id = attempts.student_id
        INNER JOIN tests ON tests.id = attempts.test_id
        WHERE attempts.id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if attempt_row is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    attempt_data = convert_row_to_dict(attempt_row) or {}
    attempt_data["test"] = build_test_payload(connection, str(attempt_row["test_id"]), include_answers=include_answers)
    attempt_data["time_limit_minutes"] = int(attempt_data["test"]["time_limit_minutes"])
    attempt_data["expires_at"] = build_attempt_expiration(attempt_data.get("started_at"), attempt_data["time_limit_minutes"])
    attempt_data["remaining_seconds"] = calculate_attempt_remaining_seconds(attempt_data["expires_at"])
    answer_rows = connection.execute(
        """
        SELECT *
        FROM attempt_answers
        WHERE attempt_id = ?
        ORDER BY created_at
        """,
        (attempt_id,),
    ).fetchall()
    answers = []
    for answer_row in answer_rows:
        answer_data = convert_row_to_dict(answer_row) or {}
        answer_data["answer_data"] = normalize_attempt_answer(
            None,
            existing_answer_data=parse_json_text(answer_data.get("answer_data"), default={}) or {},
        )
        answer_data["answer_state"] = derive_attempt_answer_state(answer_data["answer_data"])
        if not include_results:
            answer_data.pop("is_correct", None)
            answer_data.pop("earned_score", None)
        answers.append(answer_data)
    attempt_data["answers"] = answers
    answer_by_test_question_revision_id = {str(answer["test_question_revision_id"]): answer for answer in answers}
    for question in attempt_data["test"]["questions"]:
        linked_answer = answer_by_test_question_revision_id.get(str(question["test_question_revision_id"]), {})
        question["answer_data"] = linked_answer.get("answer_data", build_blank_attempt_answer_data())
        question["is_answered"] = attempt_answer_has_content(question["answer_data"])
        question["is_marked_for_review"] = bool(question["answer_data"].get("is_marked_for_review"))
        question["has_visited"] = bool(question["answer_data"].get("has_visited"))
        question["answer_state"] = linked_answer.get("answer_state", derive_attempt_answer_state(question["answer_data"]))
        if include_results:
            question["is_correct"] = bool(linked_answer.get("is_correct"))
            question["earned_score"] = linked_answer.get("earned_score", 0.0)
    attempt_data["question_state_summary"] = build_attempt_question_state_summary(attempt_data["test"]["questions"])
    attempt_data["answered_question_count"] = (
        attempt_data["question_state_summary"]["answered"] + attempt_data["question_state_summary"]["answered_and_marked_for_review"]
    )
    attempt_data["marked_for_review_count"] = (
        attempt_data["question_state_summary"]["marked_for_review"]
        + attempt_data["question_state_summary"]["answered_and_marked_for_review"]
    )
    return attempt_data


def build_blank_attempt_answer_data(
    *,
    has_visited: bool = False,
    is_marked_for_review: bool = False,
    spent_seconds: int = 0,
    last_saved_at: str | None = None,
) -> dict[str, Any]:
    return {
        "option_labels": [],
        "numeric_value": None,
        "pair_mapping": {},
        "is_marked_for_review": is_marked_for_review,
        "has_visited": has_visited,
        "spent_seconds": max(0, int(spent_seconds)),
        "last_saved_at": last_saved_at,
    }


def normalize_attempt_answer(
    answer: AttemptAnswerSubmission | AttemptAnswerUpdateRequest | None,
    existing_answer_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_blank_attempt_answer_data()
    if existing_answer_data:
        payload["option_labels"] = [str(label).strip().upper() for label in existing_answer_data.get("option_labels", []) if str(label).strip()]
        payload["numeric_value"] = existing_answer_data.get("numeric_value")
        payload["pair_mapping"] = {
            str(key): str(value)
            for key, value in (existing_answer_data.get("pair_mapping", {}) or {}).items()
            if str(value).strip()
        }
        payload["is_marked_for_review"] = bool(existing_answer_data.get("is_marked_for_review"))
        payload["has_visited"] = bool(existing_answer_data.get("has_visited"))
        payload["spent_seconds"] = max(0, int(existing_answer_data.get("spent_seconds") or 0))
        payload["last_saved_at"] = existing_answer_data.get("last_saved_at")
    if answer is None:
        payload["has_visited"] = bool(payload["has_visited"]) or attempt_answer_has_content(payload)
        return payload
    payload["option_labels"] = sorted({label.strip().upper() for label in answer.option_labels if label.strip()})
    payload["numeric_value"] = answer.numeric_value
    payload["pair_mapping"] = {str(key): str(value) for key, value in answer.pair_mapping.items() if str(value).strip()}
    payload["is_marked_for_review"] = bool(answer.is_marked_for_review)
    payload["has_visited"] = bool(answer.has_visited)
    payload["spent_seconds"] = max(0, int(answer.spent_seconds))
    payload["has_visited"] = bool(payload["has_visited"]) or attempt_answer_has_content(payload)
    return payload


def attempt_answer_has_content(answer_payload: dict[str, Any]) -> bool:
    if answer_payload.get("numeric_value") is not None:
        return True
    if answer_payload.get("option_labels"):
        return True
    return bool(answer_payload.get("pair_mapping"))


def count_attempt_answer_selections(answer_payload: dict[str, Any]) -> int:
    if answer_payload.get("numeric_value") is not None:
        return 1
    if answer_payload.get("option_labels"):
        return len(answer_payload["option_labels"])
    return len(answer_payload.get("pair_mapping", {}))


def derive_attempt_answer_state(answer_payload: dict[str, Any]) -> str:
    is_answered = attempt_answer_has_content(answer_payload)
    is_marked_for_review = bool(answer_payload.get("is_marked_for_review"))
    if is_marked_for_review and is_answered:
        return "answered_and_marked_for_review"
    if is_marked_for_review:
        return "marked_for_review"
    if is_answered:
        return "answered"
    if answer_payload.get("has_visited"):
        return "not_answered"
    return "not_visited"


def build_attempt_question_state_summary(questions: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(questions),
        "not_visited": 0,
        "not_answered": 0,
        "answered": 0,
        "marked_for_review": 0,
        "answered_and_marked_for_review": 0,
    }
    for question in questions:
        answer_state = str(question.get("answer_state") or "not_visited")
        if answer_state not in summary:
            summary[answer_state] = 0
        summary[answer_state] += 1
    return summary


def calculate_attempt_duration_minutes(question_count: int) -> int:
    question_based_duration = question_count * SECONDS_PER_QUESTION
    return max(DEFAULT_ATTEMPT_DURATION_MINUTES, (question_based_duration + 59) // 60)


def build_attempt_expiration(started_at: str | None, time_limit_minutes: int) -> str | None:
    if not started_at:
        return None
    return (datetime.fromisoformat(started_at) + timedelta(minutes=time_limit_minutes)).isoformat()


def calculate_attempt_remaining_seconds(expires_at: str | None) -> int | None:
    if not expires_at:
        return None
    remaining_seconds = int((datetime.fromisoformat(expires_at) - datetime.now(datetime.fromisoformat(expires_at).tzinfo)).total_seconds())
    return max(0, remaining_seconds)


def ensure_attempt_question_exists(connection, attempt_id: str, test_question_revision_id: str):
    attempt_row = connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    if attempt_row is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    test_question_row = connection.execute(
        """
        SELECT id, question_revision_id
        FROM test_question_revisions
        WHERE id = ? AND test_id = ?
        """,
        (test_question_revision_id, attempt_row["test_id"]),
    ).fetchone()
    if test_question_row is None:
        raise HTTPException(status_code=404, detail="Question is not part of this attempt")
    return test_question_row


def upsert_attempt_answer_record(
    connection,
    attempt_id: str,
    test_question_revision_id: str,
    question_revision_id: str,
    answer_data: dict[str, Any],
    is_correct: bool | None,
    selected_option_count: int,
    earned_score: float,
    now: str,
) -> None:
    existing_row = connection.execute(
        """
        SELECT id, created_at
        FROM attempt_answers
        WHERE attempt_id = ? AND test_question_revision_id = ?
        """,
        (attempt_id, test_question_revision_id),
    ).fetchone()
    if existing_row is None:
        connection.execute(
            """
            INSERT INTO attempt_answers (
                id, attempt_id, test_question_revision_id, question_revision_id, answer_data, is_correct,
                selected_option_count, earned_score, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_identifier(),
                attempt_id,
                test_question_revision_id,
                question_revision_id,
                build_json_text(answer_data),
                None if is_correct is None else 1 if is_correct else 0,
                selected_option_count,
                earned_score,
                now,
                now,
            ),
        )
        return
    connection.execute(
        """
        UPDATE attempt_answers
        SET question_revision_id = ?, answer_data = ?, is_correct = ?, selected_option_count = ?, earned_score = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            question_revision_id,
            build_json_text(answer_data),
            None if is_correct is None else 1 if is_correct else 0,
            selected_option_count,
            earned_score,
            now,
            existing_row["id"],
        ),
    )


def finalize_attempt_submission(connection, attempt_id: str, answers: list[AttemptAnswerSubmission] | None = None) -> None:
    now = build_timestamp()
    attempt_row = connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    if attempt_row is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt_row["status"]) != "in_progress":
        return
    test_question_rows = connection.execute(
        """
        SELECT id, question_revision_id
        FROM test_question_revisions
        WHERE test_id = ?
        ORDER BY display_order
        """,
        (attempt_row["test_id"],),
    ).fetchall()
    existing_answer_rows = connection.execute(
        """
        SELECT *
        FROM attempt_answers
        WHERE attempt_id = ?
        """,
        (attempt_id,),
    ).fetchall()
    existing_answer_lookup = {str(row["test_question_revision_id"]): row for row in existing_answer_rows}
    submitted_lookup = {answer.test_question_revision_id: answer for answer in answers or []}
    correct_answer_count = 0
    wrong_answer_count = 0
    total_earned_score = 0.0
    for test_question_row in test_question_rows:
        test_question_revision_id = str(test_question_row["id"])
        existing_answer_row = existing_answer_lookup.get(test_question_revision_id)
        existing_answer_data = (
            parse_json_text(existing_answer_row["answer_data"], default={}) if existing_answer_row is not None else {}
        ) or {}
        answer_payload = normalize_attempt_answer(
            submitted_lookup.get(test_question_revision_id),
            existing_answer_data=existing_answer_data,
        )
        answer_payload["has_visited"] = bool(answer_payload.get("has_visited")) or attempt_answer_has_content(answer_payload)
        answer_payload["last_saved_at"] = now
        revision_payload = build_question_revision_payload(connection, str(test_question_row["question_revision_id"]), include_answers=True)
        is_correct, selected_option_count, earned_score = score_attempt_answer(revision_payload, answer_payload)
        if is_correct:
            correct_answer_count += 1
        else:
            wrong_answer_count += 1
        total_earned_score += earned_score
        upsert_attempt_answer_record(
            connection=connection,
            attempt_id=attempt_id,
            test_question_revision_id=test_question_revision_id,
            question_revision_id=revision_payload["id"],
            answer_data=answer_payload,
            is_correct=is_correct,
            selected_option_count=selected_option_count,
            earned_score=earned_score,
            now=now,
        )
    total_question_count = len(test_question_rows)
    score = round((total_earned_score / total_question_count) * 100, 2) if total_question_count else 0.0
    connection.execute(
        """
        UPDATE attempts
        SET status = ?, score = ?, correct_answer_count = ?, wrong_answer_count = ?, submitted_at = ?, updated_at = ?
        WHERE id = ?
        """,
        ("submitted", score, correct_answer_count, wrong_answer_count, now, now, attempt_id),
    )


def maybe_auto_submit_attempt(connection, attempt_id: str) -> dict[str, Any]:
    attempt_row = connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    if attempt_row is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    attempt_data = convert_row_to_dict(attempt_row) or {}
    if str(attempt_data["status"]) != "in_progress":
        return attempt_data
    test_data = build_test_payload(connection, str(attempt_data["test_id"]), include_answers=False)
    expires_at = build_attempt_expiration(attempt_data.get("started_at"), int(test_data["time_limit_minutes"]))
    if calculate_attempt_remaining_seconds(expires_at) != 0:
        return attempt_data
    finalize_attempt_submission(connection, attempt_id)
    refreshed_row = connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    return convert_row_to_dict(refreshed_row) or {}


def score_attempt_answer(question_revision: dict[str, Any], answer_payload: dict[str, Any]) -> tuple[bool, int, float]:
    if question_revision["format"] in {"mcq", "msq"}:
        correct_labels = {option["label"] for option in question_revision["options"] if option.get("is_correct")}
        selected_labels = set(answer_payload["option_labels"])
        is_correct = selected_labels == correct_labels
        return is_correct, len(selected_labels), 1.0 if is_correct else 0.0
    if question_revision["format"] == "nat":
        numeric_value = answer_payload.get("numeric_value")
        if numeric_value is None:
            return False, 0, 0.0
        numeric_answer = question_revision.get("numeric_answer") or {}
        exact_value = float(numeric_answer["exact_value"])
        tolerance = float(numeric_answer["tolerance"])
        is_correct = abs(float(numeric_value) - exact_value) <= tolerance
        return is_correct, 1, 1.0 if is_correct else 0.0
    expected_pairs = {item["label"]: item["matches"] for item in question_revision.get("columns", {}).get("items_a", [])}
    actual_pairs = answer_payload.get("pair_mapping", {})
    is_correct = actual_pairs == expected_pairs
    return is_correct, len(actual_pairs), 1.0 if is_correct else 0.0


def get_or_create_student(connection, full_name: str, roll_number: str | None, email: str | None) -> dict[str, object]:
    normalized_name = full_name.strip()
    normalized_roll_number = roll_number.strip() if roll_number else None
    normalized_email = email.strip().lower() if email else None
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Student name is required")
    student_row = None
    if normalized_email:
        student_row = connection.execute("SELECT * FROM students WHERE lower(email) = ?", (normalized_email,)).fetchone()
    elif normalized_roll_number:
        student_row = connection.execute(
            """
            SELECT *
            FROM students
            WHERE full_name = ? AND roll_number = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (normalized_name, normalized_roll_number),
        ).fetchone()
    now = build_timestamp()
    if student_row is None:
        student_id = build_identifier()
        connection.execute(
            """
            INSERT INTO students (id, email, full_name, roll_number, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, normalized_email, normalized_name, normalized_roll_number, 1, now, now),
        )
        student_row = connection.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    else:
        connection.execute(
            """
            UPDATE students
            SET email = COALESCE(?, email), full_name = ?, roll_number = COALESCE(?, roll_number), is_active = 1, updated_at = ?
            WHERE id = ?
            """,
            (normalized_email, normalized_name, normalized_roll_number, now, student_row["id"]),
        )
        student_row = connection.execute("SELECT * FROM students WHERE id = ?", (student_row["id"],)).fetchone()
    return convert_row_to_dict(student_row) or {}


def ensure_admin_exists(connection, admin_id: str) -> None:
    row = connection.execute("SELECT id FROM admins WHERE id = ?", (admin_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Admin not found")


def ensure_subject_exists(connection, subject_id: str) -> None:
    row = connection.execute("SELECT id FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Subject not found")


def ensure_chapter_exists(connection, chapter_id: str) -> None:
    row = connection.execute("SELECT id FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Chapter not found")


def ensure_topic_exists(connection, topic_id: str) -> None:
    row = connection.execute("SELECT id FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Topic not found")


def ensure_concept_exists(connection, concept_id: str) -> None:
    row = connection.execute("SELECT id FROM concepts WHERE id = ?", (concept_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Concept not found")


def ensure_approved_figure_exists(connection, asset_id: str) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM extracted_assets
        WHERE id = ? AND asset_type = 'approved_figure' AND review_status = 'approved'
        """,
        (asset_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Approved figure not found")


async def save_uploaded_file(upload_file: UploadFile, destination_directory: Path) -> Path:
    destination_directory.mkdir(parents=True, exist_ok=True)
    safe_name = f"{build_identifier()}-{Path(upload_file.filename or 'upload.json').name}"
    file_path = destination_directory / safe_name
    with file_path.open("wb") as output:
        shutil.copyfileobj(upload_file.file, output)
    return file_path


def normalize_project_file_path(file_path: str) -> Path:
    path = Path(file_path)
    if not path.is_absolute():
        path = (PROJECT_DIRECTORY / path).resolve()
    return path


def load_json_file(file_path: Path) -> Any:
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Could not parse JSON file: {error}") from error
