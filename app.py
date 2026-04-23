import re
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import cast, List

from flask_cors import CORS
from flask import Flask, jsonify, request
from sqlalchemy import asc, desc, select, and_, or_, func

from models import db, Profile, Gender
from utils import genderize, agify, nationalize, seed_profiles

# --- Logging setup ---
logger = logging.getLogger()  # root logger — all module loggers propagate here
logger.setLevel(logging.DEBUG)

_stream_handler = logging.StreamHandler()
_stream_handler.setLevel(logging.DEBUG)

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
_stream_handler.setFormatter(_formatter)
logger.addHandler(_stream_handler)

if os.environ.get("LOG_FILE"):
    _file_handler = RotatingFileHandler(
        os.environ["LOG_FILE"], maxBytes=1 * 1024 * 1024, backupCount=5
    )
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(_formatter)
    logger.addHandler(_file_handler)
# ---------------------

app = Flask(__name__)
CORS(app, origins="*")

_database_url = os.environ.get("DATABASE_URL", "")

if _database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = _database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///profile.db"

db.init_app(app)

with app.app_context():
    db.create_all()
    seed_profiles("seed_profiles.json")


@app.get("/")
def index():
    return jsonify({"message": "Hello"})


@app.get("/api")
@app.get("/api/classify")
def classify():
    try:
        params = request.args
        name = params.get("name")

        if not name:
            return jsonify({"status": "error", "message": "name not specified"}), 400

        if not isinstance(name, str):
            return (
                jsonify({"status": "error", "message": "name should be a string"}),
                422,
            )

        result = genderize(name)

        if result.get("success", False):
            return jsonify({"status": "success", "data": result.get("data", {})})

        return jsonify({"status": "error", "message": result.get("message", "")}), 400
    except:
        return jsonify({"status": "error", "message": "failed to classify name"}), 500


@app.route("/api/profiles", methods=["GET", "POST"])
def profiles():
    if request.method == "GET":
        try:
            gender = request.args.get("gender")
            age_group = request.args.get("age_group")
            country_id = request.args.get("country_id")
            min_age = request.args.get("min_age")
            max_age = request.args.get("max_age")
            min_gender_probability = request.args.get("min_gender_probability")
            min_country_probability = request.args.get("min_country_probability")
            sort_by = request.args.get(
                "sort_by", "age"
            )  # age | created_at | gender_probability
            order = request.args.get("order", "asc")  # asc | desc
            page = max(1, int(request.args.get("page", 1)))
            per_page = max(1, min(50, int(request.args.get("per_page", 10))))

            if sort_by not in [
                "age",
                "created_at",
                "gender_probability",
            ] or order not in ["asc", "desc"]:
                return (
                    jsonify({"status": "error", "message": "Invalid query parameters"}),
                    400,
                )

            query = select(Profile)

            if gender:
                query = query.where(Profile.gender == Gender(gender.lower()))
            if age_group:
                query = query.where(Profile.age_group == age_group)
            if country_id:
                query = query.where(Profile.country_id == country_id)
            if min_age:
                query = query.where(Profile.age >= min_age)
            if max_age:
                query = query.where(Profile.age <= max_age)
            if min_gender_probability:
                query = query.where(
                    Profile.gender_probability >= min_gender_probability
                )
            if min_country_probability:
                query = query.where(
                    Profile.country_probability >= min_country_probability
                )

            sort_param = getattr(Profile, sort_by)
            order_fn = asc if order == "asc" else desc

            query = query.order_by(order_fn(sort_param))

            pagination = db.paginate(
                query, page=page, per_page=per_page, error_out=False
            )

            return jsonify(
                {
                    "status": "success",
                    "page": pagination.page,
                    "per_page": pagination.per_page,
                    "limit": pagination.per_page,
                    "total": pagination.total,
                    "data": [
                        profile.to_json()
                        for profile in cast(List[Profile], pagination.items)
                    ],
                }
            )
        except:
            return (
                jsonify({"status": "error", "message": "Failed to get profiles"}),
                500,
            )

    else:  # method = POST
        try:
            request_data: dict = request.get_json()
            name: str = str(request_data.get("name", ""))

            if not name:
                return (
                    jsonify({"status": "error", "message": "name not specified"}),
                    400,
                )

            existing_profile: Profile | None = (
                db.session.query(Profile).filter(Profile.name == name).first()
            )

            if existing_profile:
                return jsonify(
                    {
                        "status": "success",
                        "message": "Profile already exists",
                        "data": existing_profile.to_json(),
                    }
                )

            # create new profile
            gender_result = genderize(name).get("data", {})
            age_result = agify(name).get("data", {})
            country_result = nationalize(name).get("data", {})

            if (
                isinstance(gender_result, dict)
                and isinstance(age_result, dict)
                and isinstance(country_result, dict)
            ):
                gender = str(gender_result.get("gender", "male"))
                gender_probability = float(gender_result.get("gender_probability", 0))
                age = int(age_result.get("age", 0))
                age_group = str(age_result.get("age_group", ""))
                country_id = str(country_result.get("country_id", ""))
                country_probability = float(
                    country_result.get("country_probability", 0)
                )

                new_profile = Profile(
                    name=name,
                    gender=Gender(gender.lower()),
                    gender_probability=round(gender_probability, 2),
                    age=age,
                    age_group=age_group,
                    country_id=country_id,
                    country_probability=round(country_probability, 2),
                )

                db.session.add(new_profile)
                db.session.commit()
                db.session.refresh(new_profile)

                return jsonify({"status": "success", "data": new_profile.to_json()})
            else:
                return (
                    jsonify({"status": "error", "message": "Failed to create profile"}),
                    500,
                )
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 502


