# Name Classifier API

A Flask REST API that classifies a name by gender, age, and nationality by aggregating data from [Genderize.io](https://genderize.io), [Agify.io](https://agify.io), and [Nationalize.io](https://nationalize.io). Profiles are persisted to a database — SQLite locally, or a PostgreSQL database (e.g. [Supabase](https://supabase.com)) in production.

## Endpoints

### `GET /api/classify`

Classifies a name by predicted gender only. Also accessible at `GET /api`.

**Query Parameters**

| Parameter | Type   | Required | Description          |
| --------- | ------ | -------- | -------------------- |
| `name`    | string | Yes      | The name to classify |

**Success Response `200`**

```json
{
  "status": "success",
  "data": {
    "gender": "male",
    "gender_probability": 0.99,
    "sample_size": 1234
  }
}
```

**Error Responses**

| Status | Condition                            | Body                                                        |
| ------ | ------------------------------------ | ----------------------------------------------------------- |
| `400`  | `name` is missing or empty           | `{"status": "error", "message": "name not specified"}`      |
| `400`  | No prediction available for the name | `{"status": "error", "message": "..."}`                     |
| `500`  | Unexpected server error              | `{"status": "error", "message": "failed to classify name"}` |

---

### `GET /api/profiles`

Returns a paginated, filterable, sortable list of profiles.

**Query Parameters**

| Parameter                 | Type   | Required | Description                                            |
| ------------------------- | ------ | -------- | ------------------------------------------------------ |
| `gender`                  | string | No       | `male` or `female`                                     |
| `age_group`               | string | No       | `child`, `teenager`, `adult`, or `senior`              |
| `country_id`              | string | No       | ISO 3166-1 alpha-2 code (e.g. `NG`)                    |
| `min_age`                 | int    | No       | Minimum age (inclusive)                                |
| `max_age`                 | int    | No       | Maximum age (inclusive)                                |
| `min_gender_probability`  | float  | No       | Minimum gender prediction confidence (0–1)             |
| `min_country_probability` | float  | No       | Minimum country prediction confidence (0–1)            |
| `sort_by`                 | string | No       | `age` (default), `created_at`, or `gender_probability` |
| `order`                   | string | No       | `asc` (default) or `desc`                              |
| `page`                    | int    | No       | Page number (default: `1`)                             |
| `per_page`                | int    | No       | Results per page, max 50 (default: `10`)               |

**Age groups:** `child` (≤12), `teenager` (13–20), `adult` (21–59), `senior` (60+)

**Success Response `200`**

```json
{
  "status": "success",
  "page": 1,
  "per_page": 10,
  "total": 42,
  "data": [
    {
      "id": "abc123",
      "name": "james",
      "gender": "male",
      "gender_probability": 0.99,
      "age": 35,
      "age_group": "adult",
      "country_id": "US",
      "country_name": "United States",
      "country_probability": 0.85,
      "created_at": "2026-04-17T10:00:00+00:00"
    }
  ]
}
```

---

### `POST /api/profiles`

Creates a new profile for a name, fetching gender, age, and nationality predictions. Returns the existing profile if one already exists for that name.

**Request Body** (`application/json`)

```json
{ "name": "james" }
```

**Success Response `200`**

```json
{
  "status": "success",
  "data": {
    "id": "abc123",
    "name": "james",
    "gender": "male",
    "gender_probability": 0.99,
    "age": 35,
    "age_group": "adult",
    "country_id": "US",
    "country_name": "United States",
    "country_probability": 0.85,
    "created_at": "2026-04-17T10:00:00+00:00"
  }
}
```

**Error Responses**

| Status | Condition               | Body                                                         |
| ------ | ----------------------- | ------------------------------------------------------------ |
| `400`  | `name` missing or empty | `{"status": "error", "message": "name not specified"}`       |
| `500`  | Prediction API failure  | `{"status": "error", "message": "Failed to create profile"}` |
| `502`  | Unexpected error        | `{"status": "error", "message": "..."}`                      |

---

### `GET /api/profiles/search`

Natural language search over profiles. Parses plain English queries into filters using rule-based logic. No AI or LLMs involved.

**Query Parameters**

| Parameter  | Type   | Required | Description                                            |
| ---------- | ------ | -------- | ------------------------------------------------------ |
| `q`        | string | Yes      | Plain English query (see examples below)               |
| `sort_by`  | string | No       | `age` (default), `created_at`, or `gender_probability` |
| `order`    | string | No       | `asc` (default) or `desc`                              |
| `page`     | int    | No       | Page number (default: `1`)                             |
| `per_page` | int    | No       | Results per page, max 50 (default: `10`)               |

**Example queries**

| Query                                | Interpreted as                                    |
| ------------------------------------ | ------------------------------------------------- |
| `young males`                        | `gender=male` + `age` 16–24                       |
| `females above 30`                   | `gender=female` + `age >= 30`                     |
| `people from nigeria`                | `country_name=nigeria`                            |
| `adult males from kenya`             | `gender=male` + `age_group=adult` + country=kenya |
| `male and female teenagers above 17` | `age_group=teenager` + `age >= 17`                |

**Success Response `200`**

```json
{
  "status": "success",
  "page": 1,
  "per_page": 10,
  "total": 5,
  "data": [ ...profile objects... ]
}
```

**Error Responses**

| Status | Condition                 | Body                                                          |
| ------ | ------------------------- | ------------------------------------------------------------- |
| `400`  | `q` missing or empty      | `{"status": "error", "message": "Search query is required"}`  |
| `400`  | Query could not be parsed | `{"status": "error", "message": "Unable to interpret query"}` |

---

### `GET /api/profiles/<id>`

Returns a single profile by its ID.

**Success Response `200`**

```json
{
  "status": "success",
  "data": { ...full profile object... }
}
```

**Error Response**

| Status | Condition         | Body                                                  |
| ------ | ----------------- | ----------------------------------------------------- |
| `404`  | Profile not found | `{"status": "error", "message": "profile not found"}` |

---

### `DELETE /api/profiles/<id>`

Deletes a profile by its ID.

**Success Response:** `204 No Content`

**Error Response**

| Status | Condition         | Body                                                  |
| ------ | ----------------- | ----------------------------------------------------- |
| `404`  | Profile not found | `{"status": "error", "message": "profile not found"}` |

---

## Database

The app selects its database based on environment variables at startup:

- **Locally** — if `DATABASE_URL` is not set, it uses SQLite (`profile.db` in the project root).
- **Production** — if `DATABASE_URL` is set, it connects to a PostgreSQL database.

Add to a `.env` file for production use locally:

```
DATABASE_URL=postgresql://user:password@host:port/dbname
```

For [Supabase](https://supabase.com), use the **Transaction Pooler** connection string (port `6543`) found under **Project Settings → Database**.

File-based logging is disabled by default (Vercel's filesystem is read-only). To enable it locally, set `LOG_FILE` in your `.env`:

```
LOG_FILE=app.log
```

When `LOG_FILE` is not set, logs go to stdout only (stream handler).

## Running Locally

**Prerequisites:** Python 3.13+

```bash
# Clone the repository
git clone <your-repo-url>
cd hng-14

# Create and activate a virtual environment
python -m venv env
# Windows
env\Scripts\activate
# macOS/Linux
source env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

The API will be available at `http://localhost:5000`.

**Example requests:**

```bash
# Classify a name
curl "http://localhost:5000/api/classify?name=james"

# Create a profile
curl -X POST http://localhost:5000/api/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "james"}'

# List profiles — paginated, filtered, sorted
curl "http://localhost:5000/api/profiles?gender=female&age_group=adult&sort_by=age&order=desc&page=1&per_page=10"

# Natural language search
curl "http://localhost:5000/api/profiles/search?q=young+males+from+nigeria"

# Delete a profile
curl -X DELETE http://localhost:5000/api/profiles/<id>
```

## Deploying to Vercel

1. Set `DATABASE_URL` as an environment variable in your Vercel project settings.
2. Ensure a `vercel.json` is present specifying the Python runtime:
   ```json
   { "functions": { "app.py": { "runtime": "python3.13" } } }
   ```
3. Install command: `pip install -r requirements.txt`

## Tech Stack

- **Python 3.13+** — Flask, Flask-CORS, Flask-SQLAlchemy, SQLAlchemy
- **Database** — SQLite (local) / PostgreSQL via Supabase (production)
- **External APIs** — Genderize.io, Agify.io, Nationalize.io

## Endpoints

### `GET /api/classify`

Classifies a name by predicted gender only. Also accessible at `GET /api`.

**Query Parameters**

| Parameter | Type   | Required | Description          |
| --------- | ------ | -------- | -------------------- |
| `name`    | string | Yes      | The name to classify |

**Success Response `200`**

```json
{
  "status": "success",
  "data": {
    "gender": "male",
    "gender_probability": 0.99,
    "sample_size": 1234
  }
}
```

**Error Responses**

| Status | Condition                            | Body                                                        |
| ------ | ------------------------------------ | ----------------------------------------------------------- |
| `400`  | `name` is missing or empty           | `{"status": "error", "message": "name not specified"}`      |
| `400`  | No prediction available for the name | `{"status": "error", "message": "..."}`                     |
| `500`  | Unexpected server error              | `{"status": "error", "message": "failed to classify name"}` |

---

### `GET /api/profiles`

Returns a list of saved profiles. Supports optional filtering.

**Query Parameters**

| Parameter    | Type   | Required | Description                          |
| ------------ | ------ | -------- | ------------------------------------ |
| `country_id` | string | No       | Filter by country code (e.g. `"US"`) |
| `age_group`  | string | No       | Filter by age group (see below)      |

**Age groups:** `child` (≤12), `teenager` (13–20), `adult` (21–59), `senior` (60+)

**Success Response `200`**

```json
{
  "status": "success",
  "count": 1,
  "data": [
    {
      "id": "abc123",
      "name": "james",
      "gender": "male",
      "age": 35,
      "age_group": "adult",
      "country_id": "US",
      "created_at": "2026-04-17T10:00:00+00:00"
    }
  ]
}
```

---

### `POST /api/profiles`

Creates a new profile for a name, fetching gender, age, and nationality predictions. Returns the existing profile if one already exists for that name.

**Request Body** (`application/json`)

```json
{ "name": "james" }
```

**Success Response `200`**

```json
{
  "status": "success",
  "data": {
    "id": "abc123",
    "name": "james",
    "gender": "male",
    "gender_probability": 0.99,
    "sample_size": 1234,
    "age": 35,
    "age_group": "adult",
    "country_id": "US",
    "country_probability": 0.85,
    "created_at": "2026-04-17T10:00:00+00:00"
  }
}
```

**Error Responses**

| Status | Condition               | Body                                                         |
| ------ | ----------------------- | ------------------------------------------------------------ |
| `400`  | `name` missing or empty | `{"status": "error", "message": "name not specified"}`       |
| `500`  | Prediction API failure  | `{"status": "error", "message": "Failed to create profile"}` |
| `502`  | Unexpected error        | `{"status": "error", "message": "..."}`                      |

---

### `GET /api/profiles/<id>`

Returns a single profile by its ID.

**Success Response `200`**

```json
{
  "status": "success",
  "data": { ...full profile object... }
}
```

**Error Response**

| Status | Condition         | Body                                                  |
| ------ | ----------------- | ----------------------------------------------------- |
| `404`  | Profile not found | `{"status": "error", "message": "profile not found"}` |

---

### `DELETE /api/profiles/<id>`

Deletes a profile by its ID.

**Success Response:** `204 No Content`

**Error Response**

| Status | Condition         | Body                                                  |
| ------ | ----------------- | ----------------------------------------------------- |
| `404`  | Profile not found | `{"status": "error", "message": "profile not found"}` |

---

## Database

The app selects its database based on environment variables at startup:

- **Locally** — if `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are not set, it uses SQLite (`profile.db` in the project root).
- **Production** — if both env vars are present, it connects to a [Turso](https://turso.tech) LibSQL database.

Add these to a `.env` file for production use locally:

```
TURSO_DATABASE_URL=libsql://<your-db>.turso.io
TURSO_AUTH_TOKEN=<your-token>
```

## Running Locally

**Prerequisites:** Python 3.13+

```bash
# Clone the repository
git clone <your-repo-url>
cd hng-14

# Create and activate a virtual environment
python -m venv env
# Windows
env\Scripts\activate
# macOS/Linux
source env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

The API will be available at `http://localhost:5000`.

**Example requests:**

```bash
# Classify a name
curl "http://localhost:5000/api/classify?name=james"

# Create a profile
curl -X POST http://localhost:5000/api/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "james"}'

# List profiles filtered by country
curl "http://localhost:5000/api/profiles?country_id=US"

# Delete a profile
curl -X DELETE http://localhost:5000/api/profiles/<id>
```

## Deploying to Vercel

1. Set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` as environment variables in your Vercel project settings.
2. Set the install command to:
   ```
   pip install -r requirements-prod.txt
   ```
   `requirements-prod.txt` extends `requirements.txt` with `libsql-experimental`, which provides the LibSQL SQLAlchemy driver (Linux only — not required for local development on Windows/macOS).

## Tech Stack

- **Python 3.13+** — Flask, Flask-CORS, Flask-SQLAlchemy, SQLAlchemy
- **Database** — SQLite (local) / Turso LibSQL (production)
- **External APIs** — Genderize.io, Agify.io, Nationalize.io
