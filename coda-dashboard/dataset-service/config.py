import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://coda:coda-pass@dataset-db:5432/dataset-db")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
DATA_DIRECTORY = os.getenv("DATA_DIRECTORY", "/app/data")

# Ensure data directory exists
os.makedirs(DATA_DIRECTORY, exist_ok=True)
