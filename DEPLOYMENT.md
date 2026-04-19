# BrainGain Deployment

## Current Recommendation
- deploy the whole FastAPI app first
- use managed Postgres
- keep frontend served by FastAPI for the first live launch

This is the simplest path because the current `web/` app uses same-origin `fetch(...)` calls.

## Environment Variables
- `DATABASE_URL=postgresql://...`
- `PORT=8000`
- `BRAINGAIN_HOST=0.0.0.0`
- `BRAINGAIN_CORS_ORIGINS=https://your-frontend-domain.vercel.app`

## Local Migration To Postgres
1. install dependencies
2. provision Postgres
3. run:

```bash
export DATABASE_URL='postgresql://...'
export SOURCE_SQLITE_PATH='/absolute/path/to/data/braingain.sqlite3'
python3 scripts/migrate_sqlite_to_postgres.py
```

## Railway
1. Push repo to GitHub.
2. Create a new Railway project from the GitHub repo.
3. Add a PostgreSQL service.
4. In the app service, set:
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `PORT=8000`
   - `BRAINGAIN_HOST=0.0.0.0`
5. Start command:

```bash
python3 run_api.py
```

## Render
1. Push repo to GitHub.
2. Create a new Web Service from the repo.
3. Create a PostgreSQL database in Render.
4. Add env vars:
   - `DATABASE_URL=<Render external database URL>`
   - `PORT=8000`
   - `BRAINGAIN_HOST=0.0.0.0`
5. Build command:

```bash
pip3 install -r requirements.txt
```

6. Start command:

```bash
python3 run_api.py
```

## Vercel
Use Vercel later for a separate frontend only.

Before that split, the frontend needs:
- configurable API base URL instead of same-origin fetches
- static asset path cleanup for Vercel hosting

For the first production launch, do not split yet.
