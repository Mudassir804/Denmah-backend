import models
from database import SessionLocal, engine
from security import PasswordUtils

def seed_admin():
    db = SessionLocal()
    # Replace with your actual desired credentials
    email = "admin@denmah.com"
    password = "YourSecretPassword123"

    try:
        # Check if exists
        admin = db.query(models.Admin).filter(models.Admin.email == email).first()
        if admin:
            print(f"⚠️ Admin {email} already exists.")
            return

        new_admin = models.Admin(
            email=email,
            hashed_password=PasswordUtils.hash_password(password)
        )
        db.add(new_admin)
        db.commit()
        print(f"✅ Admin created successfully: {email}")
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    seed_admin()