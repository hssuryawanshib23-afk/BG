# BrainGain

BrainGain converts textbook content into a structured, revisioned question bank that admins can review, publish, edit safely, and use for both admin-created tests and student practice tests.

## Current Scope
- OCR textbooks and extract figure candidates
- Review and approve figures
- Import AI-generated question banks through a versioned JSON contract
- Materialize questions into relational storage
- Support immutable question revision history
- Generate tests from active published questions
- Let students take tests and receive scored results

## Supported Question Formats
- `mcq`
- `msq`
- `nat`
- `match`

## Current Commands
```bash
pip3 install --break-system-packages -r requirements.txt
python3 run_api.py
python3 smoke_test_product.py
```

## Current Local Safety Behavior
- On startup, BrainGain detects the legacy pre-revision SQLite schema and automatically moves it aside to a timestamped backup before creating the current schema.
- This avoids booting the new code against stale local tables such as `questions` and `question_bank_imports`.

## Current Backend Shape
- FastAPI API in `api/app.py`
- Database bootstrap in `api/database.py`
- AI import validation and materialization in `api/question_bank_import.py`
- Local development database defaults to SQLite
- Production target remains PostgreSQL

## Current Data Model
- `subjects -> chapters -> topics -> concepts`
- `question_items` are stable logical questions
- `question_revisions` are immutable content snapshots
- Tests store exact revision snapshots
- Attempts score against those stored snapshots

## Current AI Import Principle
- JSON is a transport contract only
- The system validates and normalizes the payload
- The system stores the raw payload for audit
- The system decomposes the content into relational rows
- The system never uses raw JSON as the operational source of truth

## Verification Snapshot
- `python3 smoke_test_product.py` verifies:
  - AI import batch creation
  - import materialization
  - question publishing
  - manual draft question creation
  - test generation
  - student attempt scoring across MCQ, MSQ, NAT, and match

## Frontend Snapshot
- Student practice flow now handles `mcq`, `msq`, `nat`, and `match`.
- The admin UI remains partly compatibility-driven:
  - legacy admin manual question screens are bridged to the new revisioned backend
  - full revision-history UX still needs a dedicated frontend pass
