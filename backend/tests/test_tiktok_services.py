import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.services.tiktok_auth_service import TikTokAuthService
from backend.services.tiktok_sync_service import TikTokSyncService
from backend.utils.encryption import decrypt_token, encrypt_token


class FakeApi:
    def __init__(self):
        self._cursor_pages = {
            0: {"data": {"videos": [{"id": "v1", "title": "One", "create_time": "1700000000", "duration": 10, "view_count": 100, "like_count": 10, "comment_count": 2, "share_count": 1}], "cursor": 1, "has_more": True}},
            1: {"data": {"videos": [{"id": "v2", "title": "Two", "create_time": "1700001000", "duration": 12, "view_count": 120, "like_count": 12, "comment_count": 3, "share_count": 2}], "cursor": 2, "has_more": False}},
        }

    def build_authorize_url(self, redirect_uri, scopes, state):
        return f"https://www.tiktok.com/v2/auth/authorize/?redirect_uri={redirect_uri}&scope={scopes}&state={state}"

    def exchange_code(self, code, redirect_uri):
        return {"data": {"access_token": "acc", "refresh_token": "ref", "open_id": "open123", "expires_in": 3600, "scope": "user.info.basic,video.list"}}

    def user_info(self, access_token, fields):
        return {"data": {"user": {"open_id": "open123", "display_name": "Creator", "avatar_url": "https://img", "profile_deep_link": "https://tt/profile"}}}

    def refresh_token(self, refresh_token):
        return {"data": {"access_token": "acc2", "refresh_token": "ref2", "expires_in": 3600}}

    def video_list(self, access_token, fields, max_count=20, cursor=0):
        return self._cursor_pages[cursor]

    def video_query(self, access_token, fields, video_ids):
        return {"data": {"videos": [{"id": vid} for vid in video_ids]}}


class TikTokServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "test.db")
        os.environ["TOKEN_ENCRYPTION_KEY"] = "unit-test-key"

        conn = sqlite3.connect(self.db_path)
        for migration in sorted(Path("backend/migrations").glob("*.sql")):
            conn.executescript(migration.read_text())
        conn.commit()
        conn.close()

        def conn_factory():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

        self.conn_factory = conn_factory
        self.api = FakeApi()
        self.auth = TikTokAuthService(conn_factory, self.api, "http://localhost/callback", "user.info.basic,video.list")
        self.sync = TikTokSyncService(conn_factory, self.auth, self.api)

    def tearDown(self):
        self.tmp.cleanup()

    def test_token_encryption_roundtrip(self):
        encrypted = encrypt_token("abc123")
        self.assertNotEqual(encrypted, "abc123")
        self.assertEqual(decrypt_token(encrypted), "abc123")

    def test_oauth_exchange_and_store(self):
        result = self.auth.exchange_callback_code("u1", "code123")
        self.assertIn("accountId", result)
        conn = self.conn_factory()
        row = conn.execute("SELECT * FROM tiktok_tokens").fetchone()
        self.assertIsNotNone(row)
        self.assertNotEqual(row["access_token_encrypted"], "acc")
        conn.close()

    def test_sync_videos_pagination(self):
        account = self.auth.exchange_callback_code("u1", "code123")
        out = self.sync.sync_account(account["accountId"])
        self.assertIn(out["status"], ["success", "partial"])
        conn = self.conn_factory()
        count = conn.execute("SELECT COUNT(*) c FROM tiktok_videos").fetchone()["c"]
        self.assertEqual(count, 2)
        conn.close()


if __name__ == "__main__":
    unittest.main()
