# ReinCrew Internship Management System — MVP

A beginner-friendly Streamlit + SQLite prototype for the internship lifecycle:
application → admin review → intern profile → task assignment → daily reports →
task review → completion approval → PDF document.

## Important scope statement

This is a working MVP prototype, not a production-ready enterprise deployment.
The following are implemented in this code:
- Public internship listing and application form
- Unique application IDs and duplicate active-application check
- Resume upload
- Admin login and dashboard
- Application status decisions and intern profile creation on selection
- Intern login creation by admin
- Task assignment, intern submission and admin review
- Daily work reports and basic weekly report summary
- Completion gate requiring all tasks to be approved
- PDF completion letter generation and document ID
- SMTP email integration when valid credentials are configured
- Email delivery attempt log

Partially implemented / not yet production-ready:
- Role access is basic; add stronger session controls, password reset and audit trails
- Selection does not yet create a signed offer-letter PDF or acceptance workflow
- Task allocation is manual; skills/domain/availability/workload-based auto-allocation is pending
- Daily reminder scheduling and weekly email digests need a scheduler/worker
- Attendance check-in/check-out is not included; daily reporting is included
- Certificate delivery currently emails a notification; PDF attachment delivery should be added
- Upload validation, antivirus scanning, private object storage and retention policy are pending
- SQLite is suitable for local prototype, not multi-user production hosting
- Streamlit Community Cloud local filesystem is ephemeral; use managed PostgreSQL and object storage for production
- Add rate limiting, CSRF/security review, backups, monitoring, and privacy/legal review before real candidate data

## Run locally (Windows PowerShell)

1. Install Python 3.10 or newer.
2. Extract this ZIP.
3. Open PowerShell in the extracted folder.
4. Create and activate an environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

5. Install packages:

```powershell
pip install -r requirements.txt
```

6. Copy `.env.example` to `.env`. Change the admin password. Configure SMTP only if you want real emails.
7. Start the app:

```powershell
streamlit run app.py
```

8. Open the local URL shown by Streamlit.

Default local admin (change immediately):
- Email: `admin@reincrew.local`
- Password: `ChangeMe123!`

The app loads `.env` automatically using `python-dotenv`.

## Main modules

- `app.py`: Streamlit pages, forms, dashboards and workflow actions.
- `db.py`: SQLite database, tables, password hashing and login verification.
- `services.py`: resume storage, SMTP email sending and PDF generation.
- `data/`: local database (created automatically).
- `uploads/`: uploaded resumes.
- `generated/`: generated PDF documents.

## Database tables

`users`, `internships`, `applications`, `interns`, `tasks`, `daily_reports`, `documents`, `email_logs`.

## GitHub deployment

1. Create a new private GitHub repository for the prototype.
2. Do not upload `.env`, real candidate data, database files, resumes, or generated certificates.
3. Commit the source files and push to GitHub.
4. In Streamlit Community Cloud, create an app from the repository and set `app.py` as the entry point.
5. Add secrets in Streamlit app settings. The current prototype reads environment variables; for Community Cloud, adapt startup to read `st.secrets` or set environment variables in the deployment environment.
6. Important: Streamlit Community Cloud storage is not durable. Do not use this SQLite/upload-folder setup for actual ReinCrew candidate records. For real deployment, migrate to managed PostgreSQL and private object storage (e.g. S3-compatible storage), and use a background worker/scheduler for reminders.
7. Test the full workflow with dummy records before sharing.

## End-to-end test checklist

1. Open the public application form and submit a test application.
2. Confirm an `APP-...` ID appears.
3. Log in as admin and find the application.
4. Change status to Shortlisted, then Selected.
5. Confirm an `INT-...` intern profile is created.
6. Create intern login from Admin users.
7. Log out and log in as the intern.
8. Submit a task link and notes.
9. As admin, review the task and approve it.
10. As intern, submit a daily report.
11. As admin, generate the completion PDF after all tasks are approved.
12. Check the Email log. Without SMTP credentials, delivery is not sent; the app records that configuration is missing.

## Suggested two-day implementation plan

Day 1:
- Run app locally and verify application flow
- Review application admin actions
- Configure email and test with your own email
- Test selection and intern account creation
- Test task assignment and submission

Day 2:
- Test daily reporting and completion letter
- Fix bugs and add validation
- Deploy a demo with dummy data
- Record end-to-end screen capture
- Prepare test evidence, API/database notes and pending-work report

## API note

This MVP is a Streamlit application and does not expose a REST API. If ReinCrew requires integration with its existing website or backend, build authenticated API endpoints (e.g. FastAPI) and connect this interface to the approved production database. Do not connect directly to ReinCrew production data without authorization.
