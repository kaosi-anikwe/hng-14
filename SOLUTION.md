# Stage 4B: System Optimization & Data Ingestion

## Query Performance

### What was optimized

#### 1. Database Indexes

Six indexes were added to the `profiles` table in `app/models.py`:

| Index                            | Columns                       | Query type covered                    |
| -------------------------------- | ----------------------------- | ------------------------------------- |
| `ix_profile_gender_age`          | `gender, age`                 | Gender filter + age range/sort        |
| `ix_profile_gender_country_name` | `gender, lower(country_name)` | Combined gender + country NLP queries |
| `ix_profile_country_name_lower`  | `lower(country_name)`         | Country-only NLP queries              |
| `ix_profile_country_id`          | `country_id`                  | Exact-match filter in `GET /profiles` |
| `ix_profile_age_group`           | `age_group`                   | Exact-match filter in `GET /profiles` |
| `ix_profile_created_at`          | `created_at`                  | Sort-by-date queries                  |

**Why:** Without indexes, every filtered query on 1M+ rows requires a full sequential scan. A B-tree index reduces that to a sub-millisecond lookup. The functional indexes on `lower(country_name)` are required because search queries normalize country names to lowercase before comparing.

---

#### 2. Eliminate ORM Hydration on List Endpoints

`GET /profiles` and `GET /profiles/search` previously used `select(Profile)`, which causes SQLAlchemy to construct a full Python `Profile` object per row calling `__init__`, registering the instance in the session's identity map, resolving all mapped columns — for every row in every page, including columns not used in the response.

Changed to `select(*_PROFILE_COLS)` (the ten columns that are actually serialized), executed via `.mappings().all()`. This returns lightweight `RowMapping` dict-like objects. This skips the ORM overhead.

**Why:** For a page of 50 rows, this removes 50 object instantiation cycles that are immediately discarded after serialization.

---

#### 3. Eliminated Double COUNT

`db.paginate()` always issues two SQL queries per request by default: `SELECT … LIMIT n` and `SELECT COUNT(*)`. The COUNT on 1M takes time even with indexes, because PostgreSQL must visit all matching leaf pages.

Changed to:

- Execute `SELECT count(id) WHERE <filters>` **once** and cache the result separately (10-minute TTL, keyed on filters only, not page/sort).
- Execute `SELECT <cols> WHERE <filters> ORDER BY … LIMIT n OFFSET m` directly via `db.session.execute(...).mappings().all()` (no second COUNT).

**Why:** The total count depends only on the active filters, not on the current page number or sort order. Caching it independently means pages 2, 3, 4… of the same query never re-execute the COUNT — they read it from Redis in < 1ms.

---

#### 4. Full-Page Response Caching (Redis)

`GET /profiles` and `GET /profiles/search` cache the complete serialized JSON response in Redis with a 5-minute TTL. The cache key is a SHA-256 hash of the canonical filter + pagination parameters.

On a cache hit, the raw bytes stored in Redis are returned directly as the HTTP response body skipping deserialization, re-serialization and database querying.

**Why:** The read-to-write ratio is high. Repeated queries from multiple users for the same filtered page — the dominant workload — are answered from Redis (< 1ms network round-trip) instead of from PostgreSQL.

---

#### 5. orjson for Serialization

Replaced stdlib `json` with `orjson` for all cache operations. `orjson` produces `bytes` natively (no `.encode()` needed), handles `datetime` without a `default=` argument, and is 2–10x faster than `json` for typical Python dicts.

The Redis client uses `decode_responses=False` so cached values are returned as raw `bytes` and passed directly to `Response(response=bytes)` without decoding.

**Why:** On a cache miss, the result is serialized once (`cache_dumps(result)`), stored in Redis, and returned as the HTTP body — one serialization call for both. Previously `json.dumps()` was called to store, and `jsonify()` called a second time to respond.

---

#### 6. Response Compression

`flask-compress` is registered via `Compress(app)` in `create_app()`. It automatically gzips any `application/json` response larger than 500 bytes and sets `Content-Encoding: gzip` and `Vary: Accept-Encoding` correctly.

