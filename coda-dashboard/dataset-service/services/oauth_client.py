"""
Checks OAuth access-token revocation against auth-service.

An oauth_access token (issued to a Connected App like Biomni) is otherwise a
stateless JWT — its signature and exp claim can't reflect a grant the user
has since revoked from their Connected Apps list. Only auth-service's DB
knows that, so this is the one extra network hop paid only on the
oauth_access path; normal session-token requests never call out.
"""
import logging

import httpx

from config import AUTH_SERVICE_URL

logger = logging.getLogger(__name__)


def introspect_is_active(token: str) -> bool:
    """Fails closed (treats the token as inactive) on any error — this guards
    an authorization decision, so an unreachable auth-service should deny,
    not silently allow."""
    try:
        response = httpx.post(
            f"{AUTH_SERVICE_URL}/oauth/introspect",
            json={"token": token},
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("active", False)
    except Exception as e:
        logger.error(f"OAuth introspection failed: {str(e)}")
        return False
