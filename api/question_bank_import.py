from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .database import build_identifier
from .database import build_json_text
from .database import build_timestamp
from .database import convert_row_to_dict
from .database import insert_admin_activity_log
from .database import parse_json_text


QUESTION_FORMAT_VALUES = {"mcq", "msq", "nat", "match"}
QUESTION_DIFFICULTY_VALUES = {"easy", "medium", "hard"}
QUESTION_TYPE_VALUES = {"definition", "identification", "trap", "application", "comparison", "reasoning"}
QUESTION_LIFECYCLE_VALUES = {"draft", "active", "disabled", "archived"}
BATCH_STATUS_VALUES = {"needs_review", "ready", "materialized", "published", "failed"}
OPTION_LABELS = ["A", "B", "C", "D"]
QUESTION_ID_PATTERN = re.compile(r"^CH\d+_C\d+_Q\d+$")


@dataclass(slots=True)
class ValidationMessage:
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


def load_question_bank_payload(source_file_path: str) -> dict[str, Any]:
    path = Path(source_file_path)
    if not path.exists():
        raise HTTPException(status_code=400, detail="Question bank file does not exist")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Could not parse question bank JSON: {error}") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Question bank root must be a JSON object")
    return payload


def validate_question_bank_file(source_file_path: str) -> dict[str, Any]:
    payload = load_question_bank_payload(source_file_path)
    return build_question_bank_result(source_file_path, payload)