**Why:** A page of 50 profiles is maybe around 8–15 KB of JSON. gzip reduces that to 2–4 KB (70–80% compression), cutting transfer time proportionally on any non-loopback network. No application code changes are required.

---

#### 7. Connection Pooling

SQLAlchemy engine options set in `create_app()`:

```python
"pool_pre_ping": True,   # SELECT 1 before checkout — kills stale connections
"pool_recycle": 1800,    # Recycle after 30 min — avoids PostgreSQL idle timeout
```

**Why:** Without pooling, each request opens a new TCP + TLS + PostgreSQL auth handshake. With `pool_size=10`, up to 10 connections are kept open and reused. `pool_pre_ping` prevents `OperationalError` on stale connections after network blips or DB restarts.

---

### Before / After Comparison

> **Note:** Run your test suite against the live database and fill in the measured values below. The structure and baseline estimates are provided; replace them with your actual measurements.

| Query                                                                                    | Before (ms) |
| ---------------------------------------------------------------------------------------- | ----------- |
| `GET /profiles` (no filters, page 1, cold)                                               | 1117        |
| `GET /profiles` (no filters, page 1, warm cache)                                         | 631         |
| `GET /profiles?gender=female` (cold)                                                     | 775         |
| `GET /profiles?gender=female` (warm cache)                                               | 612         |
| `GET /profiles/search?q=Nigerian females aged 20-45` (cold)                              | 987         |
| `GET /profiles/search?q=Women from Nigeria between 20 and 45` (same filters, warm cache) | 616         |
| `POST /upload` (50,000 rows)                                                             | 60000       |

---

## Query Normalization

### Problem

Users express the same intent in different ways:

- `"Nigerian females between ages 20 and 45"`
- `"Women aged 20–45 living in Nigeria"`
- `"females from nigeria between 20 and 45"`

Without normalization, each produces a different cache key, causes a separate database query, and returns three identical result sets — wasting compute and cache space.

### Solution

Before touching the cache or the database, the NLP parser in `search_profile()` extracts all recognized filters into a **canonical dict**:

```python
canon = {
    "gender": None,           # "male" | "female" | "any" | None
    "country_name": None,     # lowercase, always the stored form ("nigeria")
    "age_gte": None,          # inclusive lower bound
    "age_lte": None,          # inclusive upper bound
    "age_gt": None,           # exclusive lower bound
    "age_lt": None,           # exclusive upper bound
    "age_groups": [],         # sorted list of age group strings
}
```

All three example queries above produce the same `canon`:

```python
{
    "gender": "female",
    "country_name": "nigeria",
    "age_gte": 20,
    "age_lte": 45,
    "age_gt": None,
    "age_lt": None,
    "age_groups": [],
}
```

The cache key is `sha256(orjson.dumps(canon))`. Because the canonical form is deterministic and `orjson.dumps` is deterministic (consistent key ordering for dicts), the same filters always produce the same key regardless of how the query was phrased.

### How each signal is extracted

**Gender** — regex over a closed word list:

- Male: `males?|m[ae]n|guys?|boys?`
- Female: `females?|wom[ae]n|girls?`
- If both match, gender is set to `"any"` (no restriction applied).

**Country** — three sources, in priority order:

1. **Demonym adjective**: a pre-built dict of ~100 entries (`"nigerian" → "nigeria"`, `"british" → "united kingdom"`, …). Matched with a single precompiled regex sorted longest-first to prevent partial matches.
2. **`from <name>`**: regex capturing the country name after the word "from".
3. **`living in <name>` / `in <name>`**: fallback pattern.

All three resolve to the same lowercase stored form. "Nigerian" and "from Nigeria" and "living in Nigeria" all produce `canon["country_name"] = "nigeria"`.

**Age range** — three patterns:

- Between: `between ages? X and/to Y` or `aged X-Y` (bounds sorted so `"45 to 20"` equals `"20 to 45"`)
- Above: `above X` → `age_gt = X`
- Below: `below X` → `age_lt = X`

**Age groups** — word list (`children`, `teenagers`, `adults`, `seniors`, `young`). Results collected into a set (order-independent), then sorted before storing in `canon["age_groups"]`, so `"adults and seniors"` equals `"seniors and adults"`.

