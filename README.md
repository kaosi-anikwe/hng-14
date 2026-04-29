# Insighta Labs+ API

A Flask REST API backend for the Insighta Labs system. It classifies names by predicted gender, age, and nationality by aggregating data from [Genderize.io](https://genderize.io), [Agify.io](https://agify.io), and [Nationalize.io](https://nationalize.io). Profiles are persisted to a database — SQLite locally, or a PostgreSQL database in production.

Authentication is handled via **GitHub OAuth** with PKCE. Access and refresh tokens are issued as JWTs stored in secure HTTP-only cookies (web) or returned as JSON (CLI). A **Redis** instance is used to maintain a token blocklist for logout and token rotation.

---

## Roles

| Role      | Permissions                                              |
| --------- | -------------------------------------------------------- |
| `analyst` | Default role. Read-only access to profiles and data.     |
| `admin`   | All analyst permissions plus create, delete, and export. |

---

## API Version Header

All `/api/*` endpoints require:

```
X-API-Version: 1
```

| Status | Condition               | Body                                                            |
| ------ | ----------------------- | --------------------------------------------------------------- |
| `400`  | Header missing          | `{"status": "error", "message": "API version header required"}` |
| `401`  | Header value is invalid | `{"error": "Invalid header value"}`                             |

---

## Endpoints

### Auth

#### `GET /auth/github`

Initiates the GitHub OAuth flow. Generates a PKCE challenge and stores `oauth_state` and `code_verifier` in an encrypted session cookie, then redirects the browser to GitHub.

---

#### `GET /auth/github/callback`

GitHub redirects here after user authorization. Validates state, exchanges code for a GitHub token, fetches the user profile, creates or updates the user record, issues JWTs in secure cookies, and redirects to the frontend dashboard.

**Redirects to:** `FRONTEND_URL/dashboard`

---

#### `POST /auth/cli/callback`

CLI variant of the OAuth callback. Accepts code and verifier as JSON and returns tokens in the response body instead of setting cookies.

**Request Body** (`application/json`)

```json
{
  "code": "<github_authorization_code>",
  "code_verifier": "<pkce_verifier>"
}
```

**Success Response `200`**

```json
{
  "status": "success",
  "username": "octocat",
  "access_token": "<jwt>",
  "refresh_token": "<jwt>"
}
```

**Error Responses**

| Status | Condition                         | Body                                    |
| ------ | --------------------------------- | --------------------------------------- |
| `400`  | `code` or `code_verifier` missing | `{"status": "error", "message": "..."}` |
| `500`  | Unexpected error                  | `{"status": "error", "message": "..."}` |

---

#### `POST /auth/refresh`

Issues new access and refresh tokens. The supplied refresh token is immediately blocklisted (one-time use). Accepts the token via the `Authorization: Bearer` header.

**Success Response `200`**

```json
{
  "status": "success",
  "access_token": "<new_jwt>",
  "refresh_token": "<new_jwt>"
}
```

---

#### `POST /auth/logout`

Revokes the current token by adding it to the Redis blocklist. Marks the user as inactive and clears JWT cookies.

**Success Response `200`**

```json
{ "status": "success" }
```

---

### Profiles

All profile endpoints require `X-API-Version: 1` and a valid JWT.

---

#### `GET /api/classify`

Classifies a name by predicted gender. Requires `analyst` or `admin` role.

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

#### `GET /api/profiles`

Returns a paginated, filterable, sortable list of profiles. Requires `analyst` or `admin` role.

**Query Parameters**

| Parameter                 | Type   | Required | Description                                            |
| ------------------------- | ------ | -------- | ------------------------------------------------------ |
| `gender`                  | string | No       | `male` or `female`                                     |
| `age_group`               | string | No       | `child`, `teenager`, `adult`, or `senior`              |
| `country_id`              | string | No       | ISO 3166-1 alpha-2 code (e.g. `NG`)                    |
| `min_age`                 | int    | No       | Minimum age (inclusive)                                |
| `max_age`                 | int    | No       | Maximum age (inclusive)                                |
| `min_gender_probability`  | float  | No       | Minimum gender confidence (0-1)                        |
| `min_country_probability` | float  | No       | Minimum country confidence (0-1)                       |
| `sort_by`                 | string | No       | `age` (default), `created_at`, or `gender_probability` |
| `order`                   | string | No       | `asc` (default) or `desc`                              |
| `page`                    | int    | No       | Page number (default: `1`)                             |
| `limit`                   | int    | No       | Results per page, max 50 (default: `10`)               |

**Age groups:** `child` (<=12), `teenager` (13-20), `adult` (21-59), `senior` (60+)

**Success Response `200`**

```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 42,
  "total_pages": 5,
  "links": {
    "self": "/api/profiles?page=1&limit=10",
    "next": "/api/profiles?page=2&limit=10",
    "prev": null
  },
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

**Error Responses**

| Status | Condition                 | Body                                                         |
| ------ | ------------------------- | ------------------------------------------------------------ |
| `400`  | Invalid `sort_by`/`order` | `{"status": "error", "message": "Invalid query parameters"}` |
| `500`  | Unexpected error          | `{"status": "error", "message": "Failed to get profiles"}`   |

---

#### `POST /api/profiles`

Creates a new profile by fetching gender, age, and nationality predictions. Returns the existing profile if one already exists for that name. Requires `admin` role.

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

If a profile already exists for the name, a `200` is returned with `"message": "Profile already exists"` alongside the existing `data`.

**Error Responses**

| Status | Condition               | Body                                                         |
| ------ | ----------------------- | ------------------------------------------------------------ |
| `400`  | `name` missing or empty | `{"status": "error", "message": "name not specified"}`       |
| `403`  | Not an admin            | `{"status": "error", "message": "Admin access required"}`    |
| `500`  | Prediction API failure  | `{"status": "error", "message": "Failed to create profile"}` |

---

#### `GET /api/profiles/search`

Natural language search over profiles. Parses plain English queries into filters using rule-based logic. No AI or LLMs involved. Requires `analyst` or `admin` role.

**Query Parameters**

| Parameter | Type   | Required | Description                                            |
| --------- | ------ | -------- | ------------------------------------------------------ |
| `q`       | string | Yes      | Plain English query (see examples below)               |
| `sort_by` | string | No       | `age` (default), `created_at`, or `gender_probability` |
| `order`   | string | No       | `asc` (default) or `desc`                              |
| `page`    | int    | No       | Page number (default: `1`)                             |
| `limit`   | int    | No       | Results per page, max 50 (default: `10`)               |

**Example queries**

| Query                                | Interpreted as                                    |
| ------------------------------------ | ------------------------------------------------- |
| `young males`                        | `gender=male` + age 16-24                         |
| `females above 30`                   | `gender=female` + `age > 30`                      |
| `people from nigeria`                | `country_name=nigeria`                            |
| `adult males from kenya`             | `gender=male` + `age_group=adult` + country=kenya |
| `male and female teenagers above 17` | `age_group=teenager` + `age > 17`                 |

**Success Response `200`**

```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 5,
  "total_pages": 1,
  "links": { "self": "...", "next": null, "prev": null },
  "data": [ ...profile objects... ]
}
```

**Error Responses**

| Status | Condition                 | Body                                                          |
| ------ | ------------------------- | ------------------------------------------------------------- |
| `400`  | `q` missing or empty      | `{"status": "error", "message": "Search query is required"}`  |
| `400`  | Query could not be parsed | `{"status": "error", "message": "Unable to interpret query"}` |

---

#### `GET /api/profiles/export`

Exports all (optionally filtered) profiles as a CSV file. Requires `admin` role.

**Query Parameters**

| Parameter                 | Type   | Required | Description                                            |
| ------------------------- | ------ | -------- | ------------------------------------------------------ |
| `format`                  | string | Yes      | Must be `csv`                                          |
| `gender`                  | string | No       | `male` or `female`                                     |
| `age_group`               | string | No       | `child`, `teenager`, `adult`, or `senior`              |
| `country_id`              | string | No       | ISO 3166-1 alpha-2 code                                |
| `min_age`                 | int    | No       | Minimum age (inclusive)                                |
| `max_age`                 | int    | No       | Maximum age (inclusive)                                |
| `min_gender_probability`  | float  | No       | Minimum gender confidence (0-1)                        |
| `min_country_probability` | float  | No       | Minimum country confidence (0-1)                       |
| `sort_by`                 | string | No       | `age` (default), `created_at`, or `gender_probability` |
| `order`                   | string | No       | `asc` (default) or `desc`                              |

**Success Response `200`** — `Content-Type: text/csv`

Downloads a CSV with columns: `id`, `name`, `gender`, `gender_probability`, `age`, `age_group`, `country_id`, `country_name`, `country_probability`, `created_at`.

**Error Responses**

| Status | Condition                     | Body                                                         |
| ------ | ----------------------------- | ------------------------------------------------------------ |
| `400`  | `format` missing or not `csv` | `{"status": "error", "message": "Invalid export format"}`    |
| `400`  | Invalid `sort_by`/`order`     | `{"status": "error", "message": "Invalid query parameters"}` |
| `403`  | Not an admin                  | `{"status": "error", "message": "Admin access required"}`    |

---

#### `GET /api/profiles/<id>`

Returns a single profile by its ID. Requires `analyst` or `admin` role.

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

**Error Response**

| Status | Condition         | Body                                                  |
| ------ | ----------------- | ----------------------------------------------------- |
| `404`  | Profile not found | `{"status": "error", "message": "profile not found"}` |

---

#### `DELETE /api/profiles/<id>`

Deletes a profile by its ID. Requires `admin` role.

**Success Response:** `204 No Content`

**Error Responses**

| Status | Condition         | Body                                                      |
| ------ | ----------------- | --------------------------------------------------------- |
| `403`  | Not an admin      | `{"status": "error", "message": "Admin access required"}` |
| `404`  | Profile not found | `{"status": "error", "message": "profile not found"}`     |

---

### Users

#### `GET /api/users/me`

Returns the authenticated user's profile. Requires a valid JWT.

**Success Response `200`**

```json
{
  "status": "success",
  "user": {
    "id": "abc123",
    "github_id": "12345678",
    "username": "octocat",
    "email": "octocat@example.com",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
    "role": "analyst",
    "is_active": true,
    "last_login_at": "2026-04-17T10:00:00+00:00"
  }
}
```

---

#### `GET /api/dashboard`

Returns aggregate statistics about the profile database. Requires a valid JWT.

**Success Response `200`**

```json
{
  "status": "success",
  "dashboard": {
    "total_profiles": 500,
    "gender_breakdown": { "male": 300, "female": 200 },
    "age_group_breakdown": { "adult": 250, "teenager": 100, "senior": 90, "child": 60 },
    "top_countries": [
      { "country_id": "US", "country_name": "United States", "count": 80 }
    ],
    "averages": {
      "age": 32.5,
      "gender_probability": 0.9412,
      "country_probability": 0.7831
    },
    "recent_profiles": [ ...last 5 profile summaries... ]
  }
}
```

---

## Environment Variables

Create a `.env` file in the project root. All variables are required unless marked optional.

```env
# Flask
SECRET_KEY=<your-secret-key>
DEBUG=true                    # optional, default: true

