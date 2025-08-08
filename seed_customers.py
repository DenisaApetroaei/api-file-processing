import secrets
from flask import Flask
from dotenv import load_dotenv
load_dotenv()
from config import Config
from database import db
from models import Customer

def _ensure_customer(name: str):
    c = Customer.query.filter_by(name=name).first()
    created = False
    if c is None:
        c = Customer(name=name, token=secrets.token_urlsafe(32))
        db.session.add(c)
        created = True
    elif not c.token:
        c.token = secrets.token_urlsafe(32)
    db.session.commit()
    return c, created

def main(names=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()

        if not names:
            names = ["Customer One", "Customer Two"]

        results = []
        for n in names:
            cust, created = _ensure_customer(n)
            results.append((cust, created))

        print("\nSeeded customers:")
        for cust, created in results:
            status = "created" if created else "existing"
            print(f"- id={cust.id}  name='{cust.name}'  token='{cust.token}'  ({status})")
        print()

if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else None)