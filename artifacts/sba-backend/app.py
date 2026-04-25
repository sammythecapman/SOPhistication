"""
SBA Loan Data Extraction Tool — Flask Backend
Serves all extraction API endpoints at /api
"""

import io
import os
import uuid
import json
import logging
import threading
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

import db
import file_security
from extraction.pipeline import run_extraction_pipeline
from extraction.errors import ExtractionStageError

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────

app = Flask(__name__)

# ── CORS allowlist ──
# ALLOWED_ORIGINS is a comma-separated list of permitted origins.
# If unset/empty we fall back to safe localhost dev defaults — never "*".
_DEV_DEFAULT_ORIGINS = ["http://localhost:5173", "http://localhost:21230"]
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = _DEV_DEFAULT_ORIGINS

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)
app.logger.setLevel(logging.INFO)
app.logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

FILES_FOLDER = Path(__file__).parent / "stored_files"
FILES_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}

# Number of days to retain stored source files before automatic deletion
FILE_RETENTION_DAYS = int(os.environ.get("FILE_RETENTION_DAYS", "30"))

# In-memory job store: job_id -> job_dict
_job_store: dict = {}
_job_store_lock = threading.Lock()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────

@app.route("/api/healthz")
def health_check():
    return jsonify({"status": "ok"})


# ──────────────────────────────────────────────
# Extract endpoint
# ──────────────────────────────────────────────

@app.route("/api/extract", methods=["POST"])
def start_extraction():
    if "terms_pdf" not in request.files:
        return jsonify({"error": "terms_pdf file is required"}), 400

    terms_file = request.files["terms_pdf"]
    memo_file = request.files.get("credit_memo_pdf")

    if not terms_file.filename:
        return jsonify({"error": "No file selected for terms_pdf"}), 400

    if not allowed_file(terms_file.filename):
        return jsonify({"error": "Only PDF files are accepted"}), 400

    # Save uploaded files to temp directory
    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_FOLDER / job_id
    job_dir.mkdir(exist_ok=True)

    terms_filename = secure_filename(terms_file.filename)
    terms_path = str(job_dir / terms_filename)
    terms_file.save(terms_path)

    memo_path = None
    if memo_file and memo_file.filename and allowed_file(memo_file.filename):
        memo_filename = secure_filename(memo_file.filename)
        memo_path = str(job_dir / memo_filename)
        memo_file.save(memo_path)

    # Initialize job in store
    with _job_store_lock:
        _job_store[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "stage": "reading_pdf",
            "stage_label": "Queued",
            "progress": 0,
            "error": None,
            "extraction_id": None,
            "result": None,
        }

    # Launch background thread
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, terms_path, memo_path, job_dir),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id, "message": "Extraction job started"}), 202


