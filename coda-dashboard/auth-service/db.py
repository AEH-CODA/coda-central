import psycopg2
import os

DB_HOST = os.getenv("POSTGRES_HOST", "user-db")
DB_NAME = os.getenv("POSTGRES_DB", "user-db")
DB_USER = os.getenv("POSTGRES_USER", "coda")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "coda-pass")

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    conn.commit()
    cur.close()
    conn.close()