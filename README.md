# ReinCrew Internship Management System

An end-to-end **Internship Lifecycle Management Platform** built using Streamlit, SQLite, ReportLab, and Gmail SMTP. The system automates the complete internship management workflow, from public internship applications and interview scheduling to student onboarding, stream-based task assignments, daily progress tracking, and automated PDF offer letters and completion certificates.

---

## 1. Project Overview

The **ReinCrew Internship Management System** is designed to simplify and automate internship operations for administrators and interns through a centralized web-based portal.

It provides dedicated interfaces for applicants, administrators, and interns, ensuring a structured and transparent internship lifecycle.

The platform handles:

- Public internship discovery and applications.
- Resume submission and application tracking.
- Interview scheduling and candidate selection.
- Automated intern account creation.
- Offer letter generation and email delivery.
- Stream-specific task assignment.
- Daily progress and attendance reporting.
- Task submission and administrative approval.
- Automated internship completion certificates.

---

## 2. Key Features

### 2.1 Public Internship Portal & Role-Based Authentication

**Internship Discovery and Application**
- Browse available internship opportunities.
- Submit applications with personal and academic information.
- Upload resumes in PDF, DOC, and DOCX formats.
- Receive a unique application tracking ID (`APP-XXXXXXXXXX`).
- Automated email confirmation after successful submission.
- Duplicate active-application prevention.

**Dedicated Login Portals**
- Separate Student / Intern Login and Administrator Login.
- Strict backend role-based access control.
- Secure password storage using salted PBKDF2-HMAC-SHA256 hashing.
- Protected dashboards based on user roles.

### 2.2 Automated Selection, Onboarding & Offer Letters

**One-Click Selection Pipeline**

When an administrator changes an applicant's status to `Selected`, the system automatically:

1. Creates a unique intern profile (`INT-XXXXXXXX`).
2. Registers student portal login credentials.
3. Generates a cryptographically secure 5-digit temporary password.
4. Sends login credentials through email.
5. Generates a timestamped Offer Letter PDF.
6. Attaches the offer letter to the selection email.
7. Assigns domain-specific internship tasks.

**Interview Scheduling**
- Filter applicants according to application status.
- View and inspect submitted resumes.
- Schedule candidate interviews.
- Share meeting and assessment links.
- Send automated application status notifications.

### 2.3 Stream-Based Task Management & Daily Reporting

**Configurable Stream Templates**

Administrators can create reusable task templates for different internship domains, including:

- Data Analytics
- Artificial Intelligence
- Machine Learning
- Web Development
- Other technical and non-technical streams.

Each task template supports configurable priorities and relative deadlines.

**Intern Workspace**

Interns can:
- View assigned internship tasks.
- Track task deadlines and priorities.
- Submit GitHub and Google Drive deliverable links.
- Add notes and task-related descriptions.
- Maintain daily work progress reports.

**Daily Reporting**

Interns can record:
- Hours spent working.
- Tasks completed.
- Pending activities.
- Challenges and blockers.
- Daily internship progress.

**Administrative Review**
- Review submitted task deliverables.
- Approve completed tasks.
- Request revisions.
- Reject submissions when necessary.
- Export daily attendance and progress records as CSV files.

### 2.4 Automated Internship Completion Certificate

**Task-Gated Completion Approval**

The completion approval process is restricted until all assigned tasks for an intern have reached `Approved` status.

**Automatic Certificate Generation**

Once all tasks are approved, the system:

1. Generates a verified Completion Letter PDF.
2. Assigns a unique document identifier (`RC-CERT-...`).
3. Updates the internship status to `Completed`.
4. Emails the completion document to the intern.
5. Unlocks the document for download under **My Documents**.

Administrators can also manually trigger the completion process where applicable.

---

## 3. Technology Stack