# Database (optional - defaults to SQLite at profile.db)
SQLALCHEMY_DATABASE_URI=postgresql://user:password@host:port/dbname

# JWT
JWT_SECRET_KEY=<your-jwt-secret>
JWT_ACCESS_TOKEN_EXPIRES=180   # optional, seconds (default: 3 minutes)
JWT_REFRESH_TOKEN_EXPIRES=300  # optional, seconds (default: 5 minutes)

# GitHub OAuth
GITHUB_CLIENT_ID=<your-github-client-id>
GITHUB_CLIENT_SECRET=<your-github-client-secret>
REDIRECT_URI=http://localhost:5000/auth/github/callback

# Frontend
FRONTEND_URL=http://localhost:5173

# Redis (token blocklist)
REDIS_HOST=<host>
REDIS_PORT=6379
REDIS_USERNAME=<username>
REDIS_PASSWORD=<password>

# Logging (optional - stdout only when not set)
LOG_FILE=app.log
```

---

## Running Locally

**Prerequisites:** Python 3.14+, a Redis instance, and a GitHub OAuth App.

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

# Copy and fill in environment variables
cp .env.example .env

# Start the server
python main.py
```

The API will be available at `http://localhost:5000`.

**Example authenticated requests:**

After completing the OAuth flow, cookies are set automatically by the browser. For curl, save and reuse the cookie jar:

