from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.core import now_iso
from backend.utils.encryption import decrypt_token, encrypt_token


def _iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class TikTokAuthService:
    def __init__(self, conn_factory, api_client, redirect_uri: str, scopes: str):
        self.conn_factory = conn_factory
        self.api_client = api_client
        self.redirect_uri = redirect_uri
        self.scopes = scopes

    def authorization_url(self, state: str | None = None) -> dict[str, str]:
        st = state or uuid.uuid4().hex
        return {"authorizationUrl": self.api_client.build_authorize_url(self.redirect_uri, self.scopes, st), "state": st}

    def exchange_callback_code(self, app_user_id: str, code: str) -> dict[str, Any]:
        token_response = self.api_client.exchange_code(code, self.redirect_uri)
        data = token_response.get("data", token_response)
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        open_id = data.get("open_id")
        if not access_token or not refresh_token or not open_id:
            raise ValueError("Invalid token response from TikTok")

        profile_resp = self.api_client.user_info(access_token, ["open_id", "union_id", "display_name", "avatar_url", "profile_deep_link"])
        profile_data = profile_resp.get("data", {}).get("user", profile_resp.get("data", {}))

        now = now_iso()
        account_id = uuid.uuid4().hex
        token_id = uuid.uuid4().hex

        conn: sqlite3.Connection = self.conn_factory()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT id FROM tiktok_accounts WHERE open_id=?", (open_id,)).fetchone()
            if row:
                account_id = row["id"]
                conn.execute(
                    "UPDATE tiktok_accounts SET app_user_id=?, union_id=?, display_name=?, avatar_url=?, profile_url=?, updated_at=? WHERE id=?",
                    (
                        app_user_id,
                        profile_data.get("union_id"),
                        profile_data.get("display_name"),
                        profile_data.get("avatar_url"),
                        profile_data.get("profile_deep_link"),
                        now,
                        account_id,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO tiktok_accounts (id, app_user_id, open_id, union_id, display_name, avatar_url, profile_url, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        account_id,
                        app_user_id,
                        open_id,
                        profile_data.get("union_id"),
                        profile_data.get("display_name"),
                        profile_data.get("avatar_url"),
                        profile_data.get("profile_deep_link"),
                        now,
                        now,
                    ),
                )

            expires_in = int(data.get("expires_in", 86400))
            refresh_expires_in = data.get("refresh_expires_in")
            conn.execute(
                """INSERT INTO tiktok_tokens (id, tiktok_account_id, access_token_encrypted, refresh_token_encrypted, scopes, expires_at, refresh_expires_at, last_refreshed_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(tiktok_account_id) DO UPDATE SET access_token_encrypted=excluded.access_token_encrypted, refresh_token_encrypted=excluded.refresh_token_encrypted,
                   scopes=excluded.scopes, expires_at=excluded.expires_at, refresh_expires_at=excluded.refresh_expires_at, last_refreshed_at=excluded.last_refreshed_at, updated_at=excluded.updated_at""",
                (
                    token_id,
                    account_id,
                    encrypt_token(access_token),
                    encrypt_token(refresh_token),
                    data.get("scope", self.scopes),
                    _iso_after(expires_in),
                    _iso_after(int(refresh_expires_in)) if refresh_expires_in else None,
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {"accountId": account_id, "openId": open_id, "displayName": profile_data.get("display_name")}

    def get_valid_access_token(self, account_id: str) -> str:
        conn = self.conn_factory()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM tiktok_tokens WHERE tiktok_account_id=?", (account_id,)).fetchone()
            if not row:
                raise ValueError("No token for account")
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires_at - timedelta(minutes=5):
                refresh_plain = decrypt_token(row["refresh_token_encrypted"])
                refresh = self.api_client.refresh_token(refresh_plain)
                data = refresh.get("data", refresh)
                now = now_iso()
                conn.execute(
                    "UPDATE tiktok_tokens SET access_token_encrypted=?, refresh_token_encrypted=?, expires_at=?, refresh_expires_at=?, last_refreshed_at=?, updated_at=? WHERE tiktok_account_id=?",
                    (
                        encrypt_token(data.get("access_token", "")),
                        encrypt_token(data.get("refresh_token", refresh_plain)),
                        _iso_after(int(data.get("expires_in", 86400))),
                        _iso_after(int(data.get("refresh_expires_in"))) if data.get("refresh_expires_in") else row["refresh_expires_at"],
                        now,
                        now,
                        account_id,
                    ),
                )
                conn.commit()
                return data.get("access_token", "")
            return decrypt_token(row["access_token_encrypted"])
        finally:
            conn.close()

    def list_accounts(self) -> list[dict[str, Any]]:
        conn = self.conn_factory()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM tiktok_accounts ORDER BY updated_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