| Component | Technology |
|---|---|
| Frontend & Web Application | Streamlit |
| Backend Logic | Python |
| Database | SQLite |
| PDF Generation | ReportLab |
| Email Notifications | Gmail SMTP |
| Authentication | PBKDF2-HMAC-SHA256 |
| Data Export | CSV |
| Configuration | Environment Variables / Streamlit Secrets |
| Version Control | Git & GitHub |

---

## 4. Project Architecture

```text
reincrew_internship_mng/
│
├── app.py
│   └── Streamlit UI, authentication, role routing,
│       dashboards, and workflow triggers
│
├── db.py
│   └── SQLite database schema, migrations,
│       password hashing, and authentication helpers
│
├── services.py
│   └── PDF generation, SMTP email attachments,
│       and stream-based task assignment
│
├── requirements.txt
│   └── Python project dependencies
│
├── .env.example
│   └── Environment variable configuration template
│
├── data/
│   └── reincrew.db
│
├── uploads/
│   └── Candidate resume storage
│
└── generated/
    └── Offer Letters and Completion Certificates
```

---

## 5. Database Architecture

The application uses SQLite for structured storage and internship lifecycle management.

| Table | Purpose |
|---|---|
| `users` | Stores hashed credentials and role assignments (admin or intern). |
| `internships` | Stores active internship listings, domains, departments, and durations. |
| `applications` | Stores applicant information, resume paths, application status, and admin notes. |
| `interns` | Stores selected intern profiles, assigned domains, start/end dates, and internship status. |
| `task_templates` | Stores reusable stream-specific task definitions and deadline offsets. |
| `tasks` | Stores individual intern tasks, deliverable links, feedback, and approval status. |
| `daily_reports` | Stores daily work logs, hours tracked, and reported blockers. |
| `documents` | Stores metadata and file paths for issued offer and completion letters. |
| `email_logs` | Maintains an audit log of outgoing SMTP notifications and delivery statuses. |

---

## 6. Installation & Local Setup

### Prerequisites

Ensure the following software is installed:

- Python 3.10 or later (compatible with project dependencies).
- Git.
- Visual Studio Code or another code editor.
- Gmail account with an App Password enabled for SMTP authentication.

### Step 1: Clone the Repository

```bash
git clone https://github.com/acpajay-7/Internship-Management-System.git

cd Internship-Management-System
```

### Step 2: Create a Virtual Environment

**Option A: Using uv**

```powershell
uv venv

.\.venv\Scripts\Activate.ps1

uv pip install -r requirements.txt
```

**Option B: Using Standard Python venv**

```powershell
py -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Create a `.env` file in the project root directory using `.env.example` as the template.

```env
ADMIN_EMAIL=admin@reincrew.local
ADMIN_PASSWORD=ChangeMe123!

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_FROM=your-email@gmail.com

DATABASE_PATH=data/reincrew.db
```

**Important:**
- Replace the placeholder Gmail credentials with your actual SMTP configuration.
- Use a Google App Password rather than your regular Gmail password.
- Never upload `.env` files or actual credentials to GitHub.
- Use strong administrator credentials in production.

### Step 4: Launch the Application

```bash
streamlit run app.py
```

The application will be available at:

```text
http://localhost:8501
```

---

## 7. Deployment

### Streamlit Community Cloud

The application can be deployed using Streamlit Community Cloud.

**Deployment Steps:**

1. Push the project repository to GitHub.
2. Visit [Streamlit Community Cloud](https://share.streamlit.io/).
3. Sign in using your GitHub account.
4. Select the project repository.
5. Configure the main application file as `app.py`.
6. Add environment variables through **App Settings → Secrets**.
7. Deploy the application.

**Example Streamlit Secrets Configuration**

```toml
ADMIN_EMAIL = "admin@reincrew.local"
ADMIN_PASSWORD = "your-secure-password"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

SMTP_USERNAME = "your-email@gmail.com"
SMTP_PASSWORD = "your-gmail-app-password"
SMTP_FROM = "your-email@gmail.com"

