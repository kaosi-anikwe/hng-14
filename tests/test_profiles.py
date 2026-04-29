"""
Tests for profile endpoints.

External API calls (genderize / agify / nationalize) are mocked so tests
run offline without any live HTTP traffic.
"""

from unittest.mock import patch

import pytest

MOCK_GENDER = {
    "success": True,
    "data": {"gender": "male", "gender_probability": 0.99, "sample_size": 100},
}
MOCK_AGE = {"success": True, "data": {"age": 30, "age_group": "adult"}}
MOCK_COUNTRY = {
    "success": True,
    "data": {"country_id": "US", "country_probability": 0.85},
}


# ---------------------------------------------------------------------------
# GET /api/classify
# ---------------------------------------------------------------------------


class TestClassify:
    def test_missing_name_returns_400(self, client, auth_headers):
        r = client.get("/api/classify", headers=auth_headers)
        assert r.status_code == 400
        assert r.json["status"] == "error"

    def test_empty_name_returns_400(self, client, auth_headers):
        r = client.get("/api/classify?name=", headers=auth_headers)
        assert r.status_code == 400

    def test_valid_name_returns_gender(self, client, auth_headers):
        with patch("app.routes.profile.genderize", return_value=MOCK_GENDER):
            r = client.get("/api/classify?name=james", headers=auth_headers)
        assert r.status_code == 200
        assert r.json["status"] == "success"
        assert r.json["data"]["gender"] == "male"

    def test_missing_version_header_returns_400(self, client, auth_headers):
        headers = {k: v for k, v in auth_headers.items() if k != "X-API-Version"}
        r = client.get("/api/classify?name=james", headers=headers)
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/profiles
# ---------------------------------------------------------------------------


class TestGetProfiles:
    def test_empty_db_returns_empty_list(self, client, auth_headers):
        r = client.get("/api/profiles", headers=auth_headers)
        assert r.status_code == 200
        assert r.json["status"] == "success"
        assert r.json["data"] == []
        assert r.json["total"] == 0

    def test_invalid_sort_by_returns_400(self, client, auth_headers):
        r = client.get("/api/profiles?sort_by=invalid", headers=auth_headers)
        assert r.status_code == 400

    def test_invalid_order_returns_400(self, client, auth_headers):
        r = client.get("/api/profiles?order=random", headers=auth_headers)
        assert r.status_code == 400

    def test_pagination_fields_present(self, client, auth_headers):
        r = client.get("/api/profiles", headers=auth_headers)
        assert r.status_code == 200
        for field in ("page", "limit", "total", "total_pages", "links"):
            assert field in r.json


# ---------------------------------------------------------------------------
# POST /api/profiles  (admin-only)
# ---------------------------------------------------------------------------


class TestCreateProfile:
    def test_missing_name_returns_400(self, client, app):
        # Need an admin token
        from flask_jwt_extended import create_access_token
        from app.models import db, User, Role

        with app.app_context():
            user = User(
                github_id="gh-admin-1",
                username="admin_user",
                email="admin@test.com",
                avatar_url="",
                role=Role.ADMIN,
            )
            db.session.add(user)
            db.session.commit()
            token = create_access_token(identity=user.id)

        headers = {
            "Authorization": f"Bearer {token}",
            "X-API-Version": "1",
            "Content-Type": "application/json",
        }
        r = client.post("/api/profiles", json={}, headers=headers)
        assert r.status_code == 400
        assert r.json["message"] == "name not specified"

    def test_non_admin_gets_403(self, client, auth_headers):
        r = client.post(
            "/api/profiles",
            json={"name": "james"},
            headers={**auth_headers, "Content-Type": "application/json"},
        )
        assert r.status_code == 403

    def test_creates_profile_returns_200(self, client, app):
        from flask_jwt_extended import create_access_token
        from app.models import db, User, Role

        with app.app_context():
            user = User(
                github_id="gh-admin-2",
                username="admin_user2",
                email="admin2@test.com",
                avatar_url="",
                role=Role.ADMIN,
            )
            db.session.add(user)
            db.session.commit()
            token = create_access_token(identity=user.id)

        headers = {
            "Authorization": f"Bearer {token}",
            "X-API-Version": "1",
            "Content-Type": "application/json",
        }

        with (
            patch("app.routes.profile.genderize", return_value=MOCK_GENDER),
            patch("app.routes.profile.agify", return_value=MOCK_AGE),
            patch("app.routes.profile.nationalize", return_value=MOCK_COUNTRY),
        ):
            r = client.post("/api/profiles", json={"name": "james"}, headers=headers)

        assert r.status_code == 200
        assert r.json["status"] == "success"
        data = r.json["data"]
        assert data["name"] == "james"
        assert data["gender"] == "male"
        assert data["age"] == 30
        assert data["country_id"] == "US"

    def test_duplicate_name_returns_existing(self, client, app):
        from flask_jwt_extended import create_access_token
        from app.models import db, User, Role

        with app.app_context():
            user = db.session.query(User).filter_by(username="admin_user2").first()
            token = create_access_token(identity=user.id)

        headers = {
            "Authorization": f"Bearer {token}",
            "X-API-Version": "1",
            "Content-Type": "application/json",
        }

        with (
            patch("app.routes.profile.genderize", return_value=MOCK_GENDER),
            patch("app.routes.profile.agify", return_value=MOCK_AGE),
            patch("app.routes.profile.nationalize", return_value=MOCK_COUNTRY),
        ):
            r = client.post("/api/profiles", json={"name": "james"}, headers=headers)

        assert r.status_code == 200
        assert r.json["message"] == "Profile already exists"


# ---------------------------------------------------------------------------
# GET /api/profiles/<id>
# ---------------------------------------------------------------------------


class TestGetProfile:
    def test_missing_profile_returns_404(self, client, auth_headers):
        r = client.get("/api/profiles/nonexistent-id", headers=auth_headers)
        assert r.status_code == 404
        assert r.json["status"] == "error"


# ---------------------------------------------------------------------------
# DELETE /api/profiles/<id>
# ---------------------------------------------------------------------------


class TestDeleteProfile:
    def test_non_admin_gets_403(self, client, auth_headers):
        r = client.delete("/api/profiles/some-id", headers=auth_headers)
        assert r.status_code == 403

    def test_missing_profile_returns_404(self, client, app):
        from flask_jwt_extended import create_access_token
        from app.models import db, User

        with app.app_context():
            user = db.session.query(User).filter_by(username="admin_user2").first()
            token = create_access_token(identity=user.id)

        headers = {"Authorization": f"Bearer {token}", "X-API-Version": "1"}
        r = client.delete("/api/profiles/nonexistent-id", headers=headers)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/profiles/search
# ---------------------------------------------------------------------------


class TestSearchProfiles:
    def test_missing_query_returns_400(self, client, auth_headers):
        r = client.get("/api/profiles/search", headers=auth_headers)
        assert r.status_code == 400

    def test_uninterpretable_query_returns_400(self, client, auth_headers):
        r = client.get("/api/profiles/search?q=xyzzy+foo+bar", headers=auth_headers)
        assert r.status_code == 400
        assert r.json["message"] == "Unable to interpret query"

    def test_valid_query_returns_results(self, client, auth_headers):
        r = client.get("/api/profiles/search?q=adult+males", headers=auth_headers)
        assert r.status_code == 200
        assert r.json["status"] == "success"
