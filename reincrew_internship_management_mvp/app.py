from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import os
import pandas as pd

# Read deployment secrets into environment variables before importing db/services.
try:
    for secret_key in ["ADMIN_EMAIL", "ADMIN_PASSWORD", "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "DATABASE_PATH"]:
        if secret_key in st.secrets:
            os.environ[secret_key] = str(st.secrets[secret_key])
except Exception:
    pass
from pathlib import Path
from datetime import date, datetime
from db import init_db, get_conn, create_user, verify_user, log_email
from services import send_email, make_letter_pdf, save_upload

st.set_page_config(page_title="ReinCrew Internship Portal", page_icon="🎓", layout="wide")
init_db()

def df_query(sql, params=()):
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)

def execute(sql, params=()):
    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()

def notify(to_email, subject, body):
    ok, detail = send_email(to_email, subject, body)
    log_email(to_email, subject, "Sent" if ok else "Pending/Failed", detail)
    return ok, detail

def logout():
    for key in ["user", "role"]:
        st.session_state.pop(key, None)
    st.rerun()

st.title("🎓 ReinCrew Internship Management System")
st.caption("MVP prototype — application to internship completion")

if "user" not in st.session_state:
    public_tab, login_tab = st.tabs(["Apply for an Internship", "Login"])
    with public_tab:
        st.subheader("Explore internship opportunities")
        opportunities = df_query("SELECT * FROM internships WHERE active=1")
        if opportunities.empty:
            st.info("No active internships are listed yet. Please check again later.")
        else:
            for _, item in opportunities.iterrows():
                with st.expander(f"{item['title']} · {item['domain']}"):
                    st.write(item["description"])
                    st.write(f"Duration: {item['duration']} | Department: {item['department']}")
        st.divider()
        st.subheader("Internship application form")
        with st.form("application_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                full_name = st.text_input("Full name *")
                email = st.text_input("Email address *")
                phone = st.text_input("Phone number *")
                college = st.text_input("College / University *")
            with c2:
                education = st.text_input("Education details *", placeholder="B.Tech IT, Year 4")
                skills = st.text_area("Skills *", placeholder="Python, SQL, Machine Learning")
                domains = df_query("SELECT DISTINCT domain FROM internships WHERE active=1")
                domain_options = domains["domain"].tolist() if not domains.empty else ["Data Science", "Web Development", "AI/ML"]
                preferred_domain = st.selectbox("Preferred internship domain", domain_options)
                resume = st.file_uploader("Resume (PDF/DOC/DOCX)", type=["pdf", "doc", "docx"])
            submitted = st.form_submit_button("Submit application", type="primary")
        if submitted:
            if not all([full_name.strip(), email.strip(), phone.strip(), college.strip(), education.strip(), skills.strip()]):
                st.error("Please complete all required fields.")
            elif "@" not in email or "." not in email.split("@")[-1]:
                st.error("Please enter a valid email address.")
            else:
                existing = df_query("SELECT id FROM applications WHERE lower(email)=lower(?) AND status NOT IN ('Rejected')", (email.strip(),))
                if not existing.empty:
                    st.warning("An active application already exists for this email address.")
                else:
                    resume_path = save_upload(resume) if resume else ""
                    import uuid
                    app_id = "APP-" + uuid.uuid4().hex[:10].upper()
                    execute("""INSERT INTO applications
                    (application_id, full_name, email, phone, college, education, skills, preferred_domain, resume_path, status, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (app_id, full_name.strip(), email.strip(), phone.strip(), college.strip(), education.strip(),
                     skills.strip(), preferred_domain, resume_path, "Received", datetime.now().isoformat(timespec="seconds")))
                    notify(email.strip(), "ReinCrew application received",
                           f"Hello {full_name},\n\nYour application {app_id} has been received for {preferred_domain}.\nCurrent status: Received.\n\nReinCrew Team")
                    st.success(f"Application submitted successfully. Your Application ID is {app_id}")
    with login_tab:
        st.subheader("Admin / Intern login")
        with st.form("login_form"):
            login_email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            do_login = st.form_submit_button("Login", type="primary")
        if do_login:
            user = verify_user(login_email.strip().lower(), password)
            if user:
                st.session_state["user"] = user["email"]
                st.session_state["role"] = user["role"]
                st.rerun()
            else:
                st.error("Invalid email or password.")
    st.stop()

user_email = st.session_state["user"]
role = st.session_state["role"]
with st.sidebar:
    st.success(f"Signed in: {user_email}")
    st.caption(f"Role: {role}")
    if st.button("Logout"):
        logout()

if role == "admin":
    pages = ["Overview", "Applications", "Internships", "Tasks", "Reports", "Completion letters", "Email log", "Admin users"]
    page = st.sidebar.radio("Admin navigation", pages)
    if page == "Overview":
        st.header("Admin dashboard")
        cols = st.columns(4)
        for col, label, sql in [
            (cols[0], "Applications", "SELECT COUNT(*) n FROM applications"),
            (cols[1], "Selected interns", "SELECT COUNT(*) n FROM interns"),
            (cols[2], "Open tasks", "SELECT COUNT(*) n FROM tasks WHERE status!='Approved'"),
            (cols[3], "Daily reports", "SELECT COUNT(*) n FROM daily_reports")]:
            value = int(df_query(sql).iloc[0]["n"])
            col.metric(label, value)
        st.subheader("Recent applications")
        st.dataframe(df_query("SELECT application_id,full_name,email,preferred_domain,status,created_at FROM applications ORDER BY id DESC LIMIT 10"), use_container_width=True)
    elif page == "Applications":
        st.header("Application management")
        apps = df_query("SELECT * FROM applications ORDER BY id DESC")
        st.dataframe(apps.drop(columns=["resume_path"], errors="ignore"), use_container_width=True)
        ids = apps["application_id"].tolist() if not apps.empty else []
        selected_id = st.selectbox("Choose application", ids)
        if selected_id:
            record = apps[apps.application_id == selected_id].iloc[0]
            st.write(f"**{record['full_name']}** · {record['email']} · {record['preferred_domain']}")
            if record["resume_path"] and Path(record["resume_path"]).exists():
                st.download_button("Download resume", Path(record["resume_path"]).read_bytes(), file_name=Path(record["resume_path"]).name)
            new_status = st.selectbox("Update application status", ["Under Review", "Shortlisted", "Selected", "Rejected", "Additional Information Required"])
            notes = st.text_area("Admin notes")
            if st.button("Save application decision"):
                execute("UPDATE applications SET status=?, admin_notes=? WHERE application_id=?", (new_status, notes, selected_id))
                subject = f"ReinCrew application update: {new_status}"
                body = f"Hello {record['full_name']},\n\nYour application {selected_id} is now: {new_status}.\n{notes}\n\nReinCrew Team"
                notify(record["email"], subject, body)
                if new_status == "Selected":
                    existing_intern = df_query("SELECT id FROM interns WHERE email=?", (record["email"],))
                    if existing_intern.empty:
                        import uuid
                        intern_id = "INT-" + uuid.uuid4().hex[:8].upper()
                        execute("""INSERT INTO interns(internship_id,application_id,full_name,email,domain,start_date,end_date,status)
                        VALUES(?,?,?,?,?,?,?,?)""",
                        (intern_id, selected_id, record["full_name"], record["email"], record["preferred_domain"], date.today().isoformat(), "", "Offer Pending"))
                        st.info(f"Intern profile created: {intern_id}. Add a login in Admin users.")
                st.rerun()
    elif page == "Internships":
        st.header("Manage internship opportunities")
        with st.form("new_internship"):
            title = st.text_input("Internship title")
            domain = st.text_input("Domain")
            department = st.text_input("Department")
            duration = st.text_input("Duration", "8 weeks")
            description = st.text_area("Description")
            add = st.form_submit_button("Add internship")
        if add and title and domain:
            execute("INSERT INTO internships(title,domain,department,duration,description,active) VALUES(?,?,?,?,?,1)",
                    (title,domain,department,duration,description))
            st.success("Internship added.")
        st.dataframe(df_query("SELECT * FROM internships"), use_container_width=True)
    elif page == "Tasks":
        st.header("Task allocation")
        interns = df_query("SELECT internship_id,full_name,email,domain FROM interns")
        with st.form("create_task"):
            task_title = st.text_input("Task title")
            task_description = st.text_area("Task description / submission requirements")
            priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
            deadline = st.date_input("Deadline", value=date.today())
            intern_options = interns["internship_id"].tolist() if not interns.empty else []
            assignee = st.selectbox("Assign to intern ID", intern_options) if intern_options else None
            create = st.form_submit_button("Create and assign task")
        if create:
            if not task_title or not assignee:
                st.error("Enter a title and create an intern profile first.")
            else:
                execute("""INSERT INTO tasks(internship_id,title,description,priority,deadline,status,created_at)
                VALUES(?,?,?,?,?,?,?)""", (assignee,task_title,task_description,priority,deadline.isoformat(),"Assigned",datetime.now().isoformat()))
                person = interns[interns.internship_id == assignee].iloc[0]
                notify(person["email"], "New ReinCrew task assigned", f"Hello {person['full_name']},\n\nTask: {task_title}\nDeadline: {deadline}\n\nPlease log in to submit your work.")
                st.success("Task assigned and notification attempted.")
        st.subheader("All tasks")
        st.dataframe(df_query("SELECT t.*,i.full_name FROM tasks t LEFT JOIN interns i ON t.internship_id=i.internship_id ORDER BY t.id DESC"), use_container_width=True)
        task_rows = df_query("SELECT id,title,status FROM tasks WHERE status IN ('Submitted','Revision Required')")
        if not task_rows.empty:
            st.subheader("Review submissions")
            task_id = st.selectbox("Submission", task_rows["id"].tolist())
            decision = st.selectbox("Decision", ["Approved", "Revision Required", "Rejected"])
            feedback = st.text_area("Review feedback")
            if st.button("Save review"):
                execute("UPDATE tasks SET status=?, review_feedback=? WHERE id=?", (decision,feedback,int(task_id)))
                st.success("Review saved.")
                st.rerun()
    elif page == "Reports":
        st.header("Daily reporting and attendance")
        reports = df_query("SELECT d.*,i.full_name FROM daily_reports d LEFT JOIN interns i ON d.internship_id=i.internship_id ORDER BY d.id DESC")
        st.dataframe(reports, use_container_width=True)
        if not reports.empty:
            st.download_button("Download reports CSV", reports.to_csv(index=False).encode("utf-8"), "daily_reports.csv", "text/csv")
        st.subheader("Weekly summary (basic)")
        st.dataframe(df_query("""SELECT internship_id, COUNT(*) report_days, SUM(CAST(hours_spent AS REAL)) total_hours
        FROM daily_reports WHERE report_date >= date('now','-7 day') GROUP BY internship_id"""), use_container_width=True)
    elif page == "Completion letters":
        st.header("Internship completion approval and PDF")
        interns = df_query("SELECT * FROM interns ORDER BY id DESC")
        st.dataframe(interns, use_container_width=True)
        if not interns.empty:
            intern_id = st.selectbox("Select intern", interns["internship_id"].tolist())
            person = interns[interns.internship_id == intern_id].iloc[0]
            start = st.date_input("Internship start date", value=date.fromisoformat(person["start_date"]) if person["start_date"] else date.today())
            end = st.date_input("Completion date", value=date.today())
            signatory = st.text_input("Authorised signatory", "Authorised Signatory, ReinCrew")
            required = df_query("SELECT COUNT(*) n FROM tasks WHERE internship_id=? AND status!='Approved'", (intern_id,)).iloc[0]["n"]
            st.write(f"Tasks not approved: {int(required)}")
            if st.button("Approve completion and generate PDF"):
                if int(required) > 0:
                    st.error("Completion blocked: approve all assigned tasks first.")
                else:
                    cert_id = "RC-CERT-" + datetime.now().strftime("%Y%m%d%H%M%S")
                    pdf_path = make_letter_pdf(person["full_name"], person["domain"], start.isoformat(), end.isoformat(), cert_id, signatory)
                    execute("UPDATE interns SET start_date=?,end_date=?,status='Completed' WHERE internship_id=?", (start.isoformat(),end.isoformat(),intern_id))
                    execute("INSERT INTO documents(internship_id,document_id,file_path,created_at) VALUES(?,?,?,?)",
                            (intern_id,cert_id,str(pdf_path),datetime.now().isoformat()))
                    notify(person["email"], "Your ReinCrew internship completion document", f"Congratulations {person['full_name']}! Your completion document {cert_id} has been generated. The admin can download it from the portal.")
                    st.success(f"Generated {cert_id}")
                    st.download_button("Download completion PDF", Path(pdf_path).read_bytes(), file_name=f"{cert_id}.pdf", mime="application/pdf")
    elif page == "Email log":
        st.header("Email delivery log")
        st.dataframe(df_query("SELECT * FROM email_logs ORDER BY id DESC"), use_container_width=True)
    elif page == "Admin users":
        st.header("Create intern login")
        interns = df_query("SELECT internship_id,full_name,email FROM interns")
        with st.form("create_login"):
            email = st.text_input("Intern email")
            password = st.text_input("Temporary password", type="password")
            create = st.form_submit_button("Create intern login")
        if create:
            if not email or not password:
                st.error("Email and password are required.")
            else:
                try:
                    create_user(email.strip().lower(), password, "intern")
                    st.success("Intern login created.")
                except Exception as e:
                    st.error(f"Could not create user: {e}")
        st.dataframe(interns, use_container_width=True)

elif role == "intern":
    page = st.sidebar.radio("Intern navigation", ["My dashboard", "My tasks", "Daily report", "My documents"])
    intern = df_query("SELECT * FROM interns WHERE lower(email)=lower(?)", (user_email,))
    if intern.empty:
        st.error("No intern profile is linked to this login. Contact the administrator.")
        st.stop()
    person = intern.iloc[0]
    intern_id = person["internship_id"]
    if page == "My dashboard":
        st.header(f"Welcome, {person['full_name']}")
        a,b,c = st.columns(3)
        a.metric("Internship ID", intern_id)
        b.metric("Domain", person["domain"])
        c.metric("Status", person["status"])
        st.subheader("My task status")
        st.dataframe(df_query("SELECT title,priority,deadline,status,review_feedback FROM tasks WHERE internship_id=?", (intern_id,)), use_container_width=True)
    elif page == "My tasks":
        st.header("My assigned tasks")
        tasks = df_query("SELECT * FROM tasks WHERE internship_id=? ORDER BY id DESC", (intern_id,))
        st.dataframe(tasks, use_container_width=True)
        available = tasks[tasks.status.isin(["Assigned","Revision Required"])] if not tasks.empty else tasks
        if not available.empty:
            task_id = st.selectbox("Select task to submit", available["id"].tolist())
            task_link = st.text_input("Submission link (GitHub / Drive)")
            submission_note = st.text_area("Submission notes")
            if st.button("Submit task"):
                if not task_link and not submission_note:
                    st.error("Add a submission link or notes.")
                else:
                    execute("UPDATE tasks SET status='Submitted',submission_link=?,submission_note=?,submitted_at=? WHERE id=?",
                            (task_link,submission_note,datetime.now().isoformat(),int(task_id)))
                    st.success("Submission received.")
                    st.rerun()
    elif page == "Daily report":
        st.header("Submit daily progress")
        with st.form("daily_report"):
            report_date = st.date_input("Date", value=date.today())
            completed = st.text_area("Tasks completed")
            description = st.text_area("Work description")
            links = st.text_input("Submission links")
            hours = st.number_input("Time spent (hours)", min_value=0.0, max_value=24.0, step=0.5)
            pending = st.text_area("Pending work")
            blockers = st.text_area("Blockers")
            send = st.form_submit_button("Submit daily report")
        if send:
            execute("""INSERT INTO daily_reports(internship_id,report_date,completed,work_description,submission_links,hours_spent,pending,blockers,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""", (intern_id,report_date.isoformat(),completed,description,links,str(hours),pending,blockers,datetime.now().isoformat()))
            st.success("Daily report submitted.")
    elif page == "My documents":
        st.header("My completion documents")
        docs = df_query("SELECT * FROM documents WHERE internship_id=?", (intern_id,))
        if docs.empty:
            st.info("No completion document has been issued yet.")
        for _, doc in docs.iterrows():
            p = Path(doc["file_path"])
            if p.exists():
                st.download_button(f"Download {doc['document_id']}", p.read_bytes(), file_name=p.name, mime="application/pdf")

else:
    st.error("Unknown account role. Contact the administrator.")
