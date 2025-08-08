import os
from flask import Flask, jsonify, request, current_app, send_from_directory, send_file
from dotenv import load_dotenv
from database import db, migrate
from config import Config  
from werkzeug.utils import secure_filename
import hmac
from uuid import uuid4
from glob import glob
import json
import os
from typing import Optional
load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)  
db.init_app(app)
migrate.init_app(app, db)

from models import UploadedFile, Customer, ProcessedFile

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")

def _get_current_customer():
    cid_raw = request.headers.get("X-Customer-Id")
    if not cid_raw:
        return None, "Missing X-Customer-Id header"
    try:
        customer_id = int(cid_raw)
    except ValueError:
        return None, "X-Customer-Id must be an integer"
  
    auth = request.headers.get("Authorization")
    if not auth:
        return None, "Missing Authorization header"
    try:
        scheme, cred = auth.split(" ", 1)
    except ValueError:
        return None, "Malformed Authorization header (expected: 'Bearer <token>')"
    if scheme.lower() != "bearer":
        return None, "Wrong auth scheme (use: Bearer)"
    token = cred.strip()

    print(customer_id)
    print(token)
    print("All customers:", [(c.id, c.name, c.token) for c in Customer.query.all()])
    customer = Customer.query.get(customer_id)
    if not customer:
        return None, "Unknown customer"

    if not customer.token or not hmac.compare_digest(customer.token, token):
        return None, "Invalid token for this customer"

    return customer, None

def _customer_dir(customer_id: int) -> str:
    return os.path.join(current_app.config["UPLOAD_FOLDER"], str(customer_id))

def _find_parent_disk_file(customer_id: int, parent_uuid: str):
    """Return (ext, full_path) for the stored parent on disk, or (None, None)."""
    base = _customer_dir(customer_id)
    matches = glob(os.path.join(base, f"{parent_uuid}.*"))
    if not matches:
        return None, None
    path = matches[0]
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext, path

def add_suffix_before_ext(filename: str, suffix: str, *, ext_hint: Optional[str] = None) -> str:
    base, ext = os.path.splitext(filename or "")
    if not ext and ext_hint:
        ext = "." + ext_hint.lstrip(".")
    suffix = suffix.strip("_")
    return f"{base}_{suffix}{ext}" if (base or ext) else f"processed{ext}"

def _ensure_processed(customer_id: int, parent: UploadedFile) -> ProcessedFile:
    """Create a mock processed file if it doesn't exist, then return it."""
    proc = ProcessedFile.query.filter_by(uploaded_file_id=parent.id, customer_id=customer_id).first()
    if proc:
        return proc

    ext, parent_path = _find_parent_disk_file(customer_id, parent.uuid)
    if ext is None:
        ext = "json"

    processed_dir = os.path.join(_customer_dir(customer_id), "processed")
    os.makedirs(processed_dir, exist_ok=True)
    pretty_name = add_suffix_before_ext(parent.file_name, "processed", ext_hint=ext)
    proc = ProcessedFile(
        uploaded_file_id=parent.id,
        customer_id=customer_id,
        name=pretty_name,
    )
    db.session.add(proc)
    db.session.flush()  

    processed_path = os.path.join(processed_dir, f"{proc.uuid}.{ext}")

    if ext == "csv":
        with open(processed_path, "w", encoding="utf-8", newline="") as f:
            f.write("parent_uuid,status\n")
            f.write(f"{parent.uuid},OK\n")
    else:
        with open(processed_path, "w", encoding="utf-8") as f:
            json.dump(
                {"parent_uuid": parent.uuid, "status": "OK", "processed": True},
                f,
                ensure_ascii=False,
            )

    db.session.commit()
    return proc

@app.post("/upload-file")
def upload_file():
    ALLOWED_EXTENSIONS = {"csv", "json"}
    customer, err = _get_current_customer()
    if err:
        return jsonify({"error": "Unauthorized", "detail": err}), 401

    root = app.config["UPLOAD_FOLDER"]
    customer_dir = os.path.join(root, str(customer.id))
    os.makedirs(customer_dir, exist_ok=True)

    original_name = None
    ext = None
    payload_bytes = None
    uploaded_file = None  

    if "file" in request.files:
        uploaded_file = request.files["file"]
        original_name = secure_filename(uploaded_file.filename or "")
        if not original_name:
            return jsonify({"error": "File must have a filename"}), 400
        ext = (original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "")
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": f"Only {', '.join(sorted(ALLOWED_EXTENSIONS))} allowed"}), 400

    elif request.is_json:
        original_name = "inline.json"
        ext = "json"
        payload_bytes = json.dumps(request.get_json(), ensure_ascii=False).encode("utf-8")

    elif request.data and request.mimetype in ("text/csv", "application/csv"):
        original_name = "inline.csv"
        ext = "csv"
        payload_bytes = request.data

    else:
        return jsonify({"error": "No file provided. Use multipart 'file', application/json, or text/csv."}), 400

    rec = UploadedFile(file_name=original_name, customer_id=customer.id)
    db.session.add(rec)
    db.session.flush()  

    storage_name = f"{rec.uuid}.{ext}"
    storage_path = os.path.join(customer_dir, storage_name)

    if uploaded_file is not None:
        uploaded_file.save(storage_path)
    else:
        with open(storage_path, "wb") as f:
            f.write(payload_bytes)

    db.session.commit()

    return jsonify({
        "message": "File uploaded",
        "file": {
            "id": rec.id,
            "uuid": rec.uuid,
            "file_name": rec.file_name,         
            "stored_as": storage_name,         
            "customer_id": rec.customer_id,
            "timestamp": rec.timestamp.isoformat()
        }
    }), 201

@app.get("/file-status/<uuid_str>")
def file_status(uuid_str):
    customer, err = _get_current_customer()
    if err:
        return jsonify({"error": "Unauthorized", "detail": err}), 401

    rec = UploadedFile.query.filter_by(uuid=uuid_str, customer_id=customer.id).first()
    if not rec:
        return jsonify({"error": "Not found"}), 404

    return jsonify({
        "uuid": rec.uuid,
        "status": rec.status,
        "file_name": rec.file_name,
        "customer_id": rec.customer_id,
        "timestamp": rec.timestamp.isoformat()
    })
@app.get("/get-results")
def get_results():
    customer, err = _get_current_customer()
    if err:
        return jsonify({"error": "Unauthorized", "detail": err}), 401

    parent_uuid = request.args.get("uuid") or request.args.get("parent_uuid")
    if not parent_uuid:
        return jsonify({"error": "Missing query param 'uuid' (parent file UUID)"}), 400

    parent = UploadedFile.query.filter_by(uuid=parent_uuid, customer_id=customer.id).first()
    if not parent:
        return jsonify({"error": "Parent file not found for this customer"}), 404

    proc = _ensure_processed(customer.id, parent)

    processed_dir = os.path.join(_customer_dir(customer.id), "processed")
    matches = glob(os.path.join(processed_dir, f"{proc.uuid}.*"))
    if not matches:
        return jsonify({"error": "Processed artifact missing on disk"}), 500

    stored_filename = os.path.basename(matches[0])
    return send_file(
        os.path.join(processed_dir, stored_filename),
        as_attachment=True,
        download_name=proc.name, 
    )
if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")