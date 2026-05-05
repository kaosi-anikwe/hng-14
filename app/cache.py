import orjson
import redis
from app.config import settings

# db=1 keeps cache separate from the JWT blocklist (db=0).
# decode_responses=False: Redis returns raw bytes — orjson consumes bytes
# directly, skipping a redundant encode/decode round-trip.
cache_redis = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    username=settings.REDIS_USERNAME,
    password=settings.REDIS_PASSWORD,
    db=0,
    decode_responses=False,
)

SEARCH_CACHE_TTL = 300  # seconds (5 minutes)
COUNT_CACHE_TTL = 600  # seconds (10 minutes) — counts change less often than page data


def cache_dumps(obj) -> bytes:
    """Serialize to bytes with orjson (2-10x faster than stdlib json)."""
    return orjson.dumps(obj)


def cache_loads(data: bytes) -> object:
    """Deserialize from bytes with orjson."""
    return orjson.loads(data)


def cache_get(key: str) -> bytes | None:
    """Typed wrapper around cache_redis.get() that always returns bytes or None."""
    result = cache_redis.get(key)
    return result  # type: ignore[return-value]


def cache_invalidate_profiles() -> None:
    """Delete all profiles: and search: cache entries.

    Uses SCAN in batches and pipelines the DELETEs so it never blocks Redis
    the way KEYS would on a large keyspace.
    """
    pipe = cache_redis.pipeline(transaction=False)
    found = False
    for prefix in ("profiles:*", "search:*"):
        cursor = 0
        while True:
            cursor, keys = cache_redis.scan(cursor, match=prefix, count=200)  # type: ignore[misc]
            if keys:
                pipe.delete(*keys)
                found = True
            if cursor == 0:
                break
    if found:
        pipe.execute()
