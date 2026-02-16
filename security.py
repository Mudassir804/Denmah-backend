from passlib.context import CryptContext

# Setup the hashing algorithm
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class PasswordUtils:
    @staticmethod
    def hash_password(password: str) -> str:
        """Encodes the password into a secure hash."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Checks if the typed password matches the stored hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    