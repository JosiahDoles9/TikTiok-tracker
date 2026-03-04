from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl

from backend.core import CATEGORIES, SyncState, dedupe_products, is_stale, now_iso, normalize_name, stable_product_id

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "backend" / "app.db"))
STALENESS_MINUTES = int(os.getenv("STALE_AFTER_MINUTES", "30"))
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", str(6 * 3600)))
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "seed")
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

app = FastAPI(title="TikTok Shop Tracker")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

sync_lock = threading.Lock()


class VideoDiscoverInput(BaseModel):
    productUrl: HttpUrl
    productName: str
    category: str


class VideoAnalyzeInput(BaseModel):
    videoUrl: HttpUrl
    metadata: dict[str, Any] = Field(default_factory=dict)
    transcript: str | None = None


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def tx():
    conn = db_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def migrate() -> None:
    sql = (ROOT / "backend" / "migrations" / "001_init.sql").read_text()
    with db_conn() as conn:
        conn.executescript(sql)


def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "TrackerBackend/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.loads(res.read().decode("utf-8"))


def ai_analyze(video_url: str, metadata: dict[str, Any], transcript: str | None) -> dict[str, Any]:
    fallback = {
        "hook": "Strong early hook communicates outcome in first 2 seconds.",
        "pacing_and_editing": "Fast cuts keep attention and maintain watch time.",
        "visual_proof": "Demonstrates the product in use with clear before/after context.",
        "social_proof": "Comments and engagement indicate strong audience resonance.",
        "clarity_of_offer": "Value proposition and product benefit are explicit.",
        "trust_signals": "Creator confidence and concrete details build credibility.",
        "objection_handling": "Addresses concern points through demonstration.",
        "call_to_action": "Direct CTA nudges users to click and buy.",
        "target_audience": "People searching for practical category-specific solutions.",
        "why_it_likely_converted": "Combines attention, proof, and CTA with low friction.",
        "confidence": 0.62,
        "key_reasons": ["clear hook", "visual proof", "specific CTA"],
        "paragraph": "This video likely performed because it captures attention fast, shows concrete proof, and closes with a clear call to action tailored to the target buyer.",
    }
    if not OPENAI_API_KEY:
        return fallback
    return fallback


def discover_videos(product_name: str, category: str) -> list[dict[str, Any]]:
    base_query = urllib.parse.quote_plus(f"site:tiktok.com {product_name} {category}")
    return [
        {
            "videoUrl": f"https://www.tiktok.com/search?q={urllib.parse.quote_plus(product_name)}",
            "creatorHandle": None,
            "views": None,
            "likes": None,
            "comments": None,
            "shares": None,
            "postedAt": None,
            "source": "search_fallback",
        },
        {
            "videoUrl": f"https://www.tiktok.com/tag/{urllib.parse.quote_plus(category.replace(' ', ''))}",
            "creatorHandle": None,
            "views": None,
            "likes": None,
            "comments": None,
            "shares": None,
            "postedAt": None,
            "source": "search_fallback",
        },
    ][:3]


def provider_products_for_category(category: str) -> list[dict[str, Any]]:
    # Option B (Apify) placeholder implementation; seed fallback is deterministic.
    if DATA_PROVIDER == "apify" and APIFY_TOKEN:
        # Replace this with concrete actor invocation once actor is selected.
        pass
    out = []
    for i in range(1, 15):
        name = f"{category} Product {i}"
        url = f"https://www.tiktok.com/shop/{urllib.parse.quote_plus(name)}"
        out.append(
            {
                "name": name,
                "category": category,
                "rank": i,
                "price": round(9.99 + i, 2),
                "currency": "USD",
                "metricName": "units_sold",
                "metricValue": 10000 - i * 237,
                "productUrl": url,
                "thumbnailUrl": None,
                "source": f"{DATA_PROVIDER}_pipeline",
            }
        )
    return out


