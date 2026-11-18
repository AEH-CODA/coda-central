"""
OAuth2 provider endpoints for connected apps (e.g. Biomni).

CODA has no cookie session — the interactive session JWT lives only in the
browser's localStorage — so the "authorize" step can't be a bare backend
redirect the way /auth/login/google is. Instead, an already-authenticated
page in the React app (which holds the session token) calls
POST /oauth/authorize with it and performs the browser redirect itself using
the URL that comes back.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from jose import jwt, JWTError
from pydantic import BaseModel

from config import JWT_SECRET, JWT_ALGORITHM
from services.oauth_service import (
    create_authorization_code,
    exchange_code_for_token,
    get_client,
    is_grant_revoked,
    list_grants,
    revoke_grant,
)

router = APIRouter(prefix="/oauth", tags=["oauth"])


def require_session_user(authorization: str = Header(...)) -> str:
    """
    Verify the caller's own interactive-session JWT and return their user id.

    Deliberately rejects `oauth_access` tokens: a connected app's own scoped
    token must never be usable to mint further grants or manage a user's
    Connected Apps list.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("token_type") == "oauth_access":
        raise HTTPException(status_code=403, detail="An OAuth access token cannot manage OAuth grants")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    return user_id


class AuthorizeRequest(BaseModel):
    client_id: str
    redirect_uri: str
    scope: str
    state: str


@router.post("/authorize")
def authorize(req: AuthorizeRequest, user_id: str = Depends(require_session_user)):
    """
    Called by the authenticated consent page in the CODA UI after the user
    clicks "Allow". Issues a one-time authorization code and tells the
    frontend where to send the browser next (back to the requesting app).
    """
    client = get_client(req.client_id)
    if not client:
        raise HTTPException(status_code=400, detail="Unknown client_id")

    if req.redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="redirect_uri is not registered for this client")

    requested_scopes = set(req.scope.split())
    if not requested_scopes or not requested_scopes.issubset(set(client["allowed_scopes"])):
        raise HTTPException(status_code=400, detail="Requested scope exceeds what this client is allowed")

    code = create_authorization_code(
        user_id=user_id,
        client_id=req.client_id,
        redirect_uri=req.redirect_uri,
        scope=req.scope,
    )

    separator = "&" if "?" in req.redirect_uri else "?"
    redirect_url = f"{req.redirect_uri}{separator}code={code}&state={req.state}"
    return {"redirect_url": redirect_url}


class TokenRequest(BaseModel):
    grant_type: str
    code: str
    client_id: str
    client_secret: str
    redirect_uri: str


@router.post("/token")
def token(req: TokenRequest):
    """
    Server-to-server code exchange. Called directly by a connected app's
    backend (e.g. Biomni's local server) with its client_secret — never by a
    browser — to trade a one-time authorization code for a scoped access
    token.
    """
    if req.grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")

    try:
        access_token, scope, expires_in = exchange_code_for_token(
            code=req.code,
            client_id=req.client_id,
            client_secret=req.client_secret,
            redirect_uri=req.redirect_uri,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "scope": scope,
    }


class IntrospectRequest(BaseModel):
    token: str


@router.post("/introspect")
def introspect(req: IntrospectRequest):
    """
    RFC 7662-style token introspection for resource servers (e.g.
    dataset-service) that run against a separate database. They can verify
    an oauth_access JWT's signature/expiry themselves via the shared
    JWT_SECRET, but only auth-service's DB knows whether the grant behind it
    has since been revoked from Connected Apps — that's what this checks.
    """
    try:
        payload = jwt.decode(req.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (JWTError, ValueError):
        return {"active": False}

    if payload.get("token_type") != "oauth_access":
        return {"active": False}

    jti = payload.get("jti")
    if not jti or is_grant_revoked(jti):
        return {"active": False}

    return {
        "active": True,
        "sub": payload.get("sub"),
        "scope": payload.get("scope"),
        "client_id": payload.get("client_id"),
    }


@router.get("/grants")
def get_grants(user_id: str = Depends(require_session_user)):
    """List this user's active OAuth grants, for the Connected Apps settings page."""
    return {"grants": list_grants(user_id)}


@router.delete("/grants/{grant_id}")
def delete_grant(grant_id: str, user_id: str = Depends(require_session_user)):
    """Revoke one of this user's OAuth grants."""
    revoked = revoke_grant(grant_id, user_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Grant not found")
    return {"status": "revoked"}
