
import os
import json
import glob
import uuid
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for
)
from flask_login import (
    LoginManager, login_required, current_user
)
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text

from config import Config
from models import (
    db, User, Task, TaskProof, FocusSession,
    DistractionEvent, EmergencyUnlock
)
from routes.auth import auth


# ==========================================
# APP CONFIGURATION
# ==========================================

app = Flask(__name__)
app.config.from_object(Config)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

app.register_blueprint(auth)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHIELD_STATE_FILE = os.path.join(BASE_DIR, "shield_state.json")

PROOF_FOLDER = os.path.join(
    BASE_DIR, "static", "uploads", "proofs"
)

ALLOWED_PROOF_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp"
}


# ==========================================
# WINDOWS PROTECTION STATE
# ==========================================

def update_shield_state(active, blocked_apps=None):

    state = {}

    try:
        with open(SHIELD_STATE_FILE, "r") as file:
            state = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    if blocked_apps is not None:
        state["blocked_apps"] = blocked_apps
    else:
        state.setdefault("blocked_apps", [])

    state["active"] = active

    with open(SHIELD_STATE_FILE, "w") as file:
        json.dump(state, file)


# ==========================================
# APPLICATION DISCOVERY
# ==========================================

def find_installed_application(app_name):

    app_name = app_name.strip()

    if not app_name:
        return None

    app_name = os.path.splitext(app_name)[0]

    try:
        import psutil

        for process in psutil.process_iter(["name", "exe"]):
            try:
                name = process.info.get("name")
                exe = process.info.get("exe")

                if name and os.path.splitext(name)[0].lower() == app_name.lower():
                    return name.lower()

                if exe:
                    exe_name = os.path.basename(exe)

                    if os.path.splitext(exe_name)[0].lower() == app_name.lower():
                        return exe_name.lower()

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    except ImportError:
        pass

    folders = [
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("APPDATA", ""),
        os.path.join(
            os.environ.get("SystemRoot", "C:\\Windows"),
            "System32"
        )
    ]

    for folder in folders:

        if not folder or not os.path.isdir(folder):
            continue

        pattern = os.path.join(folder, "**", app_name + ".exe")

        try:
            matches = glob.glob(pattern, recursive=True)

            if matches:
                return os.path.basename(matches[0]).lower()

        except OSError:
            continue

    start_menu_folders = [
        os.path.join(
            os.environ.get("PROGRAMDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs"
        ),
        os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs"
        )
    ]

    for folder in start_menu_folders:

        if not folder or not os.path.isdir(folder):
            continue

        for shortcut in glob.glob(
            os.path.join(folder, "**", "*.lnk"),
            recursive=True
        ):

            if os.path.splitext(
                os.path.basename(shortcut)
            )[0].lower() == app_name.lower():

                return app_name.lower() + ".exe"

    return None


# ==========================================
# LOGIN MANAGER
# ==========================================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==========================================
# MAIN PAGES
# ==========================================

@app.route("/")
def home():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    return redirect(url_for("auth.login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/health")
def health():
    return jsonify(status="OK")


# ==========================================
# TASK MANAGEMENT
# ==========================================

@app.route("/api/tasks", methods=["GET"])
@login_required
def get_tasks():

    tasks = Task.query.filter_by(
        user_id=current_user.id
    ).order_by(Task.created_at.desc()).all()

    task_list = []

    for task in tasks:

        task_list.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "proof_required": task.proof_required,
            "proofs": [
                {
                    "id": proof.id,
                    "url": url_for(
                        "static",
                        filename="uploads/proofs/" + proof.filename
                    ),
                    "uploaded_at": proof.uploaded_at.isoformat()
                }
                for proof in task.proofs
            ]
        })

    return jsonify(tasks=task_list)


