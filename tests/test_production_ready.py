import json
from pathlib import Path
import sqlite3
from db import (
    apply_audit_schema,
    fetch_audit_logs,
    log_audit,
    submit_application_idempotent,
)


def make_test_conn():
  conn = sqlite3.connect(":memory:")
  conn.row_factory = sqlite3.Row
  conn.executescript("""
        CREATE TABLE applications(
          id INTEGER PRIMARY KEY, application_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
          email TEXT NOT NULL, phone TEXT, college TEXT, education TEXT, skills TEXT,
          preferred_domain TEXT, resume_path TEXT, status TEXT, admin_notes TEXT, created_at TEXT
        );
    """)
  apply_audit_schema(conn, "audit_log_schema.sql")
  return conn


def test_duplicate_application_idempotent():
  conn = make_test_conn()
  first = submit_application_idempotent(
      "Ajay",
      "Ajay@Example.com",
      "9999999999",
      "NIT",
      "B.Tech",
      "Python",
      "AI/ML",
      conn=conn,
  )
  second = submit_application_idempotent(
      "Ajay",
      "  ajay@example.com ",
      "9999999999",
      "NIT",
      "B.Tech",
      "Python",
      "AI/ML",
      conn=conn,
  )

  assert first["status"] == "created"
  assert first["idempotent"] is False
  assert second["status"] == "duplicate_ignored"
  assert second["idempotent"] is True
  assert second["application_id"] == first["application_id"]

  total = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
  assert total == 1


def test_audit_logging_and_json_export():
  conn = make_test_conn()

  log_audit(
      "admin@reincrew.local",
      "admin",
      "CREATE",
      "user",
      "hr@reincrew.local",
      None,
      {"name": "Priya Sharma", "email": "hr@reincrew.local", "role": "hr"},
      conn=conn,
  )
  log_audit(
      "hr@reincrew.local",
      "hr",
      "STATUS_CHANGE",
      "application",
      "APP-101",
      {"status": "Received"},
      {"status": "Selected"},
      conn=conn,
  )
  log_audit(
      "hr@reincrew.local",
      "hr",
      "DOC_GENERATED",
      "document",
      "RC-OFFER-20261124",
      None,
      {"doc_type": "Offer Letter"},
      conn=conn,
  )

  logs = fetch_audit_logs(limit=10, conn=conn)
  assert len(logs) == 3
  assert {item["action_type"] for item in logs} == {
      "CREATE",
      "STATUS_CHANGE",
      "DOC_GENERATED",
  }

  Path("sample_audit_logs.json").write_text(
      json.dumps(logs, indent=2), encoding="utf-8"
  )