import requests
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()


def genderize(name: str) -> dict[str, str | bool | dict]:
    url = "https://api.genderize.io"

    if not name:
        return {"success": False, "message": "name not specified"}

    try:
        params = {"name": name}
        response = requests.get(url, params=params)

        if response.ok:
            raw_data: dict = response.json()
            gender: str | None = raw_data.get("gender")
            count: int = raw_data.get("count", 0)

            if not gender or not count:
                raise Exception(
                    "Genderize: No prediction available for the provided name"
                )

            probability: float = raw_data.get("probability", 0)

            return {
                "success": True,
                "data": {
                    "gender": gender,
                    "gender_probability": probability,
                    "sample_size": count,
                },
            }
        return {
            "success": False,
            "message": "Failed to query gender. Please try again.",
        }
    except:
        raise Exception("Genderize returned an invalid response")


def agify(name: str) -> dict[str, str | bool | dict]:
    url = "https://api.agify.io"

    if not name:
        return {"success": False, "message": "name not specified"}

    try:
        params = {"name": name}
        response = requests.get(url, params=params)

        if response.ok:
            raw_data: dict = response.json()
            age: int = int(raw_data.get("age", 0))

            if not age:
                raise Exception("Agify: No prediction available for the provided name")

            age_group: str = "child"

            if age > 12:
                age_group = "teenager"

            if age > 20:
                age_group = "adult"

            if age > 59:
                age_group = "senior"

            return {"success": True, "data": {"age": age, "age_group": age_group}}
        return {"success": False, "message": "Failed to query age. Please try again."}
    except:
        raise Exception("Agify returned an invalid response")


def nationalize(name: str) -> dict[str, str | bool | dict]:
    url = "https://api.nationalize.io"

    if not name:
        return {"success": False, "message": "name not specified"}

    try:
        params = {"name": name}
        response = requests.get(url, params=params)

        if response.ok:
            raw_data: dict = response.json()
            countries: list[dict[str, str | float]] = raw_data.get("country", [])

            if not countries:
                raise Exception(
                    "Nationalize: No prediction available for the provided name"
                )

            return {
                "success": True,
                "data": {
                    "country_id": countries[0]["country_id"],
                    "country_probability": countries[0].get("probability"),
                },
            }

        return {
            "success": False,
            "message": "Failed to query nationality. Please try again.",
        }
    except:
        raise Exception("Nationalize returned an invalid response")
