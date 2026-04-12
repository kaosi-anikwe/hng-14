import requests
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

URL = "https://api.genderize.io"


def classify_name(name: str) -> dict[str, str | bool | dict]:
    if not name:
        return {"success": False, "message": "name not specified"}

    params = {"name": name}
    response = requests.get(URL, params=params)

    if response.ok:
        raw_data: dict = response.json()
        gender: str | None = raw_data.get("gender")
        count: int = raw_data.get("count", 0)

        if not gender or not count:
            return {
                "success": False,
                "message": "No prediction available for the provided name",
            }

        probability: float = raw_data.get("probability", 0)
        is_confident = True if probability >= 0.7 and count >= 100 else False
        processed_at = datetime.now(timezone.utc).isoformat()

        return {
            "success": True,
            "data": {
                "name": name,
                "gender": gender,
                "probability": probability,
                "sample_size": count,
                "is_confident": is_confident,
                "processed_at": processed_at,
            },
        }
    return {"success": False, "message": "Failed to query gender. Please try again."}
