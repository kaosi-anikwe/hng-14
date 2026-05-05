import re
import io
import csv
import math
import hashlib
import logging
from datetime import datetime, timezone

import pycountry

from flask_jwt_extended import jwt_required
from sqlalchemy import asc, desc, select, and_, or_, func
from flask import jsonify, request, Blueprint, url_for, Response

from app.models import db, Profile, Gender
from app.utils import genderize, agify, nationalize, version_required, admin_required
from app.cache import (
    cache_redis,
    cache_dumps,
    cache_loads,
    cache_get,
    cache_invalidate_profiles,
    SEARCH_CACHE_TTL,
    COUNT_CACHE_TTL,
)

logger = logging.getLogger(__name__)
routes = Blueprint("profiles", __name__, url_prefix="/api")

# Demonym → lowercase country name (as stored by pycountry)
DEMONYMS: dict[str, str] = {
    "afghan": "afghanistan",
    "albanian": "albania",
    "algerian": "algeria",
    "american": "united states of america",
    "angolan": "angola",
    "argentinian": "argentina",
    "argentine": "argentina",
    "armenian": "armenia",
    "australian": "australia",
    "austrian": "austria",
    "azerbaijani": "azerbaijan",
    "bangladeshi": "bangladesh",
    "belarusian": "belarus",
    "belgian": "belgium",
    "bolivian": "bolivia",
    "bosnian": "bosnia and herzegovina",
    "brazilian": "brazil",
    "british": "united kingdom",
    "bulgarian": "bulgaria",
    "cambodian": "cambodia",
    "cameroonian": "cameroon",
    "canadian": "canada",
    "chilean": "chile",
    "chinese": "china",
    "colombian": "colombia",
    "congolese": "congo",
    "croatian": "croatia",
    "cuban": "cuba",
    "czech": "czechia",
    "danish": "denmark",
    "dutch": "netherlands",
    "ecuadorian": "ecuador",
    "egyptian": "egypt",
    "emirati": "united arab emirates",
    "eritrean": "eritrea",
    "ethiopian": "ethiopia",
    "finnish": "finland",
    "french": "france",
    "georgian": "georgia",
    "german": "germany",
    "ghanaian": "ghana",
    "greek": "greece",
    "guatemalan": "guatemala",
    "guinean": "guinea",
    "haitian": "haiti",
    "honduran": "honduras",
    "hungarian": "hungary",
    "indian": "india",
    "indonesian": "indonesia",
    "iranian": "iran",
    "iraqi": "iraq",
    "irish": "ireland",
    "israeli": "israel",
    "italian": "italy",
    "ivorian": "côte d'ivoire",
    "jamaican": "jamaica",
    "japanese": "japan",
    "jordanian": "jordan",
    "kazakh": "kazakhstan",
    "kenyan": "kenya",
    "kuwaiti": "kuwait",
    "lebanese": "lebanon",
    "libyan": "libya",
    "malian": "mali",
    "mexican": "mexico",
    "moroccan": "morocco",
    "mozambican": "mozambique",
    "namibian": "namibia",
    "nepalese": "nepal",
    "nepali": "nepal",
    "nicaraguan": "nicaragua",
    "nigerian": "nigeria",
    "nigerien": "niger",
    "norwegian": "norway",
    "omani": "oman",
    "pakistani": "pakistan",
    "panamanian": "panama",
    "peruvian": "peru",
    "filipino": "philippines",
    "philippine": "philippines",
    "polish": "poland",
    "portuguese": "portugal",
    "qatari": "qatar",
    "romanian": "romania",
    "russian": "russian federation",
    "rwandan": "rwanda",
    "saudi": "saudi arabia",
    "senegalese": "senegal",
    "serbian": "serbia",
    "singaporean": "singapore",
    "somali": "somalia",
    "south african": "south africa",
    "south korean": "korea, republic of",
    "spanish": "spain",
    "sri lankan": "sri lanka",
    "sudanese": "sudan",
    "swedish": "sweden",
    "swiss": "switzerland",
    "syrian": "syrian arab republic",
    "taiwanese": "taiwan",
    "tanzanian": "tanzania",
    "thai": "thailand",
    "tunisian": "tunisia",
    "turkish": "türkiye",
    "ugandan": "uganda",
    "ukrainian": "ukraine",
    "uruguayan": "uruguay",
    "venezuelan": "venezuela",
    "vietnamese": "viet nam",
    "yemeni": "yemen",
    "zambian": "zambia",
    "zimbabwean": "zimbabwe",
}
# Build a single regex from all demonym keys; longest first to avoid partial matches
_DEMONYM_RE = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in sorted(DEMONYMS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

# Columns fetched for list/search endpoints.
_PROFILE_COLS = (
    Profile.id,
    Profile.name,
    Profile.gender,
    Profile.gender_probability,
    Profile.age,
    Profile.age_group,
    Profile.country_id,
    Profile.country_name,
    Profile.country_probability,
    Profile.created_at,
)


def _profile_row_to_dict(row) -> dict:
    """Serialise a RowMapping returned by select(*_PROFILE_COLS).mappings()."""
    gender = row["gender"]
    created_at = row["created_at"]
    return {
        "id": row["id"],
        "name": row["name"],
        # gender may be a Gender enum instance or a plain string depending on dialect
        "gender": gender.value if hasattr(gender, "value") else gender,
        "gender_probability": row["gender_probability"],
        "age": row["age"],
        "age_group": row["age_group"],
        "country_id": row["country_id"],
        "country_name": row["country_name"],
        "country_probability": row["country_probability"],
        "created_at": (
            created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
        ),
    }


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

        # --- Cache check ---
        cache_key = (
            "profiles:"
            + hashlib.sha256(
                cache_dumps(
                    {
                        "gender": gender,
                        "age_group": age_group,
                        "country_id": country_id,
                        "min_age": min_age,
                        "max_age": max_age,
                        "min_gender_probability": min_gender_probability,
                        "min_country_probability": min_country_probability,
                        "sort_by": sort_by,
                        "order": order,
                        "page": page,
                        "per_page": per_page,
                    }
                )
            ).hexdigest()
        )

        cached = cache_get(cache_key)
        if cached:
            logger.debug("Cache hit: %s", cache_key[:16])
            return Response(response=cached, mimetype="application/json", status=200)

        # Build WHERE conditions as a list so the same clauses can be reused
        # for both the data query and the count query without duplication.
        where_clauses = []
        if gender:
            where_clauses.append(Profile.gender == Gender(gender.lower()))
        if age_group:
            where_clauses.append(Profile.age_group == age_group)
        if country_id:
            where_clauses.append(Profile.country_id == country_id)
        if min_age:
            where_clauses.append(Profile.age >= int(min_age))
        if max_age:
            where_clauses.append(Profile.age <= int(max_age))
        if min_gender_probability:
            where_clauses.append(
                Profile.gender_probability >= float(min_gender_probability)
            )
        if min_country_probability:
            where_clauses.append(
                Profile.country_probability >= float(min_country_probability)
            )

        # --- Count (cached separately with a longer TTL) ---
        # The total row count depends only on filters, not on page/per_page,
        # so it can be cached independently and reused across every page of
        # the same filtered query — avoiding a repeated COUNT(*) on 500k rows.
        count_cache_key = (
            "count:profiles:"
            + hashlib.sha256(
                cache_dumps(
                    {
                        "gender": gender,
                        "age_group": age_group,
                        "country_id": country_id,
                        "min_age": min_age,
                        "max_age": max_age,
                        "min_gender_probability": min_gender_probability,
                        "min_country_probability": min_country_probability,
                    }
                )
            ).hexdigest()
        )
        cached_count = cache_get(count_cache_key)
        if cached_count is not None:
            total: int = cache_loads(cached_count)  # type: ignore[assignment]
        else:
            count_stmt = select(func.count(Profile.id))
            if where_clauses:
                count_stmt = count_stmt.where(and_(*where_clauses))
            total = db.session.scalar(count_stmt) or 0
            cache_redis.setex(count_cache_key, COUNT_CACHE_TTL, cache_dumps(total))

        # Fetch page data using manual LIMIT/OFFSET + .mappings().
        # db.paginate() calls .scalars() internally; on a multi-column select
        # that returns only the first column (the id strings), causing the
        # 'str has no attribute id' error. Executing directly avoids this.
        sort_param = getattr(Profile, sort_by)
        order_fn = asc if order == "asc" else desc

        data_query = select(*_PROFILE_COLS).order_by(order_fn(sort_param))
        if where_clauses:
            data_query = (
                select(*_PROFILE_COLS)
                .where(and_(*where_clauses))
                .order_by(order_fn(sort_param))
            )
        offset = (page - 1) * per_page
        rows = (
            db.session.execute(data_query.limit(per_page).offset(offset))
            .mappings()
            .all()
        )

        active_filters = {
            k: v for k, v in request.args.items() if k not in ("page", "limit")
        }

        total_pages = math.ceil(total / per_page) if total else 0
        next_num = page + 1 if page * per_page < total else None
        prev_num = page - 1 if page > 1 else None

        result = {
            "status": "success",
            "page": page,
            "limit": per_page,
            "total": total,
            "total_pages": total_pages,
            "links": {
                "self": url_for(
                    "profiles.get_profiles",
                    page=page,
                    limit=per_page,
                    _external=False,
                    **active_filters,
                ),
                "next": (
                    url_for(
                        "profiles.get_profiles",
                        page=next_num,
                        limit=per_page,
                        _external=False,
                        **active_filters,
                    )
                    if next_num
                    else None
                ),
                "prev": (
                    url_for(
                        "profiles.get_profiles",
                        page=prev_num,
                        limit=per_page,
                        _external=False,
                        **active_filters,
                    )
                    if prev_num
                    else None
                ),
            },
            "data": [_profile_row_to_dict(row) for row in rows],
        }

        payload = cache_dumps(result)
        cache_redis.setex(cache_key, SEARCH_CACHE_TTL, payload)
        logger.debug("Cached profiles result: %s", cache_key[:16])
        return Response(response=payload, mimetype="application/json", status=200)
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

        existing_profile: Profile | None = db.session.scalar(
            select(Profile).where(Profile.name == name)
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

            # A new profile changes counts and may change page results —
            # flush all cached list/search pages so stale data isn't served.
            cache_invalidate_profiles()

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

    query = select(*_PROFILE_COLS)
    filters_applied = False
    # Canonical filter dict — normalised representation used for cache keying.
    # Two queries with different phrasing but identical filters produce the same canon.
    canon: dict = {
        "gender": None,
        "country_name": None,
        "age_gte": None,  # inclusive lower bound (from "between")
        "age_lte": None,  # inclusive upper bound (from "between")
        "age_gt": None,  # exclusive lower bound (from "above")
        "age_lt": None,  # exclusive upper bound (from "below")
        "age_groups": [],
    }

    # --- Gender ---
    # Matches: male/males, man/men, guy/guys, boy/boys
    male_match = re.search(
        r"\b(males?|m[ae]n|guys?|boys?)\b", search_query, re.IGNORECASE
    )
    # Matches: female/females, woman/women, girl/girls
    female_match = re.search(
        r"\b(females?|wom[ae]n|girls?)\b", search_query, re.IGNORECASE
    )

    if male_match and not female_match:
        query = query.where(Profile.gender == Gender.MALE)
        filters_applied = True
        canon["gender"] = "male"
        logger.info("Search filter applied: gender=male")
    elif female_match and not male_match:
        query = query.where(Profile.gender == Gender.FEMALE)
        filters_applied = True
        canon["gender"] = "female"
        logger.info("Search filter applied: gender=female")
    elif male_match and female_match:
        # Both mentioned — no gender restriction, but it's still interpretable
        filters_applied = True
        canon["gender"] = "any"
        logger.info("Search filter applied: gender=male+female (no restriction)")

    # --- Country ---
    # Priority: 1) demonym adjective, 2) "from <name>", 3) "living in / in <name>"
    _STOP = r"(?=\s+(?:above|below|aged?|between|who|and|with)|[.,!]|$)"
    country_name: str | None = None

    demonym_match = _DEMONYM_RE.search(search_query)
    if demonym_match:
        country_name = DEMONYMS[demonym_match.group(1).lower()]

    if not country_name:
        from_match = re.search(
            r"\bfrom\s+([a-z]+(?:\s+[a-z]+)*?)" + _STOP,
            search_query,
            re.IGNORECASE,
        )
        if from_match:
            country_name = from_match.group(1).strip().lower()

    if not country_name:
        in_match = re.search(
            r"\b(?:living\s+in|in)\s+([a-z]+(?:\s+[a-z]+)*?)" + _STOP,
            search_query,
            re.IGNORECASE,
        )
        if in_match:
            country_name = in_match.group(1).strip().lower()

    if country_name:
        query = query.where(db.func.lower(Profile.country_name) == country_name)
        filters_applied = True
        canon["country_name"] = country_name
        logger.info("Search filter applied: country_name=%s", country_name)

    # --- Age (range / above / below) ---
    # Matches: "between ages 20 and 45", "between 20 and 45",
    #          "aged 20-45", "aged 20–45", "age 20 to 45"
    between_match = re.search(
        r"\b(?:between\s+(?:ages?\s+)?|ages?\s+)(\d{1,3})\s*(?:and|to|[-\u2013\u2014])\s*(\d{1,3})\b",
        search_query,
        re.IGNORECASE,
    )
    above_match = re.search(r"\babove\s+(\d{1,3})\b", search_query, re.IGNORECASE)
    below_match = re.search(r"\bbelow\s+(\d{1,3})\b", search_query, re.IGNORECASE)

    if between_match:
        lo, hi = sorted([int(between_match.group(1)), int(between_match.group(2))])
        query = query.where(Profile.age >= lo).where(Profile.age <= hi)
        filters_applied = True
        canon["age_gte"] = lo
        canon["age_lte"] = hi
        logger.info("Search filter applied: age=%d-%d", lo, hi)
    else:
        if above_match:
            val = int(above_match.group(1))
            query = query.where(Profile.age > val)
            filters_applied = True
            canon["age_gt"] = val
            logger.info("Search filter applied: age>%s", val)
        if below_match:
            val = int(below_match.group(1))
            query = query.where(Profile.age < val)
            filters_applied = True
            canon["age_lt"] = val
            logger.info("Search filter applied: age<%s", val)

    # --- Age group keywords ---
    age_pattern = r"\b(children|child|teenagers?|adults?|seniors?|young)\b"
    found_categories = set(re.findall(age_pattern, search_query, re.IGNORECASE))

    age_group_conditions = []
    age_group_strs: list[str] = []
    for match in found_categories:
        ag = match.lower()
        if ag.endswith("s") and ag != "children":
            ag = ag[:-1]
        if ag == "children":
            ag = "child"

        if ag in ["child", "teenager", "adult", "senior"]:
            age_group_conditions.append(Profile.age_group == ag)
            age_group_strs.append(ag)
            filters_applied = True
            logger.info("Search filter applied: age_group=%s", ag)
        elif ag == "young":
            query = query.where(and_(Profile.age >= 16, Profile.age <= 24))
            age_group_strs.append("young")
            filters_applied = True
            logger.info("Search filter applied: age=16-24 (young)")

    canon["age_groups"] = sorted(age_group_strs)

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

    # --- Cache check ---
    # Build canonical key from extracted filters + pagination params.
    cache_key = (
        "search:"
        + hashlib.sha256(
            cache_dumps(
                {
                    **canon,
                    "sort_by": sort_by,
                    "order": order,
                    "page": page,
                    "per_page": per_page,
                }
            )
        ).hexdigest()
    )

    cached = cache_get(cache_key)
    if cached:
        logger.debug("Cache hit: %s", cache_key[:16])
        return Response(response=cached, mimetype="application/json", status=200)

    # --- Count (cached separately — count depends on filters only, not page/sort) ---
    # `query` at this point is the fully-filtered select with no ORDER BY, so
    # with_only_columns(count()) gives an exact COUNT without duplicating WHERE clauses.
    count_cache_key_search = (
        "count:search:" + hashlib.sha256(cache_dumps(canon)).hexdigest()
    )
    cached_count = cache_get(count_cache_key_search)
    if cached_count is not None:
        total: int = cache_loads(cached_count)  # type: ignore[assignment]
    else:
        count_stmt = query.with_only_columns(func.count()).order_by(None)
        total = db.session.scalar(count_stmt) or 0
        cache_redis.setex(count_cache_key_search, COUNT_CACHE_TTL, cache_dumps(total))

    # --- Execute data query ---
    sort_param = getattr(Profile, sort_by)
    order_fn = asc if order == "asc" else desc

    data_query = query.order_by(order_fn(sort_param))
    offset = (page - 1) * per_page
    rows = (
        db.session.execute(data_query.limit(per_page).offset(offset)).mappings().all()
    )

    active_filters = {
        k: v for k, v in request.args.items() if k not in ("page", "limit")
    }

    total_pages = math.ceil(total / per_page) if total else 0
    next_num = page + 1 if page * per_page < total else None
    prev_num = page - 1 if page > 1 else None

    result = {
        "status": "success",
        "page": page,
        "limit": per_page,
        "total": total,
        "total_pages": total_pages,
        "links": {
            "self": url_for(
                "profiles.search_profile",
                page=page,
                limit=per_page,
                _external=False,
                **active_filters,
            ),
            "next": (
                url_for(
                    "profiles.search_profile",
                    page=next_num,
                    limit=per_page,
                    _external=False,
                    **active_filters,
                )
                if next_num
                else None
            ),
            "prev": (
                url_for(
                    "profiles.search_profile",
                    page=prev_num,
                    limit=per_page,
                    _external=False,
                    **active_filters,
                )
                if prev_num
                else None
            ),
        },
        "data": [_profile_row_to_dict(row) for row in rows],
    }

    payload = cache_dumps(result)
    cache_redis.setex(cache_key, SEARCH_CACHE_TTL, payload)
    logger.debug("Cached search result: %s", cache_key[:16])
    return Response(response=payload, mimetype="application/json", status=200)


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
    cache_invalidate_profiles()

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

        profiles: list[Profile] = list(db.session.execute(query).scalars().all())

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
