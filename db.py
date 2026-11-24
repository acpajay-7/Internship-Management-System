from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import uuid

try:
  import libsql
except ImportError:
  libsql = None

DB_PATH = os.getenv("DATABASE_PATH", "data/reincrew.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


class _DictRow(dict):
  """Supports both row['col'] and row[0] indexing like sqlite3.Row."""

  def __init__(self, columns, values):
    super().__init__(zip(columns, values))
    self._values = tuple(values)

  def __getitem__(self, key):
    if isinstance(key, int):
      return self._values[key]
    return super().__getitem__(key)


class _LibsqlCursorWrapper:

  def __init__(self, raw_cursor):
    self._cur = raw_cursor

  @property
  def description(self):
    return self._cur.description

  @property
  def lastrowid(self):
    return getattr(self._cur, "lastrowid", None)

  @property
  def rowcount(self):
    return getattr(self._cur, "rowcount", -1)

  def _wrap_row(self, row):
    if row is None or not self._cur.description:
      return row
    cols = [d[0] for d in self._cur.description]
    return _DictRow(cols, row)

  def execute(self, sql, params=()):
    self._cur.execute(sql, params)
    return self

  def executemany(self, sql, seq_of_params):
    self._cur.executemany(sql, seq_of_params)
    return self

  def fetchone(self):
    return self._wrap_row(self._cur.fetchone())

  def fetchall(self):
    rows = self._cur.fetchall()
    if not rows or not self._cur.description:
      return rows
    cols = [d[0] for d in self._cur.description]
    return [_DictRow(cols, r) for r in rows]

  def close(self):
    if hasattr(self._cur, "close"):
      self._cur.close()


class _LibsqlConnWrapper:
  """Makes libsql connection compatible with sqlite3 context managers, row access, and pandas."""

  def __init__(self, raw_conn):
    self._conn = raw_conn

  def cursor(self):
    return _LibsqlCursorWrapper(self._conn.cursor())

  def execute(self, sql, params=()):
    cur = self.cursor()
    cur.execute(sql, params)
    return cur

  def executemany(self, sql, seq_of_params):
    cur = self.cursor()
    cur.executemany(sql, seq_of_params)
    return cur

  def executescript(self, script):
    self._conn.executescript(script)

  def commit(self):
    self._conn.commit()

  def sync(self):
    if hasattr(self._conn, "sync"):
      self._conn.sync()

  def close(self):
    if hasattr(self._conn, "close"):
      self._conn.close()

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    if exc_type is None:
      self.commit()
      self.sync()
    self.close()
    return False


def _sync_if_remote(conn):
  if hasattr(conn, "sync"):
    conn.sync()


def get_conn():
  turso_url = os.getenv("TURSO_DATABASE_URL")
  turso_token = os.getenv("TURSO_AUTH_TOKEN")

  if turso_url and turso_token and libsql is not None:
    raw = libsql.connect(
        "data/reincrew_replica.db",
        sync_url=turso_url,
        auth_token=turso_token,
    )
    raw.sync()
    conn = _LibsqlConnWrapper(raw)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

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


def apply_audit_schema(conn, schema_path="audit_log_schema.sql"):
  if Path(schema_path).exists():
    conn.executescript(Path(schema_path).read_text(encoding="utf-8"))
  else:
    conn.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_application
        ON applications (lower(email))
        WHERE status IN ('Received', 'Under Review', 'Shortlisted', 'Interview Scheduled', 'Selected');

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_email TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            action_type TEXT NOT NULL CHECK (action_type IN ('CREATE', 'STATUS_CHANGE', 'DOC_GENERATED', 'DELETE')),
            target_entity TEXT NOT NULL,
            target_id TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)


