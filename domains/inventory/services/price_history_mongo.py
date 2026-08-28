from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from core.services.mongo import get_collection

logger = logging.getLogger(__name__)

COLLECTION = "price_history"


def log_price_change(
    *,
    variant_id: int,
    sku: str,
    product_name: str,
    old_price: Decimal,
    new_price: Decimal,
    cost_basis: Decimal,
    cost_strategy: str,
    expected_profit_percentage: Decimal,
    source: str,
) -> None:
    try:
        doc = {
            "variant_id": variant_id,
            "sku": sku,
            "product_name": product_name,
            "old_price": float(old_price),
            "new_price": float(new_price),
            "cost_basis": float(cost_basis),
            "cost_strategy": cost_strategy,
            "expected_profit_percentage": float(expected_profit_percentage),
            "source": source,
            "created_at": datetime.now(timezone.utc),
        }
        get_collection(COLLECTION).insert_one(doc)
    except Exception:
        logger.exception("Failed to log price change to MongoDB for variant %s", variant_id)


def get_price_history(variant_id: int, limit: int = 50) -> list[dict]:
    try:
        cursor = (
            get_collection(COLLECTION)
            .find({"variant_id": variant_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        results = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            if isinstance(doc.get("created_at"), datetime):
                doc["created_at"] = doc["created_at"].isoformat()
            results.append(doc)
        return results
    except Exception:
        logger.exception("Failed to read price history from MongoDB for variant %s", variant_id)
        return []
