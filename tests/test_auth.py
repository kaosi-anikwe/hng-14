"""
Tests for auth endpoints.

OAuth flows that require a live GitHub redirect are tested at the unit level
(correct redirect URL, correct state/PKCE storage). The full OAuth token
exchange is not tested here as it requires a live GitHub environment.
"""

import pytest

# ---------------------------------------------------------------------------
# GET /auth/github
# ---------------------------------------------------------------------------


class TestGithubRedirect:
    def test_redirects_to_github(self, client):
        r = client.get("/auth/github")
        assert r.status_code == 302
        location = r.headers["Location"]
        assert "github.com/login/oauth/authorize" in location

    def test_redirect_includes_client_id(self, client, app):
        from app.config import settings

        r = client.get("/auth/github")
        assert settings.GITHUB_CLIENT_ID in r.headers["Location"]

    def test_redirect_includes_pkce_challenge(self, client):
        r = client.get("/auth/github")
        assert "code_challenge=" in r.headers["Location"]
        assert "code_challenge_method=S256" in r.headers["Location"]

    def test_state_stored_in_session(self, client):
        with client.session_transaction() as sess:
            sess.clear()

        client.get("/auth/github")

        with client.session_transaction() as sess:
            assert "oauth_state" in sess
            assert "code_verifier" in sess


# ---------------------------------------------------------------------------
# POST /auth/cli/callback
# ---------------------------------------------------------------------------


class TestCliCallback:
    def test_missing_code_returns_400(self, client):
        r = client.post("/auth/cli/callback", json={"code_verifier": "abc"})
        assert r.status_code == 400
        assert r.json["status"] == "error"

    def test_missing_verifier_returns_400(self, client):
        r = client.post("/auth/cli/callback", json={"code": "abc"})
        assert r.status_code == 400
        assert r.json["status"] == "error"

    def test_missing_both_returns_400(self, client):
        r = client.post("/auth/cli/callback", json={})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_no_token_returns_401(self, client):
        r = client.post("/auth/refresh")
        assert r.status_code == 401

    def test_access_token_rejected(self, client, app):
        """Refresh endpoint rejects access tokens (wrong type): sends access token
        in the JSON body under the refresh_token key → 422."""
        from flask_jwt_extended import create_access_token

        with app.app_context():
            token = create_access_token(identity="user-1")

        r = client.post(
            "/auth/refresh",
            json={"refresh_token": token},
        )
        assert r.status_code == 422  # invalid token type


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_no_token_returns_401(self, client):
        r = client.post("/auth/logout")
        assert r.status_code == 401

    def test_valid_token_returns_200(self, client, app):
        from flask_jwt_extended import create_access_token
        from app.models import db, User, Role

        with app.app_context():
            user = db.session.query(User).filter_by(github_id="gh-logout-test").first()
            if not user:
                user = User(
                    github_id="gh-logout-test",
                    username="logout_test_user",
                    email="logout@test.com",
                    avatar_url="",
                    role=Role.ANALYST,
                )
                db.session.add(user)
                db.session.commit()
                db.session.refresh(user)
            token = create_access_token(identity=user.id)

        r = client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json["status"] == "success"