def init_db():
  with get_conn() as c:
    existing_users_sql = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if existing_users_sql and "'hr'" not in existing_users_sql["sql"]:
      c.executescript("""
            ALTER TABLE users RENAME TO users_old;
            CREATE TABLE users(
              id INTEGER PRIMARY KEY,
              email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('admin','hr','intern')),
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users(id, email, password_hash, role, created_at)
            SELECT id, email, password_hash, role, created_at FROM users_old;
            DROP TABLE users_old;
            """)

    existing_audit_sql = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='audit_logs'"
    ).fetchone()
    if existing_audit_sql and "'DELETE'" not in existing_audit_sql["sql"]:
      c.executescript("""
            ALTER TABLE audit_logs RENAME TO audit_logs_old;
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_email TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action_type TEXT NOT NULL CHECK (action_type IN ('CREATE', 'STATUS_CHANGE', 'DOC_GENERATED', 'DELETE')),
                target_entity TEXT NOT NULL,
                target_id TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO audit_logs(id, actor_email, actor_role, action_type, target_entity, target_id, old_value, new_value, created_at)
            SELECT id, actor_email, actor_role, action_type, target_entity, target_id, old_value, new_value, created_at FROM audit_logs_old;
            DROP TABLE audit_logs_old;
            """)

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('admin','hr','intern')), created_at TEXT DEFAULT CURRENT_TIMESTAMP);
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

    apply_audit_schema(c)

    cols = [
        row["name"]
        for row in c.execute("PRAGMA table_info(documents)").fetchall()
    ]
    if "doc_type" not in cols:
      c.execute(
          "ALTER TABLE documents ADD COLUMN doc_type TEXT DEFAULT 'Completion"
          " Letter'"
      )

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
    _sync_if_remote(c)


