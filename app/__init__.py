import logging

import redis
from flask_cors import CORS
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from logging.handlers import RotatingFileHandler

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

    logger.debug("MODEL DUMP")
    logger.debug(settings.model_dump())
    
    app.config.from_mapping(settings.model_dump())
    CORS(app, origins="*")

    db.init_app(app)
    jwt.init_app(app)

    from app.routes.auth import routes as auth_bp
    from app.routes.profile import routes as profile_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)

    return app