@app.get("/api/profiles/search")
def search_profile():
    search_query = request.args.get("q", "").strip()
    sort_by = request.args.get(
        "sort_by", "age"
    )  # age | created_at | gender_probability
    order = request.args.get("order", "asc")  # asc | desc
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(50, int(request.args.get("per_page", 10))))

    if not search_query:
        return jsonify({"status": "error", "message": "Search query is required"}), 400

    query = select(Profile)
    filters_applied = False

    # --- Gender ---
    male_match = re.search(r"\bmales?\b", search_query, re.IGNORECASE)
    female_match = re.search(r"\bfemales?\b", search_query, re.IGNORECASE)

    if male_match and not female_match:
        query = query.where(Profile.gender == Gender.male)
        filters_applied = True
        logger.info("Search filter applied: gender=male")
    elif female_match and not male_match:
        query = query.where(Profile.gender == Gender.female)
        filters_applied = True
        logger.info("Search filter applied: gender=female")
    elif male_match and female_match:
        # Both mentioned — no gender restriction, but it's still interpretable
        filters_applied = True
        logger.info("Search filter applied: gender=male+female (no restriction)")

    # --- Country ---
    # Stop capture at age keywords, prepositions, or punctuation
    country_match = re.search(
        r"\bfrom\s+([a-z]+(?:\s+[a-z]+)*?)(?=\s+(?:above|below|aged?|who|and|with)|[.,!]|$)",
        search_query,
        re.IGNORECASE,
    )
    if country_match:
        country_name = country_match.group(1).strip().lower()
        query = query.where(db.func.lower(Profile.country_name) == country_name)
        filters_applied = True
        logger.info("Search filter applied: country_name=%s", country_name)

    # --- Age (above / below) ---
    above_match = re.search(r"\babove\s+(\d{1,3})\b", search_query, re.IGNORECASE)
    below_match = re.search(r"\bbelow\s+(\d{1,3})\b", search_query, re.IGNORECASE)

    if above_match:
        query = query.where(Profile.age >= int(above_match.group(1)))
        filters_applied = True
        logger.info("Search filter applied: age>=%s", above_match.group(1))
    if below_match:
        query = query.where(Profile.age < int(below_match.group(1)))
        filters_applied = True
        logger.info("Search filter applied: age<%s", below_match.group(1))

    # --- Age group keywords ---
    age_pattern = r"\b(children|child|teenagers?|adults?|seniors?|young)\b"
    found_categories = set(re.findall(age_pattern, search_query, re.IGNORECASE))

    age_group_conditions = []
    for match in found_categories:
        ag = match.lower()
        if ag.endswith("s") and ag != "children":
            ag = ag[:-1]
        if ag == "children":
            ag = "child"

        if ag in ["child", "teenager", "adult", "senior"]:
            age_group_conditions.append(Profile.age_group == ag)
            filters_applied = True
            logger.info("Search filter applied: age_group=%s", ag)
        elif ag == "young":
            query = query.where(and_(Profile.age >= 16, Profile.age <= 24))
            filters_applied = True
            logger.info("Search filter applied: age=16-24 (young)")

    if age_group_conditions:
        query = query.where(
            age_group_conditions[0]
            if len(age_group_conditions) == 1
            else or_(*age_group_conditions)
        )

    if not filters_applied:
        logger.info("Search query could not be interpreted: %s", search_query)
        return (
            jsonify({"status": "error", "message": "Unable to interpret query"}),
            400,
        )

    sort_param = getattr(Profile, sort_by)
    order_fn = asc if order == "asc" else desc

    query = query.order_by(order_fn(sort_param))

    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

    return jsonify(
        {
            "status": "success",
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "data": [
                profile.to_json() for profile in cast(List[Profile], pagination.items)
            ],
        }
    )


@app.route("/api/profiles/<string:id>", methods=["GET", "DELETE"])
def profile(id: str):
    profile: Profile | None = db.session.get(Profile, id)

    if not profile:
        return jsonify({"status": "error", "message": "profile not found"}), 404

    if request.method == "GET":
        return jsonify({"status": "success", "data": profile.to_json()})
    else:  # method = DELETE
        db.session.delete(profile)
        db.session.commit()

        return "", 204


if __name__ == "__main__":
    app.run(debug=True)
