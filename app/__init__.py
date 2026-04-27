import logging
from flask import Flask
from flask_cors import CORS
from logging.handlers import RotatingFileHandler

from app.models import db
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


def create_app() -> Flask:
    app = Flask(__name__)

    app.config.from_mapping(settings.model_dump())
    CORS(app, origins="*")

    db.init_app(app)

    from app.routes.auth import routes as auth_bp
    from app.routes.profile import routes as profile_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)

    return app
