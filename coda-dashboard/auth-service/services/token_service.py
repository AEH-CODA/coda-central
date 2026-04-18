"""JWT token creation and management."""
from jose import jwt
from datetime import datetime, timedelta
from config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


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
