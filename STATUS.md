# BrainGain Status

## Current State
- BrainGain now uses a revisioned question-bank backend instead of mutable live question rows.
- Syllabus structure is now `subject -> chapter -> topic -> concept`.
- Question identity and question content are separated:
  - `question_items` hold lifecycle and lineage
  - `question_revisions` hold immutable content snapshots
- Supported question formats are now:
  - `mcq`
  - `msq`
  - `nat`
  - `match`
- AI question-bank JSON is now treated as a versioned transport contract, not a storage format.
- AI imports now flow through:
  - validation
  - import batch creation
  - payload review/edit
  - materialization into draft or published revisions
- Tests now snapshot exact published revisions through `test_question_revisions`.
- Student attempts now score against those immutable snapshots.
- Later admin edits do not mutate historical tests or scores.

## Verified Flow
- Verified on a fresh temporary SQLite database through `python3 smoke_test_product.py`
- Confirmed working flow:
  - create subject, chapter, topic
  - create AI import batch from versioned JSON
  - materialize imported questions into the database
  - auto-publish imported questions
  - create and publish a manual draft question
  - generate a test from published question items
  - start a student attempt
  - submit correct answers for MCQ, MSQ, NAT, and match
  - retrieve a 100% scored result

## Current Product Direction
- Keep admin operations database-first and UI-driven.
- Keep raw AI payloads only for audit and troubleshooting.
- Keep all future test generation restricted to active question items with published revisions.
- Preserve immutable history for any question revision that has appeared in a generated test or student attempt.

## Main Backend Areas
- `api/database.py`: schema bootstrap and shared database helpers
- `api/question_bank_import.py`: versioned AI import validation and materialization
- `api/app.py`: FastAPI routes for syllabus management, import batches, revision lifecycle, tests, and attempts
- `smoke_test_product.py`: end-to-end verification

## Current Known Gaps
- The admin frontend still needs a full pass to expose the revision lifecycle natively instead of through compatibility shims.
- PostgreSQL-first migration tooling is still not in place yet; local and smoke validation currently run on SQLite.
- The current startup path now protects local development by rolling legacy SQLite files into timestamped backups before creating the current schema.
