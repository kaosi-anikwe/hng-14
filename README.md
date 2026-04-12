# Name Gender Classifier API

A lightweight Flask REST API that accepts a name and returns gender prediction data by integrating with the [Genderize.io](https://genderize.io) API.

## Endpoint

### `GET /api/classify`

Classifies a name by predicted gender.

**Query Parameters**

| Parameter | Type   | Required | Description          |
| --------- | ------ | -------- | -------------------- |
| `name`    | string | Yes      | The name to classify |

**Success Response `200`**

```json
{
  "status": "success",
  "data": {
    "name": "james",
    "gender": "male",
    "probability": 0.99,
    "sample_size": 1234,
    "is_confident": true,
    "processed_at": "2026-04-12T10:00:00+00:00"
  }
}
```

**Fields**

| Field          | Type    | Description                                                      |
| -------------- | ------- | ---------------------------------------------------------------- |
| `name`         | string  | The name that was classified                                     |
| `gender`       | string  | `"male"` or `"female"`                                           |
| `probability`  | float   | Confidence probability from Genderize.io (0–1)                   |
| `sample_size`  | integer | Number of samples used for the prediction (`count` from the API) |
| `is_confident` | boolean | `true` when `probability >= 0.7` **and** `sample_size >= 100`    |
| `processed_at` | string  | UTC timestamp of the request in ISO 8601 format                  |

**Error Responses**

| Status | Condition                                | Body                                                                              |
| ------ | ---------------------------------------- | --------------------------------------------------------------------------------- |
| `400`  | `name` is missing or empty               | `{"status": "error", "message": "name not specified"}`                            |
| `400`  | Genderize returns no prediction for name | `{"status": "error", "message": "No prediction available for the provided name"}` |
| `422`  | `name` is not a string                   | `{"status": "error", "message": "name should be a string"}`                       |
| `500`  | Unexpected server error                  | `{"status": "error", "message": "failed to classify name"}`                       |

## Running Locally

**Prerequisites:** Python 3.10+

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

**Example request:**

```bash
curl "http://localhost:5000/api/classify?name=james"
```

## Tech Stack

- **Python** — Flask, flask-cors, requests, python-dotenv
