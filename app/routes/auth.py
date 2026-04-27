import logging
import secrets
from typing import List
from datetime import datetime, timezone

import requests
from requests import Request
from sqlalchemy.exc import IntegrityError
from flask import Blueprint, redirect, jsonify, session, request
from flask_jwt_extended import (
    get_jwt,
    jwt_required,
    get_current_user,
    get_jwt_identity,
    create_access_token,
    create_refresh_token,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from app.config import settings
from app.models import db, User
from app import jwt_redis_blocklist
from app.utils import generate_pkce

logger = logging.getLogger(__name__)
routes = Blueprint("auth", __name__, url_prefix="/auth")


@routes.get("/github")
def github_redirect():
    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce()

    # Store state and verifier in the encrypted session cookie
    session["oauth_state"] = state
    session["code_verifier"] = code_verifier

    url = "https://github.com/login/oauth/authorize"
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.REDIRECT_URI,
        "scope": "user:email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    req = Request("GET", url=url, params=params)
    prepared = req.prepare()
    return redirect(str(prepared.url))


@routes.get("/github/callback")
def github_callback():
    try:
        # 1. Verify state
        returned_state = request.args.get("state")
        stored_state = session.pop("oauth_state", None)  # pop removes it after reading

        if not stored_state or returned_state != stored_state:
            return "Invalid state parameter", 400

        # 2. Retrieve Code and Verifier
        code = request.args.get("code")
        code_verifier = session.pop("code_verifier", None)

        if not code_verifier:
            return "Missing code verifier", 400

        # 3. Exchange for OAuth Token
        token_url = "https://github.com/login/oauth/access_token"
        token_payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.REDIRECT_URI,
            "code_verifier": code_verifier,
        }
        token_headers = {"Accept": "application/json"}
        token_response = requests.post(
            url=token_url, headers=token_headers, data=token_payload
        )
        token_response.raise_for_status()

        token_response_data: dict[str, str] = token_response.json()
        oauth_token = token_response_data.get("access_token", "")

        logger.info(f"OAUTH TOKEN: {oauth_token}")

        # 4. Retrieve user data with access token
        user_url = "https://api.github.com/user"
        user_headers = {"Authorization": f"Bearer {oauth_token}"}
        user_response = requests.get(url=user_url, headers=user_headers)
        user_response.raise_for_status()
        user_data: dict[str, str] = user_response.json()

        username = user_data.get("login")
        github_id = str(user_data.get("id"))
        avatar_url = user_data.get("avatar_url")
        email = user_data.get("email")

        if not email:
            # 4.1 Get User email
            emails_url = "https://api.github.com/user/emails"
            emails_response = requests.get(url=emails_url, headers=user_headers)
            emails_response.raise_for_status()
            emails: List[dict[str, str]] = emails_response.json()
            primary_email = [email["email"] for email in emails if email["primary"]]
            email = primary_email[0] if primary_email else None
            if not email:
                return jsonify({"status": "error", "message": "No email found"})

        logger.info(f"{username, github_id, avatar_url, email}")

        user: User | None = None

        # 5. Create or update user login time
        existing_user: User | None = (
            db.session.query(User).filter(User.github_id == github_id).first()
        )
        if existing_user:
            existing_user.login_now()
            db.session.commit()
            user = existing_user
        else:
            new_user: User = User(
                github_id=github_id,
                username=username,
                email=email,
                avatar_url=avatar_url,
            )
            new_user.login_now()
            db.session.add(new_user)

            try:
                db.session.commit()
                db.session.refresh(new_user)
                user = new_user
            except IntegrityError:
                db.session.rollback()
                return (
                    jsonify({"status": "error", "message": "Email already registered"}),
                    429,
                )

        # 6. Issue access and refresh token
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)
        response = jsonify(
            {
                "status": "success",
                "access_token": access_token,
                "refresh_token": refresh_token,
            }
        )
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        return response
    except Exception as e:
        db.session.rollback()
        logger.error(str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@routes.post("/refresh")
@jwt_required(refresh=True, locations=["json"])
def refresh():
    try:
        identity = get_jwt_identity()

        # Get the JTI of the current refresh token to blocklist it
        jwt_payload = get_jwt()
        jti = jwt_payload["jti"]

        # Calculate remaining life to set Redis TTL
        exp = jwt_payload["exp"]
        now = datetime.now(timezone.utc).timestamp()
        ttl = int(exp - now)

        # Add to Redis blocklist
        if ttl > 0:
            jwt_redis_blocklist.setex(f"blacklist:{jti}", ttl, "revoked")

        # Generate brand new tokens
        new_access_token = create_access_token(identity=identity)
        new_refresh_token = create_refresh_token(identity=identity)

        return jsonify(
            {
                "status": "success",
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
            }
        )

    except Exception as e:
        logger.error(str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@routes.post("/logout")
@jwt_required(verify_type=False)
def logout():
    try:
        jwt_data = get_jwt()
        jti = jwt_data["jti"]

        # Calculate how much longer the token is valid (in seconds)
        # This is the TTL for the Redis entry
        exp = jwt_data["exp"]
        now = datetime.now(timezone.utc).timestamp()
        ttl = int(exp - now)

        # Store JTI in Redis with calculated TTL
        if ttl > 0:
            jwt_redis_blocklist.setex(f"blacklist:{jti}", ttl, "revoked")

        user: User | None = get_current_user()
        if user:
            user.is_active = False
            db.session.commit()

        # Clear the cookies
        response = jsonify({"status": "success"})
        unset_jwt_cookies(response)

        return response
    except Exception as e:
        db.session.rollback()
        logger.error(str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
