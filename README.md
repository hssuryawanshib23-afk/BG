# BrainGain

BrainGain is a FastAPI + SQLite prototype for building a revisioned question bank, generating published tests, and letting students take scored attempts.

## What Works
- syllabus structure: `subjects -> chapters -> topics -> concepts`
- OCR/figure review pipeline for textbook assets
- AI question-bank import with validation and materialization
- immutable question revisions and published snapshots
- test generation from active published questions
- student attempt flow for `mcq`, `msq`, `nat`, and `match`

## Run
```bash
pip3 install --break-system-packages -r requirements.txt
python3 run_api.py
python3 smoke_test_product.py
```

## Graphify Pack
`BrainGain` now includes a generated `.graphify/` folder that acts as a high-signal project map for LLMs.

Use it like this:
- start with `.graphify/llm_context.md`
- inspect `.graphify/graph.json` for file, symbol, and import relationships
- open raw files only after locating the relevant paths in the graph

Regenerate the pack after project changes:
```bash
python3 scripts/build_graphify.py
```

## Main Files
- `api/app.py`: routes and business flow
- `api/database.py`: schema bootstrap and connection helpers
- `api/question_bank_import.py`: import validation/materialization
- `web/`: admin, login, and student static UI
- `smoke_test_product.py`: end-to-end verification

## Notes
- Local startup protects against the old SQLite schema by moving the legacy file aside before creating the current schema.
- JSON imports are treated as transport input, not the live source of truth.
- The student UI only lists published tests and resumes an in-progress attempt for the same student and test.
