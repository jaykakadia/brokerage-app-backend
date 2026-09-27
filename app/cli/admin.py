import os
import argparse
import getpass
from app.db.session import SessionLocal
from app.db.models.user import User
from app.core.security import hash_password


def create_admin():
    parser = argparse.ArgumentParser(
        description="Securely bootstrap or create an Admin user without leaking credentials in shell history."
    )
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--name", help="Admin display name")
    parser.add_argument("--phone", help="Admin phone number")
    # Note: Password argument intentionally omitted to prevent leakage in shell history (.zsh_history).
    # Password can be entered interactively via secure prompt or passed via ADMIN_PASSWORD environment variable.

    args, unknown = parser.parse_known_args()

    if args.email:
        email = args.email.strip()
        name = args.name.strip() if args.name else "TradeCall Admin"
        phone = args.phone.strip() if args.phone else "9992292828"
    else:
        email = input("Enter Admin Email: ").strip()
        name = input("Enter Admin Name [TradeCall Admin]: ").strip() or "TradeCall Admin"
        phone = input("Enter Admin Phone [9992292828]: ").strip() or "9992292828"


    # Retrieve password securely
    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Enter Admin Password (input hidden): ")
        confirm = getpass.getpass("Confirm Admin Password (input hidden): ")
        if password != confirm:
            print("Error: Passwords do not match.")
            return

    if len(password) < 8:
        print("Error: For security, Admin password must be at least 8 characters.")
        return

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email.lower().strip()).first()
        if existing:
            existing.role = "Admin"
            existing.password_hash = hash_password(password)
            existing.status = "active"
            db.commit()
            print(f"Success: Updated existing user '{email}' to role 'Admin'.")
        else:
            admin_user = User(
                name=name or "TradeCall Admin",
                phone=phone or "9992292828",
                email=email.lower().strip(),
                password_hash=hash_password(password),
                role="Admin",
                status="active"
            )
            db.add(admin_user)
            db.commit()
            print(f"Success: Admin user '{email}' successfully created.")
    finally:
        db.close()
