from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import mkdtemp


PROJECT_DIRECTORY = Path(__file__).resolve().parent
QUESTION_BANK_DIRECTORY = PROJECT_DIRECTORY / "data" / "uploads" / "question_banks"


def prepare_temp_database() -> Path:
    temp_directory = Path(mkdtemp(prefix="braingain-smoke-"))
    temp_database_path = temp_directory / "braingain.sqlite3"
    os.environ["BRAINGAIN_DATABASE_PATH"] = str(temp_database_path)
    sys.path.insert(0, str(PROJECT_DIRECTORY))
    return temp_database_path


def write_sample_question_bank() -> Path:
    QUESTION_BANK_DIRECTORY.mkdir(parents=True, exist_ok=True)
    sample_payload = {
        "schema_version": "2.0",
        "meta": {
            "subject": "Physics",
            "grade": 9,
            "board": "ICSE",
            "chapter_number": 1,
            "chapter_name": "Refraction of Light at Plane Surfaces",
        },
        "concepts": [
            {
                "name": "Core Refraction",
                "display_order": 1,
                "questions": [
                    {
                        "id": "CH1_C1_Q1",
                        "format": "mcq",
                        "type": "definition",
                        "difficulty": "easy",
                        "text": "Refraction is the change in the direction of light when it passes from one transparent medium to another.",
                        "image": None,
                        "options": [
                            {"label": "A", "text": "frequency of light"},
                            {"label": "B", "text": "direction of light"},
                            {"label": "C", "text": "mass of light"},
                            {"label": "D", "text": "charge of light"},
                        ],
                        "answer": {"type": "option_labels", "value": ["B"]},
                    },
                    {
                        "id": "CH1_C1_Q2",
                        "format": "msq",
                        "type": "comparison",
                        "difficulty": "hard",
                        "text": "Which statements about refraction are correct?",
                        "image": None,
                        "options": [
                            {"label": "A", "text": "Speed changes across media"},
                            {"label": "B", "text": "Frequency always changes"},
                            {"label": "C", "text": "Direction can change"},
                            {"label": "D", "text": "Wavelength can change"},
                        ],
                        "answer": {"type": "option_labels", "value": ["A", "C", "D"]},
                    },
                    {
                        "id": "CH1_C1_Q3",
                        "format": "nat",
                        "type": "application",
                        "difficulty": "hard",
                        "text": "If the refractive index of a medium is 1.5 and the speed of light in vacuum is 3.0 x 10^8 m/s, what is the speed of light in the medium in units of 10^8 m/s?",
                        "image": None,
                        "answer": {"type": "numeric", "exact_value": 2.0, "tolerance": 0.01, "unit": "10^8 m/s"},
                    },
                    {
                        "id": "CH1_C1_Q4",
                        "format": "match",
                        "type": "reasoning",
                        "difficulty": "medium",
                        "text": "Match each term with the correct description.",
                        "image": None,
                        "columns": {
                            "a_heading": "Term",
                            "b_heading": "Description",
                            "items_a": [
                                {"label": "1", "text": "Incident ray", "matches": "P"},
                                {"label": "2", "text": "Normal", "matches": "Q"},
                            ],
                            "items_b": [
                                {"label": "P", "text": "Ray striking the surface"},
                                {"label": "Q", "text": "Perpendicular at point of incidence"},
                                {"label": "R", "text": "Ray leaving the medium"},
                            ],
                        },
                        "answer": {"type": "pairs", "value": {"1": "P", "2": "Q"}},
                    },
                ],
            }
        ],
    }
    sample_path = QUESTION_BANK_DIRECTORY / "smoke_schema_v2.json"
    sample_path.write_text(json.dumps(sample_payload, indent=2), encoding="utf-8")
    return sample_path


