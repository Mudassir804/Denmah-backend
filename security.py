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
        

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=os.getenv(ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, os.getenv(SECRET_KEY), algorithm=os.getenv(ALGORITHM))