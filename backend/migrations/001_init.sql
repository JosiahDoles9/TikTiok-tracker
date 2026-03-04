CREATE TABLE IF NOT EXISTS sync_logs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  progress_percent INTEGER NOT NULL DEFAULT 0,
  current_category TEXT,
  error_message TEXT,
  per_category_results TEXT NOT NULL,
  stale_after_minutes INTEGER NOT NULL DEFAULT 30
);

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  rank INTEGER,
  price REAL,
  currency TEXT,
  metric_name TEXT,
  metric_value REAL,
  product_url TEXT NOT NULL,
  thumbnail_url TEXT,
  source TEXT NOT NULL,
  last_updated_at TEXT NOT NULL,
  normalized_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL,
  video_url TEXT NOT NULL,
  creator_handle TEXT,
  views INTEGER,
  likes INTEGER,
  comments INTEGER,
  shares INTEGER,
  posted_at TEXT,
  ai_analysis_json TEXT,
  ai_why_it_did_well TEXT,
  FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_metric ON products(metric_value DESC);
CREATE INDEX IF NOT EXISTS idx_videos_product ON videos(product_id);
