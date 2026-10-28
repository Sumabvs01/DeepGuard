
from flask import Flask, request, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import uuid
import shutil

import cv2

from deepfake_detector import predict_image, predict_video

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
FRAMES_DIR = DATA_DIR / "frames"
REPORTS_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "deepguard.db"

for folder in (UPLOAD_DIR, FRAMES_DIR, REPORTS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp",
    "mp4", "mov", "avi", "mkv", "webm",
}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}


# --------------------------------------------------
# Database
# --------------------------------------------------

def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables and repair an older extras-table schema."""
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS screenings (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                media_type TEXT NOT NULL,
                status TEXT NOT NULL,
                model_status TEXT NOT NULL,
                result_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                file_size INTEGER NOT NULL
            )
        """)

        table_exists = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'screening_extras'
        """).fetchone()

        if not table_exists:
            conn.execute("""
                CREATE TABLE screening_extras (
                    scan_id TEXT PRIMARY KEY,
                    duration_seconds REAL DEFAULT 0,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    frame_count INTEGER DEFAULT 0,
                    report_filename TEXT DEFAULT ''
                )
            """)
        else:
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(screening_extras)"
                ).fetchall()
            }

            if "scan_id" not in columns:
                # Preserve the old table as a backup and create the
                # correct table. Existing scan history is not deleted.
                conn.execute("""
                    ALTER TABLE screening_extras
                    RENAME TO screening_extras_legacy
                """)

                conn.execute("""
                    CREATE TABLE screening_extras (
                        scan_id TEXT PRIMARY KEY,
                        duration_seconds REAL DEFAULT 0,
                        width INTEGER DEFAULT 0,
                        height INTEGER DEFAULT 0,
                        frame_count INTEGER DEFAULT 0,
                        report_filename TEXT DEFAULT ''
                    )
                """)

            else:
                expected_columns = {
                    "duration_seconds": "REAL DEFAULT 0",
                    "width": "INTEGER DEFAULT 0",
                    "height": "INTEGER DEFAULT 0",
                    "frame_count": "INTEGER DEFAULT 0",
                    "report_filename": "TEXT DEFAULT ''",
                }

                for name, definition in expected_columns.items():
                    if name not in columns:
                        conn.execute(
                            f"ALTER TABLE screening_extras "
                            f"ADD COLUMN {name} {definition}"
                        )


# --------------------------------------------------
# Media helpers
# --------------------------------------------------

def extension_of(filename):
    return Path(filename).suffix.lower().lstrip(".")


def is_video(filename):
    return extension_of(filename) in VIDEO_EXTENSIONS


def extract_video_frames(video_path, scan_id, max_frames=12):
    """Extract up to 12 evenly spaced video frames."""
    frame_folder = FRAMES_DIR / scan_id
    frame_folder.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        cap.release()
        raise ValueError(
            "The uploaded video could not be opened. "
            "Try an MP4 video encoded with H.264."
        )

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    duration = total_frames / fps if fps > 0 else 0
    frames = []

    try:
        if total_frames > 0:
            count = min(max_frames, total_frames)

            if count == 1:
                positions = [0]
            else:
                positions = [
                    round(i * (total_frames - 1) / (count - 1))
                    for i in range(count)
                ]

            for index, position in enumerate(positions, start=1):
                cap.set(cv2.CAP_PROP_POS_FRAMES, position)
                success, frame = cap.read()

                if not success:
                    continue

                frame_name = f"frame_{index:02d}.jpg"
                frame_path = frame_folder / frame_name

                if cv2.imwrite(str(frame_path), frame):
                    timestamp = position / fps if fps > 0 else 0
                    frames.append({
                        "filename": frame_name,
                        "timestamp_seconds": round(timestamp, 2),
                        "url": (
                            f"/api/frames/{scan_id}/{frame_name}"
                        ),
                    })
    finally:
        cap.release()

    return {
        "duration_seconds": round(duration, 2),
        "width": width,
        "height": height,
        "frames": frames,
    }


# --------------------------------------------------
# PDF reports
# --------------------------------------------------

def generate_pdf_report(
    scan_id, filename, media_type, file_size, created_at, video_info
):
    report_name = f"{scan_id}.pdf"
    report_path = REPORTS_DIR / report_name
    styles = getSampleStyleSheet()

    story = [
        Paragraph("DeepGuard Media Scan Report", styles["Title"]),
        Spacer(1, 16),
        Paragraph(
            "This report contains media metadata and processing details. "
            "It does not establish whether the media is authentic or fake.",
            styles["BodyText"],
        ),
        Spacer(1, 16),
    ]

    rows = [
        ["Field", "Value"],
        ["Scan ID", scan_id],
        ["Filename", filename],
        ["Media type", media_type],
        ["File size", f"{file_size:,} bytes"],
        ["Scanned at", created_at],
        ["AI model status", "Not connected"],
        ["Detection result", "Not evaluated"],
    ]

    if media_type == "video":
        rows.extend([
            [
                "Duration",
                f"{video_info['duration_seconds']} seconds",
            ],
            [
                "Resolution",
                f"{video_info['width']} × {video_info['height']}",
            ],
            ["Extracted frames", str(len(video_info["frames"]))],
        ])

    table = Table(rows, colWidths=[140, 340])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#242424")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(table)

    SimpleDocTemplate(
        str(report_path),
        pagesize=letter,
        title="DeepGuard Scan Report",
    ).build(story)

    return report_name


# --------------------------------------------------
# Serialize history records
# --------------------------------------------------

def serialize_screening(row, extra=None):
    record = dict(row)
    extra = dict(extra) if extra else {}

    record["duration_seconds"] = extra.get("duration_seconds", 0)
    record["width"] = extra.get("width", 0)
    record["height"] = extra.get("height", 0)
    record["frame_count"] = extra.get("frame_count", 0)

    report_name = extra.get("report_filename", "")
    record["report_url"] = (
        f"/api/report/{record['id']}" if report_name else None
    )

    record["frames"] = []

    if record["media_type"] == "video":
        frame_folder = FRAMES_DIR / record["id"]

        if frame_folder.is_dir():
            for frame_path in sorted(frame_folder.glob("*.jpg")):
                record["frames"].append({
                    "filename": frame_path.name,
                    "url": (
                        f"/api/frames/{record['id']}/"
                        f"{frame_path.name}"
                    ),
                })

    return record


# --------------------------------------------------
# Main pages and status
# --------------------------------------------------

@app.get("/")
def home():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/status")
def api_status():
    with connect_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM screenings"
        ).fetchone()[0]

    return jsonify({
        "ok": True,
        "service": "DeepGuard",
        "total_screenings": total,
        "detection_model": "not_connected",
    })


# --------------------------------------------------
# Scan history
# --------------------------------------------------

@app.get("/api/screenings")
def get_screenings():
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT * FROM screenings
            ORDER BY created_at DESC
        """).fetchall()

        results = []

        for row in rows:
            extra = conn.execute("""
                SELECT * FROM screening_extras
                WHERE scan_id = ?
            """, (row["id"],)).fetchone()

            results.append(serialize_screening(row, extra))

    return jsonify(results)


