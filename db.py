import hashlib
import hmac
import os
from pathlib import Path
import sqlite3

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
        CREATE TABLE IF NOT EXISTS task_templates(
          id INTEGER PRIMARY KEY, domain TEXT NOT NULL, title TEXT NOT NULL,
          description TEXT NOT NULL, priority TEXT DEFAULT 'Medium', due_days INTEGER DEFAULT 7);
        CREATE TABLE IF NOT EXISTS daily_reports(
          id INTEGER PRIMARY KEY, internship_id TEXT, report_date TEXT, completed TEXT,
          work_description TEXT, submission_links TEXT, hours_spent TEXT, pending TEXT, blockers TEXT,
          created_at TEXT, FOREIGN KEY(internship_id) REFERENCES interns(internship_id));
        CREATE TABLE IF NOT EXISTS documents(
          id INTEGER PRIMARY KEY, internship_id TEXT, document_id TEXT UNIQUE,
          doc_type TEXT DEFAULT 'Completion Letter', file_path TEXT, created_at TEXT,
          FOREIGN KEY(internship_id) REFERENCES interns(internship_id));
        CREATE TABLE IF NOT EXISTS email_logs(
          id INTEGER PRIMARY KEY, recipient TEXT, subject TEXT, status TEXT, detail TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)

    # Safe schema migration if documents table existed without doc_type
    cols = [
        row["name"]
        for row in c.execute("PRAGMA table_info(documents)").fetchall()
    ]
    if "doc_type" not in cols:
      c.execute(
          "ALTER TABLE documents ADD COLUMN doc_type TEXT DEFAULT 'Completion"
          " Letter'"
      )

    # Seed default admin
    if (
        c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        == 0
    ):
      admin_email = os.getenv("ADMIN_EMAIL", "admin@reincrew.local")
      admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
      c.execute(
          "INSERT OR IGNORE INTO users(email,password_hash,role) VALUES(?,?,?)",
          (admin_email.lower(), hash_password(admin_password), "admin"),
      )

    # Seed default internships
    if c.execute("SELECT COUNT(*) FROM internships").fetchone()[0] == 0:
      c.executemany(
          """INSERT INTO internships(title,domain,department,duration,description,active)
             VALUES(?,?,?,?,?,1)""",
          [
              (
                  "Data Analytics Intern",
                  "Data Analytics",
                  "Analytics",
                  "8 weeks",
                  "Work on data cleaning, analysis, dashboards and reporting.",
              ),
              (
                  "AI/ML Intern",
                  "AI/ML",
                  "Technology",
                  "8 weeks",
                  (
                      "Work on Python, machine learning, model evaluation and"
                      " deployment."
                  ),
              ),
              (
                  "Web Development Intern",
                  "Web Development",
                  "Engineering",
                  "8 weeks",
                  (
                      "Build full-stack web applications, REST APIs, and"
                      " responsive UI."
                  ),
              ),
          ],
      )

    # Seed default stream-based task templates
    if c.execute("SELECT COUNT(*) FROM task_templates").fetchone()[0] == 0:
      c.executemany(
          """INSERT INTO task_templates(domain,title,description,priority,due_days)
             VALUES(?,?,?,?,?)""",
          [
              (
                  "Data Analytics",
                  "Week 1: Exploratory Data Analysis & Cleaning",
                  (
                      "Clean the provided raw dataset using Pandas/SQL, handle"
                      " missing values, and submit a cleaned CSV + Jupyter"
                      " Notebook."
                  ),
                  "High",
                  7,
              ),
              (
                  "Data Analytics",
                  "Week 2: KPI Extraction & SQL Reporting",
                  (
                      "Write SQL queries to compute retention, conversion, and"
                      " cohort metrics with an executive summary."
                  ),
                  "Medium",
                  14,
              ),
              (
                  "Data Analytics",
                  "Week 3: Interactive BI Dashboard",
                  (
                      "Build and deploy an interactive dashboard"
                      " (Streamlit/PowerBI) visualizing key business trends."
                  ),
                  "High",
                  21,
              ),
              (
                  "AI/ML",
                  "Week 1: Feature Engineering & Baseline Model",
                  (
                      "Preprocess training data, engineer domain features, and"
                      " train a baseline ML model with cross-validation."
                  ),
                  "High",
                  7,
              ),
              (
                  "AI/ML",
                  "Week 2: Model Optimization & Evaluation Report",
                  (
                      "Tune hyperparameters, evaluate precision/recall/ROC-AUC,"
                      " and submit an error analysis report."
                  ),
                  "Medium",
                  14,
              ),
              (
                  "AI/ML",
                  "Week 3: End-to-End Inference App Deployment",
                  (
                      "Wrap the trained model into a FastAPI or Streamlit app"
                      " and push complete code to GitHub."
                  ),
                  "High",
                  21,
              ),
              (
                  "Web Development",
                  "Week 1: Database Schema & REST API Setup",
                  (
                      "Design normalized database tables and implement CRUD API"
                      " endpoints with input validation."
                  ),
                  "High",
                  7,
              ),
              (
                  "Web Development",
                  "Week 2: Frontend UI & Authentication Integration",
                  (
                      "Connect frontend views with backend APIs and implement"
                      " role-based authentication."
                  ),
                  "Medium",
                  14,
              ),
              (
                  "Web Development",
                  "Week 3: Testing & Production Deployment",
                  (
                      "Write unit/integration tests and deploy the live web"
                      " application with documentation."
                  ),
                  "High",
                  21,
              ),
          ],
      )
    c.commit()


def create_user(email, password, role):
  with get_conn() as c:
    c.execute(
        "INSERT INTO users(email,password_hash,role) VALUES(?,?,?)",
        (email.lower(), hash_password(password), role),
    )
    c.commit()


def upsert_intern_user(email, password):
  """Creates a new intern user or updates password if email already exists as intern."""
  with get_conn() as c:
    existing = c.execute(
        "SELECT id, role FROM users WHERE email=?", (email.lower(),)
    ).fetchone()
    if existing:
      if existing["role"] == "intern":
        c.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (hash_password(password), email.lower()),
        )
        c.commit()
    else:
      c.execute(
          "INSERT INTO users(email,password_hash,role) VALUES(?,?,?)",
          (email.lower(), hash_password(password), "intern"),
      )
      c.commit()


def verify_user(email, password, expected_role=None):
  with get_conn() as c:
    row = c.execute(
        "SELECT * FROM users WHERE email=?", (email.lower(),)
    ).fetchone()
    if row and check_password(password, row["password_hash"]):
      if expected_role and row["role"] != expected_role:
        return None
      return {"email": row["email"], "role": row["role"]}
    return None


def log_email(recipient, subject, status, detail):
  with get_conn() as c:
    c.execute(
        "INSERT INTO email_logs(recipient,subject,status,detail)"
        " VALUES(?,?,?,?)",
        (recipient, subject, status, detail),
    )
    c.commit()