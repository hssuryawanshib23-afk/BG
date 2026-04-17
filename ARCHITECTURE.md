# BrainGain Architecture

## Current Implementation
The project starts with a file-based OCR pipeline.

```text
Books
  -> OCR pipeline
  -> OCR_Output
  -> later question generation
  -> later validation and ingestion
```

## Current OCR Flow
1. Read every supported file from `Books`
2. Convert PDF pages to images
3. Preprocess images with OpenCV
4. Run OCR with RapidOCR
5. Detect non-text figure regions on each page
6. Match nearby captions such as `Fig. 4.1` where possible
7. Filter text-heavy regions before saving figure candidates
8. Write page text, block-level OCR data, cropped figures, and review metadata to `OCR_Output`

## Current Output Structure
```text
OCR_Output/
  <book-name>/
    manifest.json
    figures/
      page-07-Fig-4.1.png
    figure_review_manifest.json
    page_text/
      page-01.txt
      page-01.blocks.json
```

## Design Direction
- Keep OCR output on disk first
- Improve figure detection and caption matching after OCR is stable
- Add database ingestion only after the extracted data shape is reliable

## Next Platform Step
The next stable step is not another OCR feature. It is the content-management layer that can store:
- subjects
- chapters
- topics
- approved figures
- manual MCQs and MSQs
- options
- question-to-figure links

## Why This Is Next
- OCR already gives usable figure assets.
- You want to generate image-based questions separately later.
- That means the platform now needs a clean admin flow to attach an approved figure to an MCQ or MSQ under a specific topic and chapter.
- Without this layer, extracted figures remain files, not reusable assessment content.

## Content Management Flow
1. Admin creates or selects a subject.
2. Admin creates or selects a chapter.
3. Admin creates or selects a topic.
4. Admin reviews extracted figure candidates and approves good ones.
5. Admin can also upload a JSON file that already includes metadata and questions.
6. The uploaded JSON is validated and stored in a review session.
7. Admin sees all imported questions, edits them if needed, and approves them into the live bank.
8. Admin creates a question manually and chooses `mcq` or `msq`.
9. Admin adds four options and marks the correct option set.
10. Admin links one or more approved figures to the question.
11. Admin activates the question for test generation.

## Backend Module Boundary
- `content_structure`
  Stores subjects, chapters, and topics.
- `extracted_assets`
  Stores approved figures and their review state.
- `question_bank_import`
  Validates JSON, stores editable review sessions, and approves reviewed question banks into the live model.
- `questions`
  Stores manual MCQs, MSQs, options, and question-figure links.
- `admin_activity`
  Stores audit history for imports, approvals, deletions, and other admin actions.
- `tests`
  Builds tests from active questions with hard-question enforcement.

## UI Boundary
- Admin app
  - content structure
  - figure review
  - question import review
  - live question editing
  - test generation
- Student app
  - available tests
  - attempt taking
  - results

## Source Of Truth
- `database_schema.md` is now the source of truth for this phase.
- Backend code should follow that schema instead of inventing table shapes later.

## Current Backend Baseline
- Framework: FastAPI
- Development storage: SQLite through the standard library `sqlite3`
- Entry point: `run_api.py`
- Database bootstrap: `api/database.py`
- Route layer: `api/app.py`

## Current Frontend Baseline
- Centralized login page at `/`
- Static admin app served by FastAPI
- Static student practice app served by FastAPI
- No frontend framework yet
- One page for admin workflows
- One page for learner attempts
- One page for demo login and role routing
- Upload-first testing flow through drag-and-drop file inputs
- One debug panel for request and error visibility
- Student practice now handles `mcq`, `msq`, `nat`, and `match`
- Admin manual editing is still in transition from the legacy flat-question UI to the revision-first backend

## Implemented Endpoints
- `GET /health`
- `GET /`
- `GET /project-files/{file_path}`
- `GET /admins`
- `GET /tests`
- `GET /tests/{test_id}`
- `POST /tests/generate`
- `POST /students/ensure`
- `POST /attempts/start`
- `GET /attempts/{attempt_id}`
- `POST /attempts/{attempt_id}/submit`
- `GET /attempts/{attempt_id}/results`
- `GET /admin-activity`
- `DELETE /subjects/{subject_id}`
- `POST /subjects`
- `GET /subjects`
- `POST /chapters`
- `GET /subjects/{subject_id}/chapters`
- `POST /topics`
- `GET /chapters/{chapter_id}/topics`
- `POST /figure-review/import`
- `POST /figure-review/import-upload`
- `GET /chapters/{chapter_id}/figure-candidates`
- `PATCH /extracted-assets/{asset_id}/review`
- `GET /topics/{topic_id}/approved-figures`
- `POST /questions`
- `GET /topics/{topic_id}/questions`
- `POST /question-banks/validate`
- `POST /question-banks/validate-upload`
- `POST /question-banks/import`
- `POST /question-banks/import-upload`
- `GET /question-banks/imports`
- `GET /question-banks/imports/{question_bank_import_id}`
- `PATCH /question-banks/imports/{question_bank_import_id}/questions`
- `POST /question-banks/imports/{question_bank_import_id}/approve`

## Implemented Admin UI Workflows
- subject creation
- subject deletion
- chapter creation
- topic creation
- admin activity viewing
- figure review manifest upload
- figure approval and rejection
- question-bank validation by drag-and-drop upload
- question-bank import into review by drag-and-drop upload
- imported-question editing before approval
- approval of reviewed questions into the database
- manual MCQ and MSQ creation
- test generation from active questions
- learner-facing practice page with scoring

## Local Database Safety
- If the default local SQLite file still uses the legacy schema, startup now moves that file to a timestamped backup and recreates the current revisioned schema.
- This is a safety rollover, not a relational migration.
