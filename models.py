# models.py
from datetime import datetime
from uuid import uuid4  
from database import db

class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    token = db.Column(db.String(255), unique=True)

class UploadedFile(db.Model):
    __tablename__ = "uploaded_files"
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid4()))
    file_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Processing", index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime)
    deleted_by = db.Column(db.String(120))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)

    customer = db.relationship("Customer", backref=db.backref("files", lazy=True))
    
class ProcessedFile(db.Model):
    __tablename__ = "processed_files"
    id = db.Column(db.Integer, primary_key=True)
    uploaded_file_id = db.Column(db.Integer, db.ForeignKey("uploaded_files.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)  # "{parent_file_name}_processed"
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid4()))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploaded_file = db.relationship("UploadedFile", backref=db.backref("processed_files", lazy=True))
    customer = db.relationship("Customer")