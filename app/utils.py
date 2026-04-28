import os
import json
import base64
import hashlib
import secrets
import logging
from functools import wraps
from typing import Optional, List

import requests
from flask import jsonify, request
from flask_jwt_extended import verify_jwt_in_request, current_user

from app.models import User, Role

logger = logging.getLogger(__name__)

type ProfileData = dict[str, str | int | float]


def genderize(name: str) -> dict[str, str | bool | dict]:
    """Predicts the gender of a name using the Genderize.io API.

    Args:
        name: The first name to classify.

    Returns:
        A dict with a ``success`` key. On success, ``data`` contains:
            - ``gender`` (str): ``"male"`` or ``"female"``.
            - ``gender_probability`` (float): Confidence score between 0 and 1.
            - ``sample_size`` (int): Number of data points used for the prediction.
        On failure, ``message`` describes the reason.

    Raises:
        Exception: If the API returns an unparseable or unexpected response.
    """
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
    """Predicts the age associated with a name using the Agify.io API.

    Args:
        name: The first name to classify.

    Returns:
        A dict with a ``success`` key. On success, ``data`` contains:
            - ``age`` (int): Predicted age in years.
            - ``age_group`` (str): One of ``"child"`` (≤12), ``"teenager"`` (13–20),
              ``"adult"`` (21–59), or ``"senior"`` (60+).
        On failure, ``message`` describes the reason.

    Raises:
        Exception: If the API returns an unparseable or unexpected response.
    """
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
    """Predicts the most likely nationality for a name using the Nationalize.io API.

    Returns the highest-probability country from the API response.

    Args:
        name: The first name to classify.

    Returns:
        A dict with a ``success`` key. On success, ``data`` contains:
            - ``country_id`` (str): ISO 3166-1 alpha-2 country code (e.g. ``"US"``).
            - ``country_probability`` (float): Confidence score between 0 and 1.
        On failure, ``message`` describes the reason.

    Raises:
        Exception: If the API returns an unparseable or unexpected response.
    """
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


def seed_profiles(json_file: Optional[str], fresh: bool = False) -> None:
    """Seeds the database with profile data from a JSON file.
    Call within a Flask-app context.

    Args:
        json_file: Path to a JSON file containing profile records to insert.
            If ``None``, the function does nothing.
        fresh (bool): If ``True``, database is cleared.
    """
    if json_file and os.path.exists(json_file):
        from app.models import db, Profile, Gender

        if db.session.query(Profile).first() and not fresh:
            logger.info("Profile data already exists, use fresh to clear database.")
            return

        with open(json_file, "r") as f:
            json_data: dict[str, List[ProfileData]] = json.load(f)
            profile_data = json_data.get("profiles", [])
            profiles: List[Profile] = []

            for profile in profile_data:
                new_profile: Profile = Profile(
                    name=profile.get("name"),
                    gender=Gender(str(profile.get("gender")).lower()),
                    gender_probability=profile.get("gender_probability"),
                    age=profile.get("age"),
                    age_group=profile.get("age_group"),
                    country_id=profile.get("country_id"),
                    country_name=profile.get("country_name"),
                    country_probability=profile.get("country_probability"),
                )
                profiles.append(new_profile)
                logger.debug(f"Created profile with name: {new_profile.name}")

            try:
                if fresh:
                    logger.debug("Clearing existing database")
                    db.drop_all()

                db.create_all()

                logger.info(f"Adding {len(profiles)} to database")
                db.session.add_all(profiles)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise Exception(f"Failed to add profiles to database: {str(e)}")

    logger.info(f"JSON file: {json_file} not found.")


def generate_pkce():
    verifier = secrets.token_urlsafe(64)
    sha256_hash = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(sha256_hash).decode("utf-8").rstrip("=")
    return verifier, challenge


def admin_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            # Verify JWT exists and is valid
            verify_jwt_in_request()
            # Check the property on the loaded user object
            # current_user is populated by your user_lookup_loader
            user: User | None = current_user
            if not user or user.role != Role.ADMIN:
                return (
                    jsonify({"status": "error", "message": "Admin access required"}),
                    403,
                )

            return fn(*args, **kwargs)

        return decorator

    return wrapper


def version_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            header_value = request.headers.get("X-API-Version")

            if not header_value:
                return (
                    jsonify(
                        {"status": "error", "message": "API version header required"}
                    ),
                    400,
                )

            if str(header_value) != "1":
                return jsonify({"error": "Invalid header value"}), 401

            return fn(*args, **kwargs)

        return decorator

    return wrapper