```bash
# 1. Complete the OAuth flow — cookies are set on redirect to /dashboard.
#    For testing with curl, capture cookies from the callback:
curl -c cookies.txt -L "http://localhost:5000/auth/github"

# Classify a name
curl -b cookies.txt \
     -H "X-API-Version: 1" \
     "http://localhost:5000/api/classify?name=james"

# List profiles with filters
curl -b cookies.txt \
     -H "X-API-Version: 1" \
     "http://localhost:5000/api/profiles?gender=female&age_group=adult&sort_by=age&order=desc&page=1&limit=10"

# Create a profile (admin only)
curl -b cookies.txt \
     -X POST \
     -H "X-API-Version: 1" \
     -H "Content-Type: application/json" \
     -d '{"name": "james"}' \
     "http://localhost:5000/api/profiles"

# Natural language search
curl -b cookies.txt \
     -H "X-API-Version: 1" \
     "http://localhost:5000/api/profiles/search?q=young+males+from+nigeria"

# Export CSV (admin only)
curl -b cookies.txt \
     -H "X-API-Version: 1" \
     "http://localhost:5000/api/profiles/export?format=csv" \
     -o profiles.csv

# Delete a profile (admin only)
curl -b cookies.txt \
     -X DELETE \
     -H "X-API-Version: 1" \
     "http://localhost:5000/api/profiles/<id>"
```

For **CLI usage**, obtain tokens via `POST /auth/cli/callback` and pass them in the `Authorization: Bearer` header instead.

---

## Deploying to Vercel

1. Set all required environment variables in your Vercel project settings.
2. Ensure `vercel.json` is present:
   ```json
   {
     "builds": [{ "src": "main.py", "use": "@vercel/python" }],
     "routes": [{ "src": "/(.*)", "dest": "main.py" }]
   }
   ```
3. Install command: `pip install -r requirements.txt`

> **Note:** File-based logging (`LOG_FILE`) is not supported on Vercel because the filesystem is read-only. Leave `LOG_FILE` unset in production; logs go to stdout (visible in Vercel function logs).

---

## Tech Stack

- **Python 3.14+** — Flask, Flask-CORS, Flask-SQLAlchemy, Flask-JWT-Extended, pydantic-settings, pycountry
- **Database** — SQLite (local) / PostgreSQL (production)
- **Auth** — GitHub OAuth (PKCE), JWT (access + refresh), Redis token blocklist
- **External APIs** — Genderize.io, Agify.io, Nationalize.io
