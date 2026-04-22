# BrainGain Status

## Working Now
- revisioned question bank with immutable published snapshots
- AI import validation and materialization
- manual question creation and publishing
- test generation from active published questions
- student attempts with autosave, resume, submission, and scoring

## Verified
- `python3 smoke_test_product.py` passes on a fresh temp SQLite database
- covered formats: `mcq`, `msq`, `nat`, `match`
- covered student path: start attempt, save answers, submit, score results

## Remaining Gaps
- admin UI still exposes revision behavior through compatibility-oriented screens
- local development is SQLite-first; PostgreSQL migration work is not done
