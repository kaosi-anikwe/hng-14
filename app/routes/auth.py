import logging

from flask import Blueprint

logger = logging.getLogger(__name__)
routes = Blueprint("auth", __name__)
