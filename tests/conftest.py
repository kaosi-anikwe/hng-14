"""
Shared pytest fixtures.

The test app:
 - uses an in-memory SQLite database (no file created)
 - disables Flask-Limiter (RATELIMIT_ENABLED=False) via config_overrides,
   which is applied BEFORE limiter.init_app(app) inside create_app()
 - replaces the module-level Redis clients with MagicMock stubs so no
   live Redis connection is required
"""

import pytest
from unittest.mock import MagicMock, patch
from flask_jwt_extended import create_access_token

_fake_redis = MagicMock()
_fake_redis.get.return_value = None  # tokens are never in the blocklist

_TEST_CONFIG = {
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "JWT_COOKIE_SECURE": False,
    "SECRET_KEY": "test-secret-key-for-pytest-use-only",
    "JWT_SECRET_KEY": "test-jwt-secret-key-for-pytest-use-only",
    # Disable rate limiting — applied before limiter.init_app() inside create_app()
    "RATELIMIT_ENABLED": False,
    "RATELIMIT_STORAGE_URI": "memory://",
    # Tests use Authorization: Bearer headers instead of cookies
    "JWT_TOKEN_LOCATION": ["headers"],
}


@pytest.fixture(scope="session")
def app():
    from app import create_app
    from app.models import db

    test_app = create_app(config_overrides=_TEST_CONFIG)

    # Patch module-level Redis clients so no live connection is attempted.
    # Patch both where defined (app.__init__) and where imported (auth route).
    with (
        patch("app.jwt_redis_blocklist", _fake_redis),
        patch("app.routes.auth.jwt_redis_blocklist", _fake_redis),
    ):
        with test_app.app_context():
            db.create_all()
            yield test_app
            db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    """Authorization headers for a default (analyst) user.
    Creates a real User row so user_lookup_loader returns a valid object.
    """
    from app.models import db, User, Role

    with app.app_context():
        user = db.session.query(User).filter_by(github_id="gh-analyst-fixture").first()
        if not user:
            user = User(
                github_id="gh-analyst-fixture",
                username="analyst_fixture",
                email="analyst@fixture.test",
                avatar_url="",
                role=Role.ANALYST,
            )
            db.session.add(user)
            db.session.commit()
            db.session.refresh(user)
        token = create_access_token(identity=user.id)
    return {"Authorization": f"Bearer {token}", "X-API-Version": "1"}


@pytest.fixture
def api_headers():
    """Version header only — no auth."""
    return {"X-API-Version": "1"}