DATABASE_PATH = "data/reincrew.db"
```

The application is designed to load Streamlit secrets into environment variables during startup.

### Production Scaling Considerations

For production-level deployment and multiple concurrent users, consider the following improvements:

**Database & Storage**
- Migrate SQLite to managed PostgreSQL.
- Store resumes and generated documents in private cloud storage.
- Implement database backups and recovery procedures.
- Use persistent storage instead of relying on ephemeral deployment filesystems.

**Security & Reliability**
- Implement password reset functionality.
- Add file-type and file-size validation.
- Introduce rate limiting for public application forms.
- Protect uploaded resumes and generated documents.
- Add secure session management.
- Implement background workers for automated reminders.
- Monitor SMTP delivery failures and application errors.

---

## 8. End-to-End Verification Workflow

Follow this workflow to verify the complete internship lifecycle.

### Step 1: Submit an Internship Application
- Open the public internship portal.
- Select an active internship.
- Complete the application form.
- Upload a resume.
- Submit the application.
- Verify the generated `APP-...` tracking ID and confirmation email.

### Step 2: Administrator Reviews the Application
- Open the Administrator Login portal.
- Sign in using administrator credentials.
- Navigate to Applications.
- Review applicant details and resume.
- Update the application status to `Selected`.

### Step 3: Verify Automated Onboarding
Confirm that the system:
- Creates an `INT-...` intern profile.
- Creates student login credentials.
- Generates a temporary 5-digit password.
- Generates an Offer Letter PDF.
- Sends the selection email with the PDF attachment.
- Assigns stream-specific internship tasks.

### Step 4: Intern Login
- Log out of the administrator account.
- Open Student / Intern Login.
- Sign in using the registered email and temporary password.
- Verify access to the intern dashboard.

### Step 5: Task Submission & Daily Reporting
- Open My Tasks.
- Review assigned tasks and deadlines.
- Submit GitHub or Google Drive deliverable links.
- Add submission notes.
- Open Daily Report.
- Submit daily work hours, completed tasks, pending work, and blockers.

### Step 6: Administrator Task Approval
- Sign in as administrator.
- Navigate to the Tasks panel.
- Review intern submissions.
- Approve all assigned tasks.

### Step 7: Completion Certificate Verification

After all assigned tasks reach `Approved` status, verify that:

- The completion process becomes available.
- A unique `RC-CERT-...` completion document is generated.
- The internship status changes to `Completed`.
- The completion email is delivered with the PDF attachment.
- The intern can download the document from My Documents.

---

## 9. Future Enhancements

Potential improvements for future releases include:

- Interactive analytics dashboards for administrators.
- Advanced internship performance analytics.
- Automated daily and weekly email reminders.
- Bulk candidate application management.
- Advanced resume parsing and candidate screening.
- AI-assisted candidate evaluation.
- Internship feedback and rating systems.
- Multi-admin permission management.
- PostgreSQL integration.
- Cloud-based document management.
- Internship certificate verification through unique IDs or QR codes.

---

## 10. Security & Privacy

The system incorporates security-oriented practices, including:

- Salted PBKDF2-HMAC-SHA256 password hashing.
- Role-based authentication and authorization.
- Environment-based secret management.
- Protected administrator and intern dashboards.
- Email notification audit logs.
- Controlled document generation and access.

For production use, additional security testing, access-control reviews, secure file handling, and persistent storage configuration are recommended.

---

## 11. Author & Project Information

**Project:** ReinCrew Internship Management System

**Developer:** Ajay

**Education:** B.Tech – Information Technology

**GitHub:** [acpajay-7](https://github.com/acpajay-7)

**Repository:** [Internship Management System](https://github.com/acpajay-7/Internship-Management-System)

**Platform:** ReinCrew

---

## 12. License

This project is developed for the ReinCrew internship management ecosystem. Add an explicit open-source license to the repository if public reuse and redistribution are intended.

---

**Built with Python, Streamlit, and SQLite to simplify and automate the complete internship lifecycle.**