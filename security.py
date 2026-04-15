import bcrypt
from jose import jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()


class PasswordUtils:
    @staticmethod
    def hash_password(password: str) -> str:
        """Converts plain text password to a secure hash string."""
        pwd_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pwd_bytes, salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifies if the plain password matches the stored hash."""
        try:
            return bcrypt.checkpw(
                plain_password.encode('utf-8'), 
                hashed_password.encode('utf-8')
            )
        except Exception:
            return False
        

SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key_change_me")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
# Default to 1440 minutes (24 hours) if the env variable is missing
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

def create_access_token(data: dict):
    to_encode = data.copy()
    
    # ✅ FIX: Convert the environment variable to an integer
    minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))
    
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    
    to_encode.update({"exp": expire})
    
    # ✅ FIX: Ensure SECRET_KEY and ALGORITHM are strings
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)