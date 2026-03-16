from fastapi import FastAPI, HTTPException, Depends, Header, Request
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
DATASET_SERVICE_URL = os.getenv("DATASET_SERVICE_URL")
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
    save_dataset: bool = False  # Whether to save dataset after query
    dataset_name: str = None  # Name for saved dataset (required if save_dataset=True)
    dataset_description: str = None  # Optional description for dataset

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
def proxy_login_google(request: Request, state: str = None):
    """Proxy to auth-service login endpoint with original request headers"""
    try:
        url = f"{AUTH_SERVICE_URL}/auth/login/google"
        if state:
            url += f"?state={state}"
        
        # Forward original request headers to preserve client info
        headers = {
            "x-forwarded-host": request.headers.get("host", ""),
            "x-forwarded-proto": request.headers.get("x-forwarded-proto") or request.url.scheme,
            "x-forwarded-for": request.headers.get("x-forwarded-for") or request.client.host,
        }
        
        response = requests.get(url, headers=headers, allow_redirects=False, timeout=int(GOOGLE_TIMEOUT))

        if response.status_code in [301, 302, 303, 307, 308]:
            return RedirectResponse(url=response.headers.get("location"), status_code=response.status_code)
        return response.json()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth service error: {str(e)}")

@app.get("/auth/callback")
def proxy_auth_callback(request: Request, code: str, state: str):
    """Proxy to auth-service callback endpoint with original request headers"""
    try:
        url = f"{AUTH_SERVICE_URL}/auth/callback?code={code}&state={state}"
        
        # Forward original request headers to preserve client info
        headers = {
            "x-forwarded-host": request.headers.get("host", ""),
            "x-forwarded-proto": request.headers.get("x-forwarded-proto") or request.url.scheme,
            "x-forwarded-for": request.headers.get("x-forwarded-for") or request.client.host,
        }
        
        response = requests.get(url, headers=headers, allow_redirects=False, timeout=int(GOOGLE_TIMEOUT))

        if response.status_code in [301, 302, 303, 307, 308]:
            return RedirectResponse(url=response.headers.get("location"), status_code=response.status_code)
        return response.json()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth service error: {str(e)}")

@app.post("/query")
def handle_query(req: QueryRequest, user=Depends(verify_token)):
    """
    Execute NL query with JWT verification.
    Optionally save results as a dataset.
    
    Args:
        req: Natural language query + optional save_dataset flag
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
    
    results = graphdb_resp.json()
    response = {
        "nl_query": req.query,
        "sparql": sparql_query,
        "results": results
    }
    
    # 3) Save dataset if requested
    if req.save_dataset:
        if not req.dataset_name:
            raise HTTPException(
                status_code=400,
                detail="dataset_name is required when save_dataset=True"
            )
        
        try:
            # Call dataset-service to save the dataset
            save_response = requests.post(
                f"{DATASET_SERVICE_URL}/datasets",
                json={
                    "nl_query": req.query,
                    "sparql_query": sparql_query,
                    "results": results,
                    "name": req.dataset_name,
                    "description": req.dataset_description
                },
                headers={"Authorization": f"Bearer {req.__dict__.get('token', '')}"},  # Will use the auth header from request
                timeout=int(DOCKER_API_TIMEOUT)
            )
            
            if save_response.status_code == 200:
                save_data = save_response.json()
                response["dataset_id"] = save_data.get("dataset_id")
                response["message"] = "Dataset saved successfully"
            else:
                response["dataset_error"] = "Failed to save dataset"
        except Exception as e:
            response["dataset_error"] = f"Failed to save dataset: {str(e)}"
    
    return response

# Proxy all dataset endpoints to dataset-service
@app.post("/datasets")
async def proxy_save_dataset(request: Request):
    """Proxy POST /datasets to dataset-service"""
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        body = await request.json()
        
        response = requests.post(
            f"{DATASET_SERVICE_URL}/datasets",
            json=body,
            headers={"Authorization": auth_header},
            timeout=int(DOCKER_API_TIMEOUT)
        )
        
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save dataset: {str(e)}")

@app.get("/datasets")
async def proxy_list_datasets(request: Request, skip: int = 0, limit: int = 10):
    """Proxy GET /datasets to dataset-service"""
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        response = requests.get(
            f"{DATASET_SERVICE_URL}/datasets?skip={skip}&limit={limit}",
            headers={"Authorization": auth_header},
            timeout=int(DOCKER_API_TIMEOUT)
        )
        
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list datasets: {str(e)}")

@app.get("/datasets/{dataset_id}")
async def proxy_get_dataset(dataset_id: str, request: Request):
    """Proxy GET /datasets/{dataset_id} to dataset-service"""
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        response = requests.get(
            f"{DATASET_SERVICE_URL}/datasets/{dataset_id}",
            headers={"Authorization": auth_header},
            timeout=int(DOCKER_API_TIMEOUT)
        )
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dataset: {str(e)}")

@app.put("/datasets/{dataset_id}")
async def proxy_update_dataset(dataset_id: str, request: Request):
    """Proxy PUT /datasets/{dataset_id} to dataset-service"""
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        body = await request.json()
        
        response = requests.put(
            f"{DATASET_SERVICE_URL}/datasets/{dataset_id}",
            json=body,
            headers={"Authorization": auth_header},
            timeout=int(DOCKER_API_TIMEOUT)
        )
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update dataset: {str(e)}")

@app.delete("/datasets/{dataset_id}")
async def proxy_delete_dataset(dataset_id: str, request: Request):
    """Proxy DELETE /datasets/{dataset_id} to dataset-service"""
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        response = requests.delete(
            f"{DATASET_SERVICE_URL}/datasets/{dataset_id}",
            headers={"Authorization": auth_header},
            timeout=int(DOCKER_API_TIMEOUT)
        )
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete dataset: {str(e)}")