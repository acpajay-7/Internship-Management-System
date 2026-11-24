-- 1. Server-side idempotency: Ek email se ek hi active application allowed
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_application
ON applications (lower(email))
WHERE status IN ('Received', 'Under Review', 'Shortlisted', 'Interview Scheduled', 'Selected');

-- 2. Audit log table: Har admin / HR action ka permanent record
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_email TEXT NOT NULL,
    actor_role TEXT NOT NULL,          -- 'admin' (super admin) or 'hr' (normal admin)
    action_type TEXT NOT NULL CHECK (action_type IN ('CREATE', 'STATUS_CHANGE', 'DOC_GENERATED', 'DELETE')),
    target_entity TEXT NOT NULL,       -- 'application', 'internship', 'intern', 'task', 'document', 'user'
    target_id TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (id DESC);