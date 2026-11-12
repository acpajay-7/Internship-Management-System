import sqlite3, os, hashlib, hmac
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "data/reincrew.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return salt.hex() + "$" + key.hex()

def check_password(password, stored):
    try:
        salt_hex, key_hex = stored.split("$")
        candidate = hash_password(password, bytes.fromhex(salt_hex)).split("$")[1]
        return hmac.compare_digest(candidate, key_hex)
    except Exception:
        return False

def init_db():
    with get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('admin','intern')), created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS internships(
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, domain TEXT NOT NULL, department TEXT,
          duration TEXT, description TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS applications(
          id INTEGER PRIMARY KEY, application_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
          email TEXT NOT NULL, phone TEXT, college TEXT, education TEXT, skills TEXT,
          preferred_domain TEXT, resume_path TEXT, status TEXT, admin_notes TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS interns(
          id INTEGER PRIMARY KEY, internship_id TEXT UNIQUE NOT NULL, application_id TEXT,
          full_name TEXT, email TEXT UNIQUE, domain TEXT, start_date TEXT, end_date TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY, internship_id TEXT, title TEXT, description TEXT, priority TEXT,
          deadline TEXT, status TEXT, submission_link TEXT, submission_note TEXT, submitted_at TEXT,
          review_feedback TEXT, created_at TEXT,
          FOREIGN KEY(internship_id) REFERENCES interns(internship_id));
        CREATE TABLE IF NOT EXISTS daily_reports(
          id INTEGER PRIMARY KEY, internship_id TEXT, report_date TEXT, completed TEXT,
          work_description TEXT, submission_links TEXT, hours_spent TEXT, pending TEXT, blockers TEXT,
          created_at TEXT, FOREIGN KEY(internship_id) REFERENCES interns(internship_id));
        CREATE TABLE IF NOT EXISTS documents(
          id INTEGER PRIMARY KEY, internship_id TEXT, document_id TEXT UNIQUE, file_path TEXT, created_at TEXT,
          FOREIGN KEY(internship_id) REFERENCES interns(internship_id));
        CREATE TABLE IF NOT EXISTS email_logs(
          id INTEGER PRIMARY KEY, recipient TEXT, subject TEXT, status TEXT, detail TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        count = c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        if count == 0:
            admin_email = os.getenv("ADMIN_EMAIL", "admin@reincrew.local")
            admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
            c.execute("INSERT OR IGNORE INTO users(email,password_hash,role) VALUES(?,?,?)",
                      (admin_email.lower(), hash_password(admin_password), "admin"))
        count = c.execute("SELECT COUNT(*) FROM internships").fetchone()[0]
        if count == 0:
            c.execute("""INSERT INTO internships(title,domain,department,duration,description,active)
                         VALUES(?,?,?,?,?,1)""",
                      ("Data Analytics Intern", "Data Analytics", "Analytics", "8 weeks",
                       "Work on data cleaning, analysis, dashboards and reporting."))
            c.execute("""INSERT INTO internships(title,domain,department,duration,description,active)
                         VALUES(?,?,?,?,?,1)""",
                      ("AI/ML Intern", "AI/ML", "Technology", "8 weeks",
                       "Work on Python, machine learning, model evaluation and deployment."))
        c.commit()

def create_user(email, password, role):
    with get_conn() as c:
        c.execute("INSERT INTO users(email,password_hash,role) VALUES(?,?,?)",
                  (email.lower(), hash_password(password), role))
        c.commit()

def verify_user(email, password):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
    if row and check_password(password, row["password_hash"]):
        return {"email": row["email"], "role": row["role"]}
    return None

def log_email(recipient, subject, status, detail):
    with get_conn() as c:
        c.execute("INSERT INTO email_logs(recipient,subject,status,detail) VALUES(?,?,?,?)",
                  (recipient, subject, status, detail))
        c.commit()