# --------------------------------------------------
# Upload and process media
# --------------------------------------------------

@app.post("/api/screen")
def screen_media():
    uploaded = request.files.get("file")

    if not uploaded or not uploaded.filename:
        return jsonify({
            "error": "Choose an image or video first."
        }), 400

    original_name = secure_filename(uploaded.filename)

    if not original_name:
        return jsonify({"error": "Invalid filename."}), 400

    ext = extension_of(original_name)

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": "Unsupported file type."
        }), 400

    scan_id = str(uuid.uuid4())
    saved_path = UPLOAD_DIR / f"{scan_id}.{ext}"
    uploaded.save(saved_path)

    file_size = saved_path.stat().st_size
    created_at = datetime.now(timezone.utc).isoformat()
    media_type = "video" if is_video(original_name) else "image"

    video_info = {
        "duration_seconds": 0,
        "width": 0,
        "height": 0,
        "frames": [],
    }

    try:
        if media_type == "video":
            video_info = extract_video_frames(saved_path, scan_id)

        # AI analysis is optional: preserve the scan even if the model fails.
        ai_result = {
            "prediction": "INCONCLUSIVE",
            "confidence": None,
            "status": "unavailable",
            "warning": "AI analysis could not be completed.",
        }

        try:
            if media_type == "image":
                ai_result = predict_image(saved_path)
            else:
                frame_paths = [
                    FRAMES_DIR / scan_id / frame["filename"]
                    for frame in video_info["frames"]
                ]
                ai_result = predict_video(frame_paths)

            ai_result["status"] = (
                "completed"
                if ai_result.get("prediction") in ("REAL", "FAKE")
                else "unavailable"
            )
        except Exception:
            app.logger.exception("AI detection failed")
            ai_result = {
                "prediction": "INCONCLUSIVE",
                "confidence": None,
                "status": "unavailable",
                "warning": "AI model failed; no verdict was produced.",
            }

        report_name = generate_pdf_report(
            scan_id,
            original_name,
            media_type,
            file_size,
            created_at,
            video_info,
        )

        with connect_db() as conn:
            conn.execute("""
                INSERT INTO screenings (
                    id, filename, media_type, status, model_status,
                    result_label, created_at, file_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id,
                original_name,
                media_type,
                "processed",
                ai_result.get("status", "unavailable"),
                ai_result.get("prediction", "INCONCLUSIVE"),
                created_at,
                file_size,
            ))

            conn.execute("""
                INSERT OR REPLACE INTO screening_extras (
                    scan_id, duration_seconds, width, height,
                    frame_count, report_filename
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                scan_id,
                video_info["duration_seconds"],
                video_info["width"],
                video_info["height"],
                len(video_info["frames"]),
                report_name,
            ))

        return jsonify({
            "ok": True,
            "scan_id": scan_id,
            "filename": original_name,
            "media_type": media_type,
            "file_size": file_size,
            "created_at": created_at,
            "duration_seconds": video_info["duration_seconds"],
            "width": video_info["width"],
            "height": video_info["height"],
            "frame_count": len(video_info["frames"]),
            "frames": video_info["frames"],
            "report_url": f"/api/report/{scan_id}",
            "ai_result": ai_result,
            "notice": (
                "AI screening completed. This is a model estimate, "
                "not proof of authenticity."
                if ai_result.get("status") == "completed"
                else "Media saved, but AI screening was unavailable."
            ),
        })

    except Exception:
        app.logger.exception("Media processing failed")

        saved_path.unlink(missing_ok=True)
        shutil.rmtree(FRAMES_DIR / scan_id, ignore_errors=True)
        (REPORTS_DIR / f"{scan_id}.pdf").unlink(missing_ok=True)

        return jsonify({
            "error": (
                "Media processing failed. Check the Terminal for details."
            )
        }), 500


