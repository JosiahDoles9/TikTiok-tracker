# TikTok Shop Tracker (Full Stack)

Production-oriented web app with:
- FastAPI backend
- SQLite database + SQL migrations
- Scheduled sync pipeline
- Dashboard / Trending / Products / Analytics UI
- TikTok Display API integration for creator profile + video metrics

## Important scope
This integration uses **TikTok Display API** for creator and video metadata.
It does **not** provide TikTok Shop orders/revenue/product catalog sales from TikTok Shop APIs.

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

## TikTok Display API setup
Configure in `.env`:
- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_REDIRECT_URI`
- `TIKTOK_SCOPES` (ex: `user.info.basic,video.list`)
- `TIKTOK_API_BASE_URL` (default `https://open.tiktokapis.com`)
- `TOKEN_ENCRYPTION_KEY` for encrypted token storage

OAuth flow:
1. Frontend TikTok tab calls `GET /api/integrations/tiktok/connect`
2. User authorizes on TikTok
3. TikTok redirects to `GET /api/integrations/tiktok/callback?code=...`
4. Backend exchanges code, stores encrypted access/refresh tokens, and links account

## New TikTok endpoints
- `GET /api/integrations/tiktok/connect`
- `GET /api/integrations/tiktok/callback`
- `POST /api/integrations/tiktok/sync`
- `GET /api/integrations/tiktok/accounts`
- `GET /api/integrations/tiktok/videos`
- `GET /api/integrations/tiktok/best-performing`
- `GET /api/integrations/tiktok/sync-runs`

## Data model additions
Migration `002_tiktok_display_api.sql` adds:
- `tiktok_accounts`
- `tiktok_tokens`
- `tiktok_videos`
- `tiktok_video_metrics`
- `sync_runs`

## Reliability behavior
- Retry with exponential backoff for TikTok API 429/5xx
- Cursor pagination for `/v2/video/list/` with repeat-cursor stop guard
- Idempotent upserts for accounts/videos/tokens
- Token refresh before expiry
- If token invalid: TikTok sync run marked failed with reconnect-required action in errors

## Tests
```bash
python3 -m unittest discover -s backend/tests
```

## Notes
- Tokens are encrypted at rest and never returned from API responses.
- Existing product dashboard features remain intact.