### Trade-offs

- **No AI/LLM**: all extraction is regex-based with a static demonym dictionary. It is fast (microseconds), deterministic, and requires no external service.
- **Scope is intentionally narrow**: only patterns we can reliably extract without ambiguity. Queries that don't match any known pattern return a 400 with `"Unable to interpret query"` rather than guessing.
- **Count cache uses `canon` only** (not page/sort), so `page=2` of a query reuses the cached total from `page=1`.

---

## CSV Data Ingestion

### Design

`POST /api/upload` accepts a CSV file and processes it in streaming batches of 50,000 rows using **Polars** (`pl.scan_csv(request.stream)` + `lf.collect_batches(chunk_size=50_000)`).

- The file is never fully loaded into memory. Polars reads from the WSGI request stream and processes it in chunks.
- Each batch is validated independently. A failure in one batch (caught by a `try/except`) rolls back only that batch and continues with the next. Rows already committed remain committed.
- Batch insert uses `db.session.execute(insert(Profile), list(records))` — a single parameterized SQL statement per batch, not one INSERT per row.

### Validation per batch

Each batch goes through five filters in sequence:

| Check                                                 | Action                                      |
| ----------------------------------------------------- | ------------------------------------------- |
| Any required field is null                            | Row counted as `missing_fields`, skipped    |
| Name appears more than once within the same CSV batch | Row counted as `duplicate_name`, skipped    |
| Name already exists in the database                   | Row counted as `duplicate_name`, skipped    |
| Age is not between 0 and 120 (inclusive)              | Row counted as `invalid_age`, skipped       |
| `country_id` is not a valid ISO 3166-1 alpha-2 code   | Row counted as `invalid_countries`, skipped |

Only rows that pass all five checks are inserted.

### Cross-batch duplicate detection

At the start of the upload, all existing names are loaded into an in-memory `set`. After each successful batch insert, the newly inserted names are added to the set. This means:

- DB duplicates are detected without an additional `SELECT … WHERE name IN (…)` per batch.
- Rows that appear in batch 3 but were inserted in batch 1 are correctly detected as duplicates.

**Trade-off:** For very large tables (millions of rows), loading all names into memory at upload start is expensive. The alternative — a per-row or per-batch DB lookup — is far slower. At 1M rows × ~20 bytes per name, the set uses ~20 MB of RAM, which is acceptable.

### Failure handling

- **Row-level failure**: handled by Polars filtering — bad rows are excluded from the batch before any DB operation.
- **Batch-level failure**: if the DB insert itself fails (e.g. a constraint violation that slipped through), the batch is rolled back with `db.session.rollback()`, all rows in that batch are counted as skipped, and processing continues with the next batch.
- **No upload-level rollback**: rows already committed in previous batches are never rolled back. The upload does not behave as a single atomic transaction.

### Concurrency

- Multiple concurrent uploads are supported. Each request operates on its own SQLAlchemy session and commits independently.
- Since duplicate detection uses an in-memory set loaded at request start, two concurrent uploads could theoretically both pass the duplicate check for the same name and attempt to insert it. The `UNIQUE` constraint on `profiles.name` prevents a duplicate from actually being committed — the second insert will raise a constraint error, which is caught by the batch-level `try/except` and results in that batch being rolled back and skipped.
- This is an acceptable trade-off: the failure mode is a lost batch (not a corrupt insert), and the constraint provides a hard correctness guarantee.

### Cache invalidation

After all batches complete, if any rows were inserted, `cache_invalidate_profiles()` is called. This uses Redis `SCAN` in batches of 200 (non-blocking) followed by a pipelined `DEL` on all `profiles:*` and `search:*` keys. This ensures cached pages are not served stale after a bulk upload.

### Response

```json
{
  "status": "success",
  "total_rows": 50000,
  "inserted": 48231,
  "skipped": 1769,
  "reasons": {
    "duplicate_name": 1203,
    "invalid_age": 312,
    "missing_fields": 254,
    "invalid_countries": 0
  }
}
```
