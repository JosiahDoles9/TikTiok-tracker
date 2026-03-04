from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any


class TikTokApiError(Exception):
    pass


class TikTokApiClient:
    def __init__(self, base_url: str, client_key: str, client_secret: str):
        self.base_url = base_url.rstrip("/")
        self.client_key = client_key
        self.client_secret = client_secret

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = None
        req_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        retries = 4
        for attempt in range(retries):
            req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    txt = res.read().decode("utf-8")
                    return json.loads(txt) if txt else {}
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                retryable = any(code in message for code in ["429", "500", "502", "503", "504"])
                if attempt < retries - 1 and retryable:
                    time.sleep(2**attempt)
                    continue
                raise TikTokApiError(f"TikTok API request failed: {path}") from exc
        raise TikTokApiError(f"TikTok API request failed after retries: {path}")

    def build_authorize_url(self, redirect_uri: str, scopes: str, state: str) -> str:
        query = urllib.parse.urlencode(
            {
                "client_key": self.client_key,
                "response_type": "code",
                "scope": scopes,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return f"https://www.tiktok.com/v2/auth/authorize/?{query}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        payload = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        return self._request("POST", "/v2/oauth/token/", payload=payload)

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        payload = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        return self._request("POST", "/v2/oauth/token/", payload=payload)

    def user_info(self, access_token: str, fields: list[str]) -> dict[str, Any]:
        q = urllib.parse.urlencode({"fields": ",".join(fields)})
        return self._request("GET", f"/v2/user/info/?{q}", headers={"Authorization": f"Bearer {access_token}"})

    def video_list(self, access_token: str, fields: list[str], max_count: int = 20, cursor: int = 0) -> dict[str, Any]:
        payload = {"max_count": max_count, "cursor": cursor}
        q = urllib.parse.urlencode({"fields": ",".join(fields)})
        return self._request("POST", f"/v2/video/list/?{q}", payload=payload, headers={"Authorization": f"Bearer {access_token}"})

    def video_query(self, access_token: str, fields: list[str], video_ids: list[str]) -> dict[str, Any]:
        payload = {"filters": {"video_ids": video_ids}, "max_count": min(20, len(video_ids))}
        q = urllib.parse.urlencode({"fields": ",".join(fields)})
        return self._request("POST", f"/v2/video/query/?{q}", payload=payload, headers={"Authorization": f"Bearer {access_token}"})