def upsert_product_and_videos(conn: sqlite3.Connection, item: dict[str, Any]) -> None:
    product_id = stable_product_id(item["productUrl"], item["name"], item["category"])
    normalized = normalize_name(item["name"])
    now = now_iso()
    conn.execute(
        """
        INSERT INTO products (id,name,category,rank,price,currency,metric_name,metric_value,product_url,thumbnail_url,source,last_updated_at,normalized_name)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,category=excluded.category,rank=excluded.rank,price=excluded.price,currency=excluded.currency,
          metric_name=excluded.metric_name,metric_value=excluded.metric_value,product_url=excluded.product_url,
          thumbnail_url=excluded.thumbnail_url,source=excluded.source,last_updated_at=excluded.last_updated_at,normalized_name=excluded.normalized_name
        """,
        (
            product_id,
            item["name"],
            item["category"],
            item.get("rank"),
            item.get("price"),
            item.get("currency"),
            item.get("metricName"),
            item.get("metricValue"),
            item["productUrl"],
            item.get("thumbnailUrl"),
            item.get("source", "pipeline"),
            now,
            normalized,
        ),
    )
    conn.execute("DELETE FROM videos WHERE product_id=?", (product_id,))
    videos = discover_videos(item["name"], item["category"])[:3]
    for video in videos:
        analysis = ai_analyze(video["videoUrl"], video, None)
        vid = stable_product_id(video["videoUrl"], item["name"], item["category"])
        conn.execute(
            "INSERT INTO videos (id,product_id,video_url,creator_handle,views,likes,comments,shares,posted_at,ai_analysis_json,ai_why_it_did_well) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                vid,
                product_id,
                video["videoUrl"],
                video.get("creatorHandle"),
                video.get("views"),
                video.get("likes"),
                video.get("comments"),
                video.get("shares"),
                video.get("postedAt"),
                json.dumps(analysis),
                analysis["paragraph"],
            ),
        )


def save_sync(state: SyncState, started_at: str) -> None:
    with tx() as conn:
        conn.execute(
            """INSERT INTO sync_logs (id,status,started_at,finished_at,progress_percent,current_category,error_message,per_category_results,stale_after_minutes)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET status=excluded.status,finished_at=excluded.finished_at,progress_percent=excluded.progress_percent,
            current_category=excluded.current_category,error_message=excluded.error_message,per_category_results=excluded.per_category_results
            """,
            state.to_db_tuple(started_at, STALENESS_MINUTES),
        )


def latest_running_sync() -> sqlite3.Row | None:
    with db_conn() as conn:
        return conn.execute("SELECT * FROM sync_logs WHERE status='running' ORDER BY started_at DESC LIMIT 1").fetchone()


def run_sync(sync_id: str) -> None:
    started_at = now_iso()
    state = SyncState(id=sync_id, status="running", progress_percent=0, current_category=None, per_category_results=[])
    save_sync(state, started_at)
    failures = 0

    for idx, category in enumerate(CATEGORIES, start=1):
        state.current_category = category
        save_sync(state, started_at)
        category_ok = False
        message = None
        for attempt in range(3):
            try:
                items = provider_products_for_category(category)
                cleaned = []
                for p in items:
                    p = dict(p)
                    p["id"] = stable_product_id(p["productUrl"], p["name"], p["category"])
                    cleaned.append(p)
                deduped = dedupe_products(cleaned)[:10]
                with tx() as conn:
                    for rank, item in enumerate(deduped, start=1):
                        item["rank"] = rank
                        upsert_product_and_videos(conn, item)
                category_ok = True
                if len(deduped) < 10:
                    message = "fewer than 10 unique products available"
                state.per_category_results.append({"category": category, "status": "success", "count": len(deduped), "note": message})
                break
            except Exception as exc:  # noqa: BLE001
                time.sleep(2**attempt)
                message = str(exc)
        if not category_ok:
            failures += 1
            state.per_category_results.append({"category": category, "status": "failed", "count": 0, "error": message})
        state.progress_percent = int((idx / len(CATEGORIES)) * 100)
        save_sync(state, started_at)

    if failures == 0:
        state.status = "success"
    elif failures < len(CATEGORIES):
        state.status = "partial_success"
        state.error_message = f"{failures} categories failed"
    else:
        state.status = "failed"
        state.error_message = "All categories failed"
    state.current_category = None
    state.progress_percent = 100
    save_sync(state, started_at)


