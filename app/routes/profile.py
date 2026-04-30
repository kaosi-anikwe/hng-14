import re
import io
import csv
import logging
from typing import cast, List
from datetime import datetime, timezone

import pycountry

from flask_jwt_extended import jwt_required
from sqlalchemy import asc, desc, select, and_, or_
from flask import jsonify, request, Blueprint, url_for, Response

from app.models import db, Profile, Gender
from app.utils import genderize, agify, nationalize, version_required, admin_required

logger = logging.getLogger(__name__)
routes = Blueprint("profiles", __name__, url_prefix="/api")


@routes.get("/classify")
@version_required()
@jwt_required()
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


@routes.get("/profiles")
@version_required()
@jwt_required()
def get_profiles():
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
        per_page = max(1, min(50, int(request.args.get("limit", 10))))

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
            query = query.where(Profile.gender_probability >= min_gender_probability)
        if min_country_probability:
            query = query.where(Profile.country_probability >= min_country_probability)

        sort_param = getattr(Profile, sort_by)
        order_fn = asc if order == "asc" else desc

        query = query.order_by(order_fn(sort_param))

        pagination = db.paginate(
            query, page=page, per_page=min(50, per_page), error_out=False
        )

        active_filters = {
            k: v for k, v in request.args.items() if k not in ("page", "limit")
        }

        total_pages = (
            -(-(int(pagination.total) / pagination.per_page) // 1)
            if pagination.total
            else 0
        )

        return jsonify(
            {
                "status": "success",
                "page": pagination.page,
                "limit": pagination.per_page,
                "total": pagination.total,
                "total_pages": int(total_pages),
                "links": {
                    "self": url_for(
                        "profiles.get_profiles",
                        page=pagination.page,
                        limit=pagination.per_page,
                        _external=False,
                        **active_filters,
                    ),
                    "next": (
                        url_for(
                            "profiles.get_profiles",
                            page=pagination.next_num,
                            limit=pagination.per_page,
                            _external=False,
                            **active_filters,
                        )
                        if pagination.next_num
                        else None
                    ),
                    "prev": (
                        url_for(
                            "profiles.get_profiles",
                            page=pagination.prev_num,
                            limit=pagination.per_page,
                            _external=False,
                            **active_filters,
                        )
                        if pagination.prev_num
                        else None
                    ),
                },
                "data": [
                    profile.to_json()
                    for profile in cast(List[Profile], pagination.items)
                ],
            }
        )
    except Exception as e:
        logger.error(f"Failed to get profiles: {str(e)}")
        return (
            jsonify({"status": "error", "message": "Failed to get profiles"}),
            500,
        )


@routes.post("/profiles")
@version_required()
@admin_required()
def create_profile():
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
            country_probability = float(country_result.get("country_probability", 0))
            _country = pycountry.countries.get(alpha_2=country_id)
            country_name = _country.name if _country else ""

            new_profile = Profile(
                name=name,
                gender=Gender(gender.lower()),
                gender_probability=round(gender_probability, 2),
                age=age,
                age_group=age_group,
                country_id=country_id,
                country_name=country_name,
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
        logger.error(f"Failed to create profile: {str(e)}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@routes.get("/profiles/search")
@version_required()
@jwt_required()
def search_profile():
    search_query = request.args.get("q", "").strip()
    sort_by = request.args.get(
        "sort_by", "age"
    )  # age | created_at | gender_probability
    order = request.args.get("order", "asc")  # asc | desc
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(50, int(request.args.get("limit", 10))))

    if not search_query:
        return jsonify({"status": "error", "message": "Search query is required"}), 400

    query = select(Profile)
    filters_applied = False

    # --- Gender ---
    male_match = re.search(r"\bmales?\b", search_query, re.IGNORECASE)
    female_match = re.search(r"\bfemales?\b", search_query, re.IGNORECASE)

    if male_match and not female_match:
        query = query.where(Profile.gender == Gender.MALE)
        filters_applied = True
        logger.info("Search filter applied: gender=male")
    elif female_match and not male_match:
        query = query.where(Profile.gender == Gender.FEMALE)
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
        query = query.where(Profile.age > int(above_match.group(1)))
        filters_applied = True
        logger.info("Search filter applied: age>%s", above_match.group(1))
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

    pagination = db.paginate(
        query, page=page, per_page=min(50, per_page), error_out=False
    )

    active_filters = {
        k: v for k, v in request.args.items() if k not in ("page", "limit")
    }

    total_pages = (
        -(-(int(pagination.total) / pagination.per_page) // 1)
        if pagination.total
        else 0
    )

    return jsonify(
        {
            "status": "success",
            "page": pagination.page,
            "limit": pagination.per_page,
            "total": pagination.total,
            "total_pages": int(total_pages),
            "links": {
                "self": url_for(
                    "profiles.search_profile",
                    page=pagination.page,
                    limit=pagination.per_page,
                    _external=False,
                    **active_filters,
                ),
                "next": (
                    url_for(
                        "profiles.search_profile",
                        page=pagination.next_num,
                        limit=pagination.per_page,
                        _external=False,
                        **active_filters,
                    )
                    if pagination.next_num
                    else None
                ),
                "prev": (
                    url_for(
                        "profiles.search_profile",
                        page=pagination.prev_num,
                        limit=pagination.per_page,
                        _external=False,
                        **active_filters,
                    )
                    if pagination.prev_num
                    else None
                ),
            },
            "data": [
                profile.to_json() for profile in cast(List[Profile], pagination.items)
            ],
        }
    )


@routes.get("/profiles/<string:id>")
@version_required()
@jwt_required()
def profile(id: str):
    profile: Profile | None = db.session.get(Profile, id)

    if not profile:
        return jsonify({"status": "error", "message": "profile not found"}), 404

    return jsonify({"status": "success", "data": profile.to_json()})


@routes.delete("/profiles/<string:id>")
@version_required()
@admin_required()
def delete_profile(id: str):
    profile: Profile | None = db.session.get(Profile, id)

    if not profile:
        return jsonify({"status": "error", "message": "profile not found"}), 404

    db.session.delete(profile)
    db.session.commit()

    return "", 204


@routes.get("/profiles/export")
@version_required()
@admin_required()
def export_profiles():
    try:
        export_format = request.args.get("format")

        if not export_format or export_format != "csv":
            return jsonify({"status": "error", "message": "Invalid export format"}), 400

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
            query = query.where(Profile.gender_probability >= min_gender_probability)
        if min_country_probability:
            query = query.where(Profile.country_probability >= min_country_probability)

        sort_param = getattr(Profile, sort_by)
        order_fn = asc if order == "asc" else desc

        query = query.order_by(order_fn(sort_param))

        profiles: List[Profile] = list(db.session.execute(query).scalars().all())

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "name",
                "gender",
                "gender_probability",
                "age",
                "age_group",
                "country_id",
                "country_name",
                "country_probability",
                "created_at",
            ],
        )
        writer.writeheader()
        for p in profiles:
            writer.writerow(p.to_json())

        output.seek(0)
        timestamp = datetime.now(timezone.utc).timestamp()
        return Response(
            output,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=profiles_{timestamp}.csv"
            },
        )

    except Exception as e:
        logger.error(str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
