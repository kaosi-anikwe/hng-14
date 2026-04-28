import logging

from app.models import db
from app import create_app
from app.utils import seed_profiles
from app.config import settings

logger = logging.getLogger(__name__)

app = create_app()

with app.app_context():
    db.create_all()
    seed_profiles("seed_profiles.json")

    logger.info("MODEL DUMP")
    logger.info(settings.model_dump())

if __name__ == "__main__":
    app.run(debug=settings.DEBUG)
