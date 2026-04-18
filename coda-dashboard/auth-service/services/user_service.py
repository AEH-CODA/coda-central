"""User management and database operations."""
import uuid
import psycopg2
import logging
from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Create and return a database connection.
    
    Raises:
        Exception: If database connection fails
    """
    try:
        return psycopg2.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
    except psycopg2.OperationalError as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        raise Exception(f"Database connection failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {str(e)}")
        raise


def get_or_create_user(email: str, google_id: str, name: str = None) -> tuple:
    """
    Get existing user by google_id, or create a new user.
    
    Args:
        email: User's email address
        google_id: Google's unique user ID (sub claim from ID token)
        name: User's full name (from Google profile)
    
    Returns:
        Tuple of (user_id, role)
    
    Raises:
        Exception: If database operation fails
    """
    db = None
    cur = None
    
    try:
        db = get_db_connection()
        cur = db.cursor()
        
        # Try to get existing user by google_id
        cur.execute(
            "SELECT id, role FROM users WHERE google_id=%s",
            (google_id,)
        )
        row = cur.fetchone()
        
        if row:
            logger.info(f"User found: {row[0]}")
            return row[0], row[1]
        
        # User doesn't exist, create new one
        user_id = str(uuid.uuid4())
        role = "user"  # default role for new users
        
        cur.execute(
            "INSERT INTO users (id, email, google_id, name, role) VALUES (%s, %s, %s, %s, %s)",
            (user_id, email, google_id, name, role)
        )
        db.commit()
        logger.info(f"User created: {user_id} with email: {email}, name: {name}")
        return user_id, role
        
    except psycopg2.IntegrityError as e:
        logger.error(f"Database integrity error (likely duplicate): {str(e)}")
        if db:
            db.rollback()
        raise Exception("Failed to create user: Duplicate entry or constraint violation")
    except psycopg2.OperationalError as e:
        logger.error(f"Database operational error: {str(e)}")
        if db:
            db.rollback()
        raise Exception(f"Database operation failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in get_or_create_user: {str(e)}")
        if db:
            db.rollback()
        raise Exception(f"User operation failed: {str(e)}")
    finally:
        if cur:
            cur.close()
        if db:
            db.close()