# --------------------------------------------------
# View extracted frames
# --------------------------------------------------

@app.get("/api/frames/<scan_id>/<path:filename>")
def get_frame(scan_id, filename):
    folder = FRAMES_DIR / scan_id

    if not folder.is_dir():
        abort(404)

    safe_name = secure_filename(filename)

    if safe_name != filename or not safe_name.lower().endswith(".jpg"):
        abort(404)

    return send_from_directory(folder, safe_name)


# --------------------------------------------------
# Download PDF report
# --------------------------------------------------

@app.get("/api/report/<scan_id>")
def get_report(scan_id):
    with connect_db() as conn:
        row = conn.execute("""
            SELECT report_filename
            FROM screening_extras
            WHERE scan_id = ?
        """, (scan_id,)).fetchone()

    if not row or not row["report_filename"]:
        abort(404)

    return send_from_directory(
        REPORTS_DIR,
        row["report_filename"],
        as_attachment=True,
    )


# --------------------------------------------------
# Delete a scan and its associated files
# --------------------------------------------------

@app.delete("/api/screenings/<scan_id>")
def delete_screening(scan_id):
    with connect_db() as conn:
        exists = conn.execute(
            "SELECT id FROM screenings WHERE id = ?",
            (scan_id,),
        ).fetchone()

        if not exists:
            return jsonify({"error": "Scan not found."}), 404

        conn.execute(
            "DELETE FROM screenings WHERE id = ?", (scan_id,)
        )
        conn.execute(
            "DELETE FROM screening_extras WHERE scan_id = ?",
            (scan_id,),
        )

    for path in UPLOAD_DIR.glob(f"{scan_id}.*"):
        path.unlink(missing_ok=True)

    shutil.rmtree(FRAMES_DIR / scan_id, ignore_errors=True)
    (REPORTS_DIR / f"{scan_id}.pdf").unlink(missing_ok=True)

    return jsonify({"ok": True, "deleted": scan_id})


# --------------------------------------------------
# Upload size error
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({
        "error": "File is too large. Maximum upload size is 200 MB."
    }), 413


# --------------------------------------------------
# Initialize database and start Flask
# --------------------------------------------------

init_db()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=3000,
        debug=False,
    )