@app.route("/api/tasks", methods=["POST"])
@login_required
def add_task():

    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()

    if not title:
        return jsonify(
            success=False,
            message="Please enter a task title."
        ), 400

    proof_required = data.get("proof_required", False)

    if not isinstance(proof_required, bool):
        proof_required = str(proof_required).lower() in (
            "true", "1", "yes"
        )

    task = Task(
        user_id=current_user.id,
        title=title,
        description=description,
        status="Pending",
        proof_required=proof_required
    )

    db.session.add(task)
    db.session.commit()

    return jsonify(
        success=True,
        message="Task added successfully.",
        task_id=task.id
    )


# ==========================================
# TASK PROOF UPLOAD
# ==========================================

@app.route(
    "/api/tasks/<int:task_id>/proof",
    methods=["POST"]
)
@login_required
def upload_task_proof(task_id):

    task = Task.query.filter_by(
        id=task_id,
        user_id=current_user.id
    ).first()

    if not task:
        return jsonify(
            success=False,
            message="Task not found."
        ), 404

    if not task.proof_required:
        return jsonify(
            success=False,
            message="This task does not require proof."
        ), 400

    files = request.files.getlist("proofs")

    files = [
        file for file in files
        if file and file.filename
    ]

    if not files:
        return jsonify(
            success=False,
            message="Please select at least one screenshot or photo."
        ), 400

    for file in files:

        filename = secure_filename(file.filename)

        if (
            "." not in filename
            or filename.rsplit(".", 1)[1].lower()
            not in ALLOWED_PROOF_EXTENSIONS
        ):
            return jsonify(
                success=False,
                message="Only PNG, JPG, JPEG and WEBP images are allowed."
            ), 400

    os.makedirs(PROOF_FOLDER, exist_ok=True)

    saved_files = []

    try:

        for file in files:

            extension = secure_filename(
                file.filename
            ).rsplit(".", 1)[1].lower()

            unique_filename = (
                uuid.uuid4().hex + "." + extension
            )

            save_path = os.path.join(
                PROOF_FOLDER,
                unique_filename
            )

            file.save(save_path)

            saved_files.append(save_path)

            proof = TaskProof(
                task_id=task.id,
                filename=unique_filename
            )

            db.session.add(proof)

        task.status = "Completed"

        db.session.commit()

    except Exception:

        db.session.rollback()

        for path in saved_files:
            if os.path.exists(path):
                os.remove(path)

        return jsonify(
            success=False,
            message="Proof upload failed. Please try again."
        ), 500

    return jsonify(
        success=True,
        message="Proof submitted successfully. Task completed!",
        status=task.status
    )


# ==========================================
# COMPLETE / UNCOMPLETE TASK
# ==========================================

@app.route(
    "/api/tasks/<int:task_id>/complete",
    methods=["POST"]
)
@login_required
def complete_task(task_id):

    task = Task.query.filter_by(
        id=task_id,
        user_id=current_user.id
    ).first()

    if not task:
        return jsonify(
            success=False,
            message="Task not found."
        ), 404

    if task.status == "Completed":
        task.status = "Pending"

    else:

        if task.proof_required and not task.proofs:
            return jsonify(
                success=False,
                message="Please submit proof before completing this task."
            ), 400

        task.status = "Completed"

    db.session.commit()

    return jsonify(
        success=True,
        message="Task status updated.",
        status=task.status
    )


# ==========================================
# DELETE TASK
# ==========================================

@app.route(
    "/api/tasks/<int:task_id>/delete",
    methods=["POST"]
)
@login_required
def delete_task(task_id):

    task = Task.query.filter_by(
        id=task_id,
        user_id=current_user.id
    ).first()

    if not task:
        return jsonify(
            success=False,
            message="Task not found."
        ), 404

    db.session.delete(task)
    db.session.commit()

    return jsonify(
        success=True,
        message="Task deleted successfully."
    )


# ==========================================
# FOCUS SESSION HISTORY
# ==========================================

