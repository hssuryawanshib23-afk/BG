# BrainGain Database Schema

This file is the canonical database reference for BrainGain.

Rule:
- Update this file whenever a code change adds, removes, renames, or changes database tables, columns, relationships, enums, or constraints.

## Current Architecture
- BrainGain stores syllabus structure in `subjects -> chapters -> topics -> concepts`.
- BrainGain stores question identity separately from question content.
- `question_items` are stable logical records.
- `question_revisions` are immutable content snapshots.
- Tests and attempts always point to exact published revisions, not mutable live rows.
- AI JSON is a versioned transport contract only. It is validated, normalized, and decomposed into relational rows.

## Current Storage Targets
- Local development database: SQLite
- Hosted database target: PostgreSQL
- Structured payloads are stored as JSON text in SQLite-compatible form

## Core Enums

### content_status
- `draft`
- `active`
- `disabled`
- `archived`

### question_revision_status
- `draft`
- `published`
- `archived`

### question_format
- `mcq`
- `msq`
- `nat`
- `match`

### answer_type
- `option_labels`
- `numeric`
- `pairs`

### difficulty_level
- `easy`
- `medium`
- `hard`

### question_type
- `definition`
- `identification`
- `trap`
- `application`
- `comparison`
- `reasoning`

### ai_import_batch_status
- `needs_review`
- `ready`
- `materialized`
- `published`
- `failed`

### attempt_status
- `in_progress`
- `submitted`
- `evaluated`

## Tables

### admins
- platform operators
- `id`, `email`, `full_name`, `password_hash`, `is_active`, timestamps

### subjects
- top-level syllabus grouping
- `id`, `name`, `grade`, `board`, `status`, timestamps

### chapters
- syllabus chapter under a subject
- `id`, `subject_id`, `chapter_number`, `name`, `status`, timestamps

### topics
- admin-managed syllabus topic under a chapter
- `id`, `chapter_id`, `name`, `display_order`, `status`, timestamps

### concepts
- finer instructional grouping under a topic
- used for AI imports and finer filtering
- `id`, `topic_id`, `name`, `display_order`, `status`, `source_concept_key`, timestamps

### textbook_documents
- uploaded book or chapter source file

### extraction_runs
- one OCR/import run for a textbook document

### extracted_assets
- figure candidates and approved figures
- review state stays here

### ai_import_batches
- one external AI payload ingestion run
- stores `schema_version`, `source_file_path`, uploader, optional resolved subject/chapter/topic, `status`
- stores `validation_summary`, `raw_payload`, `normalized_payload`
- tracks `materialized_question_count`, `published_question_count`, approver, and timestamps

### ai_import_batch_questions
- per-question audit row for one import batch
- stores source question id, concept name, short preview text, format, validation status/errors
- links to created `question_item_id` and `question_revision_id` after materialization

### question_items
- stable logical question identity
- tied to one `concept_id`
- stores source lineage, creator, current draft revision pointer, current published revision pointer, lifecycle status, soft-delete flag, timestamps
- this row is what admin filters and test builders reason about

### question_revisions
- immutable question content snapshot
- tied to one `question_item_id`
- stores revision number, parent revision link, creator, `format`, `difficulty`, `type`, `text`
- stores `answer_type`, `answer_payload`, `scoring_payload`
- stores `revision_status`, `published_at`, timestamps

### question_revision_options
- child rows for `mcq` and `msq`
- one row per option label A-D
- stores `is_correct` and `display_order`

### question_revision_numeric_answers
- child row for `nat`
- stores `exact_value`, `tolerance`, `unit`

### question_revision_match_sets
- container row for one `match` question revision
- stores `a_heading` and `b_heading`

### question_revision_match_left_items
- left column items for `match`
- stores `label`, `text`, `matches_right_label`, `display_order`

### question_revision_match_right_items
- right column items for `match`
- stores `label`, `text`, `display_order`

### question_revision_figures
- optional figures linked to a specific revision
- preserves exact figure usage by revision

### students
- learner records used for attempts and assignments

### tests
- logical generated test
- stores creator, syllabus scope, status, counts, and template flag

### test_question_revisions
- immutable snapshot membership table for tests
- stores exact `question_item_id` and exact `question_revision_id`
- guarantees later question edits do not mutate old tests

### batches
- student grouping for future assignment workflows

### batch_students
- many-to-many mapping between students and batches

### assignments
- published test delivery to one student or one batch

### attempts
- one learner attempt for one test
- stores score summary and timestamps

### attempt_answers
- one submitted answer per snapshotted test question
- stores exact `test_question_revision_id`, exact `question_revision_id`, normalized `answer_data`, correctness, selected count, and earned score

### admin_activity_logs
- audit log for content, imports, publishing, tests, and attempts

## Key Relationships
- one subject has many chapters
- one chapter has many topics
- one topic has many concepts
- one concept has many question items
- one question item has many revisions
- one question revision has either:
  - four options
  - one numeric answer row
  - one match set with left/right item rows
- one AI import batch can materialize many question items and revisions
- one test has many snapshotted question revisions
- one attempt has many attempt answers tied to those snapshots

## Current Lifecycle Rules
- AI imports create or update `ai_import_batches`, never live questions directly
- materialization creates draft or published revisions under `question_items`
- publishing switches the `question_items.current_published_revision_id`
- admin edits create new revisions instead of mutating published content
- disabling or archiving affects future test generation only
- existing tests and attempts remain pinned to prior revisions

## Current Scoring Rules
- `mcq`: exact single-label match
- `msq`: exact set match
- `nat`: numeric tolerance check
- `match`: exact pair mapping match
