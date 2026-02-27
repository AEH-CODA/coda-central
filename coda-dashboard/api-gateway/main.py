from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
import requests
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import os
from jose import jwt, JWTError

app = FastAPI(title="CODA API Gateway")

NL2SPARQL_URL = os.getenv("NL2SPARQL_URL")
GRAPHDB_ENDPOINT = os.getenv("GRAPHDB_ENDPOINT")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")
SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = os.getenv("JWT_ALGORITHM")

GOOGLE_TIMEOUT = os.getenv("GOOGLE_TIMEOUT")
DOCKER_API_TIMEOUT = os.getenv("DOCKER_API_TIMEOUT")

# CORS configuration
origins = os.getenv("FRONTEND_ORIGINS", "")
allow_origins = [o.strip() for o in origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

def verify_token(authorization: str = Header(...)):
    """
    Verify JWT token from Authorization header.
    
    Returns the token payload if valid, raises HTTPException otherwise.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, 
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid token signature")
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Token validation error")
    
    return payload

@app.get("/")
def health_check():
    return {"status": "API Gateway running"}

# Proxy all auth endpoints to auth-service
@app.get("/auth/login/google")
def proxy_login_google(state: str = None):
    """Proxy to auth-service login endpoint"""
    try:
        url = f"{AUTH_SERVICE_URL}/auth/login/google"
        if state:
            url += f"?state={state}"
        response = requests.get(url, allow_redirects=False, timeout=int(GOOGLE_TIMEOUT))

        if response.status_code in [301, 302, 303, 307, 308]:
            return RedirectResponse(url=response.headers.get("location"), status_code=response.status_code)
        return response.json()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth service error: {str(e)}")

@app.get("/auth/callback")
def proxy_auth_callback(code: str, state: str):
    """Proxy to auth-service callback endpoint"""
    try:
        url = f"{AUTH_SERVICE_URL}/auth/callback?code={code}&state={state}"
        response = requests.get(url, allow_redirects=False, timeout=int(GOOGLE_TIMEOUT))

        if response.status_code in [301, 302, 303, 307, 308]:
            return RedirectResponse(url=response.headers.get("location"), status_code=response.status_code)
        return response.json()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth service error: {str(e)}")

@app.post("/query")
def handle_query(req: QueryRequest, user=Depends(verify_token)):
    """
    Execute NL query with JWT verification.
    
    Args:
        req: Natural language query
        user: Verified JWT payload (user_id, role, exp)
    """
    # user contains: {"sub": user_id, "role": role, "exp": timestamp}
    
    #1) NL 2 SparQL
    resp = requests.post(
        NL2SPARQL_URL,
        json={"query": req.query},
        timeout=int(DOCKER_API_TIMEOUT)
    )

    translation = resp.json()
    sparql_query = translation["sparql"]

    #2) Execute the SparQL Query on GraphDB
    graphdb_resp = requests.post(
        GRAPHDB_ENDPOINT,
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "query": sparql_query
        },
        timeout=int(DOCKER_API_TIMEOUT)
    )

    if graphdb_resp.status_code != 200:
        return {
            "error": "GraphDB query failed",
            "status_code": graphdb_resp.status_code,
            "raw_response": graphdb_resp.text
        }
    
    return {
        "nl_query": req.query,
        "sparql": sparql_query,
        "results": graphdb_resp.json()
    }