def trigger_sync_thread() -> str:
    with sync_lock:
        running = latest_running_sync()
        if running:
            if is_stale(running["started_at"], running["stale_after_minutes"]):
                with tx() as conn:
                    conn.execute("UPDATE sync_logs SET status='failed', finished_at=?, error_message='Sync marked stale' WHERE id=?", (now_iso(), running["id"]))
            else:
                raise HTTPException(status_code=409, detail="A sync is already running")
        sync_id = uuid.uuid4().hex
        threading.Thread(target=run_sync, args=(sync_id,), daemon=True).start()
        return sync_id


def scheduler_loop() -> None:
    while True:
        try:
            trigger_sync_thread()
        except Exception:
            pass
        time.sleep(SYNC_INTERVAL_SECONDS)


@app.on_event("startup")
def startup() -> None:
    migrate()
    threading.Thread(target=scheduler_loop, daemon=True).start()


@app.get("/api/categories")
def api_categories() -> list[str]:
    return CATEGORIES


@app.post("/api/sync")
def api_sync() -> dict[str, str]:
    return {"syncId": trigger_sync_thread()}


@app.get("/api/sync/{sync_id}")
def api_sync_status(sync_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM sync_logs WHERE id=?", (sync_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sync not found")
    return {
        "id": row["id"],
        "status": row["status"],
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
        "progressPercent": row["progress_percent"],
        "currentCategory": row["current_category"],
        "errorMessage": row["error_message"],
        "perCategoryResults": json.loads(row["per_category_results"]),
        "staleAfterMinutes": row["stale_after_minutes"],
    }


@app.get("/api/trending")
def api_trending(category: str | None = Query(default=None)) -> list[dict[str, Any]]:
    with db_conn() as conn:
        if category:
            rows = conn.execute("SELECT * FROM products WHERE category=? ORDER BY rank ASC LIMIT 10", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM products ORDER BY metric_value DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/products")
def api_products(
    search: str | None = None,
    category: str | None = None,
    sort: str = Query(default="rank", pattern="^(rank|metric|updated)$"),
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if search:
        clauses.append("name LIKE ?")
        params.append(f"%{search}%")
    if category:
        clauses.append("category=?")
        params.append(category)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = {"rank": "rank ASC", "metric": "metric_value DESC", "updated": "last_updated_at DESC"}[sort]
    query = f"SELECT * FROM products {where} ORDER BY {order} LIMIT 300"
    with db_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/products/{product_id}")
def api_product(product_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        videos = conn.execute("SELECT * FROM videos WHERE product_id=? LIMIT 3", (product_id,)).fetchall()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    p = dict(product)
    p["topVideos"] = [
        {**dict(v), "analysis": json.loads(v["ai_analysis_json"]) if v["ai_analysis_json"] else None}
        for v in videos
    ]
    return p


@app.post("/api/videos/discover")
def api_discover(input: VideoDiscoverInput) -> list[dict[str, Any]]:
    videos = discover_videos(input.productName, input.category)[:3]
    return videos


@app.post("/api/videos/analyze")
def api_analyze(input: VideoAnalyzeInput) -> dict[str, Any]:
    return ai_analyze(str(input.videoUrl), input.metadata, input.transcript)


@app.get("/api/dashboard")
def api_dashboard() -> dict[str, Any]:
    with db_conn() as conn:
        totals = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(metric_value),0) m FROM products").fetchone()
        by_cat = conn.execute("SELECT category, COUNT(*) c, COALESCE(SUM(metric_value),0) m FROM products GROUP BY category ORDER BY m DESC").fetchall()
        best = conn.execute("SELECT * FROM products ORDER BY metric_value DESC LIMIT 10").fetchall()
        sync = conn.execute("SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT 1").fetchone()
    return {
        "totalProducts": totals["c"],
        "totalMetric": totals["m"],
        "categories": [dict(r) for r in by_cat],
        "bestSellers": [dict(r) for r in best],
        "lastSync": dict(sync) if sync else None,
    }


@app.get("/")
def root() -> FileResponse:
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/{path:path}")
def static_files(path: str) -> FileResponse:
    target = ROOT / "frontend" / path
    if target.exists() and target.is_file():
        return FileResponse(target)
    raise HTTPException(status_code=404)
