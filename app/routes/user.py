import logging

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_current_user
from sqlalchemy import func, select

from app.utils import version_required
from app.models import db, User, Profile

logger = logging.getLogger(__name__)
routes = Blueprint("users", __name__, url_prefix="/api")


@routes.get("/users/me")
@version_required()
@jwt_required()
def me():
    try:
        user: User | None = get_current_user()
        if not user:
            return jsonify({"status": "error", "message": "user does not exist"}), 404
        return jsonify({"status": "success", "user": user.to_json()})
    except Exception as e:
        logger.error(f"Failed to load user: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@routes.get("/dashboard")
@version_required()
@jwt_required()
def dashboard():
    try:
        total_profiles = db.session.scalar(select(func.count()).select_from(Profile))

        gender_rows = db.session.execute(
            select(Profile.gender, func.count().label("count")).group_by(Profile.gender)
        ).all()
        gender_breakdown = {row.gender.value: row.count for row in gender_rows}

        age_group_rows = db.session.execute(
            select(Profile.age_group, func.count().label("count"))
            .group_by(Profile.age_group)
            .order_by(func.count().desc())
        ).all()
        age_group_breakdown = {row.age_group: row.count for row in age_group_rows}

        top_countries = db.session.execute(
            select(
                Profile.country_id,
                Profile.country_name,
                func.count().label("count"),
            )
            .group_by(Profile.country_id, Profile.country_name)
            .order_by(func.count().desc())
            .limit(10)
        ).all()
        top_countries_data = [
            {
                "country_id": row.country_id,
                "country_name": row.country_name,
                "count": row.count,
            }
            for row in top_countries
        ]

        averages = db.session.execute(
            select(
                func.avg(Profile.age).label("avg_age"),
                func.avg(Profile.gender_probability).label("avg_gender_probability"),
                func.avg(Profile.country_probability).label("avg_country_probability"),
            )
        ).one()

        recent_profiles = db.session.scalars(
            select(Profile).order_by(Profile.created_at.desc()).limit(5)
        ).all()

        return jsonify(
            {
                "status": "success",
                "dashboard": {
                    "total_profiles": total_profiles,
                    "gender_breakdown": gender_breakdown,
                    "age_group_breakdown": age_group_breakdown,
                    "top_countries": top_countries_data,
                    "averages": {
                        "age": round(averages.avg_age, 2) if averages.avg_age else None,
                        "gender_probability": (
                            round(averages.avg_gender_probability, 4)
                            if averages.avg_gender_probability
                            else None
                        ),
                        "country_probability": (
                            round(averages.avg_country_probability, 4)
                            if averages.avg_country_probability
                            else None
                        ),
                    },
                    "recent_profiles": [p.to_summary() for p in recent_profiles],
                },
            }
        )
    except Exception as e:
        logger.error(f"Failed to load dashboard: {str(e)}")
        return jsonify({"status": "error", "message": "Failed to load dashboard"}), 500
