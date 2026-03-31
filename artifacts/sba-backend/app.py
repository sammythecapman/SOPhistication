"""
SBA Loan Data Extraction Tool — Flask Backend
Serves all extraction API endpoints at /api
"""

import os
import uuid
import json
import threading
import shutil
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

import db
from extraction.pipeline import run_extraction_pipeline

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────

app = Flask(__name__)
CORS(app, origins="*")

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

FILES_FOLDER = Path(__file__).parent / "stored_files"
FILES_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}

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

        # Persist uploaded PDFs so they can be downloaded later
        dest_dir = FILES_FOLDER / str(extraction_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(terms_path, dest_dir / Path(terms_path).name)
            if memo_path and Path(memo_path).exists():
                shutil.copy2(memo_path, dest_dir / Path(memo_path).name)
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
                    "fields_populated": result["summary"]["fields_populated"],
                    "fields_total": result["summary"]["fields_total"],
                    "completion_pct": result["summary"]["completion_percentage"],
                    "created_at": datetime.now().isoformat(),
                },
            })
    except Exception as e:
        with _job_store_lock:
            _job_store[job_id].update({
                "status": "failed",
                "stage": "failed",
                "stage_label": "Failed",
                "progress": 0,
                "error": str(e),
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


@app.route("/api/extractions/<int:extraction_id>/files/<path:filename>")
def download_source_file(extraction_id: int, filename: str):
    """Serve an original source PDF for download."""
    safe_name = secure_filename(filename)
    if not safe_name:
        return jsonify({"error": "Invalid filename"}), 400

    file_path = FILES_FOLDER / str(extraction_id) / safe_name
    if not file_path.exists():
        return jsonify({"error": "Source file not available. It may have been uploaded before file storage was enabled."}), 404

    return send_file(
        str(file_path),
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

        import io
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
# SharePoint endpoints (placeholder)
# ──────────────────────────────────────────────

@app.route("/api/sharepoint/status")
def sharepoint_status():
    from sharepoint.auth import SharePointAuth
    auth = SharePointAuth()
    return jsonify({
        "configured": auth.is_configured,
        "message": "SharePoint integration ready" if auth.is_configured
        else "SharePoint credentials not configured. Set SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET, SHAREPOINT_TENANT_ID, and SHAREPOINT_SITE_URL environment variables.",
    })


@app.route("/api/sharepoint/push/<int:extraction_id>", methods=["POST"])
def push_to_sharepoint(extraction_id: int):
    from sharepoint.auth import SharePointAuth
    from sharepoint.writer import SharePointWriter

    auth = SharePointAuth()
    if not auth.is_configured:
        return jsonify({"error": "SharePoint is not configured"}), 503

    try:
        extraction = db.get_extraction(extraction_id)
        if not extraction:
            return jsonify({"error": "Extraction not found"}), 404

        writer = SharePointWriter()
        target = request.json.get("target", "folder")  # "folder" or "list"

        if target == "list":
            result = writer.push_to_list(extraction)
        else:
            result = writer.push_to_folder(extraction)

        return jsonify({"message": "Successfully pushed to SharePoint", "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("NODE_ENV") != "production"
    print(f"🚀 SBA Extraction API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