def submit_application_idempotent(
    full_name,
    email,
    phone,
    college,
    education,
    skills,
    preferred_domain,
    resume_path="",
    conn=None,
):
  clean_email = email.strip().lower()
  if not clean_email or "@" not in clean_email:
    raise ValueError("Valid email is required.")

  own_conn = conn is None
  c = get_conn() if own_conn else conn
  try:
    existing = c.execute(
        """SELECT application_id, status FROM applications
               WHERE lower(email)=? AND status IN ('Received', 'Under Review', 'Shortlisted', 'Interview Scheduled', 'Selected')""",
        (clean_email,),
    ).fetchone()
    if existing:
      return {
          "status": "duplicate_ignored",
          "idempotent": True,
          "application_id": existing["application_id"],
          "current_status": existing["status"],
      }

    app_id = "APP-" + uuid.uuid4().hex[:10].upper()
    try:
      c.execute(
          """INSERT INTO applications
                   (application_id, full_name, email, phone, college, education, skills, preferred_domain, resume_path, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
          (
              app_id,
              full_name.strip(),
              clean_email,
              phone.strip(),
              college.strip(),
              education.strip(),
              skills.strip(),
              preferred_domain,
              resume_path,
              "Received",
              datetime.now().isoformat(timespec="seconds"),
          ),
      )
      if own_conn:
        c.commit()
        _sync_if_remote(c)
      return {
          "status": "created",
          "idempotent": False,
          "application_id": app_id,
          "current_status": "Received",
      }
    except sqlite3.IntegrityError:
      existing = c.execute(
          "SELECT application_id, status FROM applications WHERE lower(email)=?"
          " ORDER BY id DESC LIMIT 1",
          (clean_email,),
      ).fetchone()
      return {
          "status": "duplicate_ignored",
          "idempotent": True,
          "application_id": existing["application_id"],
          "current_status": existing["status"],
      }
  finally:
    if own_conn:
      c.close()


def log_audit(
    actor_email,
    actor_role,
    action_type,
    target_entity,
    target_id,
    old_value=None,
    new_value=None,
    conn=None,
):
  own_conn = conn is None
  c = get_conn() if own_conn else conn
  try:
    cursor = c.execute(
        """INSERT INTO audit_logs(actor_email, actor_role, action_type, target_entity, target_id, old_value, new_value, created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
        (
            actor_email.strip().lower(),
            actor_role,
            action_type,
            target_entity,
            str(target_id),
            json.dumps(old_value) if old_value is not None else None,
            json.dumps(new_value) if new_value is not None else None,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    if own_conn:
      c.commit()
      _sync_if_remote(c)
    return cursor.lastrowid
  finally:
    if own_conn:
      c.close()


def fetch_audit_logs(limit=100, conn=None):
  own_conn = conn is None
  c = get_conn() if own_conn else conn
  try:
    rows = c.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    result = []
    for r in rows:
      d = dict(r)
      for col in ("old_value", "new_value"):
        if d[col]:
          try:
            d[col] = json.loads(d[col])
          except Exception:
            pass
      result.append(d)
    return result
  finally:
    if own_conn:
      c.close()


def create_hr_user(
    super_admin_email, super_admin_role, hr_name, hr_email, hr_password
):
  if super_admin_role != "admin":
    raise PermissionError("Only Super Admin ('admin') can create HR accounts.")
  clean_email = hr_email.strip().lower()
  clean_name = hr_name.strip()
  with get_conn() as c:
    existing = c.execute(
        "SELECT id, role FROM users WHERE email=?", (clean_email,)
    ).fetchone()
    if existing:
      return False, f"User {clean_email} already exists ({existing['role']})."
    c.execute(
        "INSERT INTO users(email,password_hash,role) VALUES(?,?,?)",
        (clean_email, hash_password(hr_password), "hr"),
    )
    c.commit()
    _sync_if_remote(c)
  log_audit(
      actor_email=super_admin_email,
      actor_role=super_admin_role,
      action_type="CREATE",
      target_entity="user",
      target_id=clean_email,
      old_value=None,
      new_value={"name": clean_name, "email": clean_email, "role": "hr"},
  )
  return True, f"HR Admin {clean_name} ({clean_email}) created successfully."


def delete_hr_user(super_admin_email, super_admin_role, target_hr_email):
  if super_admin_role != "admin":
    raise PermissionError("Only Super Admin ('admin') can delete HR accounts.")
  clean_target = target_hr_email.strip().lower()
  with get_conn() as c:
    row = c.execute(
        "SELECT id, email, role FROM users WHERE email=?", (clean_target,)
    ).fetchone()
    if not row or row["role"] != "hr":
      return False, f"HR account '{clean_target}' not found."
    c.execute("DELETE FROM users WHERE id=?", (row["id"],))
    c.commit()
    _sync_if_remote(c)
  log_audit(
      actor_email=super_admin_email,
      actor_role=super_admin_role,
      action_type="DELETE",
      target_entity="user",
      target_id=clean_target,
      old_value={"email": clean_target, "role": "hr"},
      new_value=None,
  )
  return True, f"HR Admin ({clean_target}) has been deleted."


def delete_intern_access(actor_email, actor_role, internship_id):
  """Allows Admin ('admin') and HR ('hr') to revoke/delete an intern's portal login access."""
  if actor_role not in ("admin", "hr"):
    raise PermissionError(
        "Only Admin or HR can revoke/delete intern portal access."
    )
  with get_conn() as c:
    intern = c.execute(
        "SELECT internship_id, full_name, email, status FROM interns WHERE"
        " internship_id=?",
        (internship_id,),
    ).fetchone()
    if not intern:
      return False, f"Intern '{internship_id}' not found."

    clean_email = (intern["email"] or "").strip().lower()
    old_status = intern["status"]

    c.execute(
        "DELETE FROM users WHERE lower(email)=? AND role='intern'",
        (clean_email,),
    )
    c.execute(
        "UPDATE interns SET status='Access Revoked' WHERE internship_id=?",
        (internship_id,),
    )
    c.commit()
    _sync_if_remote(c)

  log_audit(
      actor_email=actor_email,
      actor_role=actor_role,
      action_type="DELETE",
      target_entity="intern",
      target_id=internship_id,
      old_value={
          "email": clean_email,
          "full_name": intern["full_name"],
          "status": old_status,
      },
      new_value={"status": "Access Revoked", "login_deleted": True},
  )
  return (
      True,
      (
          f"Portal access for {intern['full_name']} ({clean_email}) has been"
          " deleted."
      ),
  )


def change_user_password(email, old_password, new_password):
  """Verifies old password and updates to a new alphanumeric password (letters + numbers)."""
  clean_email = email.strip().lower()
  if len(new_password) < 6:
    return False, "New password must be at least 6 characters long."
  if not (
      any(ch.isalpha() for ch in new_password)
      and any(ch.isdigit() for ch in new_password)
  ):
    return False, "New password must contain both letters and numbers."
  if old_password == new_password:
    return False, "New password must be different from your current password."

  with get_conn() as c:
    row = c.execute(
        "SELECT id, password_hash FROM users WHERE email=?", (clean_email,)
    ).fetchone()
    if not row or not check_password(old_password, row["password_hash"]):
      return False, "Current (old) password is incorrect."
    c.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (hash_password(new_password), row["id"]),
    )
    c.commit()
    _sync_if_remote(c)
  return True, "Password updated successfully!"


def upsert_intern_user(email, password):
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
        _sync_if_remote(c)
    else:
      c.execute(
          "INSERT INTO users(email,password_hash,role) VALUES(?,?,?)",
          (email.lower(), hash_password(password), "intern"),
      )
      c.commit()
      _sync_if_remote(c)


def verify_user(email, password, expected_roles=None):
  with get_conn() as c:
    row = c.execute(
        "SELECT * FROM users WHERE email=?", (email.lower(),)
    ).fetchone()
    if row and check_password(password, row["password_hash"]):
      if expected_roles and row["role"] not in expected_roles:
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
    _sync_if_remote(c)