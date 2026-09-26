import argparse
import getpass
from app.db.session import SessionLocal
from app.db.models.user import User
from app.core.security import hash_password


def create_admin():
    parser = argparse.ArgumentParser(description="Bootstrap or create an Admin user.")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--name", help="Admin display name")
    parser.add_argument("--phone", help="Admin phone number")
    parser.add_argument("--password", help="Admin password")

    args, unknown = parser.parse_known_args()

    email = args.email or input("Enter Admin Email: ").strip()
    name = args.name or input("Enter Admin Name: ").strip()
    phone = args.phone or input("Enter Admin Phone: ").strip()
    password = args.password
    if not password:
        password = getpass.getpass("Enter Admin Password: ")
        confirm = getpass.getpass("Confirm Admin Password: ")
        if password != confirm:
            print("Error: Passwords do not match.")
            return

    if len(password) < 6:
        print("Error: Password must be at least 6 characters.")
        return

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email.lower().strip()).first()
        if existing:
            existing.role = "Admin"
            existing.password_hash = hash_password(password)
            existing.status = "active"
            db.commit()
            print(f"Updated existing user '{email}' to role 'Admin'.")
        else:
            admin_user = User(
                name=name or "TradeCall Admin",
                phone=phone or "9992292828",
                email=email.lower().strip(),
                password_hash=hash_password(password),
                role="Admin",
                status="active",
                listing_limit=9999,
                leads_balance=9999,
                leads_used=0
            )
            db.add(admin_user)
            db.commit()
            print(f"Admin user '{email}' successfully created.")
    finally:
        db.close()
