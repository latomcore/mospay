import time
from functools import wraps
from sqlalchemy.exc import OperationalError, DisconnectionError
from flask import current_app

def retry_on_db_error(max_retries=3, delay=1):
    """
    Decorator to retry database operations on connection errors
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, DisconnectionError) as e:
                    last_exception = e
                    
                    # Check if it's a connection issue
                    if 'server closed the connection' in str(e) or 'connection' in str(e).lower():
                        if attempt < max_retries - 1:
                            print(f"Database connection error on attempt {attempt + 1}, retrying in {delay} seconds...")
                            time.sleep(delay)
                            
                            # Try to refresh the database connection
                            try:
                                current_app.db.session.rollback()
                                current_app.db.session.close()
                            except:
                                pass
                            
                            continue
                    
                    # If it's not a connection issue or we've exhausted retries, raise the error
                    raise e
            
            # If we get here, all retries failed
            raise last_exception
            
        return wrapper
    return decorator

def ensure_db_connection():
    """
    Ensure database connection is active
    """
    try:
        # Try a simple query to test the connection
        current_app.db.session.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"Database connection test failed: {e}")
        try:
            current_app.db.session.rollback()
            current_app.db.session.close()
        except:
            pass
        return False