def build_question_bank_result(source_file_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    validation_report = build_validation_report(payload)
    return {
        "source_file_path": source_file_path,
        "validation_report": validation_report,
        "meta": payload.get("meta"),
        "preview": build_question_bank_preview(payload),
    }


def build_validation_report(payload: dict[str, Any]) -> dict[str, Any]:
    messages: list[ValidationMessage] = []
    schema_version = str(payload.get("schema_version", "")).strip()
    if not schema_version:
        messages.append(ValidationMessage(path="schema_version", message="schema_version is required."))

    meta = payload.get("meta")
    concepts = payload.get("concepts")
    if not isinstance(meta, dict):
        messages.append(ValidationMessage(path="meta", message="Metadata block is missing or invalid."))
    else:
        validate_meta(meta, messages)

    if not isinstance(concepts, list) or not concepts:
        messages.append(ValidationMessage(path="concepts", message="At least one concept is required."))
    else:
        seen_question_ids: set[str] = set()
        for concept_index, concept in enumerate(concepts):
            validate_concept(concept_index, concept, seen_question_ids, messages)

    preview = build_question_bank_preview(payload)
    return {
        "is_valid": not messages,
        "error_count": len(messages),
        "errors": [message.to_dict() for message in messages],
        "summary": {
            "concept_count": preview["concept_count"],
            "question_count": preview["question_count"],
            "mcq_count": preview["mcq_count"],
            "msq_count": preview["msq_count"],
            "nat_count": preview["nat_count"],
            "match_count": preview["match_count"],
        },
    }


def validate_meta(meta: dict[str, Any], messages: list[ValidationMessage]) -> None:
    required_fields = {
        "subject": "Subject is required.",
        "grade": "Grade is required.",
        "board": "Board is required.",
        "chapter_number": "Chapter number is required.",
        "chapter_name": "Chapter name is required.",
    }
    for field_name, message_text in required_fields.items():
        if meta.get(field_name) in (None, ""):
            messages.append(ValidationMessage(path=f"meta.{field_name}", message=message_text))


def validate_concept(
    concept_index: int,
    concept: Any,
    seen_question_ids: set[str],
    messages: list[ValidationMessage],
) -> None:
    concept_path = f"concepts[{concept_index}]"
    if not isinstance(concept, dict):
        messages.append(ValidationMessage(path=concept_path, message="Concept entry must be an object."))
        return
    if not str(concept.get("name", "")).strip():
        messages.append(ValidationMessage(path=f"{concept_path}.name", message="Concept name is required."))
    questions = concept.get("questions")
    if not isinstance(questions, list) or not questions:
        messages.append(ValidationMessage(path=f"{concept_path}.questions", message="Each concept must include at least one question."))
        return
    for question_index, question in enumerate(questions):
        validate_question(concept_path, question_index, question, seen_question_ids, messages)


def validate_question(
    concept_path: str,
    question_index: int,
    question: Any,
    seen_question_ids: set[str],
    messages: list[ValidationMessage],
) -> None:
    question_path = f"{concept_path}.questions[{question_index}]"
    if not isinstance(question, dict):
        messages.append(ValidationMessage(path=question_path, message="Question entry must be an object."))
        return

    question_id = str(question.get("id", "")).strip()
    if not question_id:
        messages.append(ValidationMessage(path=f"{question_path}.id", message="Question ID is required."))
    elif not QUESTION_ID_PATTERN.match(question_id):
        messages.append(ValidationMessage(path=f"{question_path}.id", message="Question ID must match CHn_Cn_Qn format."))
    elif question_id in seen_question_ids:
        messages.append(ValidationMessage(path=f"{question_path}.id", message="Question ID must be unique."))
    else:
        seen_question_ids.add(question_id)

    if not str(question.get("text", "")).strip():
        messages.append(ValidationMessage(path=f"{question_path}.text", message="Question text cannot be empty."))

    question_format = str(question.get("format", question.get("question_format", ""))).strip().lower()
    if question_format not in QUESTION_FORMAT_VALUES:
        messages.append(ValidationMessage(path=f"{question_path}.format", message="Question format is invalid."))

    difficulty = str(question.get("difficulty", "")).strip().lower()
    if difficulty not in QUESTION_DIFFICULTY_VALUES:
        messages.append(ValidationMessage(path=f"{question_path}.difficulty", message="Difficulty must be easy, medium, or hard."))

    question_type = str(question.get("type", "")).strip().lower()
    if question_type not in QUESTION_TYPE_VALUES:
        messages.append(ValidationMessage(path=f"{question_path}.type", message="Question type is invalid."))

    answer = question.get("answer")
    if not isinstance(answer, dict):
        messages.append(ValidationMessage(path=f"{question_path}.answer", message="Answer object is required."))
        return

    if question_format in {"mcq", "msq"}:
        validate_option_question(question_path, question, question_format, answer, messages)
        return
    if question_format == "nat":
        validate_numeric_question(question_path, question, answer, messages)
        return
    if question_format == "match":
        validate_match_question(question_path, question, answer, messages)


def validate_option_question(
    question_path: str,
    question: dict[str, Any],
    question_format: str,
    answer: dict[str, Any],
    messages: list[ValidationMessage],
) -> None:
    options = question.get("options")
    if not isinstance(options, list) or len(options) != 4:
        messages.append(ValidationMessage(path=f"{question_path}.options", message="Each option question must have exactly 4 options."))
        return
    labels: list[str] = []
    for option_index, option in enumerate(options):
        option_path = f"{question_path}.options[{option_index}]"
        if not isinstance(option, dict):
            messages.append(ValidationMessage(path=option_path, message="Option must be an object."))
            continue
        label = str(option.get("label", "")).strip().upper()
        text = str(option.get("text", "")).strip()
        if label not in OPTION_LABELS:
            messages.append(ValidationMessage(path=f"{option_path}.label", message="Option label must be A, B, C, or D."))
        else:
            labels.append(label)
        if not text:
            messages.append(ValidationMessage(path=f"{option_path}.text", message="Option text cannot be empty."))
    if labels != OPTION_LABELS:
        messages.append(ValidationMessage(path=f"{question_path}.options", message="Option labels must be A, B, C, D in order."))
    if "columns" in question:
        messages.append(ValidationMessage(path=f"{question_path}.columns", message="Option questions cannot include columns."))
    if answer.get("type") != "option_labels":
        messages.append(ValidationMessage(path=f"{question_path}.answer.type", message="Option questions must use answer.type option_labels."))
        return
    values = answer.get("value")
    if not isinstance(values, list) or not values:
        messages.append(ValidationMessage(path=f"{question_path}.answer.value", message="answer.value must be a non-empty label array."))
        return
    normalized = [str(value).strip().upper() for value in values if str(value).strip()]
    if len(set(normalized)) != len(normalized):
        messages.append(ValidationMessage(path=f"{question_path}.answer.value", message="Answer labels must be unique."))
    if any(value not in OPTION_LABELS for value in normalized):
        messages.append(ValidationMessage(path=f"{question_path}.answer.value", message="Answer labels must use only A, B, C, D."))
    if question_format == "mcq" and len(normalized) != 1:
        messages.append(ValidationMessage(path=f"{question_path}.answer.value", message="MCQ must have exactly one answer label."))
    if question_format == "msq" and len(normalized) < 2:
        messages.append(ValidationMessage(path=f"{question_path}.answer.value", message="MSQ must have at least two answer labels."))


def validate_numeric_question(
    question_path: str,
    question: dict[str, Any],
    answer: dict[str, Any],
    messages: list[ValidationMessage],
) -> None:
    if "options" in question:
        messages.append(ValidationMessage(path=f"{question_path}.options", message="NAT questions cannot include options."))
    if "columns" in question:
        messages.append(ValidationMessage(path=f"{question_path}.columns", message="NAT questions cannot include columns."))
    if answer.get("type") != "numeric":
        messages.append(ValidationMessage(path=f"{question_path}.answer.type", message="NAT questions must use answer.type numeric."))
        return
    try:
        float(answer.get("exact_value"))
    except Exception:
        messages.append(ValidationMessage(path=f"{question_path}.answer.exact_value", message="exact_value must be numeric."))
    try:
        tolerance = float(answer.get("tolerance"))
        if tolerance < 0:
            raise ValueError("negative")
    except Exception:
        messages.append(ValidationMessage(path=f"{question_path}.answer.tolerance", message="tolerance must be a non-negative number."))
    if answer.get("unit") is None:
        messages.append(ValidationMessage(path=f"{question_path}.answer.unit", message="unit is required for NAT questions."))


def validate_match_question(
    question_path: str,
    question: dict[str, Any],
    answer: dict[str, Any],
    messages: list[ValidationMessage],
) -> None:
    if "options" in question:
        messages.append(ValidationMessage(path=f"{question_path}.options", message="Match questions cannot include options."))
    columns = question.get("columns")
    if not isinstance(columns, dict):
        messages.append(ValidationMessage(path=f"{question_path}.columns", message="Match questions must include columns."))
        return
    items_a = columns.get("items_a")
    items_b = columns.get("items_b")
    if not isinstance(items_a, list) or len(items_a) < 2:
        messages.append(ValidationMessage(path=f"{question_path}.columns.items_a", message="items_a must contain at least two rows."))
        return
    if not isinstance(items_b, list) or len(items_b) < len(items_a):
        messages.append(ValidationMessage(path=f"{question_path}.columns.items_b", message="items_b must contain at least as many rows as items_a."))
        return
    right_labels = {str(item.get("label", "")).strip() for item in items_b if isinstance(item, dict)}
    expected_pairs: dict[str, str] = {}
    for index, item in enumerate(items_a):
        if not isinstance(item, dict):
            messages.append(ValidationMessage(path=f"{question_path}.columns.items_a[{index}]", message="Match item must be an object."))
            continue
        left_label = str(item.get("label", "")).strip()
        match_label = str(item.get("matches", "")).strip()
        if not left_label or not match_label:
            messages.append(ValidationMessage(path=f"{question_path}.columns.items_a[{index}]", message="Match item label and matches are required."))
            continue
        if match_label not in right_labels:
            messages.append(ValidationMessage(path=f"{question_path}.columns.items_a[{index}].matches", message="Match target must exist in items_b."))
        expected_pairs[left_label] = match_label
    if answer.get("type") != "pairs":
        messages.append(ValidationMessage(path=f"{question_path}.answer.type", message="Match questions must use answer.type pairs."))
        return
    value = answer.get("value")
    if not isinstance(value, dict):
        messages.append(ValidationMessage(path=f"{question_path}.answer.value", message="Match answer.value must be an object."))
        return
    normalized_value = {str(key): str(item) for key, item in value.items()}
    if normalized_value != expected_pairs:
        messages.append(ValidationMessage(path=f"{question_path}.answer.value", message="Match answer.value must exactly match items_a pairing."))


def build_question_bank_preview(payload: dict[str, Any]) -> dict[str, Any]:
    concepts = payload.get("concepts")
    if not isinstance(concepts, list):
        return {
            "concept_count": 0,
            "question_count": 0,
            "mcq_count": 0,
            "msq_count": 0,
            "nat_count": 0,
            "match_count": 0,
            "questions": [],
        }

    preview_questions: list[dict[str, Any]] = []
    counts = {"mcq": 0, "msq": 0, "nat": 0, "match": 0}
    for concept_index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            continue
        concept_name = str(concept.get("name", "")).strip()
        questions = concept.get("questions")
        if not isinstance(questions, list):
            continue
        for question_index, question in enumerate(questions):
            if not isinstance(question, dict):
                continue
            question_format = str(question.get("format", question.get("question_format", "mcq"))).strip().lower() or "mcq"
            if question_format not in counts:
                question_format = "mcq"
            counts[question_format] += 1
            preview_questions.append(
                {
                    "concept_index": concept_index,
                    "question_index": question_index,
                    "id": str(question.get("id", "")).strip(),
                    "text": str(question.get("text", "")).strip(),
                    "format": question_format,
                    "difficulty": str(question.get("difficulty", "")).strip().lower(),
                    "type": str(question.get("type", "")).strip().lower(),
                    "concept_name": concept_name,
                    "image": question.get("image"),
                    "answer": question.get("answer"),
                    "options": question.get("options"),
                    "columns": question.get("columns"),
                }
            )
    return {
        "concept_count": sum(1 for concept in concepts if isinstance(concept, dict)),
        "question_count": len(preview_questions),
        "mcq_count": counts["mcq"],
        "msq_count": counts["msq"],
        "nat_count": counts["nat"],
        "match_count": counts["match"],
        "questions": preview_questions,
    }


def normalize_question_payload(question: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "id": str(question.get("id", "")).strip(),
        "format": str(question.get("format", question.get("question_format", ""))).strip().lower(),
        "type": str(question.get("type", "")).strip().lower(),
        "difficulty": str(question.get("difficulty", "")).strip().lower(),
        "text": str(question.get("text", "")).strip(),
        "image": question.get("image"),
        "answer": question.get("answer"),
    }
    if "options" in question:
        normalized["options"] = question.get("options")
    if "columns" in question:
        normalized["columns"] = question.get("columns")
    return normalized


def create_ai_import_batch(
    connection,
    source_file_path: str,
    uploaded_by_admin_id: str,
) -> dict[str, Any]:
    payload = load_question_bank_payload(source_file_path)
    result = build_question_bank_result(source_file_path, payload)
    now = build_timestamp()
    batch_id = build_identifier()
    validation_report = result["validation_report"]
    batch_status = "ready" if validation_report["is_valid"] else "needs_review"
    connection.execute(
        """
        INSERT INTO ai_import_batches (
            id, schema_version, source_file_path, uploaded_by_admin_id, status, validation_summary,
            raw_payload, normalized_payload, materialized_question_count, published_question_count, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            str(payload.get("schema_version", "")).strip() or "unknown",
            source_file_path,
            uploaded_by_admin_id,
            batch_status,
            build_json_text(validation_report),
            build_json_text(payload),
            build_json_text(payload),
            0,
            0,
            now,
            now,
        ),
    )

    for preview_question in result["preview"]["questions"]:
        question_errors = [
            error
            for error in validation_report["errors"]
            if error["path"].startswith(
                f"concepts[{preview_question['concept_index']}].questions[{preview_question['question_index']}]"
            )
        ]
        connection.execute(
            """
            INSERT INTO ai_import_batch_questions (
                id, ai_import_batch_id, source_question_id, concept_name, question_text_preview, format,
                validation_status, validation_errors, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_identifier(),
                batch_id,
                preview_question["id"],
                preview_question["concept_name"],
                preview_question["text"][:240],
                preview_question["format"],
                "valid" if not question_errors else "invalid",
                build_json_text(question_errors),
                now,
                now,
            ),
        )

    insert_admin_activity_log(
        connection,
        uploaded_by_admin_id,
        action_type="ai_import_batch_created",
        entity_type="ai_import_batch",
        entity_id=batch_id,
        summary=f"Created AI import batch for {Path(source_file_path).name}",
        details={"status": batch_status, "error_count": validation_report["error_count"]},
    )
    return get_ai_import_batch(connection, batch_id)


def get_ai_import_batch(connection, batch_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM ai_import_batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="AI import batch not found")
    row_data = convert_row_to_dict(row) or {}
    raw_payload = parse_json_text(row_data.get("normalized_payload") or row_data.get("raw_payload"), default={}) or {}
    row_data["validation_summary"] = parse_json_text(row_data.get("validation_summary"), default={}) or {}
    row_data["meta"] = raw_payload.get("meta")
    row_data["preview"] = build_question_bank_preview(raw_payload)
    question_rows = connection.execute(
        """
        SELECT *
        FROM ai_import_batch_questions
        WHERE ai_import_batch_id = ?
        ORDER BY created_at, id
        """,
        (batch_id,),
    ).fetchall()
    questions = []
    for question_row in question_rows:
        question_data = convert_row_to_dict(question_row) or {}
        question_data["validation_errors"] = parse_json_text(question_data.get("validation_errors"), default=[]) or []
        questions.append(question_data)
    row_data["questions"] = questions
    return row_data


def update_ai_import_batch_payload(
    connection,
    batch_id: str,
    updated_by_admin_id: str,
    payload_text: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(payload_text)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Could not parse JSON payload: {error}") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Question bank root must be a JSON object")
    validation_report = build_validation_report(payload)
    preview = build_question_bank_preview(payload)
    batch_status = "ready" if validation_report["is_valid"] else "needs_review"
    now = build_timestamp()
    connection.execute(
        """
        UPDATE ai_import_batches
        SET schema_version = ?, status = ?, validation_summary = ?, normalized_payload = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            str(payload.get("schema_version", "")).strip() or "unknown",
            batch_status,
            build_json_text(validation_report),
            build_json_text(payload),
            now,
            batch_id,
        ),
    )
    connection.execute("DELETE FROM ai_import_batch_questions WHERE ai_import_batch_id = ?", (batch_id,))
    for preview_question in preview["questions"]:
        question_errors = [
            error
            for error in validation_report["errors"]
            if error["path"].startswith(
                f"concepts[{preview_question['concept_index']}].questions[{preview_question['question_index']}]"
            )
        ]
        connection.execute(
            """
            INSERT INTO ai_import_batch_questions (
                id, ai_import_batch_id, source_question_id, concept_name, question_text_preview, format,
                validation_status, validation_errors, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_identifier(),
                batch_id,
                preview_question["id"],
                preview_question["concept_name"],
                preview_question["text"][:240],
                preview_question["format"],
                "valid" if not question_errors else "invalid",
                build_json_text(question_errors),
                now,
                now,
            ),
        )
    insert_admin_activity_log(
        connection,
        updated_by_admin_id,
        action_type="ai_import_batch_payload_updated",
        entity_type="ai_import_batch",
        entity_id=batch_id,
        summary="Updated AI import payload",
        details={"status": batch_status, "question_count": preview["question_count"], "error_count": validation_report["error_count"]},
    )
    return get_ai_import_batch(connection, batch_id)


def normalize_review_editor_question_payload(question: dict[str, Any]) -> dict[str, Any]:
    question_format = str(question.get("format", question.get("question_format", ""))).strip().lower()
    payload = {
        "id": str(question.get("id", "")).strip(),
        "format": question_format,
        "difficulty": str(question.get("difficulty", "")).strip().lower(),
        "type": str(question.get("type", "")).strip().lower(),
        "text": str(question.get("text", "")).strip(),
        "image": question.get("image"),
    }
    if question_format in {"mcq", "msq"}:
        answer_values = question.get("answer", [])
        if isinstance(answer_values, dict):
            answer_values = answer_values.get("value", [])
        payload["options"] = question.get("options", [])
        payload["answer"] = {
            "type": "option_labels",
            "value": [str(value).strip().upper() for value in answer_values if str(value).strip()],
        }
    elif question_format == "nat":
        answer = question.get("answer", {})
        payload["answer"] = {
            "type": "numeric",
            "exact_value": answer.get("exact_value"),
            "tolerance": answer.get("tolerance", 0),
            "unit": answer.get("unit", ""),
        }
    elif question_format == "match":
        columns = question.get("columns") or {}
        payload["columns"] = columns
        payload["answer"] = {
            "type": "pairs",
            "value": {str(item.get("label")): str(item.get("matches")) for item in columns.get("items_a", []) if isinstance(item, dict)},
        }
    else:
        payload["answer"] = question.get("answer")
        if "options" in question:
            payload["options"] = question.get("options")
        if "columns" in question:
            payload["columns"] = question.get("columns")
    return payload


def update_ai_import_batch_question(
    connection,
    batch_id: str,
    updated_by_admin_id: str,
    concept_index: int,
    question_index: int,
    question: dict[str, Any],
) -> dict[str, Any]:
    batch = get_ai_import_batch(connection, batch_id)
    payload = parse_json_text(batch.get("normalized_payload") or batch.get("raw_payload"), default={}) or {}
    concepts = payload.get("concepts")
    if not isinstance(concepts, list) or concept_index < 0 or concept_index >= len(concepts):
        raise HTTPException(status_code=400, detail="Concept index is out of range")
    concept = concepts[concept_index]
    questions = concept.get("questions")
    if not isinstance(questions, list) or question_index < 0 or question_index >= len(questions):
        raise HTTPException(status_code=400, detail="Question index is out of range")
    concept_name = str(question.get("concept", "")).strip()
    if concept_name:
        concept["name"] = concept_name
    questions[question_index] = normalize_review_editor_question_payload(question)
    return update_ai_import_batch_payload(connection, batch_id, updated_by_admin_id, build_json_text(payload))


def insert_ai_import_batch_question(
    connection,
    batch_id: str,
    updated_by_admin_id: str,
    concept_index: int,
    insert_at_question_index: int,
    question: dict[str, Any],
) -> dict[str, Any]:
    batch = get_ai_import_batch(connection, batch_id)
    payload = parse_json_text(batch.get("normalized_payload") or batch.get("raw_payload"), default={}) or {}
    concepts = payload.get("concepts")
    if not isinstance(concepts, list) or concept_index < 0 or concept_index >= len(concepts):
        raise HTTPException(status_code=400, detail="Concept index is out of range")
    concept = concepts[concept_index]
    questions = concept.get("questions")
    if not isinstance(questions, list):
        raise HTTPException(status_code=400, detail="Concept questions are invalid")
    concept_name = str(question.get("concept", "")).strip()
    if concept_name:
        concept["name"] = concept_name
    insert_index = max(0, min(insert_at_question_index, len(questions)))
    questions.insert(insert_index, normalize_review_editor_question_payload(question))
    return update_ai_import_batch_payload(connection, batch_id, updated_by_admin_id, build_json_text(payload))


def delete_ai_import_batch_question(
    connection,
    batch_id: str,
    updated_by_admin_id: str,
    concept_index: int,
    question_index: int,
) -> dict[str, Any]:
    batch = get_ai_import_batch(connection, batch_id)
    payload = parse_json_text(batch.get("normalized_payload") or batch.get("raw_payload"), default={}) or {}
    concepts = payload.get("concepts")
    if not isinstance(concepts, list) or concept_index < 0 or concept_index >= len(concepts):
        raise HTTPException(status_code=400, detail="Concept index is out of range")
    concept = concepts[concept_index]
    questions = concept.get("questions")
    if not isinstance(questions, list) or question_index < 0 or question_index >= len(questions):
        raise HTTPException(status_code=400, detail="Question index is out of range")
    del questions[question_index]
    return update_ai_import_batch_payload(connection, batch_id, updated_by_admin_id, build_json_text(payload))


def materialize_ai_import_batch(
    connection,
    batch_id: str,
    approved_by_admin_id: str,
    topic_id: str,
    default_lifecycle_status: str = "draft",
    auto_publish: bool = False,
) -> dict[str, Any]:
    if default_lifecycle_status not in QUESTION_LIFECYCLE_VALUES:
        raise HTTPException(status_code=400, detail="default_lifecycle_status is invalid")
    batch = get_ai_import_batch(connection, batch_id)
    validation_summary = batch["validation_summary"]
    if not validation_summary.get("is_valid"):
        raise HTTPException(status_code=400, detail="AI import batch must be valid before materialization")

    payload = parse_json_text(batch.get("normalized_payload") or batch.get("raw_payload"), default={}) or {}
    meta = payload.get("meta") or {}
    chapter_row = connection.execute(
        """
        SELECT chapters.id, chapters.subject_id
        FROM chapters
        INNER JOIN topics ON topics.chapter_id = chapters.id
        WHERE topics.id = ?
        """,
        (topic_id,),
    ).fetchone()
    if chapter_row is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    now = build_timestamp()
    connection.execute(
        """
        UPDATE ai_import_batches
        SET status = ?, subject_id = ?, chapter_id = ?, topic_id = ?, approved_by_admin_id = ?, approved_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            "materialized",
            str(chapter_row["subject_id"]),
            str(chapter_row["id"]),
            topic_id,
            approved_by_admin_id,
            now,
            now,
            batch_id,
        ),
    )

    concepts = payload.get("concepts", [])
    materialized_count = 0
    published_count = 0
    batch_question_rows = connection.execute(
        "SELECT id, source_question_id FROM ai_import_batch_questions WHERE ai_import_batch_id = ?",
        (batch_id,),
    ).fetchall()
    batch_question_map = {str(row["source_question_id"]): str(row["id"]) for row in batch_question_rows}

    for concept_index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            continue
        concept_name = str(concept.get("name", "")).strip() or f"Concept {concept_index + 1}"
        concept_row = connection.execute(
            """
            SELECT id
            FROM concepts
            WHERE topic_id = ? AND name = ?
            """,
            (topic_id, concept_name),
        ).fetchone()
        if concept_row is None:
            concept_id = build_identifier()
            display_order = int(concept.get("display_order") or concept_index + 1)
            connection.execute(
                """
                INSERT INTO concepts (id, topic_id, name, display_order, status, source_concept_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (concept_id, topic_id, concept_name, display_order, "active", concept_name, now, now),
            )
        else:
            concept_id = str(concept_row["id"])

        for question in concept.get("questions", []):
            if not isinstance(question, dict):
                continue
            normalized_question = normalize_question_payload(question)
            question_item_id = build_identifier()
            question_revision_id = build_identifier()
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
                    concept_id,
                    normalized_question["id"] or None,
                    "ai_import",
                    batch_id,
                    approved_by_admin_id,
                    question_revision_id,
                    question_revision_id if auto_publish else None,
                    "active" if auto_publish and default_lifecycle_status == "active" else default_lifecycle_status,
                    0,
                    now,
                    now,
                ),
            )
            insert_question_revision(
                connection=connection,
                question_item_id=question_item_id,
                question_revision_id=question_revision_id,
                created_by_admin_id=approved_by_admin_id,
                revision_number=1,
                revision_status="published" if auto_publish else "draft",
                question=normalized_question,
                created_at=now,
            )
            if auto_publish:
                published_count += 1
            materialized_count += 1
            batch_question_row_id = batch_question_map.get(normalized_question["id"])
            if batch_question_row_id:
                connection.execute(
                    """
                    UPDATE ai_import_batch_questions
                    SET question_item_id = ?, question_revision_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (question_item_id, question_revision_id, now, batch_question_row_id),
                )

    connection.execute(
        """
        UPDATE ai_import_batches
        SET status = ?, materialized_question_count = ?, published_question_count = ?, updated_at = ?
        WHERE id = ?
        """,
        ("published" if auto_publish else "materialized", materialized_count, published_count, now, batch_id),
    )
    insert_admin_activity_log(
        connection,
        approved_by_admin_id,
        action_type="ai_import_batch_materialized",
        entity_type="ai_import_batch",
        entity_id=batch_id,
        summary=f"Materialized {materialized_count} questions from AI batch",
        details={"topic_id": topic_id, "auto_publish": auto_publish, "chapter_name": meta.get("chapter_name")},
    )
    return get_ai_import_batch(connection, batch_id)


def insert_question_revision(
    connection,
    question_item_id: str,
    question_revision_id: str,
    created_by_admin_id: str,
    revision_number: int,
    revision_status: str,
    question: dict[str, Any],
    created_at: str,
    parent_revision_id: str | None = None,
) -> None:
    answer = question["answer"]
    answer_type = str(answer.get("type", "")).strip()
    connection.execute(
        """
        INSERT INTO question_revisions (
            id, question_item_id, revision_number, parent_revision_id, created_by_admin_id, format, difficulty,
            type, text, explanation, image_asset_id, answer_type, answer_payload, scoring_payload, revision_status,
            published_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_revision_id,
            question_item_id,
            revision_number,
            parent_revision_id,
            created_by_admin_id,
            question["format"],
            question["difficulty"],
            question["type"],
            question["text"],
            None,
            question.get("image"),
            answer_type,
            build_json_text(answer),
            build_json_text(build_scoring_payload(question)),
            revision_status,
            created_at if revision_status == "published" else None,
            created_at,
            created_at,
        ),
    )
    if question["format"] in {"mcq", "msq"}:
        for display_order, option in enumerate(question.get("options", []), start=1):
            label = str(option.get("label", "")).strip().upper()
            connection.execute(
                """
                INSERT INTO question_revision_options (
                    id, question_revision_id, label, text, is_correct, display_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    build_identifier(),
                    question_revision_id,
                    label,
                    str(option.get("text", "")).strip(),
                    1 if label in {str(value).strip().upper() for value in answer.get("value", [])} else 0,
                    display_order,
                    created_at,
                    created_at,
                ),
            )
        return
    if question["format"] == "nat":
        connection.execute(
            """
            INSERT INTO question_revision_numeric_answers (
                id, question_revision_id, exact_value, tolerance, unit, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_identifier(),
                question_revision_id,
                float(answer["exact_value"]),
                float(answer["tolerance"]),
                str(answer.get("unit", "")),
                created_at,
                created_at,
            ),
        )
        return
    if question["format"] == "match":
        match_set_id = build_identifier()
        columns = question.get("columns") or {}
        connection.execute(
            """
            INSERT INTO question_revision_match_sets (
                id, question_revision_id, a_heading, b_heading, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                match_set_id,
                question_revision_id,
                str(columns.get("a_heading", "Column A")),
                str(columns.get("b_heading", "Column B")),
                created_at,
                created_at,
            ),
        )
        for display_order, item in enumerate(columns.get("items_a", []), start=1):
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
                    str(item.get("label", "")).strip(),
                    str(item.get("text", "")).strip(),
                    str(item.get("matches", "")).strip(),
                    display_order,
                    created_at,
                    created_at,
                ),
            )
        for display_order, item in enumerate(columns.get("items_b", []), start=1):
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
                    str(item.get("label", "")).strip(),
                    str(item.get("text", "")).strip(),
                    display_order,
                    created_at,
                    created_at,
                ),
            )


def build_scoring_payload(question: dict[str, Any]) -> dict[str, Any]:
    answer = question["answer"]
    if question["format"] in {"mcq", "msq"}:
        return {"mode": "exact_option_set", "correct_labels": answer.get("value", [])}
    if question["format"] == "nat":
        return {
            "mode": "numeric_tolerance",
            "exact_value": answer.get("exact_value"),
            "tolerance": answer.get("tolerance"),
            "unit": answer.get("unit", ""),
        }
    return {"mode": "exact_pairs", "pairs": answer.get("value", {})}
