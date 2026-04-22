# BrainGain Architecture

## Flow
```text
Books -> OCR / figure extraction -> reviewable assets
AI JSON -> validation -> import batch -> question revisions
Published revisions -> generated tests -> student attempts -> scored results
```

## Core Layers
- ingestion: OCR output and AI question-bank uploads
- content model: syllabus, concepts, question items, immutable question revisions
- delivery: published tests backed by `test_question_revisions`
- assessment: attempts and per-question saved answers

## Backend
- `run_api.py`: startup entry point
- `api/app.py`: route handlers and orchestration
- `api/database.py`: schema setup and low-level DB helpers
- `api/question_bank_import.py`: import validation and materialization

## Frontend
- `/`: login
- `/admin`: admin workflow surface
- `/student`: student attempt runner
- static assets live in `web/`

## Key Rules
- published tests snapshot exact question revisions
- attempts score against those snapshots, not mutable live content
- AI JSON is audited and normalized before relational storage
- `database_schema.md` is the schema source of truth
