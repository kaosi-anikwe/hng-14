# Name Classifier API

A Flask REST API that classifies a name by gender, age, and nationality by aggregating data from [Genderize.io](https://genderize.io), [Agify.io](https://agify.io), and [Nationalize.io](https://nationalize.io). Profiles are persisted to a local SQLite database.

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

## Tech Stack

- **Python 3.13+** — Flask, Flask-CORS, Flask-SQLAlchemy, SQLAlchemy
- **Database** — SQLite (via `instance/profile.db`)
- **External APIs** — Genderize.io, Agify.io, Nationalize.io
