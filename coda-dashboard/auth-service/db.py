import psycopg2
import os
import time

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

def init_db():
    """Initialize database with retry logic to handle startup timing issues."""
    max_retries = 10
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    google_id TEXT UNIQUE NOT NULL,
                    name TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;")

            # Audit trail for role changes made from the Role Management page —
            # who was changed, from/to what role, and which admin did it.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS role_changes (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id),
                    old_role TEXT NOT NULL,
                    new_role TEXT NOT NULL,
                    changed_by_id UUID NOT NULL REFERENCES users(id),
                    changed_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            conn.commit()
            cur.close()
            conn.close()
            print(f"✓ Database initialized successfully on attempt {attempt + 1}")
            return
            
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                print(f"✗ Database connection failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                print(f"  Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"✗ Failed to initialize database after {max_retries} attempts")
                raise Exception(f"Database initialization failed: {str(e)}")