def run_smoke_test() -> dict[str, object]:
    prepare_temp_database()

    from api.app import (
        AIImportBatchCreateRequest,
        AIImportBatchMaterializeRequest,
        AttemptAnswerSubmission,
        AttemptAnswerUpdateRequest,
        AttemptStartRequest,
        AttemptSubmitRequest,
        ChapterCreateRequest,
        ConceptCreateRequest,
        PublishQuestionRevisionRequest,
        QuestionRevisionCreateRequest,
        SubjectCreateRequest,
        TestCreateRequest,
        TopicCreateRequest,
        create_ai_import_batch_endpoint,
        create_chapter,
        create_concept,
        create_question_revision,
        create_subject,
        create_topic,
        generate_test,
        get_attempt,
        get_attempt_results,
        get_question_item,
        get_question_item as get_question,
        handle_startup,
        list_admins,
        list_concepts,
        list_topic_questions,
        materialize_ai_import_batch_endpoint,
        publish_question_revision,
        save_attempt_answer,
        start_attempt,
        submit_attempt,
    )

    sample_question_bank_path = write_sample_question_bank()
    handle_startup()

    admins = list_admins()
    if not admins:
        raise RuntimeError("Smoke test expected at least one admin")
    admin_id = str(admins[0]["id"])

    subject = create_subject(SubjectCreateRequest(name="Physics", grade=9, board="ICSE"))
    chapter = create_chapter(ChapterCreateRequest(subject_id=subject["id"], chapter_number=1, name="Refraction of Light at Plane Surfaces"))
    topic = create_topic(TopicCreateRequest(chapter_id=chapter["id"], name="Refraction Basics", display_order=1))

    ai_batch = create_ai_import_batch_endpoint(
        AIImportBatchCreateRequest(source_file_path=str(sample_question_bank_path), uploaded_by_admin_id=admin_id)
    )
    materialized_batch = materialize_ai_import_batch_endpoint(
        ai_batch["id"],
        AIImportBatchMaterializeRequest(
            approved_by_admin_id=admin_id,
            topic_id=topic["id"],
            default_lifecycle_status="active",
            auto_publish=True,
        ),
    )

    concepts = list_concepts(topic["id"])
    if not concepts:
        raise RuntimeError("Smoke test expected at least one concept")
    concept_id = concepts[0]["id"]

    manual_item = create_question_revision(
        QuestionRevisionCreateRequest(
            concept_id=concept_id,
            created_by_admin_id=admin_id,
            lifecycle_status="draft",
            format="mcq",
            difficulty="easy",
            type="definition",
            text="A refracted ray bends away from the normal when it enters a rarer medium from a denser medium.",
            options=[
                {"label": "A", "text": "True", "is_correct": True},
                {"label": "B", "text": "False", "is_correct": False},
                {"label": "C", "text": "Only for glass", "is_correct": False},
                {"label": "D", "text": "Only for water", "is_correct": False},
            ],
            answer={"type": "option_labels", "value": ["A"]},
        )
    )
    draft_revision_id = manual_item["current_draft_revision"]["id"]
    published_manual_item = publish_question_revision(
        draft_revision_id,
        PublishQuestionRevisionRequest(published_by_admin_id=admin_id, lifecycle_status="active"),
    )

    topic_questions = list_topic_questions(topic["id"], include_answers=True)
    if len(topic_questions) < 5:
        raise RuntimeError("Smoke test expected imported and manual questions to exist in the topic")

    generated_test = generate_test(
        TestCreateRequest(
            created_by_admin_id=admin_id,
            title="Smoke Test Practice",
            subject_id=subject["id"],
            chapter_id=chapter["id"],
            topic_id=topic["id"],
            question_count=5,
            hard_question_count=2,
            is_custom_practice_template=False,
            selected_question_item_ids=[question["id"] for question in topic_questions[:5]],
        )
    )

    attempt = start_attempt(
        AttemptStartRequest(
            test_id=generated_test["id"],
            full_name="Smoke Test Student",
            roll_number="BG-SMOKE-1",
            email="smoke@braingain.local",
        )
    )

    for index, question in enumerate(generated_test["questions"]):
        update_request_kwargs = {
            "option_labels": [],
            "numeric_value": None,
            "pair_mapping": {},
            "is_marked_for_review": index == 0,
            "has_visited": True,
            "spent_seconds": (index + 1) * 9,
        }
        if question["format"] in {"mcq", "msq"}:
            update_request_kwargs["option_labels"] = [option["label"] for option in question["options"] if option.get("is_correct")]
        elif question["format"] == "nat":
            update_request_kwargs["numeric_value"] = question["numeric_answer"]["exact_value"]
        else:
            update_request_kwargs["pair_mapping"] = {item["label"]: item["matches"] for item in question["columns"]["items_a"]}
        save_attempt_answer(
            attempt["id"],
            question["test_question_revision_id"],
            AttemptAnswerUpdateRequest(**update_request_kwargs),
        )

    draft_attempt = get_attempt(attempt["id"])
    if draft_attempt["status"] != "in_progress":
        raise RuntimeError("Smoke test expected the saved attempt to stay in progress before submission")
    if draft_attempt["marked_for_review_count"] < 1:
        raise RuntimeError("Smoke test expected at least one marked-for-review question after saving draft answers")
    if draft_attempt["answered_question_count"] != len(generated_test["questions"]):
        raise RuntimeError("Smoke test expected all questions to be counted as answered after saving draft answers")
    if draft_attempt["time_limit_minutes"] < 1 or draft_attempt["remaining_seconds"] < 1:
        raise RuntimeError("Smoke test expected a positive attempt timer")

    answers = [
        AttemptAnswerSubmission(
            test_question_revision_id=question["test_question_revision_id"],
            option_labels=question["answer_data"]["option_labels"],
            numeric_value=question["answer_data"]["numeric_value"],
            pair_mapping=question["answer_data"]["pair_mapping"],
            is_marked_for_review=question["answer_data"]["is_marked_for_review"],
            has_visited=question["answer_data"]["has_visited"],
            spent_seconds=question["answer_data"]["spent_seconds"],
        )
        for question in draft_attempt["test"]["questions"]
    ]

    submitted_attempt = submit_attempt(attempt["id"], AttemptSubmitRequest(answers=answers))
    scored_attempt = get_attempt_results(attempt["id"])
    if scored_attempt["score"] != 100.0:
        raise RuntimeError("Smoke test expected a perfect score when submitting correct answers")

    fetched_manual_item = get_question(published_manual_item["id"])
    return {
        "ai_batch_id": ai_batch["id"],
        "materialized_question_count": materialized_batch["materialized_question_count"],
        "published_question_count": materialized_batch["published_question_count"],
        "concept_count": len(concepts),
        "topic_question_count": len(topic_questions),
        "manual_question_item_id": fetched_manual_item["id"],
        "generated_test_id": generated_test["id"],
        "attempt_id": attempt["id"],
        "attempt_score": submitted_attempt["score"],
    }


if __name__ == "__main__":
    print(json.dumps(run_smoke_test(), indent=2))
