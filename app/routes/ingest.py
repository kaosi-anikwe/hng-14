import logging

import pycountry
import polars as pl
from sqlalchemy import select, insert
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.utils import version_required
from app.models import db, Profile

logger = logging.getLogger(__name__)
routes = Blueprint("ingest", __name__, url_prefix="/api")


@routes.post("/upload")
@version_required()
@jwt_required()
def upload_csv():
    """Stream and process CSV files
    A file may have up to 500,000 rows
    Validate and return stats of process
    """
    # Get required columns
    REQUIRED_COLUMNS = set(
        str(col.name).lower()
        for col in Profile.__table__.columns
        if not col.nullable and col.default is None and col.server_default is None
    )

    # Stream the CSV in batches
    lf = pl.scan_csv(request.stream)

    # Check requried columns
    actual_cols = lf.collect_schema().names()

    if not all(col in actual_cols for col in REQUIRED_COLUMNS):
        missing = REQUIRED_COLUMNS - set(actual_cols)
        logger.warning("Upload rejected: missing headers %s", missing)
        return {
            "status": "error",
            "message": f"Upload is missing required headers: {missing}",
        }, 400

    logger.info("CSV schema OK. Starting batch processing (chunk_size=50,000)")

    # Error counters
    error_counts = {
        "duplicate_name": 0,
        "invalid_age": 0,
        "missing_fields": 0,
        "invalid_countries": 0,
    }
    stats = {"total_rows": 0, "inserted": 0, "skipped": 0}
    VALID_COUNTRY_CODES = {country.alpha_2 for country in pycountry.countries}
    PROFILE_COLS = {col.name for col in Profile.__table__.columns}

    # Get all existing names from db
    existing_names = set(db.session.execute(select(Profile.name)).scalars())
    logger.debug("Loaded %d existing names from DB", len(existing_names))

    batch_num = 0
    for batch in lf.collect_batches(chunk_size=50_000):
        batch_num += 1
        try:
            # Count rows
            stats["total_rows"] += batch.height
            logger.debug("Batch %d: %d rows", batch_num, batch.height)

            # Create a mask: True if ANY required column is null in that row
            is_missing = pl.any_horizontal(
                pl.col(REQUIRED_COLUMNS).is_null()
            )  # TODO: check on lower case col names

            # Count and filter out columns with missing columns
            missing_count = batch.filter(is_missing).height
            error_counts["missing_fields"] += missing_count
            stats["skipped"] += missing_count
            if missing_count:
                logger.debug(
                    "Batch %d: %d rows skipped (missing fields)",
                    batch_num,
                    missing_count,
                )

            # Keep only rows where EVERY required field is present
            clean_batch = batch.filter(~is_missing)

            # Check for duplicate names in CSV
            is_csv_dup = clean_batch.select(pl.col("name")).is_duplicated()
            csv_dups = clean_batch.filter(is_csv_dup)
            error_counts["duplicate_name"] += csv_dups.height
            stats["skipped"] += csv_dups.height
            if csv_dups.height:
                logger.debug(
                    "Batch %d: %d rows skipped (duplicate in CSV)",
                    batch_num,
                    csv_dups.height,
                )

            # Check for duplicates names in DB
            is_in_db = clean_batch["name"].is_in(existing_names)
            db_dups = clean_batch.filter(is_in_db & ~is_csv_dup)
            error_counts["duplicate_name"] += db_dups.height
            stats["skipped"] += db_dups.height
            if db_dups.height:
                logger.debug(
                    "Batch %d: %d rows skipped (duplicate in DB)",
                    batch_num,
                    db_dups.height,
                )

            # Check for invalid age
            is_invalid_age = clean_batch["age"].is_between(0, 120, closed="both").not_()
            invalid_age = clean_batch.filter(is_invalid_age)
            error_counts["invalid_age"] += invalid_age.height
            stats["skipped"] += invalid_age.height
            if invalid_age.height:
                logger.debug(
                    "Batch %d: %d rows skipped (invalid age)",
                    batch_num,
                    invalid_age.height,
                )

            # Check for invalid countries
            is_invalid_country = ~clean_batch["country_id"].is_in(VALID_COUNTRY_CODES)
            invalid_country = clean_batch.filter(is_invalid_country)
            error_counts["invalid_countries"] += invalid_country.height
            stats["skipped"] += invalid_country.height
            if invalid_country.height:
                logger.debug(
                    "Batch %d: %d rows skipped (invalid country)",
                    batch_num,
                    invalid_country.height,
                )

            # Final filter: Keep only valid rows
            valid_rows = clean_batch.filter(
                ~is_csv_dup & ~is_in_db & ~is_invalid_age & ~is_invalid_country
            )

            # Batch insert
            if len(valid_rows) > 0:
                insert_cols = [c for c in valid_rows.columns if c in PROFILE_COLS]
                records = valid_rows.select(insert_cols).iter_rows(named=True)
                db.session.execute(insert(Profile), list(records))
                db.session.commit()

                # Update our set so the next batch knows these names are now "taken"
                existing_names.update(valid_rows["name"].to_list())
                stats["inserted"] += valid_rows.height
                logger.debug("Batch %d: inserted %d rows", batch_num, valid_rows.height)
            else:
                logger.debug("Batch %d: no valid rows to insert", batch_num)

        except Exception as e:
            db.session.rollback()
            logger.error(
                "Batch %d failed, skipping %d rows: %s", batch_num, batch.height, e
            )
            stats["skipped"] += batch.height

    logger.info(
        "Upload complete: %d total, %d inserted, %d skipped | errors: %s",
        stats["total_rows"],
        stats["inserted"],
        stats["skipped"],
        error_counts,
    )
    return jsonify({"status": "success", **stats, "reasons": {**error_counts}})
