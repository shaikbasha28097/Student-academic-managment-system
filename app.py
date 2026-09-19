# ============================================================
# app.py – SAMS 4th Year Project (Python / Flask Backend)
# Converted from PHP (3rd Year) → Python (4th Year)
# Database: drk_college (MySQL via XAMPP – unchanged)
# ============================================================

import os
import re
import csv
import json as _json
import random
import smtplib
import io
from decimal import Decimal
from datetime import datetime, timedelta, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import mysql.connector
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, send_file, send_from_directory, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import config
import jntuh_scraper

# ── App Initialisation ────────────────────────────────────────
app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)


@app.route("/uploads/<path:filename>")
def serve_uploads(filename):
    """Serve uploaded files (timetable, materials, academic calendar, etc.)."""
    return send_from_directory(config.UPLOAD_FOLDER, os.path.basename(filename))


# Custom JSON encoder to handle Decimal and Datetime types globally
from flask.json.provider import DefaultJSONProvider


class _SAMSEncoder(_json.JSONEncoder):
    """JSON encoder that handles Decimal and date/datetime objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

app.json = CustomJSONProvider(app)


# ── URL Prefix Handling ────────────────────────────────────────
@app.before_request
def handle_path_prefix():
    path = request.path
    # Check if the path begins with the project's folder name
    for prefix in ["/sams 4th year project", "/SAMS 4th year project"]:
        if path.startswith(prefix):
            # Strip the prefix from the path
            new_path = path[len(prefix):]
            if not new_path:
                new_path = "/"
            # Re-append query parameters if they exist
            if request.query_string:
                new_path += "?" + request.query_string.decode("utf-8")
            return redirect(new_path)


def _safe_tojson(value):
    """Jinja2 tojson filter that handles Decimal/datetime safely."""
    return _json.dumps(value, cls=_SAMSEncoder, ensure_ascii=False)

# Override the built-in tojson Jinja2 filter so templates work correctly
app.jinja_env.filters["tojson"] = _safe_tojson



@app.route("/styles.css")
def serve_styles():
    return send_file("styles.css", mimetype="text/css")


# ── DB Helper ─────────────────────────────────────────────────
def get_db():
    """Return a per-request MySQL connection (stored on Flask g)."""
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            autocommit=True,
            connection_timeout=5,
        )
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def query(sql, params=(), one=False, fetchall=False, commit=False):
    """Execute a query and optionally return results."""
    try:
        db = get_db()
        cur = db.cursor(dictionary=True, buffered=True)
        try:
            cur.execute(sql, params)
            if commit:
                db.commit()
                return None
            if fetchall:
                return cur.fetchall()
            if one:
                return cur.fetchone()
            return cur.fetchall()
        finally:
            cur.close()
    except Exception:
        return [] if fetchall else None


def query_many(sql, rows):
    """Execute many INSERT/UPDATE statements."""
    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        for row in rows:
            cur.execute(sql, row)
        db.commit()
    finally:
        cur.close()


def verify_password(stored_hash, provided_password, role="student"):
    """Verify a password against several common formats used by old PHP apps and Flask."""
    if not stored_hash or not provided_password:
        return False

    if isinstance(stored_hash, (bytes, bytearray)):
        stored_hash = stored_hash.decode("utf-8", errors="ignore")
    if not isinstance(stored_hash, str):
        stored_hash = str(stored_hash)

    candidate = stored_hash.strip()

    try:
        if check_password_hash(candidate, provided_password):
            return True
    except Exception:
        pass

    if candidate == provided_password:
        return True

    if role == "admin" and candidate == provided_password:
        return True

    if candidate.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt as _bcrypt
            # PHP uses $2y$, Python bcrypt uses $2b$ – they are interchangeable
            adjusted = candidate.replace("$2y$", "$2b$", 1)
            if _bcrypt.checkpw(provided_password.encode("utf-8"), adjusted.encode("utf-8")):
                return True
        except Exception:
            pass

    # Support legacy unsalted hashes used by older PHP projects.
    import hashlib
    for algo in ("md5", "sha1", "sha256"):
        try:
            if hashlib.new(algo, provided_password.encode("utf-8")).hexdigest() == candidate:
                return True
        except Exception:
            pass

    # Some older PHP projects stored passwords in plain text in the DB.
    if candidate.lower() in {provided_password.lower(), provided_password}:
        return True

    return False


def ensure_schema():
    """Create the expected tables and columns if they do not already exist."""
    try:
        query(
            """
            CREATE TABLE IF NOT EXISTS admin (
                id VARCHAR(50) PRIMARY KEY,
                password TEXT NOT NULL
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100),
                department VARCHAR(50),
                year VARCHAR(10),
                section VARCHAR(10),
                phone VARCHAR(20),
                password TEXT NOT NULL,
                dob DATE DEFAULT NULL
            )
            """,
            commit=True,
        )
        # Add dob column if it doesn't exist (for older databases)
        try:
            query("ALTER TABLE students ADD COLUMN dob DATE DEFAULT NULL", commit=True)
        except Exception:
            pass
        query(
            """
            CREATE TABLE IF NOT EXISTS faculty (
                faculty_id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100),
                phone VARCHAR(20),
                password TEXT NOT NULL,
                role VARCHAR(50) DEFAULT 'Academic'
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id VARCHAR(50) NOT NULL,
                department VARCHAR(50),
                year VARCHAR(10),
                section VARCHAR(10),
                semester VARCHAR(10),
                attendance_date DATE,
                class_name VARCHAR(100),
                status VARCHAR(20),
                reason VARCHAR(255) DEFAULT '',
                marked_by VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_attendance (student_id, attendance_date, class_name, semester)
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS exam_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id VARCHAR(50) NOT NULL,
                student_name VARCHAR(100),
                department VARCHAR(50),
                year VARCHAR(10),
                section VARCHAR(10),
                subject_name VARCHAR(100),
                exam_type VARCHAR(50),
                semester VARCHAR(10),
                total_marks INT DEFAULT 0,
                descriptive_marks INT DEFAULT 0,
                objective_marks INT DEFAULT 0,
                Assignment_marks INT DEFAULT 0,
                ppt_marks INT DEFAULT 0,
                internal_marks INT DEFAULT 0,
                external_marks INT DEFAULT 0,
                points INT DEFAULT 0,
                grade VARCHAR(5) DEFAULT '',
                passed VARCHAR(10) DEFAULT 'Fail',
                subject_code VARCHAR(20) DEFAULT '',
                credits FLOAT DEFAULT 0,
                UNIQUE KEY uk_exam_results (student_id, exam_type, subject_name, semester)
            )
            """,
            commit=True,
        )
        try:
            query("ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS internal_marks INT DEFAULT 0", commit=True)
            query("ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS external_marks INT DEFAULT 0", commit=True)
            query("ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS points INT DEFAULT 0", commit=True)
            query("ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS grade VARCHAR(5) DEFAULT ''", commit=True)
            query("ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS passed VARCHAR(10) DEFAULT 'Fail'", commit=True)
            query("ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS subject_code VARCHAR(20) DEFAULT ''", commit=True)
            query("ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS credits FLOAT DEFAULT 0", commit=True)
        except Exception:
            pass
        query(
            """
            CREATE TABLE IF NOT EXISTS tuition_fees (
                student_id VARCHAR(50) PRIMARY KEY,
                student_name VARCHAR(100),
                total_fee DECIMAL(10,2) DEFAULT 0,
                other_free DECIMAL(10,2) DEFAULT 0,
                paid_fee DECIMAL(10,2) DEFAULT 0,
                remaining_fee DECIMAL(10,2) DEFAULT 0,
                payment_status VARCHAR(20) DEFAULT 'Pending'
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS fee_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id VARCHAR(50),
                updated_by VARCHAR(50),
                paid_amount DECIMAL(10,2) DEFAULT 0,
                remaining_balance DECIMAL(10,2) DEFAULT 0,
                payment_status VARCHAR(20) DEFAULT 'Pending',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS department_files (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255),
                file_path VARCHAR(500),
                file_type VARCHAR(50),
                department VARCHAR(50),
                year VARCHAR(10),
                section VARCHAR(10),
                category VARCHAR(50),
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS faculty_assignments (
                assignment_id INT AUTO_INCREMENT PRIMARY KEY,
                faculty_id VARCHAR(50),
                department VARCHAR(50),
                year VARCHAR(10),
                semester VARCHAR(10),
                section VARCHAR(10),
                subject_name VARCHAR(100)
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS forgot_password (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(50),
                role VARCHAR(20),
                otp INT,
                email VARCHAR(100),
                phone VARCHAR(20),
                expires_at DATETIME,
                is_verified TINYINT(1) DEFAULT 0
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS allowed_students (
                student_id VARCHAR(50) PRIMARY KEY
            )
            """,
            commit=True,
        )
        query(
            """
            CREATE TABLE IF NOT EXISTS jntuh_cache (
                roll_number VARCHAR(20) PRIMARY KEY,
                student_name VARCHAR(100),
                cgpa DECIMAL(4,2),
                total_credits DECIMAL(5,1),
                sem_count INT,
                results_json LONGTEXT,
                raw_json LONGTEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                expires_at DATETIME
            )
            """,
            commit=True,
        )

        existing_admin = query("SELECT id FROM admin WHERE id=%s", ("admin",), one=True)
        if not existing_admin:
            query(
                "INSERT INTO admin (id, password) VALUES (%s, %s)",
                ("admin", generate_password_hash("admin123")),
                commit=True,
            )
    except Exception:
        pass


# ── Email OTP Helper ──────────────────────────────────────────
# Schema setup is intentionally lazy. Running it while importing this module
# can prevent Flask from binding its port when MySQL is unavailable.
_schema_initialized = False


@app.before_request
def initialize_database():
    global _schema_initialized
    if not _schema_initialized:
        ensure_schema()
        _schema_initialized = True


def send_otp_email(to_email: str, otp: int) -> bool:
    """Send OTP via Gmail SMTP. Returns True on success."""
    try:
        msg = MIMEMultipart()
        msg["From"] = config.SMTP_FROM
        msg["To"] = to_email
        msg["Subject"] = "Password Reset OTP - SAMS"
        body = (
            f"Hello,\n\nYour OTP for password reset is: {otp}\n\n"
            "This OTP will expire in 5 minutes.\n\nThank you,\nSAMS Admin"
        )
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, to_email, msg.as_string())
        return True
    except Exception:
        return False


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS
    )


def _grade_from_total(total):
    """Convert a total mark into a grade for faculty exam entry."""
    total = int(total or 0)
    if total >= 90:
        return "O"
    if total >= 80:
        return "A+"
    if total >= 70:
        return "A"
    if total >= 60:
        return "B+"
    if total >= 50:
        return "B"
    if total >= 40:
        return "C"
    return "F"


# ── Auth Guards ───────────────────────────────────────────────
def require_role(role):
    if session.get("role") != role:
        return redirect(url_for("login"))
    return None


# ════════════════════════════════════════════════════════════════
# PUBLIC ROUTES – Registration & Login
# ════════════════════════════════════════════════════════════════

@app.route("/")
def home_page():
    return render_template("index.html")


@app.route("/register_page")
def register_page():
    error = request.args.get("error", "")
    success = request.args.get("success", "")
    return render_template("Register.html", error=error, success=success)


@app.route("/register", methods=["GET", "POST"])
@app.route("/register/", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        error = request.args.get("error", "")
        success = request.args.get("success", "")
        return render_template("Register.html", error=error, success=success)

    role        = request.form.get("role", "")
    name        = request.form.get("name", "").strip()
    email       = request.form.get("email", "").strip()
    phone       = request.form.get("phone", "").strip()
    password_raw= request.form.get("password", "")

    if not all([role, name, email, phone, password_raw]):
        return redirect(url_for("register_page", error="All fields are required"))

    password_hash = generate_password_hash(password_raw)

    if role == "student":
        student_id = request.form.get("student_id", "").strip().upper()
        department = request.form.get("department", "")
        year       = request.form.get("year", "")
        section    = request.form.get("section", "")

        # Validate student ID format
        if not re.match(r'^[0-9A-Za-z]+$', student_id):
            return redirect(url_for("register_page", error="Invalid Student ID format."))

        # Check pre-approval
        allowed = query("SELECT student_id FROM allowed_students WHERE student_id=%s", (student_id,), one=True)
        if not allowed:
            return redirect(url_for("register_page", error="Student ID is not pre-approved by Admin."))

        # Check duplicate
        exists = query("SELECT student_id FROM students WHERE student_id=%s", (student_id,), one=True)
        if exists:
            return redirect(url_for("register_page", error="Student ID already exists"))

        dob = request.form.get("dob", "").strip() or None

        query(
            "INSERT INTO students (student_id, name, email, department, year, section, phone, password, dob) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (student_id, name, email, department, year, section, phone, password_hash, dob),
            commit=True,
        )
        return redirect(url_for("login", success="Student registered successfully. Please login."))

    elif role == "faculty":
        faculty_id = request.form.get("faculty_id", "").strip().upper()
        if not faculty_id:
            return redirect(url_for("register_page", error="Faculty ID is required"))

        exists = query("SELECT faculty_id FROM faculty WHERE faculty_id=%s", (faculty_id,), one=True)
        if exists:
            return redirect(url_for("register_page", error="Faculty ID already exists"))

        query(
            "INSERT INTO faculty (faculty_id, name, email, phone, password) VALUES (%s,%s,%s,%s,%s)",
            (faculty_id, name, email, phone, password_hash),
            commit=True,
        )
        return redirect(url_for("login", success="Faculty registered successfully. Please login."))

    return redirect(url_for("register_page"))


@app.route("/login")
def login():
    error   = request.args.get("error", "")
    success = request.args.get("success", "")
    return render_template("login.html", error=error, success=success)


@app.route("/login_check", methods=["POST"])
def login_check():
    user_id  = request.form.get("user_id", "").strip()
    password = request.form.get("password", "")
    role     = request.form.get("role", "")

    if not role:
        return redirect(url_for("login", error="Please select Student, Faculty, or Admin"))
    if not user_id or not password:
        return redirect(url_for("login", error="All fields are required"))

    if role == "student":
        user = query("SELECT student_id AS id, password FROM students WHERE student_id=%s", (user_id,), one=True)
    elif role == "faculty":
        user = query("SELECT faculty_id AS id, password FROM faculty WHERE faculty_id=%s", (user_id,), one=True)
    elif role == "admin":
        user = query("SELECT id, password FROM admin WHERE id=%s", (user_id,), one=True)
    else:
        return redirect(url_for("login", error="Invalid role selected"))

    if not user:
        return redirect(url_for("login", error="Invalid ID or Password"))

    stored_hash = user["password"]
    if not verify_password(stored_hash, password, role=role):
        msg = "Invalid Admin Credentials" if role == "admin" else "Invalid ID or Password"
        return redirect(url_for("login", error=msg))

    session["user_id"] = user_id
    session["role"]    = role

    if role == "student":
        return redirect(url_for("student_dashboard"))
    elif role == "faculty":
        return redirect(url_for("faculty_dashboard"))
    else:
        return redirect(url_for("admin_dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _normalize_jntuh_results(results):
    """Return a stable subject schema without mixing student and subject fields."""
    normalized = []
    for semester in results or []:
        subjects = []
        for subject in semester.get('subjects', []):
            code = str(subject.get('code') or subject.get('subject_code') or '').strip().upper()
            name = str(subject.get('name') or subject.get('subject_name') or '').strip()
            marks = str(subject.get('marks') or subject.get('total') or subject.get('total_marks') or '').strip()
            internal = str(subject.get('internal') or subject.get('int_marks') or '').strip()
            external = str(subject.get('external') or subject.get('ext_marks') or '').strip()
            grade = str(subject.get('grade') or '').strip().upper()
            credits = subject.get('credits', 0)
            passed = subject.get('passed')
            if passed is None:
                passed = grade not in {'F', 'AB', 'ABSENT', 'W', '--', ''}
            result = str(subject.get('result') or subject.get('status') or ('PASS' if passed else 'FAIL')).strip().upper()
            subjects.append({
                **subject,
                'code': code,
                'subject_code': code,
                'name': name,
                'subject_name': name,
                'marks': marks,
                'internal': internal,
                'external': external,
                'grade': grade,
                'credits': credits,
                'passed': bool(passed),
                'result': result,
            })
        normalized.append({**semester, 'subjects': subjects})
    return normalized


def _sync_jntuh_student_name(roll_number, student_name):
    """Keep the registered student name aligned with the official JNTUH name."""
    clean_name = str(student_name or '').strip()
    if not clean_name or not roll_number:
        return
    if re.fullmatch(r'\d{2}[A-Z0-9]{6,}', clean_name, re.IGNORECASE):
        return
    query(
        "UPDATE students SET name=%s WHERE student_id=%s",
        (clean_name, roll_number),
        commit=True,
    )


@app.route("/jntuh_results", methods=["POST"])
def jntuh_results():
    """Fetch JNTUH results for a roll number. Uses MySQL cache (24h) then live Playwright scrape."""
    roll = (request.form.get("roll_number") or request.form.get("roll") or "").strip().upper()
    dob  = request.form.get("dob", "").strip()       # YYYY/MM/DD or YYYY-MM-DD
    force_refresh = (request.form.get("force_refresh") in ("true", "1")) or (request.form.get("force_live") in ("true", "1"))

    if not roll or len(roll) < 8:
        return jsonify({'success': False, 'error': 'Invalid roll number. Example: 21U51A0501'})

    roll = re.sub(r'[^A-Z0-9]', '', roll)

    # 1. Check MySQL cache first (unless force_refresh)
    if not force_refresh:
        try:
            cached = query(
                "SELECT * FROM jntuh_cache WHERE roll_number=%s AND (expires_at IS NULL OR expires_at > NOW())",
                (roll,), one=True
            )
            cached_name = str(cached.get('student_name') or '').strip() if cached else ''
            cached_name_is_roll = bool(re.fullmatch(r'\d{2}[A-Z0-9]{6,}', cached_name, re.IGNORECASE))
            if cached and cached.get('results_json') and cached_name and not cached_name_is_roll:
                results_data = _json.loads(cached['results_json'])
                cached_subjects = [
                    subject
                    for semester in results_data
                    for subject in semester.get('subjects', [])
                ]
                cached_schema_valid = bool(cached_subjects) and all(
                    str(subject.get('code') or subject.get('subject_code') or '').strip()
                    and str(subject.get('name') or subject.get('subject_name') or '').strip()
                    and str(subject.get('marks') or subject.get('total') or subject.get('total_marks') or '').strip()
                    and str(subject.get('grade') or '').strip()
                    and subject.get('credits') is not None
                    for subject in cached_subjects
                )
                if not cached_schema_valid:
                    raise ValueError('Cached JNTUH results do not contain the complete subject schema')
                cgpa_summary = jntuh_scraper._compute_cgpa(results_data)
                _sync_jntuh_student_name(roll, cached['student_name'])
                fetched_str = (
                    cached['fetched_at'].isoformat()
                    if hasattr(cached.get('fetched_at'), 'isoformat')
                    else str(cached.get('fetched_at', ''))
                )
                return jsonify({
                    'success': True,
                    'cached': True,
                    'roll': cached['roll_number'],
                    'name': cached['student_name'],
                    'jntuh_name': cached['student_name'],
                    'cgpa': cgpa_summary['cgpa'],
                    'totalCredits': cgpa_summary['totalCredits'],
                    'backlogsCount': cgpa_summary['backlogsCount'],
                    'semCount': cached['sem_count'],
                    'results': _normalize_jntuh_results(results_data),
                    'fetched_at': fetched_str,
                    'developer': 'thilakreddypothuganti@gmail.com',
                    'poweredBy': 'jntuhconnect.dhethi.com'
                })
        except Exception:
            pass

    # 2. If DOB not provided, look it up in students table
    if not dob:
        try:
            student_rec = query(
                "SELECT dob FROM students WHERE student_id = %s",
                (roll,), one=True
            )
            if student_rec and student_rec.get('dob'):
                dob = str(student_rec['dob'])
        except Exception:
            pass

    # 3. If still no DOB, prompt for it
    if not dob:
        return jsonify({
            'success': False,
            'need_dob': True,
            'roll': roll,
            'error': (
                'The JNTUH server requires your <strong>Date of Birth</strong> to fetch live results. '
                'Please enter your DOB in <em>YYYY/MM/DD</em> format below.'
            )
        })

    # 4. Live fetch using Playwright scraper
    try:
        res = jntuh_scraper.fetch_jntuh_results(roll, dob)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Scraper error: {str(e)}'})

    if not res or not res.get('success'):
        return jsonify(res or {
            'success': False,
            'error': f'No results found for <strong>{roll}</strong>. Check Roll Number & DOB (YYYY/MM/DD).'
        })

    # 5. Save to cache
    try:
        res['results'] = _normalize_jntuh_results(res.get('results', []))
        results_json = _json.dumps(res['results'])
        expires_at = datetime.now() + timedelta(days=1)
        query(
            """
            INSERT INTO jntuh_cache
                (roll_number, student_name, cgpa, total_credits, sem_count, results_json, fetched_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
            ON DUPLICATE KEY UPDATE
                student_name  = VALUES(student_name),
                cgpa          = VALUES(cgpa),
                total_credits = VALUES(total_credits),
                sem_count     = VALUES(sem_count),
                results_json  = VALUES(results_json),
                fetched_at    = NOW(),
                expires_at    = VALUES(expires_at)
            """,
            (
                roll,
                res.get('name', ''),
                res.get('cgpa', 0),
                res.get('totalCredits', 0),
                res.get('semCount', 0),
                results_json,
                expires_at
            ),
            commit=True
        )
    except Exception:
        pass

    res['cached'] = False
    res['jntuh_name'] = res.get('name', '')
    _sync_jntuh_student_name(roll, res.get('name', ''))
    res['developer'] = 'thilakreddypothuganti@gmail.com'
    res['poweredBy'] = 'jntuhconnect.dhethi.com'
    return jsonify(res)


@app.route("/jntuh_class_results", methods=["POST", "GET"])
def jntuh_class_results():
    """Fetch class results & details for students in a department/section or matching a roll number series."""
    dept = (request.form.get("department") or request.args.get("department") or "").strip()
    year = (request.form.get("year") or request.args.get("year") or "").strip()
    section = (request.form.get("section") or request.args.get("section") or "").strip()
    search = (request.form.get("search") or request.args.get("search") or request.form.get("roll_number") or request.args.get("roll_number") or "").strip().upper()

    students = []
    
    # 1. Search by specific Roll Number or Class Roll Prefix (e.g. 23U51A05A6 or 23U51A05)
    clean_search = re.sub(r'[^A-Z0-9]', '', search)
    if len(clean_search) >= 6:
        roll_prefix = clean_search[:8] if len(clean_search) >= 8 else clean_search
        cached_students = query(
            """
            SELECT roll_number as student_id, student_name as name, student_name as jntuh_name, 'CSE' as department, '4' as year, 'A' as section,
                cgpa, total_credits, sem_count, results_json, fetched_at
            FROM jntuh_cache
            WHERE roll_number LIKE %s
            ORDER BY roll_number ASC
            """,
            (roll_prefix + '%',), fetchall=True
        ) or []

        db_students = query(
            """
            SELECT s.student_id, COALESCE(c.student_name, s.name) as name, c.student_name as jntuh_name, s.department, s.year, s.section,
                COALESCE(c.cgpa, 0) as cgpa, COALESCE(c.total_credits, 0) as total_credits,
                COALESCE(c.sem_count, 0) as sem_count, c.results_json, c.fetched_at
            FROM students s
            LEFT JOIN jntuh_cache c ON s.student_id = c.roll_number
            WHERE s.student_id LIKE %s
            ORDER BY s.student_id ASC
            """,
            (roll_prefix + '%',), fetchall=True
        ) or []

        seen_ids = set()
        for s in db_students:
            seen_ids.add(s['student_id'])
            students.append(s)
        for s in cached_students:
            if s['student_id'] not in seen_ids:
                seen_ids.add(s['student_id'])
                students.append(s)

    # 2. If no search or empty search results, query by dept/year/section
    if not students:
        sql = """
            SELECT s.student_id, COALESCE(c.student_name, s.name) as name, c.student_name as jntuh_name, s.department, s.year, s.section,
                COALESCE(c.cgpa, 0) as cgpa, COALESCE(c.total_credits, 0) as total_credits,
                COALESCE(c.sem_count, 0) as sem_count, c.results_json, c.fetched_at
            FROM students s
            LEFT JOIN jntuh_cache c ON s.student_id = c.roll_number
            WHERE 1=1
        """
        params = []
        if dept:
            sql += " AND s.department = %s"
            params.append(dept)
        if year:
            sql += " AND s.year = %s"
            params.append(year)
        if section:
            sql += " AND s.section = %s"
            params.append(section)
        sql += " ORDER BY s.student_id ASC"
        students = query(sql, tuple(params), fetchall=True) or []

    # 3. Only show all cached records when no hall ticket filter was supplied.
    # An unmatched hall ticket must not expose every cached student's result.
    if not students and not search and not dept and not year and not section:
        students = query(
            """
            SELECT roll_number as student_id, student_name as name, student_name as jntuh_name, 'CSE' as department, '4' as year, 'A' as section,
                cgpa, total_credits, sem_count, results_json, fetched_at
            FROM jntuh_cache
            ORDER BY roll_number ASC
            """,
            fetchall=True
        ) or []

    # Parse results_json into python object if string
    for s in students:
        if s.get('results_json') and isinstance(s['results_json'], str):
            try:
                s['results'] = _json.loads(s['results_json'])
            except Exception:
                s['results'] = []
        elif s.get('results_json') and isinstance(s['results_json'], list):
            s['results'] = s['results_json']
        else:
            s['results'] = []

    total_students = len(students)
    valid_cgpa = [float(s['cgpa']) for s in students if s.get('cgpa') and float(s['cgpa']) > 0]
    avg_cgpa = round(sum(valid_cgpa) / len(valid_cgpa), 2) if valid_cgpa else 0.0
    passed_count = sum(1 for s in students if s.get('cgpa') and float(s['cgpa']) >= 5.0)
    pass_percentage = round((passed_count / total_students * 100), 1) if total_students > 0 else 0

    return jsonify({
        "success": True,
        "department": dept or "CSE",
        "year": year or "4",
        "section": section or "A",
        "search": search,
        "totalStudents": total_students,
        "avgCgpa": avg_cgpa,
        "passPercentage": pass_percentage,
        "students": students
    })



# ════════════════════════════════════════════════════════════════
# FORGOT PASSWORD (OTP flow – 3 steps)
# ════════════════════════════════════════════════════════════════

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    msg  = ""
    step = 1
    user_id = ""

    if request.method == "POST":

        # ── STEP 1: Send OTP ─────────────────────────────────
        if "send_otp" in request.form:
            role    = request.form.get("role", "")
            user_id = request.form.get("user_id", "").strip()
            contact = request.form.get("contact", "").strip()

            if role not in ("student", "faculty"):
                msg = "Invalid role selected"
            else:
                if role == "student":
                    row = query(
                        "SELECT email, phone FROM students WHERE student_id=%s AND (email=%s OR phone=%s)",
                        (user_id, contact, contact), one=True,
                    )
                else:
                    row = query(
                        "SELECT email, phone FROM faculty WHERE faculty_id=%s AND (email=%s OR phone=%s)",
                        (user_id, contact, contact), one=True,
                    )

                if row:
                    otp    = random.randint(100000, 999999)
                    expiry = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")

                    query("DELETE FROM forgot_password WHERE user_id=%s", (user_id,), commit=True)
                    query(
                        "INSERT INTO forgot_password (user_id, role, otp, email, phone, expires_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (user_id, role, otp, row["email"], row["phone"], expiry),
                        commit=True,
                    )

                    sent = send_otp_email(row["email"], otp)
                    if sent:
                        msg = f"OTP Sent Successfully to {row['email']}"
                    else:
                        msg = f"Email Failed (Set credentials in config.py!). Demo OTP: {otp}"
                    step = 2
                else:
                    msg = "Invalid ID or Contact details"

        # ── STEP 2: Verify OTP ───────────────────────────────
        elif "verify_otp" in request.form:
            user_id     = request.form.get("user_id", "")
            entered_otp = request.form.get("otp", "")
            role        = request.form.get("role", "")

            rec = query(
                "SELECT * FROM forgot_password WHERE user_id=%s AND otp=%s AND expires_at>NOW() AND is_verified=0",
                (user_id, entered_otp), one=True,
            )
            if rec:
                query("UPDATE forgot_password SET is_verified=1 WHERE user_id=%s", (user_id,), commit=True)
                session["reset_user"] = user_id
                session["reset_role"] = role
                step = 3
            else:
                msg  = "Invalid or Expired OTP"
                step = 2

        # ── STEP 3: Reset Password ───────────────────────────
        elif "reset_password" in request.form:
            if "reset_user" not in session:
                return "Unauthorized Access", 403

            new_pass = request.form.get("new_password", "")
            if len(new_pass) < 6:
                msg  = "Password must be at least 6 characters"
                step = 3
            else:
                pw_hash = generate_password_hash(new_pass)
                uid     = session["reset_user"]
                role    = session["reset_role"]

                if role == "student":
                    query("UPDATE students SET password=%s WHERE student_id=%s", (pw_hash, uid), commit=True)
                else:
                    query("UPDATE faculty SET password=%s WHERE faculty_id=%s", (pw_hash, uid), commit=True)

                query("DELETE FROM forgot_password WHERE user_id=%s", (uid,), commit=True)
                session.pop("reset_user", None)
                session.pop("reset_role", None)
                return redirect(url_for("login", success="Password Reset Successful"))

    return render_template("forgot_password.html", msg=msg, step=step, user_id=user_id)


# ════════════════════════════════════════════════════════════════
# STUDENT DASHBOARD
# ════════════════════════════════════════════════════════════════

@app.route("/student_dashboard", methods=["GET", "POST"])
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("login"))

    sid        = session["user_id"]
    active_tab = request.args.get("tab", "attendance")

    # ── Update Profile ────────────────────────────────────────
    if request.method == "POST" and "update_profile" in request.form:
        dob_val = request.form.get("dob", "").strip() or None
        query(
            "UPDATE students SET name=%s, email=%s, phone=%s, year=%s, section=%s, dob=%s WHERE student_id=%s",
            (request.form["name"], request.form["email"], request.form["phone"],
            request.form["year"], request.form["section"], dob_val, sid),
            commit=True,
        )
        return redirect(url_for("student_dashboard", tab="profile"))

    # ── Change Password ───────────────────────────────────────
    if request.method == "POST" and "change_password" in request.form:
        old_p     = request.form.get("old_password", "")
        new_p     = request.form.get("new_password", "")
        confirm_p = request.form.get("confirm_password", "")

        user = query("SELECT password FROM students WHERE student_id=%s", (sid,), one=True)
        if user and check_password_hash(user["password"], old_p) and new_p == confirm_p:
            query("UPDATE students SET password=%s WHERE student_id=%s",
                (generate_password_hash(new_p), sid), commit=True)
            session["password_msg"] = "Password changed successfully."
        else:
            session["password_error"] = "Invalid old password or new passwords do not match."
        return redirect(url_for("student_dashboard", tab="profile"))

    # ── Filters ───────────────────────────────────────────────
    sel_att_sem  = request.args.get("att_semester", "")
    sel_exam_sem = request.args.get("exam_semester", "")

    # ── Fetch Student ─────────────────────────────────────────
    student = query("SELECT * FROM students WHERE student_id=%s", (sid,), one=True)
    if student is None:
        student = {}

    # ── Attendance Summary ────────────────────────────────────
    if sel_att_sem:
        att_data = query(
            "SELECT COUNT(*) AS total, SUM(status='Present') AS present, SUM(status='Absent') AS absent "
            "FROM attendance WHERE student_id=%s AND semester=%s",
            (sid, sel_att_sem), one=True,
        )
    else:
        att_data = query(
            "SELECT COUNT(*) AS total, SUM(status='Present') AS present, SUM(status='Absent') AS absent "
            "FROM attendance WHERE student_id=%s",
            (sid,), one=True,
        )

    total_classes   = (att_data or {}).get("total") or 0
    present_classes = (att_data or {}).get("present") or 0
    absent_classes  = (att_data or {}).get("absent") or 0
    att_pct         = round((present_classes / total_classes) * 100) if total_classes else 0

    # ── Fee Summary ───────────────────────────────────────────
    fee = query(
        "SELECT total_fee, other_free, paid_fee, remaining_fee, payment_status FROM tuition_fees WHERE student_id=%s",
        (sid,), one=True,
    )
    remaining = (fee or {}).get("remaining_fee") or 0

    # ── Attendance Records ────────────────────────────────────
    if sel_att_sem:
        att_records = query(
            "SELECT semester, attendance_date, class_name, status FROM attendance "
            "WHERE student_id=%s AND semester=%s ORDER BY attendance_date DESC",
            (sid, sel_att_sem), fetchall=True,
        )
    else:
        att_records = query(
            "SELECT semester, attendance_date, class_name, status FROM attendance "
            "WHERE student_id=%s ORDER BY attendance_date DESC",
            (sid,), fetchall=True,
        )

    # ── Exam Results ──────────────────────────────────────────
    if sel_exam_sem:
        exam_records = query(
            "SELECT exam_type, subject_name, semester, descriptive_marks, objective_marks, Assignment_marks, ppt_marks, total_marks, internal_marks, external_marks, points, grade, passed, subject_code, credits FROM exam_results "
            "WHERE student_id=%s AND semester=%s ORDER BY semester, exam_type",
            (sid, sel_exam_sem), fetchall=True,
        )
    else:
        exam_records = query(
            "SELECT exam_type, subject_name, semester, descriptive_marks, objective_marks, Assignment_marks, ppt_marks, total_marks, internal_marks, external_marks, points, grade, passed, subject_code, credits FROM exam_results "
            "WHERE student_id=%s ORDER BY semester, exam_type",
            (sid,), fetchall=True,
        )

    # ── Course Material / Timetable / Calendar ────────────────
    student = student if isinstance(student, dict) else (student[0] if student else None)
    dept = (student or {}).get("department", "")
    yr   = (student or {}).get("year", "")
    sec  = (student or {}).get("section", "")

    materials = query(
        "SELECT title, file_path FROM department_files "
        "WHERE category='course_material' AND department=%s AND year=%s AND (section=%s OR section='All')",
        (dept, yr, sec), fetchall=True,
    )
    timetables = query(
        "SELECT title, file_path FROM department_files "
        "WHERE category='timetable' AND department=%s AND year=%s AND (section=%s OR section='All')",
        (dept, yr, sec), fetchall=True,
    )
    calendars = query(
        "SELECT title, file_path FROM department_files "
        "WHERE category='academic_calendar' AND department=%s AND year=%s AND (section=%s OR section='All')",
        (dept, yr, sec), fetchall=True,
    )

    # ── Fee History ───────────────────────────────────────────
    fee_history = query(
        "SELECT * FROM fee_history WHERE student_id=%s ORDER BY updated_at DESC",
        (sid,), fetchall=True,
    )

    # Pop flash messages
    pw_msg   = session.pop("password_msg", None)
    pw_error = session.pop("password_error", None)

    return render_template(
        "student_dashboard.html",
        student=student,
        active_tab=active_tab,
        total_classes=total_classes,
        present_classes=present_classes,
        absent_classes=absent_classes,
        att_pct=att_pct,
        fee=fee,
        remaining=remaining,
        att_records=att_records,
        exam_records=exam_records,
        materials=materials,
        timetables=timetables,
        calendars=calendars,
        fee_history=fee_history,
        sel_att_sem=sel_att_sem,
        sel_exam_sem=sel_exam_sem,
        pw_msg=pw_msg,
        pw_error=pw_error,
        semesters=list(range(1, 9)),
    )


# ════════════════════════════════════════════════════════════════
# FACULTY DASHBOARD
# ════════════════════════════════════════════════════════════════

@app.route("/faculty_dashboard", methods=["GET", "POST"])
def faculty_dashboard():
    if session.get("role") != "faculty":
        return redirect(url_for("login"))

    fid = session["user_id"]

    # ── Handle Profile Update ─────────────────────────────────
    if request.method == "POST" and "update_profile" in request.form:
        f_name  = request.form.get("f_name", "")
        f_email = request.form.get("f_email", "")
        f_phone = request.form.get("f_phone", "")
        f_pass  = request.form.get("f_pass", "")
        if f_pass:
            query("UPDATE faculty SET name=%s, email=%s, phone=%s, password=%s WHERE faculty_id=%s",
                (f_name, f_email, f_phone, generate_password_hash(f_pass), fid), commit=True)
        else:
            query("UPDATE faculty SET name=%s, email=%s, phone=%s WHERE faculty_id=%s",
                (f_name, f_email, f_phone, fid), commit=True)

    # ── Handle Edit Student ───────────────────────────────────
    if request.method == "POST" and "edit_student" in request.form:
        old_id = request.form.get("old_id")
        new_id = request.form.get("student_id")
        name   = request.form.get("name")
        dept   = request.form.get("department")
        yr     = request.form.get("year")
        sec    = request.form.get("section")
        phone  = request.form.get("phone")
        query("UPDATE students SET student_id=%s, name=%s, department=%s, year=%s, section=%s, phone=%s "
            "WHERE student_id=%s", (new_id, name, dept, yr, sec, phone, old_id), commit=True)
        return redirect(url_for("faculty_dashboard", active_section="mystudents",
                                department=dept, year=yr, section=sec))

    # ── Handle Bulk Update ────────────────────────────────────
    if request.method == "POST" and "bulk_update" in request.form:
        new_year    = request.form.get("bulk_year", "")
        new_section = request.form.get("bulk_section", "")
        dept_f      = request.form.get("department", "")
        year_f      = request.form.get("year", "")
        sec_f       = request.form.get("section", "")
        if new_year or new_section:
            sets, params = [], []
            if new_year:    sets.append("year=%s");    params.append(new_year)
            if new_section: sets.append("section=%s"); params.append(new_section)
            sql = "UPDATE students SET " + ", ".join(sets) + " WHERE 1=1"
            if dept_f: sql += " AND department=%s"; params.append(dept_f)
            if year_f: sql += " AND year=%s";       params.append(year_f)
            if sec_f:  sql += " AND section=%s";    params.append(sec_f)
            query(sql, tuple(params), commit=True)
        return redirect(url_for("faculty_dashboard", active_section="mystudents",
                                department=dept_f, year=year_f, section=sec_f))

    # ── Handle File Delete ────────────────────────────────────
    if request.method == "GET" and "delete_file" in request.args:
        file_id        = request.args.get("delete_file")
        section_origin = request.args.get("active_section", "mystudents")
        rec = query("SELECT file_path FROM department_files WHERE id=%s", (file_id,), one=True)
        if rec:
            fp = rec["file_path"]
            for candidate in (fp, os.path.join(config.UPLOAD_FOLDER, os.path.basename(fp))):
                if os.path.exists(candidate):
                    os.remove(candidate)
                    break
            query("DELETE FROM department_files WHERE id=%s", (file_id,), commit=True)
        return redirect(url_for("faculty_dashboard", active_section=section_origin))

    # ── Handle Student Delete ─────────────────────────────────
    if request.method == "GET" and "delete_student" in request.args:
        del_sid = request.args.get("delete_student")
        dept    = request.args.get("department", "CSE")
        yr      = request.args.get("year", "3")
        sec     = request.args.get("section", "A")
        query("DELETE FROM students WHERE student_id=%s", (del_sid,), commit=True)
        return redirect(url_for("faculty_dashboard", active_section="mystudents",
                                department=dept, year=yr, section=sec))

    # ── Handle File Upload ────────────────────────────────────
    if request.method == "POST" and "upload_file_action" in request.form:
        title      = request.form.get("file_title", "")
        category   = request.form.get("file_category", "")
        dept       = request.form.get("department", "")
        yr         = request.form.get("year", "")
        sec        = request.form.get("section", "")
        active_sec = request.form.get("active_section", "mystudents")
        file       = request.files.get("uploaded_file")
        if file and allowed_file(file.filename):
            filename    = f"{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            target_path = f"{config.UPLOAD_FOLDER}/{filename}"
            file.save(target_path)
            ext = filename.rsplit(".", 1)[1].lower()
            query(
                "INSERT INTO department_files (title, file_path, file_type, department, year, section, category) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (title, filename, ext, dept, yr, sec, category), commit=True,
            )
        return redirect(url_for("faculty_dashboard", active_section=active_sec, department=dept, year=yr, section=sec))

    # ── Handle Save Attendance ────────────────────────────────
    if request.method == "POST" and "save_attendance_action" in request.form:
        att_date  = request.form.get("att_date")
        att_dept  = request.form.get("att_dept")
        att_year  = request.form.get("att_year")
        att_sec   = request.form.get("att_sec")
        class_nm  = request.form.get("class_name")
        semester  = request.form.get("semester")

        # Time restriction
        now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
        h, m    = now_ist.hour, now_ist.minute
        if h > 16 or (h == 16 and m >= 30) or h < 9:
            return "<script>alert('Attendance upload is restricted between 4:30 PM and 9:00 AM.'); window.history.back();</script>"

        # Authorization check
        chk = query(
            "SELECT 1 FROM faculty_assignments WHERE faculty_id=%s AND department=%s AND year=%s "
            "AND section=%s AND semester=%s AND subject_name=%s",
            (fid, att_dept, att_year, att_sec, semester, class_nm), one=True,
        )
        if not chk:
            return "Access Denied: You are not authorized for this subject/class.", 403

        for sid, status in request.form.items():
            if not sid.startswith("status["):
                continue
            actual_sid = sid[7:-1]
            query(
                "INSERT INTO attendance (student_id, department, year, section, semester, "
                "attendance_date, class_name, status, marked_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE status=%s, semester=%s",
                (actual_sid, att_dept, att_year, att_sec, semester, att_date,
                class_nm, status, fid, status, semester), commit=True,
            )
        return redirect(url_for("faculty_dashboard", active_section="attendance", department=att_dept, year=att_year, section=att_sec))

    # ── Handle Save Exam Marks ────────────────────────────────
    if request.method == "POST" and "save_exam_action" in request.form:
        ex_dept      = request.form.get("ex_dept")
        ex_year      = request.form.get("ex_year")
        ex_sec       = request.form.get("ex_sec")
        exam_type    = request.form.get("exam_type")
        subject_name = request.form.get("subject_name", "")
        semester     = request.form.get("semester")

        chk = query(
            "SELECT 1 FROM faculty_assignments WHERE faculty_id=%s AND department=%s AND year=%s "
            "AND section=%s AND semester=%s AND subject_name=%s",
            (fid, ex_dept, ex_year, ex_sec, semester, subject_name), one=True,
        )
        if not chk:
            return "Access Denied.", 403

        form_data = request.form
        # Collect marks[<sid>][field]
        marks_map = {}
        for key, val in form_data.items():
            if key.startswith("marks["):
                inner = key[6:]
                sid, rest = inner.split("][", 1)
                field = rest.rstrip("]")
                marks_map.setdefault(sid, {})[field] = val

        for sid, comp in marks_map.items():
            stu = query("SELECT name FROM students WHERE student_id=%s", (sid,), one=True)
            stu_name = stu["name"] if stu else ""
            query(
                "DELETE FROM exam_results WHERE student_id=%s AND exam_type=%s AND subject_name=%s AND semester=%s",
                (sid, exam_type, subject_name, semester), commit=True,
            )
            query(
                "INSERT INTO exam_results (student_id, student_name, department, year, section, subject_name, exam_type, semester, total_marks, descriptive_marks, objective_marks, Assignment_marks, ppt_marks, internal_marks, external_marks, points, grade, passed, subject_code, credits) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    sid, stu_name, ex_dept, ex_year, ex_sec, subject_name, exam_type, semester,
                    int(comp.get("total", 0) or 0),
                    int(comp.get("descriptive", 0) or 0),
                    int(comp.get("objective", 0) or 0),
                    int(comp.get("assignment", 0) or 0),
                    int(comp.get("ppt", 0) or 0),
                    int(comp.get("descriptive", 0) or 0) + int(comp.get("objective", 0) or 0),
                    int(comp.get("assignment", 0) or 0) + int(comp.get("ppt", 0) or 0),
                    int(comp.get("total", 0) or 0),
                    _grade_from_total(int(comp.get("total", 0) or 0)),
                    "Pass" if int(comp.get("total", 0) or 0) >= 40 else "Fail",
                    "", 0
                ),
                commit=True,
            )
        return redirect(url_for("faculty_dashboard", active_section="exam", exam_type=exam_type, department=ex_dept, year=ex_year, section=ex_sec))

    # ── Handle Save Tuition Fee ───────────────────────────────
    if request.method == "POST" and "save_fee_action" in request.form:
        fees_map = {}
        for key, val in request.form.items():
            if key.startswith("fees["):
                inner = key[5:]
                sid, rest = inner.split("][", 1)
                field = rest.rstrip("]")
                fees_map.setdefault(sid, {})[field] = val

        for sid, fd in fees_map.items():
            total   = float(fd.get("total", 0) or 0)
            other   = float(fd.get("other_free", 0) or 0)
            paid    = float(fd.get("paid", 0) or 0)
            balance = total + other - paid
            status  = fd.get("status", "Pending")
            nm      = fd.get("name", "")
            query(
                "INSERT INTO tuition_fees (student_id, student_name, total_fee, other_free, paid_fee, "
                "remaining_fee, payment_status) VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "total_fee=%s, other_free=%s, paid_fee=%s, remaining_fee=%s, payment_status=%s",
                (sid, nm, total, other, paid, balance, status,
                total, other, paid, balance, status), commit=True,
            )
            query(
                "INSERT INTO fee_history (student_id, updated_by, paid_amount, remaining_balance, payment_status) "
                "VALUES (%s,%s,%s,%s,%s)",
                (sid, fid, paid, balance, status), commit=True,
            )

    # ── AJAX: Update Single Fee ───────────────────────────────
    if request.method == "POST" and "update_single_fee" in request.form:
        sid    = request.form.get("student_id")
        nm     = request.form.get("name", "")
        total  = float(request.form.get("total_fee", 0) or 0)
        other  = float(request.form.get("other_free", 0) or 0)
        paid   = float(request.form.get("paid_fee", 0) or 0)
        remain = total + other - paid
        status = request.form.get("payment_status", "Pending")
        query(
            "INSERT INTO tuition_fees (student_id, student_name, total_fee, other_free, paid_fee, "
            "remaining_fee, payment_status) VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "total_fee=%s, other_free=%s, paid_fee=%s, remaining_fee=%s, payment_status=%s",
            (sid, nm, total, other, paid, remain, status,
            total, other, paid, remain, status), commit=True,
        )
        query(
            "INSERT INTO fee_history (student_id, updated_by, paid_amount, remaining_balance, payment_status) "
            "VALUES (%s,%s,%s,%s,%s)",
            (sid, fid, paid, remain, status), commit=True,
        )
        return jsonify({"success": True})

    # ── AJAX: Get Student Details ─────────────────────────────
    if "get_student_details" in request.args:
        student_id = request.args.get("get_student_details")
        attendance = query(
            "SELECT attendance_date, class_name, status, semester FROM attendance "
            "WHERE student_id=%s ORDER BY attendance_date DESC",
            (student_id,), fetchall=True,
        )
        exams = query(
            "SELECT exam_type, subject_name, semester, total_marks, descriptive_marks, objective_marks, Assignment_marks AS assignment_marks, ppt_marks, internal_marks, external_marks, points, grade, passed, subject_code, credits FROM exam_results "
            "WHERE student_id=%s ORDER BY exam_type, subject_name",
            (student_id,), fetchall=True,
        )
        fee = query(
            "SELECT total_fee, other_free, paid_fee, remaining_fee, payment_status "
            "FROM tuition_fees WHERE student_id=%s",
            (student_id,), one=True,
        )
        # Convert dates to strings for JSON
        for a in attendance:
            if hasattr(a.get("attendance_date"), "isoformat"):
                a["attendance_date"] = a["attendance_date"].isoformat()
        return jsonify({"attendance": attendance, "exams": exams, "fee": fee})

    # ── AJAX: Get Attendance for date/class ───────────────────
    if "get_attendance" in request.args:
        date     = request.args.get("date")
        class_nm = request.args.get("class")
        dept     = request.args.get("dept")
        yr       = request.args.get("year")
        sec      = request.args.get("sec")
        semester = request.args.get("semester", "")
        rows = query(
            "SELECT student_id, status FROM attendance WHERE attendance_date=%s AND class_name=%s "
            "AND department=%s AND year=%s AND section=%s AND semester=%s",
            (date, class_nm, dept, yr, sec, semester), fetchall=True,
        )
        result = {r["student_id"]: r["status"] for r in rows}
        return jsonify(result)

    # ── Fetch Faculty Data ────────────────────────────────────
    faculty      = query("SELECT * FROM faculty WHERE faculty_id=%s", (fid,), one=True)
    if faculty is None:
        faculty = {}
    is_accounts  = (faculty.get("role") if faculty else "Academic") == "Accounts"
    assignments  = query("SELECT * FROM faculty_assignments WHERE faculty_id=%s", (fid,), fetchall=True)

    active       = request.args.get("active_section", "mystudents")
    sel_assign   = request.args.get("assignment_id", "")
    if not sel_assign and assignments:
        sel_assign = str(assignments[0]["assignment_id"])

    dept = year = section = cur_sem = subject_name = ""
    has_access = False

    if is_accounts:
        dept    = request.args.get("department") or request.form.get("department") or "CSE"
        year    = request.args.get("year") or request.form.get("year") or "3"
        section = request.args.get("section") or request.form.get("section") or "A"
        cur_sem = request.args.get("semester") or request.form.get("semester") or "1"
        subject_name = request.args.get("subject_name") or request.form.get("subject_name") or "General"
        has_access = True
    else:
        if sel_assign:
            for a in assignments:
                if str(a["assignment_id"]) == str(sel_assign):
                    dept         = a["department"]
                    year         = a["year"]
                    section      = a["section"]
                    cur_sem      = a["semester"]
                    subject_name = a["subject_name"]
                    has_access   = True
                    break

        if not has_access:
            dept         = request.args.get("department") or request.form.get("department") or "CSE"
            year         = request.args.get("year") or request.form.get("year") or "3"
            section      = request.args.get("section") or request.form.get("section") or "A"
            cur_sem      = request.args.get("semester") or request.form.get("semester") or "1"
            subject_name = request.args.get("subject_name") or request.form.get("subject_name") or "General"
            has_access   = True

    # Filtered students
    search_sid = request.args.get("search_student_id", "")
    if has_access:
        if is_accounts and search_sid:
            filtered_students = query("SELECT * FROM students WHERE student_id=%s", (search_sid,), fetchall=True)
        else:
            filtered_students = query(
                "SELECT * FROM students WHERE department=%s AND year=%s AND section=%s ORDER BY student_id ASC",
                (dept, year, section), fetchall=True,
            )
    else:
        filtered_students = []

    # Overall attendance
    if is_accounts and search_sid:
        overall_students = query(
            "SELECT s.*, COUNT(a.student_id) AS total_classes, "
            "SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) AS present_count, "
            "SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) AS absent_count, "
            "ROUND((SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) / "
            "NULLIF(COUNT(a.student_id),0))*100,2) AS attendance_percent "
            "FROM students s LEFT JOIN attendance a ON s.student_id=a.student_id "
            "WHERE s.student_id=%s GROUP BY s.student_id ORDER BY s.student_id",
            (search_sid,), fetchall=True,
        )
    else:
        overall_students = query(
            "SELECT s.*, COUNT(a.student_id) AS total_classes, "
            "SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) AS present_count, "
            "SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) AS absent_count, "
            "ROUND((SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) / "
            "NULLIF(COUNT(a.student_id),0))*100,2) AS attendance_percent "
            "FROM students s LEFT JOIN attendance a ON s.student_id=a.student_id "
            "WHERE s.department=%s AND s.year=%s AND s.section=%s "
            "GROUP BY s.student_id ORDER BY s.student_id",
            (dept, year, section), fetchall=True,
        )

    # Uploaded files
    uploaded_files = query(
        "SELECT * FROM department_files WHERE department=%s AND year=%s AND (section=%s OR section='All') "
        "ORDER BY uploaded_at DESC",
        (dept, year, section), fetchall=True,
    )

    # Exam marks for current filter
    exam_type_filter = request.args.get("exam_type", "mid1")
    exam_marks = {}
    if subject_name:
        rows = query(
            "SELECT student_id, descriptive_marks, objective_marks, Assignment_marks, ppt_marks, total_marks "
            "FROM exam_results WHERE department=%s AND year=%s AND section=%s "
            "AND exam_type=%s AND subject_name=%s AND semester=%s",
            (dept, year, section, exam_type_filter, subject_name, cur_sem), fetchall=True,
        )
        for r in rows:
            exam_marks[r["student_id"]] = r

    # Fee data for current filter
    if is_accounts and search_sid:
        fee_rows = query(
            "SELECT student_id, total_fee, other_free, paid_fee, remaining_fee, payment_status "
            "FROM tuition_fees WHERE student_id=%s",
            (search_sid,), fetchall=True,
        )
    else:
        fee_rows = query(
            "SELECT student_id, total_fee, other_free, paid_fee, remaining_fee, payment_status "
            "FROM tuition_fees WHERE student_id IN "
            "(SELECT student_id FROM students WHERE department=%s AND year=%s AND section=%s) "
            "ORDER BY student_id",
            (dept, year, section), fetchall=True,
        )
    fee_data = {r["student_id"]: r for r in (fee_rows or [])}

    return render_template(
        "faculty_dashboard.html",
        faculty=faculty,
        is_accounts=is_accounts,
        assignments=assignments,
        active=active,
        sel_assign=sel_assign,
        dept=dept, year=year, section=section,
        cur_sem=cur_sem, subject_name=subject_name,
        has_access=has_access,
        filtered_students=filtered_students,
        overall_students=overall_students,
        uploaded_files=uploaded_files,
        exam_marks=exam_marks,
        fee_data=fee_data,
        exam_type_filter=exam_type_filter,
        search_sid=search_sid,
    )


# ════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ════════════════════════════════════════════════════════════════

@app.route("/admin_dashboard", methods=["GET", "POST"])
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    # Ensure required columns/tables exist
    try:
        query("ALTER TABLE attendance ADD COLUMN reason VARCHAR(255) DEFAULT ''", commit=True)
    except Exception:
        pass
    try:
        query("CREATE TABLE IF NOT EXISTS allowed_students (student_id VARCHAR(50) PRIMARY KEY)", commit=True)
    except Exception:
        pass

    # ── AJAX: Get Student Attendance ─────────────────────────
    if "get_student_attendance" in request.args:
        sid  = request.args.get("get_student_attendance")
        recs = query(
            "SELECT attendance_date, class_name, semester, status, reason FROM attendance "
            "WHERE student_id=%s ORDER BY attendance_date DESC",
            (sid,), fetchall=True,
        )
        for r in recs:
            if hasattr(r.get("attendance_date"), "isoformat"):
                r["attendance_date"] = r["attendance_date"].isoformat()
        return jsonify(recs)

    # ── AJAX: Get Class Attendance ────────────────────────────
    if "get_class_attendance" in request.args:
        dept     = request.args.get("dept")
        yr       = request.args.get("year")
        sec      = request.args.get("sec")
        date     = request.args.get("date")
        subject  = request.args.get("subject")
        semester = request.args.get("semester")
        rows = query(
            "SELECT s.student_id, s.name, IFNULL(a.status,'Present') AS status, IFNULL(a.reason,'') AS reason "
            "FROM students s LEFT JOIN attendance a ON s.student_id=a.student_id "
            "AND a.attendance_date=%s AND a.class_name=%s AND a.semester=%s "
            "WHERE s.department=%s AND s.year=%s AND s.section=%s ORDER BY s.student_id",
            (date, subject, semester, dept, yr, sec), fetchall=True,
        )
        return jsonify(rows)

    # ── POST: Bulk Update Attendance ──────────────────────────
    if request.method == "POST" and "bulk_update_attendance" in request.form:
        dept     = request.form.get("b_att_dept")
        yr       = request.form.get("b_att_year")
        sec      = request.form.get("b_att_sec")
        date     = request.form.get("b_att_date")
        subject  = request.form.get("b_att_subject")
        semester = request.form.get("b_att_semester")
        for key, status in request.form.items():
            if not key.startswith("b_status["):
                continue
            sid    = key[9:-1]
            reason = request.form.get(f"b_reason[{sid}]", "")
            query(
                "INSERT INTO attendance (student_id, department, year, section, semester, "
                "attendance_date, class_name, status, reason, marked_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Admin') ON DUPLICATE KEY UPDATE status=%s, reason=%s",
                (sid, dept, yr, sec, semester, date, subject, status, reason, status, reason), commit=True,
            )
        return redirect(url_for("admin_dashboard", tab="attendance", msg="Bulk+Attendance+Saved"))

    # ── POST: Update Single Attendance ───────────────────────
    if request.method == "POST" and "update_single_attendance" in request.form:
        sid       = request.form.get("student_id")
        date      = request.form.get("attendance_date")
        class_nm  = request.form.get("class_name")
        semester  = request.form.get("semester")
        status    = request.form.get("status")
        reason    = request.form.get("reason", "")
        query(
            "UPDATE attendance SET status=%s, reason=%s WHERE student_id=%s "
            "AND attendance_date=%s AND class_name=%s AND semester=%s",
            (status, reason, sid, date, class_nm, semester), commit=True,
        )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": True})
        return redirect(url_for("admin_dashboard", tab="attendance", msg="Attendance+Updated"))

    # ── AJAX: Get Student Details Performance ────────────────
    if "get_student_details_performance" in request.args:
        student_id = request.args.get("get_student_details_performance")
        attendance = query(
            "SELECT attendance_date, class_name, status, semester FROM attendance "
            "WHERE student_id=%s ORDER BY attendance_date DESC",
            (student_id,), fetchall=True,
        )
        for a in attendance:
            if hasattr(a.get("attendance_date"), "isoformat"):
                a["attendance_date"] = a["attendance_date"].isoformat()
        exams = query(
            "SELECT exam_type, subject_name, semester, total_marks, descriptive_marks, objective_marks, "
            "Assignment_marks AS assignment_marks, ppt_marks FROM exam_results "
            "WHERE student_id=%s ORDER BY exam_type, subject_name",
            (student_id,), fetchall=True,
        )
        fee = query(
            "SELECT total_fee, other_free, paid_fee, remaining_fee, payment_status "
            "FROM tuition_fees WHERE student_id=%s",
            (student_id,), one=True,
        )
        return jsonify({"attendance": attendance, "exams": exams, "fee": fee})

    # ── POST: Update Single Exam ──────────────────────────────
    if request.method == "POST" and "update_single_exam" in request.form:
        sid  = request.form.get("student_id")
        et   = request.form.get("exam_type")
        subj = request.form.get("subject_name")
        sem  = request.form.get("semester")
        desc = int(request.form.get("descriptive_marks", 0) or 0)
        obj  = int(request.form.get("objective_marks", 0) or 0)
        assig= int(request.form.get("Assignment_marks", 0) or 0)
        ppt  = int(request.form.get("ppt_marks", 0) or 0)
        tot  = int(request.form.get("total_marks", 0) or 0)
        query(
            "UPDATE exam_results SET descriptive_marks=%s, objective_marks=%s, "
            "Assignment_marks=%s, ppt_marks=%s, total_marks=%s "
            "WHERE student_id=%s AND exam_type=%s AND subject_name=%s AND semester=%s",
            (desc, obj, assig, ppt, tot, sid, et, subj, sem), commit=True,
        )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": True})
        return redirect(url_for("admin_dashboard", tab="exams", msg="Exam+Updated"))

    # ── POST: Update Single Fee ───────────────────────────────
    if request.method == "POST" and "update_single_fee" in request.form:
        sid    = request.form.get("student_id")
        total  = float(request.form.get("total_fee", 0) or 0)
        other  = float(request.form.get("other_free", 0) or 0)
        paid   = float(request.form.get("paid_fee", 0) or 0)
        remain = total + other - paid
        status = request.form.get("payment_status", "Pending")
        query(
            "UPDATE tuition_fees SET total_fee=%s, other_free=%s, paid_fee=%s, "
            "remaining_fee=%s, payment_status=%s WHERE student_id=%s",
            (total, other, paid, remain, status, sid), commit=True,
        )
        query(
            "INSERT INTO fee_history (student_id, updated_by, paid_amount, remaining_balance, payment_status) "
            "VALUES (%s,'Admin',%s,%s,%s)",
            (sid, paid, remain, status), commit=True,
        )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": True})
        return redirect(url_for("admin_dashboard", tab="fees", msg="Fee+Updated"))

    # ── POST: Delete Attendance Record ───────────────────────
    if request.method == "POST" and "delete_attendance" in request.form:
        sid      = request.form.get("student_id")
        date     = request.form.get("attendance_date")
        class_nm = request.form.get("class_name")
        semester = request.form.get("semester")
        query(
            "DELETE FROM attendance WHERE student_id=%s AND attendance_date=%s "
            "AND class_name=%s AND semester=%s",
            (sid, date, class_nm, semester), commit=True,
        )
        return redirect(url_for("admin_dashboard", tab="attendance", msg="Attendance+Deleted"))

    # ── POST: Delete Exam Record ────────────────────────────
    if request.method == "POST" and "delete_exam" in request.form:
        sid  = request.form.get("student_id")
        et   = request.form.get("exam_type")
        subj = request.form.get("subject_name")
        sem  = request.form.get("semester")
        query(
            "DELETE FROM exam_results WHERE student_id=%s AND exam_type=%s "
            "AND subject_name=%s AND semester=%s",
            (sid, et, subj, sem), commit=True,
        )
        return redirect(url_for("admin_dashboard", tab="exams", msg="Exam+Deleted"))

    # ── POST: Delete Fee Record ─────────────────────────────
    if request.method == "POST" and "delete_fee" in request.form:
        sid = request.form.get("student_id")
        query("DELETE FROM tuition_fees WHERE student_id=%s", (sid,), commit=True)
        return redirect(url_for("admin_dashboard", tab="fees", msg="Fee+Deleted"))

    # ── POST: Toggle Faculty Role ─────────────────────────────
    if request.method == "POST" and request.form.get("toggle_accounts_faculty_id"):
        fid = request.form.get("toggle_accounts_faculty_id")
        is_accounts = request.form.get("toggle_accounts") not in (None, "", "0", "false", "False")
        role = "Accounts" if is_accounts else "Academic"
        query("UPDATE faculty SET role=%s WHERE faculty_id=%s", (role, fid), commit=True)
        return redirect(url_for("admin_dashboard", tab="faculty", msg="Faculty+Role+Updated"))

    # ── POST: Add Faculty ─────────────────────────────────────
    if request.method == "POST" and "add_faculty" in request.form:
        fid   = request.form.get("faculty_id")
        fname = request.form.get("name")
        fphone= request.form.get("phone")
        frole = request.form.get("role", "Academic")
        query(
            "INSERT INTO faculty (faculty_id, name, email, phone, password, role) "
            "VALUES (%s,%s,'',%s,'', %s)",
            (fid, fname, fphone, frole), commit=True,
        )
        return redirect(url_for("admin_dashboard", tab="faculty", msg="Faculty+Added"))

    # ── POST/GET: Delete Faculty ──────────────────────────────
    if "delete_faculty" in request.args or (request.method == "POST" and ("delete_faculty" in request.form or "delete_faculty_id" in request.form)):
        fid = request.args.get("delete_faculty") or request.form.get("delete_faculty") or request.form.get("delete_faculty_id")
        if fid:
            query("DELETE FROM faculty_assignments WHERE faculty_id=%s", (fid,), commit=True)
            query("DELETE FROM faculty WHERE faculty_id=%s", (fid,), commit=True)
        return redirect(url_for("admin_dashboard", tab="faculty", msg="Faculty+Deleted"))

    # ── POST/GET: Pre-Approve / Remove Student ID ─────────────
    if request.method == "POST" and "allow_student" in request.form:
        sid = request.form.get("allow_student_id", "").strip().upper()
        if sid:
            query("INSERT IGNORE INTO allowed_students (student_id) VALUES (%s)", (sid,), commit=True)
        return redirect(url_for("admin_dashboard", tab="students", msg="Student+ID+Pre-Approved"))

    if "delete_allowed_student" in request.args:
        sid = request.args.get("delete_allowed_student")
        query("DELETE FROM allowed_students WHERE student_id=%s", (sid,), commit=True)
        return redirect(url_for("admin_dashboard", tab="students", msg="Pre-Approved+ID+Removed"))

    # ── POST: Assign Faculty ──────────────────────────────────
    if request.method == "POST" and "add_assignment" in request.form:
        fid   = request.form.get("faculty_id") or request.form.get("assign_faculty_id")
        subj  = request.form.get("subject_name") or request.form.get("assign_subject")
        depts = request.form.getlist("department[]")
        if not depts and request.form.get("assign_dept"):
            depts = [request.form.get("assign_dept")]
        years = request.form.getlist("year[]")
        if not years and request.form.get("assign_year"):
            years = [request.form.get("assign_year")]
        secs  = request.form.getlist("section[]")
        if not secs and request.form.get("assign_section"):
            secs = [request.form.get("assign_section")]
        sems  = request.form.getlist("semester[]")
        if not sems and request.form.get("assign_semester"):
            sems = [request.form.get("assign_semester")]

        if fid and subj:
            for dept in depts:
                for yr in years:
                    for sem in sems:
                        for sec in secs:
                            query(
                                "INSERT INTO faculty_assignments "
                                "(faculty_id, department, year, semester, section, subject_name) "
                                "VALUES (%s,%s,%s,%s,%s,%s)",
                                (fid, dept, yr, sem, sec, subj), commit=True,
                            )
        return redirect(url_for("admin_dashboard", tab="assignments", msg="Assignment+Created"))

    # ── GET: Delete Assignment ────────────────────────────────
    if "delete_assignment" in request.args or ("delete_assignment_id" in request.form):
        aid = request.args.get("delete_assignment") or request.form.get("delete_assignment_id")
        query("DELETE FROM faculty_assignments WHERE assignment_id=%s", (aid,), commit=True)
        return redirect(url_for("admin_dashboard", tab="assignments", msg="Assignment+Deleted"))

    # ── GET: Delete Graduated ─────────────────────────────────
    if request.args.get("delete_graduated") == "1":
        d_dept = request.args.get("department", "")
        d_sec  = request.args.get("section", "")
        d_year = request.args.get("year", "")
        d_sem  = request.args.get("semester", "")
        if d_year == "4" and d_sem == "8":
            sql    = "DELETE FROM students WHERE year='4'"
            params = []
            if d_dept: sql += " AND department=%s"; params.append(d_dept)
            if d_sec:  sql += " AND section=%s";    params.append(d_sec)
            query(sql, tuple(params), commit=True)
            return redirect(url_for("admin_dashboard", tab="students", msg="Academic+Year+Over+Students+Deleted"))

    # ── POST: Bulk Update Students ────────────────────────────
    if request.method == "POST" and "bulk_update" in request.form:
        b_dept  = request.form.get("filter_dept", "") or request.form.get("bulk_dept", "")
        b_year  = request.form.get("filter_year", "") or request.form.get("bulk_year", "")
        b_sec   = request.form.get("filter_section", "") or request.form.get("bulk_section", "")
        n_year  = request.form.get("new_year", "") or request.form.get("bulk_year", "")
        n_sec   = request.form.get("new_section", "") or request.form.get("bulk_section", "")
        if n_year or n_sec:
            sets, params = [], []
            if n_year: sets.append("year=%s"); params.append(n_year)
            if n_sec:  sets.append("section=%s"); params.append(n_sec)
            sql = "UPDATE students SET " + ", ".join(sets) + " WHERE 1=1"
            if b_dept: sql += " AND department=%s"; params.append(b_dept)
            if b_year: sql += " AND year=%s";       params.append(b_year)
            if b_sec:  sql += " AND section=%s";    params.append(b_sec)
            query(sql, tuple(params), commit=True)
            return redirect(url_for("admin_dashboard", tab="students", msg="Bulk+Update+Successful"))

    # ── GET: Delete Student ───────────────────────────────────
    if "delete_student" in request.args:
        sid = request.args.get("delete_student")
        query("DELETE FROM students WHERE student_id=%s", (sid,), commit=True)
        return redirect(url_for("admin_dashboard", tab="students", msg="Student+Deleted"))

    # ── POST: Update Student ──────────────────────────────────
    if request.method == "POST" and "update_student" in request.form:
        old_id = request.form.get("old_id")
        new_id = request.form.get("student_id")
        name   = request.form.get("name")
        dept   = request.form.get("department")
        yr     = request.form.get("year")
        sec    = request.form.get("section")
        email  = request.form.get("email")
        phone  = request.form.get("phone")
        query(
            "UPDATE students SET student_id=%s, name=%s, department=%s, year=%s, section=%s, "
            "email=%s, phone=%s WHERE student_id=%s",
            (new_id, name, dept, yr, sec, email, phone, old_id), commit=True,
        )
        return redirect(url_for("admin_dashboard", tab="students", msg="Student+Updated"))

    # ── POST: Upload Timetable ────────────────────────────────
    if request.method == "POST" and "upload_timetable" in request.form:
        dept    = request.form.get("department") or request.form.get("tt_dept")
        yr      = request.form.get("year") or request.form.get("tt_year")
        section = request.form.get("section") or request.form.get("tt_sec")
        title   = request.form.get("file_title") or request.form.get("tt_title") or f"Timetable {dept} Yr{yr} Sec{section}"
        file    = request.files.get("uploaded_file") or request.files.get("tt_file")
        if file and file.filename:
            os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
            filename    = f"{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            target_path = f"{config.UPLOAD_FOLDER}/{filename}"
            file.save(target_path)
            ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
            query(
                "INSERT INTO department_files (title, file_path, file_type, department, year, section, category) "
                "VALUES (%s,%s,%s,%s,%s,%s,'timetable')",
                (title, filename, ext, dept, yr, section), commit=True,
            )
        return redirect(url_for("admin_dashboard", tab="timetable", msg="Uploaded"))

    # ── POST: Upload Course Material or Academic Calendar ────
    if request.method == "POST" and "upload_department_file" in request.form:
        category = request.form.get("file_category", "")
        if category not in ("course_material", "academic_calendar"):
            return redirect(url_for("admin_dashboard", tab="students", msg="Invalid+File+Category"))
        dept = request.form.get("file_department", "")
        yr = request.form.get("file_year", "")
        section = request.form.get("file_section", "All") or "All"
        title = request.form.get("file_title", "").strip()
        file = request.files.get("department_file")
        if file and file.filename and allowed_file(file.filename):
            os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
            filename = f"{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            file.save(os.path.join(config.UPLOAD_FOLDER, filename))
            ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
            query(
                "INSERT INTO department_files (title, file_path, file_type, department, year, section, category) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (title or secure_filename(file.filename), filename, ext, dept, yr, section, category),
                commit=True,
            )
        tab = "material" if category == "course_material" else "calendar"
        return redirect(url_for("admin_dashboard", tab=tab, msg="Uploaded"))

    # ── GET: Delete Course Material or Academic Calendar ─────
    if "delete_department_file" in request.args:
        file_id = request.args.get("delete_department_file")
        category = request.args.get("category", "course_material")
        rec = query("SELECT file_path FROM department_files WHERE id=%s AND category=%s", (file_id, category), one=True)
        if rec:
            file_path = rec.get("file_path", "")
            candidates = [file_path, os.path.join(config.UPLOAD_FOLDER, os.path.basename(file_path))]
            for candidate in candidates:
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                    except OSError:
                        pass
                    break
            query("DELETE FROM department_files WHERE id=%s AND category=%s", (file_id, category), commit=True)
        tab = "material" if category == "course_material" else "calendar"
        return redirect(url_for("admin_dashboard", tab=tab, msg="Deleted"))

    # ── GET: Delete Timetable ─────────────────────────────────
    if "delete_timetable" in request.args:
        tid = request.args.get("delete_timetable")
        rec = query("SELECT file_path FROM department_files WHERE id=%s", (tid,), one=True)
        if rec and os.path.exists(rec["file_path"]):
            try: os.remove(rec["file_path"])
            except Exception: pass
        query("DELETE FROM department_files WHERE id=%s", (tid,), commit=True)
        return redirect(url_for("admin_dashboard", tab="timetable", msg="Deleted"))

    # ── Determine Active Tab & Fetch Data ────────────────────
    active_tab     = request.args.get("tab", "students")
    filter_dept    = request.args.get("department", "")
    filter_year    = request.args.get("year", "")
    filter_section = request.args.get("section", "")
    filter_semester= request.args.get("semester", "")
    msg            = request.args.get("msg", "")

    students_data   = []
    faculty_data    = []
    assignments_data= []
    faculty_list    = query("SELECT faculty_id, name FROM faculty ORDER BY name", fetchall=True)
    attendance_data = []
    exam_data       = []
    fee_data        = []
    timetable_data  = []
    material_data   = []
    calendar_data   = []

    # Build attendance map for all students
    att_map = {}
    att_rows = query(
        "SELECT student_id, COUNT(*) AS total_classes, "
        "SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) AS present_count "
        "FROM student_attendance GROUP BY student_id",
        fetchall=True,
    )
    if att_rows:
        for r in att_rows:
            tot = r.get("total_classes", 0)
            pres = r.get("present_count", 0)
            att_map[r["student_id"]] = round((pres / tot * 100)) if tot > 0 else 0

    def _add_filter(sql, params, prefix="s"):
        if filter_dept:    sql += f" AND {prefix}.department=%s"; params.append(filter_dept)
        if filter_year:    sql += f" AND {prefix}.year=%s";       params.append(filter_year)
        if filter_section: sql += f" AND {prefix}.section=%s";    params.append(filter_section)
        return sql, params

    if active_tab in ("students", "performance"):
        sql    = "SELECT * FROM students WHERE 1=1"
        params = []
        if filter_dept:    sql += " AND department=%s"; params.append(filter_dept)
        if filter_year:    sql += " AND year=%s";       params.append(filter_year)
        if filter_section: sql += " AND section=%s";    params.append(filter_section)
        sql += " ORDER BY department, year, section, student_id"
        students_data = query(sql, tuple(params), fetchall=True)

    elif active_tab == "faculty":
        faculty_data = query("SELECT * FROM faculty ORDER BY faculty_id", fetchall=True)

    elif active_tab == "assignments":
        assignments_data = query(
            "SELECT a.*, f.name AS f_name FROM faculty_assignments a "
            "LEFT JOIN faculty f ON a.faculty_id=f.faculty_id ORDER BY a.assignment_id DESC",
            fetchall=True,
        )

    elif active_tab == "attendance":
        sql = (
            "SELECT a.student_id, COALESCE(s.name, '') AS name, a.attendance_date, a.class_name, a.status, a.reason, "
            "a.semester, a.department, a.year, a.section "
            "FROM attendance a LEFT JOIN students s ON a.student_id=s.student_id WHERE 1=1"
        )
        params = []
        if filter_dept:    sql += " AND a.department=%s"; params.append(filter_dept)
        if filter_year:    sql += " AND a.year=%s";       params.append(filter_year)
        if filter_section: sql += " AND a.section=%s";    params.append(filter_section)
        sql += " ORDER BY a.attendance_date DESC, a.student_id"
        attendance_data = query(sql, tuple(params), fetchall=True)

    elif active_tab == "exams":
        sql    = "SELECT e.*, s.name AS s_name FROM exam_results e LEFT JOIN students s ON e.student_id=s.student_id WHERE 1=1"
        params = []
        if filter_dept:    sql += " AND e.department=%s"; params.append(filter_dept)
        if filter_year:    sql += " AND e.year=%s";       params.append(filter_year)
        if filter_section: sql += " AND e.section=%s";    params.append(filter_section)
        sql += " ORDER BY e.semester DESC, e.exam_type DESC LIMIT 500"
        exam_data = query(sql, tuple(params), fetchall=True)

    elif active_tab == "fees":
        sql    = "SELECT t.*, s.name AS s_name, s.department, s.year, s.section FROM tuition_fees t LEFT JOIN students s ON t.student_id=s.student_id WHERE 1=1"
        params = []
        if filter_dept:    sql += " AND s.department=%s"; params.append(filter_dept)
        if filter_year:    sql += " AND s.year=%s";       params.append(filter_year)
        if filter_section: sql += " AND s.section=%s";    params.append(filter_section)
        sql += " ORDER BY t.student_id"
        fee_data = query(sql, tuple(params), fetchall=True)

    elif active_tab == "timetable":
        sql    = "SELECT * FROM department_files WHERE category='timetable'"
        params = []
        if filter_dept:    sql += " AND department=%s"; params.append(filter_dept)
        if filter_year:    sql += " AND year=%s";       params.append(filter_year)
        if filter_section: sql += " AND section=%s";    params.append(filter_section)
        sql += " ORDER BY uploaded_at DESC"
        timetable_data = query(sql, tuple(params), fetchall=True)

    elif active_tab in ("material", "calendar"):
        category = "course_material" if active_tab == "material" else "academic_calendar"
        sql = "SELECT * FROM department_files WHERE category=%s"
        params = [category]
        if filter_dept:    sql += " AND department=%s"; params.append(filter_dept)
        if filter_year:    sql += " AND year=%s";       params.append(filter_year)
        if filter_section: sql += " AND section=%s";    params.append(filter_section)
        sql += " ORDER BY uploaded_at DESC"
        files = query(sql, tuple(params), fetchall=True)
        if active_tab == "material":
            material_data = files
        else:
            calendar_data = files

    # ── CSV Download ──────────────────────────────────────────
    if request.args.get("download_csv") == "1":
        output   = io.StringIO()
        writer   = csv.writer(output)
        filename = f"export_{active_tab}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        if active_tab == "attendance":
            writer.writerow(["Student ID","Name","Department","Year","Section","Total Classes","Present","Absent","Attendance %"])
            for r in attendance_data:
                writer.writerow([r["student_id"], r.get("student_name",""), r["department"], r["year"], r["section"],
                                r["total_classes"], r["present_count"], r["absent_count"],
                                str(r.get("attendance_percent", 0)) + "%"])
        elif active_tab == "exams":
            writer.writerow(["Student ID","Name","Exam Type","Subject","Semester","Descriptive","Objective","Assignment","PPT","Total"])
            for r in exam_data:
                writer.writerow([r["student_id"], r.get("s_name",""), r.get("exam_type",""), r.get("subject_name",""),
                                r.get("semester",""), r.get("descriptive_marks","0"), r.get("objective_marks","0"),
                                r.get("Assignment_marks","0"), r.get("ppt_marks","0"), r.get("total_marks","0")])
        elif active_tab == "fees":
            writer.writerow(["Student ID","Name","Department","Year","Section","Total Fee","Other Fee","Paid Fee","Remaining Fee","Status"])
            for r in fee_data:
                writer.writerow([r["student_id"], r.get("s_name",""), r.get("department",""), r.get("year",""),
                                r.get("section",""), r.get("total_fee","0"), r.get("other_free","0"),
                                r.get("paid_fee","0"), r.get("remaining_fee","0"), r.get("payment_status","Pending")])

        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode("utf-8")),
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename,
        )

    # Group assignments by faculty for display
    grouped_assignments = {}
    for a in assignments_data:
        key = a["faculty_id"]
        if key not in grouped_assignments:
            grouped_assignments[key] = {"f_name": a.get("f_name",""), "faculty_id": key, "assignments": []}
        grouped_assignments[key]["assignments"].append(a)

    allowed_students_list = query("SELECT student_id FROM allowed_students ORDER BY student_id ASC", fetchall=True)

    return render_template(
        "admin_dashboard.html",
        active_tab=active_tab,
        msg=msg.replace("+", " "),
        filter_dept=filter_dept,
        filter_year=filter_year,
        filter_section=filter_section,
        filter_semester=filter_semester,
        students_data=students_data,
        faculty_data=faculty_data,
        assignments_data=assignments_data,
        faculty_list=faculty_list,
        grouped_assignments=grouped_assignments,
        attendance_data=attendance_data,
        exam_data=exam_data,
        fee_data=fee_data,
        timetable_data=timetable_data,
        material_data=material_data,
        calendar_data=calendar_data,
        allowed_students_list=allowed_students_list,
        att_map=att_map,
        admin_id=session.get("user_id"),
    )


# ── Serve uploaded files ──────────────────────────────────────
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_file(os.path.join(config.UPLOAD_FOLDER, os.path.basename(filename)))


# ── JNTUH Results API Route ───────────────────────────────────
EXAM_CODES = [
    # R25
    {'code':'1611','sem':1,'etype':'r','reg':'R25'},
    
    # R22
    {'code':'1665','sem':1,'etype':'r','reg':'R22'},
    {'code':'1674','sem':2,'etype':'r','reg':'R22'},
    {'code':'1680','sem':1,'etype':'s','reg':'R22'},
    {'code':'1685','sem':3,'etype':'r','reg':'R22'},
    {'code':'1688','sem':2,'etype':'s','reg':'R22'},
    {'code':'1692','sem':4,'etype':'r','reg':'R22'},
    {'code':'1695','sem':3,'etype':'s','reg':'R22'},
    {'code':'1700','sem':5,'etype':'r','reg':'R22'},
    {'code':'1703','sem':4,'etype':'s','reg':'R22'},

    # R20
    {'code':'1598','sem':1,'etype':'r','reg':'R20'},
    {'code':'1600','sem':1,'etype':'s','reg':'R20'},
    {'code':'1607','sem':2,'etype':'r','reg':'R20'},
    {'code':'1609','sem':2,'etype':'s','reg':'R20'},
    {'code':'1614','sem':3,'etype':'r','reg':'R20'},
    {'code':'1616','sem':3,'etype':'s','reg':'R20'},
    {'code':'1624','sem':4,'etype':'r','reg':'R20'},
    {'code':'1626','sem':4,'etype':'s','reg':'R20'},
    {'code':'1632','sem':5,'etype':'r','reg':'R20'},
    {'code':'1634','sem':5,'etype':'s','reg':'R20'},
    {'code':'1640','sem':6,'etype':'r','reg':'R20'},
    {'code':'1642','sem':6,'etype':'s','reg':'R20'},
    {'code':'1648','sem':7,'etype':'r','reg':'R20'},
    {'code':'1651','sem':7,'etype':'s','reg':'R20'},
    {'code':'1657','sem':8,'etype':'r','reg':'R20'},
    {'code':'1660','sem':8,'etype':'s','reg':'R20'},

    # R18
    {'code':'1524','sem':1,'etype':'r','reg':'R18'},
    {'code':'1525','sem':1,'etype':'s','reg':'R18'},
    {'code':'1527','sem':1,'etype':'s','reg':'R18'},
    {'code':'1535','sem':2,'etype':'r','reg':'R18'},
    {'code':'1537','sem':2,'etype':'s','reg':'R18'},
    {'code':'1540','sem':2,'etype':'s','reg':'R18'},
    {'code':'1545','sem':3,'etype':'r','reg':'R18'},
    {'code':'1547','sem':3,'etype':'s','reg':'R18'},
    {'code':'1550','sem':3,'etype':'s','reg':'R18'},
    {'code':'1556','sem':4,'etype':'r','reg':'R18'},
    {'code':'1559','sem':4,'etype':'s','reg':'R18'},
    {'code':'1562','sem':4,'etype':'s','reg':'R18'},
    {'code':'1566','sem':5,'etype':'r','reg':'R18'},
    {'code':'1568','sem':5,'etype':'s','reg':'R18'},
    {'code':'1571','sem':5,'etype':'s','reg':'R18'},
    {'code':'1577','sem':6,'etype':'r','reg':'R18'},
    {'code':'1580','sem':6,'etype':'s','reg':'R18'},
    {'code':'1583','sem':6,'etype':'s','reg':'R18'},
    {'code':'1586','sem':7,'etype':'r','reg':'R18'},
    {'code':'1588','sem':7,'etype':'s','reg':'R18'},
    {'code':'1591','sem':7,'etype':'s','reg':'R18'},
    {'code':'1593','sem':8,'etype':'r','reg':'R18'},
    {'code':'1595','sem':8,'etype':'s','reg':'R18'},

    # R16
    {'code':'1441','sem':1,'etype':'r','reg':'R16'},
    {'code':'1442','sem':1,'etype':'s','reg':'R16'},
    {'code':'1456','sem':2,'etype':'r','reg':'R16'},
    {'code':'1457','sem':2,'etype':'s','reg':'R16'},
    {'code':'1460','sem':2,'etype':'s','reg':'R16'},
    {'code':'1466','sem':3,'etype':'r','reg':'R16'},
    {'code':'1468','sem':3,'etype':'s','reg':'R16'},
    {'code':'1471','sem':3,'etype':'s','reg':'R16'},
    {'code':'1478','sem':4,'etype':'r','reg':'R16'},
    {'code':'1480','sem':4,'etype':'s','reg':'R16'},
    {'code':'1483','sem':4,'etype':'s','reg':'R16'},
    {'code':'1490','sem':5,'etype':'r','reg':'R16'},
    {'code':'1492','sem':5,'etype':'s','reg':'R16'},
    {'code':'1495','sem':5,'etype':'s','reg':'R16'},
    {'code':'1499','sem':6,'etype':'r','reg':'R16'},
    {'code':'1501','sem':6,'etype':'s','reg':'R16'},
    {'code':'1504','sem':6,'etype':'s','reg':'R16'},
    {'code':'1510','sem':7,'etype':'r','reg':'R16'},
    {'code':'1512','sem':7,'etype':'s','reg':'R16'},
    {'code':'1515','sem':7,'etype':'s','reg':'R16'},
    {'code':'1518','sem':8,'etype':'r','reg':'R16'},
    {'code':'1520','sem':8,'etype':'s','reg':'R16'},
    {'code':'1522','sem':8,'etype':'s','reg':'R16'},
]

GRADE_POINTS = {
    'O': 10.0, 'A+': 9.0, 'A': 8.0,
    'B+': 7.0, 'B': 6.0, 'C': 5.0,
    'F': 0.0, 'AB': 0.0, 'ABSENT': 0.0,
    'W': 0.0, '--': 0.0
}

def parse_jntuh_html(html, meta):
    import urllib.parse
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    name = ""
    for td in soup.find_all('td'):
        text = td.get_text().strip().lower()
        if 'student name' in text or 'name' == text:
            sibling = td.find_next_sibling('td')
            if sibling:
                name = sibling.get_text().strip()
                break
                
    tables = soup.find_all('table')
    subjects = []
    sgpa_val = 0.0
    
    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
            
        header_cells = rows[0].find_all(['td', 'th'])
        headers = [c.get_text(' ', strip=True).lower() for c in header_cells]
        
        is_result_table = any('grade' in h or 'subject' in h or 'credits' in h for h in headers)
        if not is_result_table:
            continue
            
        sub_code_idx = -1
        sub_name_idx = -1
        total_idx = -1
        grade_idx = -1
        credits_idx = -1
        result_idx = -1
        internal_idx = -1
        external_idx = -1
        
        for idx, h in enumerate(headers):
            header_key = re.sub(r'[^a-z]', '', h)
            if header_key in {'subjectcode', 'subcode', 'coursecode', 'code'}:
                sub_code_idx = idx
            if header_key in {'subjectname', 'subname', 'coursename', 'subject'}:
                sub_name_idx = idx
            if header_key in {'total', 'totalmarks', 'marks', 'mark'}:
                total_idx = idx
            if 'grade' in header_key and 'point' not in header_key:
                grade_idx = idx
            if 'credit' in header_key:
                credits_idx = idx
            if header_key in {'result', 'status', 'passfail'}:
                result_idx = idx
            if 'internal' in header_key or header_key.startswith('int'):
                internal_idx = idx
            if 'external' in header_key or header_key.startswith('ext'):
                external_idx = idx
                
        if sub_name_idx == -1 and grade_idx == -1:
            continue
            
        for row in rows[1:]:
            cells = row.find_all('td')
            if not cells:
                continue
            cell_texts = [c.get_text().strip() for c in cells]
            
            row_text = ' '.join(cell_texts).lower()
            if 'sgpa' in row_text or 'cgpa' in row_text:
                for ct in cell_texts:
                    try:
                        val = float(ct)
                        if 0.0 < val <= 10.0:
                            sgpa_val = val
                            break
                    except ValueError:
                        continue
                continue
                
            if len(cell_texts) < 2:
                continue
                
            sub_code = cell_texts[sub_code_idx] if 0 <= sub_code_idx < len(cell_texts) else ""
            sub_name = cell_texts[sub_name_idx] if 0 <= sub_name_idx < len(cell_texts) else ""
            total_marks = cell_texts[total_idx] if 0 <= total_idx < len(cell_texts) else ""
            grade = cell_texts[grade_idx] if 0 <= grade_idx < len(cell_texts) else ""
            credits = cell_texts[credits_idx] if 0 <= credits_idx < len(cell_texts) else ""
            result_status = cell_texts[result_idx].strip().upper() if 0 <= result_idx < len(cell_texts) else ""
            internal = cell_texts[internal_idx] if 0 <= internal_idx < len(cell_texts) else ""
            external = cell_texts[external_idx] if 0 <= external_idx < len(cell_texts) else ""
            
            if not sub_name or sub_name.lower() == 'subject name':
                continue
            if sub_name.isdigit() and len(sub_name) <= 2:
                continue
                
            grade_upper = grade.upper()
            if grade_upper not in GRADE_POINTS:
                for ct in cell_texts:
                    ct_upper = ct.upper()
                    if ct_upper in GRADE_POINTS:
                        grade = ct
                        grade_upper = ct_upper
                        break
                        
            points = GRADE_POINTS.get(grade_upper, 0.0)
            try:
                cred_num = float(credits)
            except ValueError:
                cred_num = 0.0

            if not result_status:
                result_status = 'PASS' if grade_upper not in ['F', 'AB', 'ABSENT', 'W', '--', ''] else 'FAIL'
                
            subjects.append({
                'code': sub_code,
                'name': sub_name,
                'marks': total_marks,
                'total': total_marks,
                'internal': internal,
                'external': external,
                'grade': grade if grade else '-',
                'credits': cred_num,
                'result': result_status,
                'points': points,
                'passed': grade_upper not in ['F', 'AB', 'ABSENT', 'W', '--']
            })
            
    if not subjects:
        return None
        
    total_credits = sum(s['credits'] for s in subjects if s['credits'] > 0)
    total_points = sum(s['credits'] * s['points'] for s in subjects if s['credits'] > 0)
    sgpa = round(total_points / total_credits, 2) if total_credits > 0 else (sgpa_val or 0.0)
    
    return {
        'semester': int(meta['sem']),
        'type': 'Regular' if meta['etype'] == 'r' else 'Supplementary',
        'examCode': meta['code'],
        'regulation': meta['reg'],
        'subjects': subjects,
        'sgpa': sgpa,
        'credits': total_credits,
        'studentName': name
    }

def fetch_jntuh_results_with_dob(roll, dob):
    """
    Attempt to fetch JNTUH results using roll number + date of birth.
    The JNTUH server now requires DOB + CAPTCHA. This method sends a POST
    request with the DOB; CAPTCHA solving is not possible programmatically,
    so this is a best-effort attempt that may still fail.
    """
    import requests
    import concurrent.futures

    match = re.match(r'^(\d{2})', roll)
    adm_year = int(match.group(1)) if match else 22

    priority_regs = []
    if adm_year >= 25: priority_regs.append('R25')
    if adm_year >= 22: priority_regs.append('R22')
    if adm_year >= 20: priority_regs.append('R20')
    if adm_year >= 18: priority_regs.append('R18')
    if adm_year >= 16: priority_regs.append('R16')

    filtered_codes = [c for c in EXAM_CODES if c['reg'] in priority_regs] if priority_regs else EXAM_CODES
    base_url = 'http://results.jntuh.ac.in/resultAction'
    results = []

    session = requests.Session()
    # Warm up the session to get JSESSIONID cookie
    try:
        session.get('http://results.jntuh.ac.in/', timeout=5,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    except Exception:
        pass

    def fetch_one(meta):
        form_data = {
            'degree': 'btech',
            'examCode': meta['code'],
            'etype': meta['etype'],
            'result': 'null',
            'grad': 'null',
            'type': 'intgrade',
            'htno': roll,
            'dob': dob,   # YYYY/MM/DD
        }
        try:
            r = session.post(base_url, data=form_data, timeout=8,
                            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            if r.status_code == 200 and len(r.text) > 500:
                parsed = parse_jntuh_html(r.text, meta)
                if parsed:
                    return parsed
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_one, meta) for meta in filtered_codes]
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)

    return results


def fetch_jntuh_results(roll):
    import requests
    import concurrent.futures
    match = re.match(r'^(\d{2})', roll)
    adm_year = int(match.group(1)) if match else 22
    
    priority_regs = []
    if adm_year >= 25: priority_regs.append('R25')
    if adm_year >= 22: priority_regs.append('R22')
    if adm_year >= 20: priority_regs.append('R20')
    if adm_year >= 18: priority_regs.append('R18')
    if adm_year >= 16: priority_regs.append('R16')
    
    filtered_codes = [c for c in EXAM_CODES if c['reg'] in priority_regs] if priority_regs else EXAM_CODES
    
    base_url = 'http://results.jntuh.ac.in/resultAction'
    results = []
    
    def fetch_one(meta):
        params = {
            'degree': 'btech',
            'examCode': meta['code'],
            'etype': meta['etype'],
            'result': 'null',
            'grad': 'null',
            'type': 'intgrade',
            'htno': roll
        }
        try:
            r = requests.get(base_url, params=params, timeout=5)
            if r.status_code == 200 and len(r.text) > 200:
                parsed = parse_jntuh_html(r.text, meta)
                if parsed:
                    return parsed
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(fetch_one, meta) for meta in filtered_codes]
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)
                
    return results

def calculate_cgpa(results):
    regular_by_sem = {}
    for r in results:
        sem = r['semester']
        if r['type'] == 'Regular':
            if sem not in regular_by_sem or r['sgpa'] > regular_by_sem[sem]['sgpa']:
                regular_by_sem[sem] = r
                
    for r in results:
        sem = r['semester']
        if sem not in regular_by_sem:
            regular_by_sem[sem] = r
            
    total_weighted_points = sum(r['sgpa'] * r['credits'] for r in regular_by_sem.values() if r['credits'] > 0)
    total_credits = sum(r['credits'] for r in regular_by_sem.values() if r['credits'] > 0)
    cgpa = round(total_weighted_points / total_credits, 2) if total_credits > 0 else 0.0
    return cgpa, total_credits

# (jntuh_results route is defined above at /jntuh_results)


# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)