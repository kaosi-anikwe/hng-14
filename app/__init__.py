import time
import logging
import urllib.parse

import redis
from flask_cors import CORS
from flask_limiter import Limiter
from flask import Flask, g, jsonify, request
from logging.handlers import RotatingFileHandler
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager, decode_token

from app.models import db, User
from app.config import settings

# --- Logging setup ---
logging_level = logging.DEBUG if settings.DEBUG else logging.INFO

logger = logging.getLogger()  # root logger — all module loggers propagate here
logger.setLevel(logging_level)

_stream_handler = logging.StreamHandler()
_stream_handler.setLevel(logging_level)

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
_stream_handler.setFormatter(_formatter)
logger.addHandler(_stream_handler)

if settings.LOG_FILE:
    _file_handler = RotatingFileHandler(
        settings.LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=5
    )
    _file_handler.setLevel(logging_level)
    _file_handler.setFormatter(_formatter)
    logger.addHandler(_file_handler)
# ---------------------


# --- Redis URL helper ---
def _redis_url(db_index: int = 0) -> str:
    username = urllib.parse.quote(settings.REDIS_USERNAME or "", safe="")
    password = urllib.parse.quote(settings.REDIS_PASSWORD or "", safe="")
    return f"redis://{username}:{password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{db_index}"


# ---------------------


# --- Redis client ---
jwt_redis_blocklist = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    username=settings.REDIS_USERNAME,
    password=settings.REDIS_PASSWORD,
    db=0,
    decode_responses=True,
)
# ---------------------


# --- Rate limiter ---
def _rate_limit_key() -> str:
    """Use JWT identity for authenticated requests, fall back to remote IP."""
    try:
        token = request.cookies.get("access_token_cookie")
        if token:
            data = decode_token(token, allow_expired=False)
            sub = data.get("sub")
            if sub:
                return f"user:{sub}"
    except Exception:
        pass
    return f"ip:{get_remote_address()}"


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["60 per minute"],
    storage_uri=_redis_url(db_index=1),
)
# ---------------------


# --- JWT setup ---
jwt = JWTManager()


@jwt.expired_token_loader
def expired_token(jwt_header, jwt_paylod):
    return jsonify({"status": "error", "message": "Your session has expired"}), 401


@jwt.unauthorized_loader
def unauthorized(error: str):
    return jsonify({"status": "error", "message": error}), 401


@jwt.invalid_token_loader
def invalid_token(error: str):
    return jsonify({"status": "error", "message": error}), 422


@jwt.user_lookup_loader
def user_lookup_callback(jwt_header, jwt_data: dict[str, str]):
    # identity is typically stored in the 'sub' (subject) claim
    user_id = jwt_data["sub"]
    # Query your database
    return db.session.get(User, user_id)


@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token_in_redis = jwt_redis_blocklist.get(f"blacklist:{jti}")
    return token_in_redis is not None  # Returns True if revoked


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify({"status": "error", "message": "Token has been revoked"}), 401


# ---------------------


def create_app() -> Flask:
    app = Flask(__name__)

    app.config.from_mapping(settings.model_dump())

    request_logger = logging.getLogger("request")

    @app.before_request
    def _start_timer():
        g._start_time = time.perf_counter()

    @app.after_request
    def _log_request(response):
        elapsed_ms = (time.perf_counter() - g._start_time) * 1000
        request_logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return (
            jsonify(
                {"status": "error", "message": "Too many requests. Please slow down."}
            ),
            429,
        )

    CORS(
        app,
        supports_credentials=True,
        origins=[settings.FRONTEND_URL, "http://127.0.0.1:5173"],
        allow_headers=["Content-Type", "X-API-Version"],
    )

    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    from app.routes.auth import routes as auth_bp
    from app.routes.profile import routes as profile_bp
    from app.routes.user import routes as user_bp

    # Auth endpoints are unauthenticated — key by IP, stricter limit
    limiter.limit("10 per minute", key_func=get_remote_address)(auth_bp)

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(user_bp)

    return app
