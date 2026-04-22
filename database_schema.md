# BrainGain Database Schema

Canonical schema reference. Update this file whenever tables, columns, relationships, or lifecycle rules change.

## Model Summary
- syllabus: `subjects -> chapters -> topics -> concepts`
- question identity: `question_items`
- immutable content snapshots: `question_revisions`
- published test snapshots: `test_question_revisions`
- learner work: `attempts` and `attempt_answers`

## Important Status Values
- content lifecycle: `draft`, `active`, `disabled`, `archived`
- revision status: `draft`, `published`, `archived`
- question formats: `mcq`, `msq`, `nat`, `match`
- answer types: `option_labels`, `numeric`, `pairs`
- attempt status: `in_progress`, `submitted`, `evaluated`

## Table Groups

### Users
- `admins`: operators
- `students`: learner identity used for attempts and future assignments

### Syllabus
- `subjects`
- `chapters`
- `topics`
- `concepts`

### Ingestion And Assets
- `textbook_documents`
- `extraction_runs`
- `extracted_assets`
- `ai_import_batches`
- `ai_import_batch_questions`

### Question Bank
- `question_items`: logical question identity, lifecycle state, published/draft pointers
- `question_revisions`: immutable snapshot of question content
- `question_revision_options`: MCQ/MSQ options
- `question_revision_numeric_answers`: NAT answer record
- `question_revision_match_sets`: match-question header row
- `question_revision_match_left_items`
- `question_revision_match_right_items`
- `question_revision_figures`

### Delivery
- `tests`: generated test shell, scope, status, configured `time_limit_minutes`, counts
- `test_question_revisions`: exact question revision membership for a test
- `batches`
- `batch_students`
- `assignments`

### Attempts And Audit
- `attempts`: one learner run for one test
- `attempt_answers`: saved answer per snapshotted test question
- `admin_activity_logs`

## Rules
- AI imports materialize into relational rows; raw JSON is audit input only.
- Published tests must point to exact question revisions.
- Attempts must score against those exact stored revisions.
- Later question edits must not mutate old tests or old attempt results.

## Scoring
- `mcq`: exact single-label match
- `msq`: exact set match
- `nat`: numeric tolerance check
- `match`: exact pair mapping
