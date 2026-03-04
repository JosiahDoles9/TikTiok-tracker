from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.core import now_iso


class TikTokSyncService:
    def __init__(self, conn_factory, auth_service, api_client):
        self.conn_factory = conn_factory
        self.auth_service = auth_service
        self.api_client = api_client

    def _new_run(self, account_id: str, cursor_start: str = "0") -> str:
        run_id = uuid.uuid4().hex
        conn = self.conn_factory()
        try:
            conn.execute(
                "INSERT INTO sync_runs (id, source, tiktok_account_id, started_at, status, cursor_start, fetched_videos, errors_json) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, "TikTok", account_id, now_iso(), "running", cursor_start, 0, "[]"),
            )
            conn.commit()
        finally:
            conn.close()
        return run_id

    def _finish_run(self, run_id: str, status: str, cursor_end: str, fetched: int, errors: list[dict[str, Any]]) -> None:
        conn = self.conn_factory()
        try:
            conn.execute(
                "UPDATE sync_runs SET ended_at=?, status=?, cursor_end=?, fetched_videos=?, errors_json=? WHERE id=?",
                (now_iso(), status, cursor_end, fetched, json.dumps(errors), run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def sync_account(self, account_id: str) -> dict[str, Any]:
        run_id = self._new_run(account_id)
        errors: list[dict[str, Any]] = []
        cursor = 0
        last_cursor = None
        fetched = 0
        status = "success"

        try:
            token = self.auth_service.get_valid_access_token(account_id)
        except Exception as exc:  # noqa: BLE001
            self._finish_run(run_id, "failed", str(cursor), fetched, [{"stage": "token", "error": str(exc), "action": "reconnect_required"}])
            return {"syncRunId": run_id, "status": "failed"}

        fields = [
            "id",
            "title",
            "video_description",
            "create_time",
            "duration",
            "embed_link",
            "cover_image_url",
            "share_url",
            "like_count",
            "comment_count",
            "share_count",
            "view_count",
        ]

        while True:
            if last_cursor is not None and cursor == last_cursor:
                errors.append({"stage": "pagination", "error": "cursor repeated"})
                status = "partial"
                break
            last_cursor = cursor

            page_ok = False
            for attempt in range(3):
                try:
                    payload = self.api_client.video_list(token, fields=fields, max_count=20, cursor=cursor)
                    page_ok = True
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 2:
                        errors.append({"stage": "video_list", "cursor": cursor, "error": str(exc)})
            if not page_ok:
                status = "failed" if fetched == 0 else "partial"
                break

            data = payload.get("data", {})
            videos = data.get("videos", [])
            has_more = bool(data.get("has_more"))
            next_cursor = int(data.get("cursor", cursor))
            self._upsert_videos(account_id, videos)
            fetched += len(videos)

            video_ids = [v.get("id") for v in videos if v.get("id")]
            if video_ids:
                self._refresh_video_details(token, video_ids)

            cursor = next_cursor
            if not has_more:
                break

        if errors and status == "success":
            status = "partial"
        final_status = "partial" if status == "partial" else status
        self._finish_run(run_id, final_status, str(cursor), fetched, errors)
        return {"syncRunId": run_id, "status": final_status, "fetchedVideos": fetched, "errors": errors}

    def _upsert_videos(self, account_id: str, videos: list[dict[str, Any]]) -> None:
        conn = self.conn_factory()
        conn.row_factory = sqlite3.Row
        now = now_iso()
        try:
            for video in videos:
                video_id = video.get("id")
                if not video_id:
                    continue
                local_video_id = f"{account_id}:{video_id}"
                conn.execute(
                    """INSERT INTO tiktok_videos (id,tiktok_account_id,video_id,title,description,create_time,duration_seconds,embed_link,cover_image_url,share_url,raw_json,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(video_id) DO UPDATE SET title=excluded.title,description=excluded.description,create_time=excluded.create_time,
                    duration_seconds=excluded.duration_seconds,embed_link=excluded.embed_link,cover_image_url=excluded.cover_image_url,share_url=excluded.share_url,
                    raw_json=excluded.raw_json,updated_at=excluded.updated_at""",
                    (
                        local_video_id,
                        account_id,
                        video_id,
                        video.get("title"),
                        video.get("video_description"),
                        datetime.fromtimestamp(int(video.get("create_time", 0)), timezone.utc).isoformat() if video.get("create_time") else None,
                        video.get("duration"),
                        video.get("embed_link"),
                        video.get("cover_image_url"),
                        video.get("share_url"),
                        json.dumps(video),
                        now,
                        now,
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO tiktok_video_metrics (id,tiktok_video_id,like_count,comment_count,share_count,view_count,collected_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        local_video_id,
                        int(video.get("like_count", 0) or 0),
                        int(video.get("comment_count", 0) or 0),
                        int(video.get("share_count", 0) or 0),
                        int(video.get("view_count", 0) or 0),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _refresh_video_details(self, access_token: str, video_ids: list[str]) -> None:
        fields = ["id", "like_count", "comment_count", "share_count", "view_count"]
        for i in range(0, len(video_ids), 20):
            batch = video_ids[i : i + 20]
            for attempt in range(3):
                try:
                    self.api_client.video_query(access_token, fields=fields, video_ids=batch)
                    break
                except Exception:
                    if attempt == 2:
                        return

    def get_sync_runs(self, account_id: str | None = None) -> list[dict[str, Any]]:
        conn = self.conn_factory()
        conn.row_factory = sqlite3.Row
        try:
            if account_id:
                rows = conn.execute("SELECT * FROM sync_runs WHERE source='TikTok' AND tiktok_account_id=? ORDER BY started_at DESC LIMIT 50", (account_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM sync_runs WHERE source='TikTok' ORDER BY started_at DESC LIMIT 50").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_videos(self, account_id: str | None = None, title: str | None = None, since: str | None = None) -> list[dict[str, Any]]:
        conn = self.conn_factory()
        conn.row_factory = sqlite3.Row
        try:
            clauses = ["1=1"]
            params: list[Any] = []
            if account_id:
                clauses.append("v.tiktok_account_id=?")
                params.append(account_id)
            if title:
                clauses.append("COALESCE(v.title,'') LIKE ?")
                params.append(f"%{title}%")
            if since:
                clauses.append("COALESCE(v.create_time,'') >= ?")
                params.append(since)
            query = f"""
            SELECT v.*, m.like_count, m.comment_count, m.share_count, m.view_count, m.collected_at
            FROM tiktok_videos v
            LEFT JOIN tiktok_video_metrics m ON m.tiktok_video_id=v.id
            WHERE {' AND '.join(clauses)}
            GROUP BY v.id
            ORDER BY COALESCE(m.view_count,0) DESC, COALESCE(v.create_time,'') DESC
            LIMIT 300
            """
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def best_performing(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self.conn_factory()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT v.video_id, v.title, v.embed_link, v.share_url, a.display_name,
                       COALESCE(m.view_count,0) view_count, COALESCE(m.like_count,0) like_count,
                       COALESCE(m.comment_count,0) comment_count, COALESCE(m.share_count,0) share_count,
                       (COALESCE(m.view_count,0) + 3*COALESCE(m.like_count,0) + 4*COALESCE(m.comment_count,0) + 5*COALESCE(m.share_count,0)) score
                FROM tiktok_videos v
                JOIN tiktok_accounts a ON a.id=v.tiktok_account_id
                LEFT JOIN tiktok_video_metrics m ON m.tiktok_video_id=v.id
                ORDER BY score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