@app.route("/api/focus/history", methods=["GET"])
@login_required
def focus_history():

    sessions = FocusSession.query.filter_by(
        user_id=current_user.id
    ).order_by(FocusSession.started_at.desc()).all()

    session_list = []

    for session in sessions:

        session_list.append({
            "id": session.id,
            "status": session.status,
            "duration_seconds": session.duration_seconds or 0,
            "started_at": (
                session.started_at.isoformat()
                if session.started_at else None
            ),
            "ended_at": (
                session.ended_at.isoformat()
                if session.ended_at else None
            )
        })

    return jsonify(
        success=True,
        sessions=session_list
    )


# ==========================================
# FOCUS SESSION - START
# ==========================================

@app.route("/api/focus/start", methods=["POST"])
@login_required
def start_focus():

    existing_session = FocusSession.query.filter_by(
        user_id=current_user.id,
        status="In Progress"
    ).first()

    if existing_session:

        update_shield_state(True)

        return jsonify(
            success=True,
            session_id=existing_session.id,
            message="Existing focus session resumed."
        )

    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id")

    if task_id:

        task = Task.query.filter_by(
            id=task_id,
            user_id=current_user.id
        ).first()

        if not task:
            return jsonify(
                success=False,
                message="Invalid task selected."
            ), 400

    session = FocusSession(
        user_id=current_user.id,
        task_id=task_id if task_id else None,
        started_at=datetime.utcnow(),
        status="In Progress"
    )

    db.session.add(session)
    db.session.commit()

    update_shield_state(True)

    return jsonify(
        success=True,
        session_id=session.id,
        message="Focus session started."
    )


# ==========================================
# FOCUS SESSION - PAUSE
# ==========================================

@app.route("/api/focus/pause", methods=["POST"])
@login_required
def pause_focus():

    data = request.get_json(silent=True) or {}

    try:
        session_id = int(data.get("session_id"))
    except (TypeError, ValueError):
        return jsonify(
            success=False,
            message="Invalid session ID."
        ), 400

    session = FocusSession.query.filter_by(
        id=session_id,
        user_id=current_user.id,
        status="In Progress"
    ).first()

    if not session:
        return jsonify(
            success=False,
            message="Session not found."
        ), 404

    update_shield_state(False)

    return jsonify(
        success=True,
        message="Focus session paused."
    )


# ==========================================
# FOCUS SESSION - RESUME
# ==========================================

@app.route("/api/focus/resume", methods=["POST"])
@login_required
def resume_focus():

    data = request.get_json(silent=True) or {}

    try:
        session_id = int(data.get("session_id"))
    except (TypeError, ValueError):
        return jsonify(
            success=False,
            message="Invalid session ID."
        ), 400

    session = FocusSession.query.filter_by(
        id=session_id,
        user_id=current_user.id,
        status="In Progress"
    ).first()

    if not session:
        return jsonify(
            success=False,
            message="Session not found."
        ), 404

    update_shield_state(True)

    return jsonify(
        success=True,
        message="Focus session resumed."
    )


# ==========================================
# FOCUS SESSION - END
# ==========================================

@app.route("/api/focus/end", methods=["POST"])
@login_required
def end_focus():

    data = request.get_json(silent=True) or {}

    try:
        session_id = int(data.get("session_id"))
        duration = int(data.get("duration_seconds", 0))
    except (TypeError, ValueError):
        return jsonify(
            success=False,
            message="Invalid session information."
        ), 400

    if duration < 0 or duration > 86400:
        return jsonify(
            success=False,
            message="Invalid duration."
        ), 400

    session = FocusSession.query.filter_by(
        id=session_id,
        user_id=current_user.id,
        status="In Progress"
    ).first()

    if not session:
        return jsonify(
            success=False,
            message="Session not found."
        ), 404

    session.ended_at = datetime.utcnow()
    session.duration_seconds = duration
    session.status = "Completed"

    db.session.commit()

    update_shield_state(False)

    return jsonify(
        success=True,
        message="Focus session completed."
    )


# ==========================================
# EMERGENCY UNLOCK
# ==========================================

