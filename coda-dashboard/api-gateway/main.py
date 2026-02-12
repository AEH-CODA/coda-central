from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
import requests
from fastapi.middleware.cors import CORSMiddleware
import os
from jose import jwt, JWTError

app = FastAPI(title="CODA API Gateway")

NL2SPARQL_URL = "http://nl2sparql:9000/translate"
GRAPHDB_ENDPOINT = "http://graphdb:7200/repositories/feb-sample"
SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = os.getenv("JWT_ALGORITHM")

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
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"},)

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/")
def health_check():
    return {"status": "API Gateway running"}


@app.post("/query")
def handle_query(req: QueryRequest): 
    # , user=Depends(verify_token)
    # user_id = user["sub"]
    # role = user.get("role")

    #1) NL 2 SparQL
    resp = requests.post(
        NL2SPARQL_URL,
        json={"query": req.query},
        timeout=5
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
        timeout=10
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