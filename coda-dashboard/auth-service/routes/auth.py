"""Authentication routes (Google OAuth)."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token
import requests
import secrets

from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    GOOGLE_AUTH_URL, GOOGLE_TOKEN_URL, FRONTEND_ORIGIN
)
from services.token_service import create_token
from services.user_service import get_or_create_user

router = APIRouter(prefix="/auth")


@router.get("/login/google")
def login_google(state: str = None):
    """
    Initiate Google OAuth flow.
    
    Generates a CSRF state token and redirects to Google's login page.
    """
    # Generate state token for CSRF protection
    state = state or secrets.token_urlsafe(32)
    
    # Build Google OAuth URL
    google_auth_url = (
        f"{GOOGLE_AUTH_URL}?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=openid%20email%20profile&"
        f"state={state}"
    )
    
    return RedirectResponse(url=google_auth_url)


@router.get("/callback")
def auth_callback(code: str = Query(...), state: str = Query(...)):
    """
    Google OAuth callback.
    
    Exchanges authorization code for ID token, validates it,
    creates/fetches user, and issues our JWT token.
    """
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")
    
    try:
        # Step 1: Exchange authorization code for tokens
        token_response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_REDIRECT_URI
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
                GOOGLE_CLIENT_ID
            )
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid ID token: {str(e)}")
        
        # Step 4: Extract user information
        google_id = id_token_decoded.get("sub")
        email = id_token_decoded.get("email")
        
        if not google_id or not email:
            raise HTTPException(status_code=400, detail="Missing sub or email in ID token")
        
        # Step 5: Get or create user in database
        user_id, role = get_or_create_user(email, google_id)
        
        # Step 6: Issue our internal JWT token
        our_token = create_token(user_id, role)
        
        # Step 7: Redirect to frontend with token
        redirect_url = f"{FRONTEND_ORIGIN}/?token={our_token}"
        return RedirectResponse(url=redirect_url)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback error: {str(e)}")
