# BrainGain Handoff

## Project
- path: `/home/harsh-suryawanshi/projects/BrainGain`
- stack: Python, FastAPI, SQLite, OpenCV, RapidOCR

## Read In Order
1. `README.md`
2. `STATUS.md`
3. `database_schema.md`
4. `api/app.py`

## Key Files
- backend: `api/app.py`, `api/database.py`, `api/question_bank_import.py`
- frontend: `web/index.html`, `web/app.js`, `web/student.html`, `web/student.js`
- verification: `smoke_test_product.py`
- prompt contract: `prompts/question-bank-generator.md`

## Run
```bash
cd /home/harsh-suryawanshi/projects/BrainGain
pip3 install --break-system-packages -r requirements.txt
python3 run_api.py
```

## URLs
- login: `http://127.0.0.1:8000/`
- admin: `http://127.0.0.1:8000/admin`
- student: `http://127.0.0.1:8000/student`

## Demo Credentials
- admin: `admin@braingain.local` / `admin123`
- student: `student@braingain.local` / `student123`

## Current Behavior
- startup protects against the legacy SQLite schema by backing it up before recreating the current schema
- student view only shows published tests
- starting the same test with the same student identity resumes an in-progress attempt

## Rules
- use `apply_patch` for edits
- update `database_schema.md` when schema changes