def _run_job(job_id: str, terms_path: str, memo_path, job_dir: Path):
    """Background worker that runs the extraction pipeline."""
    with _job_store_lock:
        _job_store[job_id]["status"] = "running"

    try:
        result = run_extraction_pipeline(
            terms_path=terms_path,
            memo_path=memo_path,
            job_id=job_id,
            job_store=_job_store,
        )

        # Save to database
        extraction_id = db.save_extraction(result)

        # Persist encrypted copies of the uploaded PDFs for later download
        dest_dir = FILES_FOLDER / str(extraction_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            enc_terms = dest_dir / (Path(terms_path).name + ".enc")
            file_security.encrypt_file(terms_path, str(enc_terms))
            if memo_path and Path(memo_path).exists():
                enc_memo = dest_dir / (Path(memo_path).name + ".enc")
                file_security.encrypt_file(memo_path, str(enc_memo))
        except Exception as copy_err:
            print(f"⚠️  Could not persist source files for extraction {extraction_id}: {copy_err}")

        # Mark complete
        with _job_store_lock:
            _job_store[job_id].update({
                "status": "complete",
                "stage": "complete",
                "stage_label": "Complete",
                "progress": 100,
                "extraction_id": extraction_id,
                "result": {
                    "id": extraction_id,
                    "terms_filename": result["terms_filename"],
                    "credit_memo_filename": result.get("credit_memo_filename"),
                    "deal_structure": result.get("deal_structure") or {},
                    "formatted_data": result.get("formatted_data") or {},
                    "raw_data": result.get("raw_data") or {},
                    "ner_warnings": result.get("ner_warnings") or [],
                    "confidence_scores": result.get("confidence_scores") or {},
                    "extraction_health": result.get("extraction_health") or {"degraded": False, "stage_failures": []},
                    "prompt_versions": result.get("prompt_versions"),
                    "fields_populated": result["summary"]["fields_populated"],
                    "fields_total": result["summary"]["fields_total"],
                    "completion_pct": result["summary"]["completion_percentage"],
                    "created_at": datetime.now().isoformat(),
                },
            })
    except Exception as e:
        error_str = str(e)
        if "overloaded_error" in error_str or "529" in error_str:
            friendly = "The AI service is temporarily overloaded. Please wait a moment and try again."
        elif "401" in error_str or "authentication" in error_str.lower():
            friendly = "API authentication error. Please check the API key configuration."
        elif "rate_limit" in error_str or "429" in error_str:
            friendly = "Rate limit reached. Please wait a minute before trying again."
        else:
            friendly = error_str
        with _job_store_lock:
            _job_store[job_id].update({
                "status": "failed",
                "stage": "failed",
                "stage_label": "Failed",
                "progress": 0,
                "error": friendly,
            })
    finally:
        # Clean up uploaded files after a delay
        try:
            shutil.rmtree(str(job_dir), ignore_errors=True)
        except Exception:
            pass


# ──────────────────────────────────────────────
# Job status endpoint
# ──────────────────────────────────────────────

@app.route("/api/jobs/<job_id>")
def get_job_status(job_id: str):
    with _job_store_lock:
        job = _job_store.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(job)


# ──────────────────────────────────────────────
# Extractions history
# ──────────────────────────────────────────────

@app.route("/api/extractions")
def list_extractions():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = max(1, min(100, int(request.args.get("per_page", 20))))
    except (ValueError, TypeError):
        page, per_page = 1, 20

    try:
        result = db.list_extractions(page=page, per_page=per_page)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/extractions/<int:extraction_id>")
def get_extraction(extraction_id: int):
    try:
        extraction = db.get_extraction(extraction_id)
        if not extraction:
            return jsonify({"error": "Extraction not found"}), 404
        return jsonify(extraction)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/extractions/<int:extraction_id>/files/<path:filename>/token")
def get_download_token(extraction_id: int, filename: str):
    """
    Issue a time-limited signed download token for a stored source file.
    Tokens expire after 1 hour.
    """
    safe_name = secure_filename(filename)
    if not safe_name:
        return jsonify({"error": "Invalid filename"}), 400

    enc_path = FILES_FOLDER / str(extraction_id) / (safe_name + ".enc")
    raw_path = FILES_FOLDER / str(extraction_id) / safe_name
    if not enc_path.exists() and not raw_path.exists():
        return jsonify({
            "error": "Source file not available. Files from extractions before secure storage was enabled cannot be downloaded."
        }), 404

    token = file_security.generate_download_token(extraction_id, safe_name)
    db.log_file_access(extraction_id, safe_name, "token_issued", request.remote_addr, True)
    print(f"🔑 Download token issued — extraction={extraction_id} file={safe_name} ip={request.remote_addr}")
    return jsonify({"token": token, "expires_in": 3600})


@app.route("/api/extractions/<int:extraction_id>/files/<path:filename>")
def download_source_file(extraction_id: int, filename: str):
    """
    Serve an original source PDF for download.
    Requires a valid signed token issued by the /token endpoint.
    """
    safe_name = secure_filename(filename)
    if not safe_name:
        return jsonify({"error": "Invalid filename"}), 400

    token = request.args.get("token", "")

    # Validate signed token
    try:
        payload = file_security.verify_download_token(token)
    except ValueError as e:
        db.log_file_access(extraction_id, safe_name, "download_denied", request.remote_addr, False, str(e))
        print(f"🚫 Download denied — extraction={extraction_id} file={safe_name} reason={e} ip={request.remote_addr}")
        return jsonify({"error": "Invalid or expired download link. Please request a new one."}), 401

    # Ensure the token was issued for exactly this file
    if payload.get("eid") != extraction_id or payload.get("fn") != safe_name:
        db.log_file_access(extraction_id, safe_name, "download_denied", request.remote_addr, False, "token_mismatch")
        return jsonify({"error": "Token does not match the requested file."}), 403

    # Resolve file — prefer encrypted, fall back to legacy unencrypted
    enc_path = FILES_FOLDER / str(extraction_id) / (safe_name + ".enc")
    raw_path = FILES_FOLDER / str(extraction_id) / safe_name

    try:
        if enc_path.exists():
            data = file_security.decrypt_file(str(enc_path))
        elif raw_path.exists():
            # Legacy file stored before encryption was enabled
            data = raw_path.read_bytes()
        else:
            db.log_file_access(extraction_id, safe_name, "download", request.remote_addr, False, "not_found")
            return jsonify({"error": "Source file not available."}), 404
    except Exception as e:
        db.log_file_access(extraction_id, safe_name, "download", request.remote_addr, False, str(e))
        print(f"❌ Decrypt error — extraction={extraction_id} file={safe_name}: {e}")
        return jsonify({"error": "Could not retrieve file."}), 500

    db.log_file_access(extraction_id, safe_name, "download", request.remote_addr, True)
    print(f"✅ File downloaded — extraction={extraction_id} file={safe_name} ip={request.remote_addr}")

    return send_file(
        io.BytesIO(data),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=safe_name,
    )


@app.route("/api/extractions/<int:extraction_id>", methods=["DELETE"])
def delete_extraction(extraction_id: int):
    try:
        deleted = db.delete_extraction(extraction_id)
        if not deleted:
            return jsonify({"error": "Extraction not found"}), 404
        # Remove stored source files
        stored_dir = FILES_FOLDER / str(extraction_id)
        if stored_dir.exists():
            shutil.rmtree(str(stored_dir), ignore_errors=True)
        return jsonify({"message": "Extraction deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/extractions/<int:extraction_id>/download")
def download_extraction(extraction_id: int):
    try:
        extraction = db.get_extraction(extraction_id)
        if not extraction:
            return jsonify({"error": "Extraction not found"}), 404

        formatted = extraction.get("formatted_data", {})
        borrower = formatted.get("Borrower1Name", "extraction").replace(" ", "_")
        filename = f"SBA_Extraction_{borrower}_{extraction_id}.json"

        data = json.dumps(formatted, indent=2).encode("utf-8")
        return send_file(
            io.BytesIO(data),
            mimetype="application/json",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Feedback endpoints
# ──────────────────────────────────────────────

@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    data = request.get_json(silent=True) or {}
    extraction_id = data.get("extraction_id")
    field_name = data.get("field_name")
    extracted_value = data.get("extracted_value", "")
    confidence_tier = data.get("confidence_tier")
    reviewer_verdict = data.get("reviewer_verdict")

    if not all([extraction_id, field_name, confidence_tier, reviewer_verdict]):
        return jsonify({"error": "extraction_id, field_name, confidence_tier, reviewer_verdict are required"}), 400
    if confidence_tier not in ("red", "yellow"):
        return jsonify({"error": "confidence_tier must be 'red' or 'yellow'"}), 400
    if reviewer_verdict not in ("correct", "incorrect"):
        return jsonify({"error": "reviewer_verdict must be 'correct' or 'incorrect'"}), 400

    try:
        fid = db.save_feedback(extraction_id, field_name, extracted_value, confidence_tier, reviewer_verdict)
        return jsonify({"feedback_id": fid, "message": "Feedback recorded"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Analytics endpoint
# ──────────────────────────────────────────────

@app.route("/api/analytics")
def get_analytics():
    try:
        return jsonify(db.get_analytics())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics/learning/<field_name>", methods=["DELETE"])
def reset_field_learning(field_name: str):
    try:
        count = db.reset_field_learning(field_name)
        return jsonify({"message": f"Cleared {count} feedback records for '{field_name}'"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# SharePoint endpoints
# ──────────────────────────────────────────────

@app.route("/api/sharepoint/status")
def sharepoint_status():
    from sharepoint.factory import get_status
    return jsonify(get_status())


@app.route("/api/sharepoint/push/<int:extraction_id>", methods=["POST"])
def push_to_sharepoint(extraction_id: int):
    from sharepoint.factory import get_writer

    try:
        extraction = db.get_extraction(extraction_id)
        if not extraction:
            return jsonify({"error": "Extraction not found"}), 404

        writer = get_writer()
        body = request.get_json(silent=True) or {}
        target = body.get("target", "folder")  # "folder" or "list"

        if target == "list":
            result = writer.push_to_list(extraction)
        else:
            result = writer.push_to_folder(extraction)

        mode = getattr(writer, "mode", "live")
        return jsonify({
            "message": f"Successfully pushed to SharePoint ({mode} mode)",
            "mode": mode,
            "result": result,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sharepoint/browse")
def sharepoint_browse():
    """
    Browse the SharePoint document library.
    Optional ?folder=<folder_id> to list files inside a specific folder.
    Without the param, lists top-level folders.
    """
    from sharepoint.factory import get_reader

    try:
        reader = get_reader()
        folder_id = request.args.get("folder")

        if folder_id:
            items = reader.list_pdfs_in_folder(folder_id)
        else:
            items = reader.list_folders()

        return jsonify({
            "mode": getattr(reader, "mode", "live"),
            "folder": folder_id,
            "items": items,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sharepoint/list-items")
def sharepoint_list_items():
    """
    Return all items that have been pushed to the SharePoint List.
    In mock mode, reads from mock_sharepoint_library/list_items.json.
    """
    from sharepoint.factory import get_reader

    try:
        reader = get_reader()
        if not hasattr(reader, "list_items"):
            return jsonify({"error": "list_items not supported in live mode yet"}), 501

        items = reader.list_items()
        return jsonify({
            "mode": getattr(reader, "mode", "live"),
            "count": len(items),
            "items": items,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# File expiration — background thread
# ──────────────────────────────────────────────

def _expire_old_files() -> None:
    """Delete stored file sets older than FILE_RETENTION_DAYS."""
    cutoff = datetime.now() - timedelta(days=FILE_RETENTION_DAYS)
    expired = 0
    try:
        for extraction_dir in FILES_FOLDER.iterdir():
            if not extraction_dir.is_dir():
                continue
            mtime = datetime.fromtimestamp(extraction_dir.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(str(extraction_dir), ignore_errors=True)
                print(f"🗑️  Expired stored files for extraction dir: {extraction_dir.name}")
                expired += 1
        if expired:
            print(f"🗑️  File expiration complete — removed {expired} old extraction set(s)")
    except Exception as e:
        print(f"⚠️  File expiration error: {e}")


def _start_expiration_thread() -> None:
    """Launch a daemon thread that runs file expiration every hour."""
    def _loop():
        while True:
            time.sleep(3600)
            _expire_old_files()
    t = threading.Thread(target=_loop, daemon=True, name="file-expiration")
    t.start()
    print(f"🔒 File expiration thread started — retention: {FILE_RETENTION_DAYS} days")


# ──────────────────────────────────────────────
# Startup
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # Initialize DB
    try:
        db.init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️  Database init failed: {e}")

    _start_expiration_thread()

    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("NODE_ENV") != "production"
    print(f"🚀 SBA Extraction API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
