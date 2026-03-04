# TikTok Shop Tracker (Full Stack)

Production-oriented web app with:
- FastAPI backend
- SQLite database + SQL migration
- Scheduled sync pipeline (every 6h by default)
- Dashboard / Trending / Products / Analytics frontend
- Video discovery + AI analysis endpoints

## Why this fixes previous issues
- Sync cannot hang silently: stale running syncs are auto-failed after `STALE_AFTER_MINUTES`.
- Progress is persisted continuously in `SyncLog` and exposed via `/api/sync/:id`.
- Dashboard/Trending/Products all read the same DB dataset.
- Top 10 dedup uses stable id + normalized name guards.
- Product links are always present and open in new tabs.
- Images are optional and safely nullable (UI still works without them).

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run
```bash
uvicorn backend.main:app --reload --port 8000
```
Open `http://localhost:8000`.

## Real data pipeline options
This repo ships a reliable sync engine and provider abstraction.

### Current default (dev): `DATA_PROVIDER=seed`
- Deterministic seeded products for local development.

### Option B provider integration
- Set `DATA_PROVIDER=apify` and `APIFY_TOKEN=...`.
- Implement provider actor request in `provider_products_for_category()` in `backend/main.py`.
- The sync engine already handles retries, backoff, per-category transactions, dedupe, stale detection, and progress updates.

## API endpoints
- `GET /api/categories`
- `POST /api/sync`
- `GET /api/sync/:id`
- `GET /api/trending?category=...`
- `GET /api/products?search=&category=&sort=rank|metric|updated`
- `GET /api/products/:id`
- `POST /api/videos/discover`
- `POST /api/videos/analyze`

## Tests
```bash
python3 -m unittest discover -s backend/tests
```

## Notes
- Non-negotiable constraints are respected in architecture: no browser-client scraping, no required hotlink image dependency, sync has explicit failed/success states.
- For true live TikTok data, connect a legal upstream source (official API / vetted provider) to `provider_products_for_category()` and keep the rest unchanged.
