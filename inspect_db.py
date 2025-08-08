from flask import Flask
from dotenv import load_dotenv
load_dotenv()
from config import Config
from database import db
from models import Customer, UploadedFile
from sqlalchemy import inspect, text

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    print("Tables:", inspect(db.engine).get_table_names())
    print("Customers:", db.session.execute(text("SELECT id, name, token FROM customers")).all())
    print("Files:", UploadedFile.query.count())