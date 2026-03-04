CREATE TABLE IF NOT EXISTS tiktok_accounts (
  id TEXT PRIMARY KEY,
  app_user_id TEXT NOT NULL,
  open_id TEXT NOT NULL UNIQUE,
  union_id TEXT,
  display_name TEXT,
  avatar_url TEXT,
  profile_url TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tiktok_tokens (
  id TEXT PRIMARY KEY,
  tiktok_account_id TEXT NOT NULL UNIQUE,
  access_token_encrypted TEXT NOT NULL,
  refresh_token_encrypted TEXT NOT NULL,
  scopes TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  refresh_expires_at TEXT,
  last_refreshed_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(tiktok_account_id) REFERENCES tiktok_accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tiktok_videos (
  id TEXT PRIMARY KEY,
  tiktok_account_id TEXT NOT NULL,
  video_id TEXT NOT NULL UNIQUE,
  title TEXT,
  description TEXT,
  create_time TEXT,
  duration_seconds INTEGER,
  embed_link TEXT,
  cover_image_url TEXT,
  share_url TEXT,
  raw_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(tiktok_account_id) REFERENCES tiktok_accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tiktok_video_metrics (
  id TEXT PRIMARY KEY,
  tiktok_video_id TEXT NOT NULL,
  like_count INTEGER,
  comment_count INTEGER,
  share_count INTEGER,
  view_count INTEGER,
  collected_at TEXT NOT NULL,
  FOREIGN KEY(tiktok_video_id) REFERENCES tiktok_videos(id) ON DELETE CASCADE,
  UNIQUE(tiktok_video_id, collected_at)
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  tiktok_account_id TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  cursor_start TEXT,
  cursor_end TEXT,
  fetched_videos INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT,
  FOREIGN KEY(tiktok_account_id) REFERENCES tiktok_accounts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tiktok_videos_account_time ON tiktok_videos(tiktok_account_id, create_time);
CREATE INDEX IF NOT EXISTS idx_tiktok_metrics_video_time ON tiktok_video_metrics(tiktok_video_id, collected_at);
