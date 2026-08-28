from __future__ import annotations

import logging
from functools import lru_cache

from django.conf import settings
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

logger = logging.getLogger(__name__)

_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        kwargs: dict = {
            "host": settings.MONGO_HOST,
            "port": settings.MONGO_PORT,
            "serverSelectionTimeoutMS": 3000,
        }
        if settings.MONGO_USER and settings.MONGO_PASSWORD:
            kwargs["username"] = settings.MONGO_USER
            kwargs["password"] = settings.MONGO_PASSWORD
        _client = MongoClient(**kwargs)
    return _client


def get_mongo_db() -> Database:
    return get_mongo_client()[settings.MONGO_DB_NAME]


def get_collection(name: str) -> Collection:
    return get_mongo_db()[name]


def ping_mongo() -> bool:
    try:
        get_mongo_client().admin.command("ping")
        return True
    except Exception:
        logger.warning("MongoDB ping failed", exc_info=True)
        return False
