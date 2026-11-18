"""
Client for connecting Biomni to a user's CODA account via OAuth2, so a saved
CODA dataset can be pulled in and used exactly like a manually uploaded file.

Biomni never sees the user's CODA session or password — only a narrow,
revocable `datasets:read` access token obtained through the browser consent
screen CODA's own UI serves (coda-dashboard/ui/src/pages/OAuthAuthorizePage.jsx).
Biomni's client_secret is only ever sent server-to-server in exchange_code()
below, never placed in a URL or exposed to the browser.
"""

import json
import os
import secrets
import stat
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import requests

CODA_API_BASE_URL = os.getenv("CODA_API_BASE_URL", "http://localhost:8000")
CODA_UI_BASE_URL = os.getenv("CODA_UI_BASE_URL", "http://localhost:5000")
BIOMNI_OAUTH_CLIENT_ID = os.getenv("BIOMNI_OAUTH_CLIENT_ID", "biomni")
BIOMNI_OAUTH_CLIENT_SECRET = os.getenv("BIOMNI_OAUTH_CLIENT_SECRET")
BIOMNI_OAUTH_REDIRECT_URI = os.getenv("BIOMNI_OAUTH_REDIRECT_URI", "http://127.0.0.1:7860/oauth/callback")
BIOMNI_OAUTH_SCOPE = "datasets:read"

TOKEN_PATH = Path(os.path.expanduser("~/.biomni/coda_token.json"))

# Pending OAuth states, so the callback route can reject a code/state pair it
# didn't request. A module-level dict is fine: the Gradio demo is a single
# local process serving one user, not a multi-tenant web service.
_pending_states: dict[str, float] = {}
_STATE_TTL_SECONDS = 600


def _prune_expired_states() -> None:
    now = time.time()
    for state, expires_at in list(_pending_states.items()):
        if expires_at < now:
            _pending_states.pop(state, None)


def generate_state() -> str:
    state = secrets.token_urlsafe(24)
    _prune_expired_states()
    _pending_states[state] = time.time() + _STATE_TTL_SECONDS
    return state


def consume_state(state: str) -> bool:
    """True (and forgets it) if this is a state we issued that hasn't expired."""
    _prune_expired_states()
    return _pending_states.pop(state, None) is not None


def build_authorize_url() -> str:
    """URL for the browser to visit to start the consent flow — lands on
    CODA's own UI, not auth-service directly, since granting consent requires
    the user's already-authenticated browser session (see OAuthAuthorizePage.jsx)."""
    params = {
        "client_id": BIOMNI_OAUTH_CLIENT_ID,
        "redirect_uri": BIOMNI_OAUTH_REDIRECT_URI,
        "scope": BIOMNI_OAUTH_SCOPE,
        "state": generate_state(),
        "response_type": "code",
    }
    return f"{CODA_UI_BASE_URL}/oauth/authorize?{urlencode(params)}"


def _save_token(data: dict) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data))
    os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600 — this is a bearer credential


def _load_token() -> Optional[dict]:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def disconnect() -> None:
    TOKEN_PATH.unlink(missing_ok=True)


def is_connected() -> bool:
    token = _load_token()
    return bool(token) and token.get("expires_at", 0) > time.time()


def exchange_code(code: str) -> None:
    """Server-to-server code exchange — trades a one-time authorization code
    for a datasets:read access token. Never called from the browser."""
    if not BIOMNI_OAUTH_CLIENT_SECRET:
        raise RuntimeError(
            "BIOMNI_OAUTH_CLIENT_SECRET is not set. Ask whoever runs your CODA "
            "instance for Biomni's client secret and set it in the environment "
            "before connecting."
        )

    response = requests.post(
        f"{CODA_API_BASE_URL}/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": BIOMNI_OAUTH_CLIENT_ID,
            "client_secret": BIOMNI_OAUTH_CLIENT_SECRET,
            "redirect_uri": BIOMNI_OAUTH_REDIRECT_URI,
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    _save_token(
        {
            "access_token": data["access_token"],
            "scope": data.get("scope", ""),
            "expires_at": time.time() + data.get("expires_in", 0),
        }
    )


def _auth_headers() -> dict:
    token = _load_token()
    if not token:
        raise RuntimeError('Not connected to CODA. Click "Connect CODA account" first.')
    return {"Authorization": f"Bearer {token['access_token']}"}


def list_datasets() -> list[dict]:
    """Returns the user's saved CODA datasets: [{"id", "name", "description", "created_at"}, ...]."""
    response = requests.get(
        f"{CODA_API_BASE_URL}/datasets",
        headers=_auth_headers(),
        params={"limit": 100},
        timeout=15,
    )
    if response.status_code == 401:
        disconnect()
        raise RuntimeError("CODA access has expired or been revoked. Please reconnect.")
    response.raise_for_status()
    return response.json().get("datasets", [])


def download_dataset_csv(dataset_id: str, dataset_name: str, destination_dir: str) -> str:
    """Downloads a saved CODA dataset as CSV into destination_dir and returns the local path."""
    response = requests.get(
        f"{CODA_API_BASE_URL}/datasets/{dataset_id}/export",
        headers=_auth_headers(),
        params={"format": "csv"},
        timeout=30,
    )
    if response.status_code == 401:
        disconnect()
        raise RuntimeError("CODA access has expired or been revoked. Please reconnect.")
    response.raise_for_status()

    os.makedirs(destination_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dataset_name) or dataset_id
    local_path = os.path.join(destination_dir, f"{safe_name}.csv")
    with open(local_path, "wb") as f:
        f.write(response.content)
    return local_path
