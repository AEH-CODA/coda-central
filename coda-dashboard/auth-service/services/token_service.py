"""JWT token creation and management."""
import uuid
from jose import jwt
from datetime import datetime, timedelta, timezone
from config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, OAUTH_ACCESS_TOKEN_EXPIRE_DAYS


def create_token(user_id: str, role: str, user_name: str = None) -> str:
    """
    Create a JWT token for internal authorization.

    Args:
        user_id: User's UUID
        role: User's role (e.g., 'user', 'admin')
        user_name: User's display name (optional)

    Returns:
        Encoded JWT token string
    """
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    if user_name:
        payload["name"] = user_name
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_oauth_access_token(user_id: str, client_id: str, scope: str):
    """
    Create a scoped access token for a connected app (e.g. Biomni).

    Unlike create_token(), this carries no `role` claim and is restricted to
    `scope` — a connected app should never be handed enough privilege to do
    more than what the user explicitly consented to in the OAuth grant. The
    `jti` lets a resource server check for revocation via /oauth/introspect,
    since the token itself is otherwise a stateless JWT.

    Returns:
        Tuple of (token, jti, expires_at)
    """
    jti = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=OAUTH_ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "token_type": "oauth_access",
        "client_id": client_id,
        "scope": scope,
        "jti": jti,
        "exp": expires_at,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, jti, expires_at