@app.route(
    "/api/focus/emergency-unlock",
    methods=["POST"]
)
@login_required
def emergency_unlock():

    data = request.get_json(silent=True) or {}

    try:
        session_id = int(data.get("session_id"))
        duration = int(data.get("duration_seconds", 0))
    except (TypeError, ValueError):
        return jsonify(
            success=False,
            message="Invalid session information."
        ), 400

    if duration < 0 or duration > 86400:
        return jsonify(
            success=False,
            message="Invalid duration."
        ), 400

    session = FocusSession.query.filter_by(
        id=session_id,
        user_id=current_user.id,
        status="In Progress"
    ).first()

    if not session:
        return jsonify(
            success=False,
            message="No active focus session found."
        ), 404

    unlock_record = EmergencyUnlock(
        user_id=current_user.id,
        used_at=datetime.utcnow()
    )

    session.ended_at = datetime.utcnow()
    session.duration_seconds = duration
    session.status = "Emergency Unlocked"

    db.session.add(unlock_record)
    db.session.commit()

    update_shield_state(False)

    return jsonify(
        success=True,
        message="Emergency unlock successful. Protection deactivated.",
        remaining_unlocks=None
    )


# ==========================================
# EMERGENCY UNLOCK HISTORY
# ==========================================

@app.route(
    "/api/focus/emergency-unlocks",
    methods=["GET"]
)
@login_required
def emergency_unlock_history():

    records = EmergencyUnlock.query.filter_by(
        user_id=current_user.id
    ).order_by(EmergencyUnlock.used_at.desc()).all()

    return jsonify(
        success=True,
        total_uses=len(records),
        uses=[
            {
                "id": record.id,
                "used_at": record.used_at.isoformat()
            }
            for record in records
        ]
    )


# ==========================================
# APPLICATION SELECTION
# ==========================================

@app.route("/api/apps", methods=["GET"])
@login_required
def get_selected_apps():

    try:
        with open(SHIELD_STATE_FILE, "r") as file:
            state = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state = {}

    return jsonify(
        selected_apps=state.get("blocked_apps", [])
    )


@app.route("/api/apps", methods=["POST"])
@login_required
def save_selected_apps():

    data = request.get_json(silent=True) or {}
    selected_apps = data.get("blocked_apps", [])

    if not isinstance(selected_apps, list):
        return jsonify(
            success=False,
            message="Invalid application selection."
        ), 400

    verified_apps = []

    for app_name in selected_apps:

        if not isinstance(app_name, str):
            continue

        verified = find_installed_application(app_name)

        if not verified:
            return jsonify(
                success=False,
                message=f"Could not locate {app_name} on this computer."
            ), 404

        verified_apps.append(verified)

    try:
        with open(SHIELD_STATE_FILE, "r") as file:
            state = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state = {}

    state["blocked_apps"] = list(dict.fromkeys(verified_apps))
    state.setdefault("active", False)

    with open(SHIELD_STATE_FILE, "w") as file:
        json.dump(state, file)

    return jsonify(
        success=True,
        message="Application selection saved successfully.",
        selected_apps=verified_apps
    )


# ==========================================
# DATABASE INITIALIZATION + SAFE MIGRATION
# ==========================================

with app.app_context():

    os.makedirs(
        os.path.join(BASE_DIR, "instance"),
        exist_ok=True
    )

    os.makedirs(PROOF_FOLDER, exist_ok=True)

    db.create_all()

    # Add the new proof_required column to an existing database.
    # Existing task records are preserved and default to False.

    inspector = inspect(db.engine)

    if "task" in inspector.get_table_names():

        task_columns = [
            column["name"]
            for column in inspector.get_columns("task")
        ]

        if "proof_required" not in task_columns:

            db.session.execute(
                text(
                    "ALTER TABLE task "
                    "ADD COLUMN proof_required BOOLEAN NOT NULL DEFAULT 0"
                )
            )

            db.session.commit()


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":
    app.run(debug=True)
