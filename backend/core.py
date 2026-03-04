from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

CATEGORIES = [
    "Beauty",
    "Fashion",
    "Home & Living",
    "Food & Beverage",
    "Health",
    "Electronics",
    "Pets",
    "Baby",
    "Sports",
    "Accessories",
]

VALID_SYNC_STATES = {"idle", "running", "partial_success", "success", "failed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", value.lower())).strip()


def stable_product_id(product_url: str, name: str, category: str) -> str:
    base = product_url.strip() or f"{normalize_name(name)}|{category.lower()}"
    return hashlib.sha256(base.encode()).hexdigest()[:20]


def dedupe_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids = set()
    seen_names_by_cat: dict[str, set[str]] = {}
    output = []
    for product in products:
        category = product["category"]
        norm = normalize_name(product["name"])
        seen_names_by_cat.setdefault(category, set())
        if product["id"] in seen_ids:
            continue
        if norm in seen_names_by_cat[category]:
            continue
        seen_ids.add(product["id"])
        seen_names_by_cat[category].add(norm)
        output.append(product)
    return output


def is_stale(started_at: str, stale_after_minutes: int) -> bool:
    started = datetime.fromisoformat(started_at)
    return datetime.now(timezone.utc) - started > timedelta(minutes=stale_after_minutes)


def transition_sync_status(current: str, new: str) -> str:
    if current not in VALID_SYNC_STATES or new not in VALID_SYNC_STATES:
        raise ValueError("invalid state")
    valid = {
        "idle": {"running"},
        "running": {"success", "failed", "partial_success"},
        "partial_success": {"running"},
        "success": {"running"},
        "failed": {"running"},
    }
    if new not in valid[current]:
        raise ValueError(f"invalid transition {current}->{new}")
    return new


def validate_product_response(product: dict[str, Any]) -> None:
    required = ["id", "name", "category", "product_url"]
    for key in required:
        if not product.get(key):
            raise ValueError(f"missing {key}")


@dataclass
class SyncState:
    id: str
    status: str
    progress_percent: int
    current_category: str | None
    per_category_results: list[dict[str, Any]]
    error_message: str | None = None

    def to_db_tuple(self, started_at: str, stale_after: int) -> tuple[Any, ...]:
        finished = now_iso() if self.status in {"success", "failed", "partial_success"} else None
        return (
            self.id,
            self.status,
            started_at,
            finished,
            self.progress_percent,
            self.current_category,
            self.error_message,
            json.dumps(self.per_category_results),
            stale_after,
        )
