import os
from flask_cors import CORS
from flask import Flask, jsonify, request

from models import db, Profile, Gender
from utils import genderize, agify, nationalize

app = Flask(__name__)
CORS(app, origins="*")

_turso_url = os.environ.get("TURSO_DATABASE_URL", "")
_turso_token = os.environ.get("TURSO_AUTH_TOKEN", "")

if _turso_url and _turso_token:
    import libsql_experimental as libsql

    def _libsql_creator():
        return libsql.connect(database="", sync_url=_turso_url, auth_token=_turso_token)

    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite+pysqlite://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"creator": _libsql_creator}
else:
    _db_path = os.path.join(os.path.dirname(__file__), "profile.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{_db_path}"

db.init_app(app)

with app.app_context():
    db.create_all()


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
            country_id = request.args.get("country_id")
            age_group = request.args.get("age_group")

            query = db.session.query(Profile)

            if country_id:
                query = query.filter(Profile.country_id == country_id)
            if age_group:
                query = query.filter(Profile.age_group == age_group)

            all_profiles = query.all()

            return jsonify(
                {
                    "status": "success",
                    "count": len(all_profiles),
                    "data": [profile.to_summary() for profile in all_profiles],
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
                sample_size = int(gender_result.get("sample_size", 0))
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
                    sample_size=sample_size,
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
