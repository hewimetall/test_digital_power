"""redis.py"""
from typing import Tuple

import redis

from enum import IntEnum

class RedisEvent(IntEnum):
    """Redis client events."""

    CONNECT_BEGIN = 1
    CONNECT_SUCCESS = 2
    CONNECT_FAIL = 3
    KEY_ADDED_TO_CACHE = 4
    KEY_FOUND_IN_CACHE = 5
    FAILED_TO_CACHE_KEY = 6

class RedisStatus(IntEnum):
    """Connection status for the redis client."""

    NONE = 0
    CONNECTED = 1
    AUTH_ERROR = 2
    CONN_ERROR = 3


def redis_connect(host_url: str) -> Tuple[RedisStatus, redis.client.Redis]:
    """Attempt to connect to `host_url` and return a Redis client instance if successful."""
    return _connect(host_url)


def _connect(host, port=6379, db=0) -> Tuple[RedisStatus, redis.client.Redis]:  # pragma: no cover
    try:
        redis_client = redis.Redis(host=host, port=port, db=db)
        if redis_client.ping():
            return (RedisStatus.CONNECTED, redis_client)
        return (RedisStatus.CONN_ERROR, None)
    except redis.AuthenticationError:
        return (RedisStatus.AUTH_ERROR, None)
    except redis.ConnectionError:
        return (RedisStatus.CONN_ERROR, None)
