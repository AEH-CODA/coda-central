"""OAuth2 provider logic: client registry, authorization codes, and grants.

CODA acts as an OAuth2 provider so external tools (e.g. Biomni) can be handed
a narrow, revocable `datasets:read` token instead of a user's full session
JWT, which carries `role` claims and is honored by every endpoint. See
routes/oauth.py for the HTTP surface this backs.
"""
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2

from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD
from services.token_service import create_oauth_access_token

logger = logging.getLogger(__name__)

AUTHORIZATION_CODE_TTL_SECONDS = 60


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def hash_secret(secret: str) -> str:
    """Client secrets are high-entropy generated tokens (not user passwords),
    so a plain salted hash is sufficient — no need for a slow KDF."""
    return hashlib.sha256(secret.encode()).hexdigest()


def _secrets_match(secret: str, secret_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(secret), secret_hash)


def seed_client_from_env(client_id: str, client_secret: str, redirect_uri: str, allowed_scopes: list, name: str = None):
    """
    Register (or update) an OAuth client from env-provided config at startup.

    Internal clients are configured this way rather than through a
    self-service registration UI, since CODA only expects to integrate with
    a small, known set of first-party tools for now.
    """
    if not client_id or not client_secret or not redirect_uri:
        logger.info("Skipping OAuth client seed: client_id/secret/redirect_uri not fully configured")
        return

    db = None
    cur = None
    try:
        db = get_db_connection()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO oauth_clients (client_id, client_secret_hash, name, redirect_uris, allowed_scopes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (client_id) DO UPDATE SET
                client_secret_hash = EXCLUDED.client_secret_hash,
                name = EXCLUDED.name,
                redirect_uris = EXCLUDED.redirect_uris,
                allowed_scopes = EXCLUDED.allowed_scopes
            """,
            (client_id, hash_secret(client_secret), name or client_id, [redirect_uri], allowed_scopes),
        )
        db.commit()
        logger.info(f"OAuth client '{client_id}' registered/updated")
    except Exception as e:
        logger.error(f"Failed to seed OAuth client '{client_id}': {str(e)}")
        if db:
            db.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if db:
            db.close()


def get_client(client_id: str) -> dict:
    db = None
    cur = None
    try:
        db = get_db_connection()
        cur = db.cursor()
        cur.execute(
            "SELECT client_id, client_secret_hash, name, redirect_uris, allowed_scopes FROM oauth_clients WHERE client_id=%s",
            (client_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "client_id": row[0],
            "client_secret_hash": row[1],
            "name": row[2],
            "redirect_uris": row[3],
            "allowed_scopes": row[4],
        }
    finally:
        if cur:
            cur.close()
        if db:
            db.close()


def create_authorization_code(user_id: str, client_id: str, redirect_uri: str, scope: str) -> str:
    """One-time, short-lived code handed back to the browser by /oauth/authorize."""
    code = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=AUTHORIZATION_CODE_TTL_SECONDS)

    db = None
    cur = None
    try:
        db = get_db_connection()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO oauth_codes (code, client_id, user_id, redirect_uri, scope, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (code, client_id, user_id, redirect_uri, scope, expires_at),
        )
        db.commit()
        return code
    except Exception:
        if db:
            db.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if db:
            db.close()


def exchange_code_for_token(code: str, client_id: str, client_secret: str, redirect_uri: str):
    """
    Validate and consume a one-time authorization code, then mint a scoped
    access token. Raises ValueError on any validation failure (mapped to a
    400 by the route).

    Returns:
        Tuple of (access_token, scope, expires_in_seconds)
    """
    client = get_client(client_id)
    if not client or not _secrets_match(client_secret, client["client_secret_hash"]):
        raise ValueError("Invalid client credentials")

    db = None
    cur = None
    try:
        db = get_db_connection()
        cur = db.cursor()

        # Lock the row so a code can't be redeemed twice by a racing request.
        cur.execute(
            """
            SELECT client_id, user_id, redirect_uri, scope, expires_at, used
            FROM oauth_codes WHERE code=%s FOR UPDATE
            """,
            (code,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Invalid authorization code")

        code_client_id, user_id, code_redirect_uri, scope, expires_at, used = row

        if used:
            raise ValueError("Authorization code has already been used")
        if code_client_id != client_id:
            raise ValueError("Authorization code was not issued to this client")
        if code_redirect_uri != redirect_uri:
            raise ValueError("redirect_uri does not match the one used to request this code")
        if expires_at < datetime.now(timezone.utc):
            raise ValueError("Authorization code has expired")

        cur.execute("UPDATE oauth_codes SET used=TRUE WHERE code=%s", (code,))

        access_token, jti, expires_at_token = create_oauth_access_token(user_id, client_id, scope)

        cur.execute(
            """
            INSERT INTO oauth_grants (id, user_id, client_id, scope, jti, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), user_id, client_id, scope, jti, expires_at_token),
        )

        db.commit()
        expires_in = int((expires_at_token - datetime.now(timezone.utc)).total_seconds())
        return access_token, scope, expires_in
    except ValueError:
        if db:
            db.rollback()
        raise
    except Exception as e:
        logger.error(f"Failed to exchange authorization code: {str(e)}")
        if db:
            db.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if db:
            db.close()


def list_grants(user_id: str) -> list:
    """Active (non-revoked, unexpired) grants for the Connected Apps settings page."""
    db = None
    cur = None
    try:
        db = get_db_connection()
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, client_id, scope, issued_at, expires_at
            FROM oauth_grants
            WHERE user_id=%s AND revoked_at IS NULL AND expires_at > NOW()
            ORDER BY issued_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [
            {"id": r[0], "client_id": r[1], "scope": r[2], "issued_at": r[3], "expires_at": r[4]}
            for r in rows
        ]
    finally:
        if cur:
            cur.close()
        if db:
            db.close()


def revoke_grant(grant_id: str, user_id: str) -> bool:
    """Returns False if no matching, not-already-revoked grant was found (route maps to 404)."""
    db = None
    cur = None
    try:
        db = get_db_connection()
        cur = db.cursor()
        cur.execute(
            "UPDATE oauth_grants SET revoked_at=NOW() WHERE id=%s AND user_id=%s AND revoked_at IS NULL",
            (grant_id, user_id),
        )
        updated = cur.rowcount > 0
        db.commit()
        return updated
    finally:
        if cur:
            cur.close()
        if db:
            db.close()


def is_grant_revoked(jti: str) -> bool:
    """
    Used by /oauth/introspect for resource servers (e.g. dataset-service)
    that run against a separate database — they can verify an oauth_access
    JWT's signature/exp themselves, but only auth-service's DB knows whether
    the grant behind it has since been revoked from Connected Apps.
    """
    db = None
    cur = None
    try:
        db = get_db_connection()
        cur = db.cursor()
        cur.execute("SELECT revoked_at, expires_at FROM oauth_grants WHERE jti=%s", (jti,))
        row = cur.fetchone()
        if not row:
            return True  # unknown jti — treat as invalid
        revoked_at, expires_at = row
        return revoked_at is not None or expires_at < datetime.now(timezone.utc)
    finally:
        if cur:
            cur.close()
        if db:
            db.close()
