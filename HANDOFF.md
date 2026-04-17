# BrainGain Handoff

## Project Path
- `/home/harsh-suryawanshi/projects/BrainGain`

## Read First
- `README.md`
- `STATUS.md`
- `ARCHITECTURE.md`
- `database_schema.md`

## Current Stack
- Python
- FastAPI
- SQLite
- OpenCV
- RapidOCR
- `pdftoppm`

## Important Files
- Backend: `api/app.py`
- Database bootstrap: `api/database.py`
- Question bank import: `api/question_bank_import.py`
- OCR pipeline: `ocr_books.py`
- Frontend: `web/index.html`
- Frontend logic: `web/app.js`
- Student frontend: `web/student.html`
- Student frontend logic: `web/student.js`
- Styles: `web/styles.css`
- Prompt: `prompts/question-bank-generator.md`
- Dependencies: `requirements.txt`

## Current Product State
- OCR reads files from `Books/`
- OCR writes output to `OCR_Output/`
- Figure candidates are extracted and reviewed separately
- Login UI is served at `http://127.0.0.1:8000/`
- Admin UI is served by FastAPI at `http://127.0.0.1:8000/admin`
- Student UI is served by FastAPI at `http://127.0.0.1:8000/student`
- Admin UI supports:
  - subject, chapter, topic creation
  - subject deletion
  - question-bank JSON validate by drag and drop
  - question-bank JSON import into a review session
  - editing imported review questions before approval
  - approval of reviewed questions into the live database
  - figure-review manifest import by drag and drop
  - manual MCQ and MSQ creation
  - figure approval and rejection
  - admin activity history
  - debug log output in the UI
- Admin UI also supports:
  - test generation from admin-selected questions in a chapter-topic-question builder
- Student UI supports:
  - loading generated tests
  - starting an attempt
  - submitting answers
  - seeing a scored result immediately
- Student UI now supports `mcq`, `msq`, `nat`, and `match`
- Admin manual question screens are still compatibility-oriented and not yet a full revision-history UI

## Important Fix Already Made
- Upload routes required `python-multipart`
- It is now included in `requirements.txt`
- Without that package, drag-and-drop validate/import will not work

## Run Commands
```bash
cd /home/harsh-suryawanshi/projects/BrainGain
pip3 install --break-system-packages -r requirements.txt
python3 run_api.py
```

## Demo Credentials
- Admin: `admin@braingain.local` / `admin123`
- Student: `student@braingain.local` / `student123`

## Current Data State
- Local database:
  - `data/braingain.sqlite3`
- If that SQLite file still contains the legacy schema, startup now rolls it to a timestamped `*.legacy-YYYYMMDDHHMMSS.sqlite3` backup and recreates the current schema
- Test subjects were cleared
- Current `subjects` table should be empty unless new data was added after this handoff

## Current Known Priority
1. Use the admin app to keep the active question bank healthy
2. Use the student app to verify generated tests and scoring on real content
3. Decide whether the next build step is assignment/batch workflows or analytics

## Working Rules
- Keep file count low
- One responsibility per file
- Clear names, no abbreviations
- Functions are verbs
- Booleans start with `is`, `has`, or `can`
- Use `apply_patch` for edits
- Update `database_schema.md` whenever database-related code changes

## Likely Next Step
- Start the API
- Open `/` for admin workflows and `/practice` for the learner flow
- If test generation fails, check whether the selected questions are `active`
- If attempt scoring fails, inspect `api/app.py` and `smoke_test_product.py`
