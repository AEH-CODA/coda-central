from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt
import psycopg2
import uuid
import os
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from db import init_db

app = FastAPI(title="Auth Service")

# Config
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# CORS configuration
origins = os.getenv("FRONTEND_ORIGINS", "")
allow_origins = [o.strip() for o in origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    return psycopg2.connect(
        dbname="user-db",
        user="coda",
        password="coda-pass",
        host="user-db"
    )

class SignupRequest(BaseModel):
    email: str
    password: str
    role: str

class LoginRequest(BaseModel):
    email: str
    password: str

def create_token(user_id: str, role: str):
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

@app.on_event("startup")
def startup():
    init_db()

@app.post("/signup")
def signup(req: SignupRequest):
    db = get_db()
    cur = db.cursor()

    password_hash = pwd_context.hash(req.password)
    user_id = str(uuid.uuid4())

    try:
        cur.execute(
            "INSERT INTO users (id, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (user_id, req.email, password_hash, req.role)
        )
        db.commit()
    except:
        raise HTTPException(status_code=400, detail="User already exists")

    return {"message": "User created"}

@app.post("/login")
def login(req: LoginRequest):
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT id, password_hash, role FROM users WHERE email=%s",
        (req.email,)
    )
    row = cur.fetchone()

    if not row or not pwd_context.verify(req.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(row[0], row[2])
    return {"access_token": token, "token_type": "bearer"}