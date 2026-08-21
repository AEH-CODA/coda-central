"""Authentication routes (Google OAuth)."""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token
import requests
import secrets

from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
    GOOGLE_AUTH_URL, GOOGLE_TOKEN_URL
)
from services.token_service import create_token
from services.user_service import get_or_create_user
from services.url_service import get_base_url, get_frontend_url

router = APIRouter(prefix="/auth")

@router.get("/login/google")
def login_google(request: Request, state: str = None):
    """
    Initiate Google OAuth flow.
    
    Generates a CSRF state token and redirects to Google's login page.
    Uses the request's host to dynamically construct the callback URI.
    """
    # Generate state token for CSRF protection
    state = state or secrets.token_urlsafe(32)
    
    # Dynamically construct redirect URI from request
    base_url = get_base_url(request)
    redirect_uri = f"{base_url}/auth/callback"
    
    # Build Google OAuth URL
    google_auth_url = (
        f"{GOOGLE_AUTH_URL}?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=openid%20email%20profile&"
        f"state={state}"
    )
    
    return RedirectResponse(url=google_auth_url)


@router.get("/callback")
def auth_callback(request: Request, code: str = Query(...), state: str = Query(...)):
    """
    Google OAuth callback.
    
    Exchanges authorization code for ID token, validates it,
    creates/fetches user, and issues our JWT token.
    Uses the request's host to construct callback URI and frontend redirect.
    """
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")
    
    try:
        # Dynamically construct redirect URI from request
        base_url = get_base_url(request)
        redirect_uri = f"{base_url}/auth/callback"
        
        # Step 1: Exchange authorization code for tokens
        token_response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            },
            timeout=10
        )
        
        if token_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Failed to exchange code for token")
        
        # Step 2: Extract ID token from response
        token_data = token_response.json()
        id_token_str = token_data.get("id_token")
        
        if not id_token_str:
            raise HTTPException(status_code=401, detail="No ID token in response")
        
        # Step 3: Verify and decode ID token
        try:
            request_obj = google_auth_requests.Request()
            id_token_decoded = id_token.verify_oauth2_token(
                id_token_str,
                request_obj,
                GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=10
            )
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")
        
        # Step 4: Extract user information
        google_id = id_token_decoded.get("sub")
        email = id_token_decoded.get("email")
        name = id_token_decoded.get("name")
        
        if not google_id or not email:
            raise HTTPException(status_code=400, detail="Missing sub or email in ID token")
        
        # Step 5: Get or create user in database
        user_id, role = get_or_create_user(email, google_id, name)
        
        # Step 6: Issue our internal JWT token (include user name)
        our_token = create_token(user_id, role, name)
        
        # Step 7: Redirect to frontend with token (use frontend URL with UI port)
        frontend_url = get_frontend_url(request)
        redirect_url = f"{frontend_url}/?token={our_token}"
        return RedirectResponse(url=redirect_url)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback error: {str(e)}")
