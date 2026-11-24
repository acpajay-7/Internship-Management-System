from dotenv import load_dotenv

load_dotenv()

from datetime import date, datetime
import json
import os
from pathlib import Path
import uuid
import pandas as pd
import streamlit as st

# Read deployment secrets into environment variables before importing db/services.
try:
  for secret_key in [
      "ADMIN_EMAIL",
      "ADMIN_PASSWORD",
      "SMTP_HOST",
      "SMTP_PORT",
      "SMTP_USERNAME",
      "SMTP_PASSWORD",
      "SMTP_FROM",
      "DATABASE_PATH",
  ]:
    if secret_key in st.secrets:
      os.environ[secret_key] = str(st.secrets[secret_key])
except Exception:
  pass

from db import (
    change_user_password,
    create_hr_user,
    delete_hr_user,
    delete_intern_access,
    fetch_audit_logs,
    get_conn,
    init_db,
    log_audit,
    log_email,
    submit_application_idempotent,
    upsert_intern_user,
    verify_user,
)
from services import (
    auto_assign_stream_tasks,
    generate_5_digit_password,
    generate_random_alphanumeric_password,
    make_letter_pdf,
    make_offer_letter_pdf,
    save_upload,
    send_email,
)

st.set_page_config(
    page_title="ReinCrew Internship Portal", page_icon="🎓", layout="wide"
)
init_db()


def df_query(sql, params=()):
  with get_conn() as conn:
    return pd.read_sql_query(sql, conn, params=params)


def execute(sql, params=()):
  with get_conn() as conn:
    conn.execute(sql, params)
    conn.commit()


def notify(to_email, subject, body, attachment_path=None):
  ok, detail = send_email(
      to_email, subject, body, attachment_path=attachment_path
  )
  log_email(to_email, subject, "Sent" if ok else "Pending/Failed", detail)
  return ok, detail


def render_change_password_section(current_email: str):
  st.header("Change Password")
  st.caption(
      "Update your account password. Your new password must be at least 6"
      " characters and include both letters and numbers."
  )
  with st.form("change_password_form", clear_on_submit=True):
    old_pwd = st.text_input("Current (Old) Password *", type="password")
    new_pwd = st.text_input(
        "New Password (letters + numbers) *", type="password"
    )
    confirm_pwd = st.text_input("Confirm New Password *", type="password")
    submit_pwd = st.form_submit_button("Update Password", type="primary")

  if submit_pwd:
    if not old_pwd or not new_pwd or not confirm_pwd:
      st.error("Please fill in all password fields.")
    elif new_pwd != confirm_pwd:
      st.error("New password and confirm password do not match.")
    else:
      ok, msg = change_user_password(current_email, old_pwd, new_pwd)
      if ok:
        st.success(msg)
      else:
        st.error(msg)


def check_and_auto_issue_completion(
    internship_id, actor_email="system", actor_role="admin"
):
  """Checks if all assigned tasks for an intern are Approved; if so, auto-generates Completion Letter PDF."""
  total_tasks = int(
      df_query(
          "SELECT COUNT(*) n FROM tasks WHERE internship_id=?", (internship_id,)
      ).iloc[0]["n"]
  )
  unapproved = int(
      df_query(
          "SELECT COUNT(*) n FROM tasks WHERE internship_id=? AND"
          " status!='Approved'",
          (internship_id,),
      ).iloc[0]["n"]
  )
  already_issued = int(
      df_query(
          "SELECT COUNT(*) n FROM documents WHERE internship_id=? AND"
          " doc_type='Completion Letter'",
          (internship_id,),
      ).iloc[0]["n"]
  )

  if total_tasks > 0 and unapproved == 0 and already_issued == 0:
    person = df_query(
        "SELECT * FROM interns WHERE internship_id=?", (internship_id,)
    ).iloc[0]
    start_str = person["start_date"] or date.today().isoformat()
    end_str = date.today().isoformat()
    cert_id = "RC-CERT-" + datetime.now().strftime("%Y%m%d%H%M%S")
    pdf_path = make_letter_pdf(
        person["full_name"],
        person["domain"],
        start_str,
        end_str,
        cert_id,
        "Authorised Signatory, ReinCrew",
    )
    execute(
        "UPDATE interns SET start_date=?, end_date=?, status='Completed' WHERE"
        " internship_id=?",
        (start_str, end_str, internship_id),
    )
    execute(
        "INSERT INTO"
        " documents(internship_id,document_id,doc_type,file_path,created_at)"
        " VALUES(?,?,?,?,?)",
        (
            internship_id,
            cert_id,
            "Completion Letter",
            str(pdf_path),
            datetime.now().isoformat(),
        ),
    )
    log_audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action_type="DOC_GENERATED",
        target_entity="document",
        target_id=cert_id,
        old_value=None,
        new_value={
            "doc_type": "Completion Letter",
            "internship_id": internship_id,
            "auto_issued": True,
        },
    )
    notify(
        person["email"],
        f"ReinCrew Internship Completion Letter ({cert_id})",
        (
            f"Congratulations {person['full_name']}!\n\nYou have successfully"
            f" completed all assigned tasks for your {person['domain']}"
            f" internship.\nYour Completion Certificate ({cert_id}) is attached"
            " and available in your portal under 'My documents'.\n\nReinCrew"
            " Team"
        ),
        attachment_path=pdf_path,
    )
    return cert_id
  return None


def logout():
  for key in ["user", "role"]:
    st.session_state.pop(key, None)
  st.rerun()


st.title("🎓 ReinCrew Internship Management System")
st.caption("Production-ready — application to internship completion")

# ─── Public Landing Interface (3 Distinct Tabs) ────────────────────────────────
if "user" not in st.session_state:
  public_tab, student_login_tab, admin_login_tab = st.tabs(
      ["Apply for an Internship", "Student / Intern Login", "Admin Login"]
  )

  with public_tab:
    st.subheader("Explore internship opportunities")
    opportunities = df_query("SELECT * FROM internships WHERE active=1")
    if opportunities.empty:
      st.info("No active internships are listed yet. Please check again later.")
    else:
      for _, item in opportunities.iterrows():
        with st.expander(f"{item['title']} · {item['domain']}"):
          st.write(item["description"])
          st.write(
              f"Duration: {item['duration']} | Department: {item['department']}"
          )
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
        education = st.text_input(
            "Education details *", placeholder="B.Tech IT, Year 4"
        )
        skills = st.text_area(
            "Skills *", placeholder="Python, SQL, Machine Learning"
        )
        domains = df_query(
            "SELECT DISTINCT domain FROM internships WHERE active=1"
        )
        domain_options = (
            domains["domain"].tolist()
            if not domains.empty
            else ["Data Analytics", "AI/ML", "Web Development"]
        )
        preferred_domain = st.selectbox(
            "Preferred internship domain", domain_options
        )
        resume = st.file_uploader(
            "Resume (PDF/DOC/DOCX)", type=["pdf", "doc", "docx"]
        )
      submitted = st.form_submit_button("Submit application", type="primary")
    if submitted:
      if not all([
          full_name.strip(),
          email.strip(),
          phone.strip(),
          college.strip(),
          education.strip(),
          skills.strip(),
      ]):
        st.error("Please complete all required fields.")
      elif "@" not in email or "." not in email.split("@")[-1]:
        st.error("Please enter a valid email address.")
      else:
        resume_path = save_upload(resume) if resume else ""
        res = submit_application_idempotent(
            full_name=full_name,
            email=email,
            phone=phone,
            college=college,
            education=education,
            skills=skills,
            preferred_domain=preferred_domain,
            resume_path=resume_path,
        )
        if res["status"] == "duplicate_ignored":
          st.warning(
              f"An active application ({res['application_id']} —"
              f" {res['current_status']}) already exists for this email"
              " address."
          )
        else:
          app_id = res["application_id"]
          notify(
              email.strip(),
              "ReinCrew application received",
              (
                  f"Hello {full_name},\n\nYour application {app_id} has been"
                  f" received for {preferred_domain}.\nCurrent status:"
                  " Received.\n\nReinCrew Team"
              ),
          )
          st.success(
              "Application submitted successfully! Your Application ID is"
              f" {app_id}"
          )

  with student_login_tab:
    st.subheader("🎓 Student / Intern Login")
    st.caption(
        "Selected candidates: log in with your registered email and your"
        " portal password."
    )
    with st.form("student_login_form"):
      student_email = st.text_input("Registered Student Email")
      student_password = st.text_input("Password", type="password")
      do_student_login = st.form_submit_button(
          "Login as Student", type="primary"
      )
    if do_student_login:
      user = verify_user(
          student_email.strip().lower(),
          student_password,
          expected_roles=["intern"],
      )
      if user:
        st.session_state["user"] = user["email"]
        st.session_state["role"] = user["role"]
        st.rerun()
      else:
        st.error(
            "Invalid student credentials, access revoked, or your application"
            " has not been selected yet."
        )

  with admin_login_tab:
    st.subheader("🛡️ Administrator / HR Login")
    st.caption("Authorized ReinCrew Super Admins and HR Coordinators only.")
    with st.form("admin_login_form"):
      admin_email = st.text_input("Admin / HR Email")
      admin_password = st.text_input("Password", type="password")
      do_admin_login = st.form_submit_button("Login", type="primary")
    if do_admin_login:
      user = verify_user(
          admin_email.strip().lower(),
          admin_password,
          expected_roles=["admin", "hr"],
      )
      if user:
        st.session_state["user"] = user["email"]
        st.session_state["role"] = user["role"]
        st.rerun()
      else:
        st.error("Invalid administrator or HR email/password.")

  st.stop()

# ─── Authenticated Area ────────────────────────────────────────────────────────
user_email = st.session_state["user"]
role = st.session_state["role"]
role_label = "SUPER ADMIN" if role == "admin" else role.upper()

with st.sidebar:
  st.success(f"Signed in: {user_email}")
  st.caption(f"Role: {role_label}")
  if st.button("Logout"):
    logout()

if role in ("admin", "hr"):
  pages = [
      "Overview",
      "Applications",
      "Interns & Access",
      "Internships",
      "Tasks",
      "Stream Templates",
      "Reports",
      "Completion letters",
      "Email log",
  ]
  if role == "admin":
    pages.extend(["Audit logs", "Manage HR Admins"])
  if role == "hr":
    pages.append("Change Password")

  page = st.sidebar.radio("Admin / HR navigation", pages)

  if page == "Overview":
    st.header("Admin & HR dashboard")
    cols = st.columns(4)
    for col, label, sql in [
        (cols[0], "Applications", "SELECT COUNT(*) n FROM applications"),
        (
            cols[1],
            "Active interns",
            "SELECT COUNT(*) n FROM interns WHERE status!='Access Revoked'",
        ),
        (
            cols[2],
            "Open tasks",
            "SELECT COUNT(*) n FROM tasks WHERE status!='Approved'",
        ),
        (cols[3], "Daily reports", "SELECT COUNT(*) n FROM daily_reports"),
    ]:
      value = int(df_query(sql).iloc[0]["n"])
      col.metric(label, value)
    st.subheader("Recent applications")
    st.dataframe(
        df_query(
            "SELECT application_id,full_name,email,preferred_domain,status,created_at"
            " FROM applications ORDER BY id DESC LIMIT 10"
        ),
        use_container_width=True,
    )

  elif page == "Applications":
    col_head, col_ref = st.columns([4, 1])
    with col_head:
      st.header("Application management")
    with col_ref:
      if st.button("🔄 Refresh list", use_container_width=True):
        st.rerun()

    apps = df_query("SELECT * FROM applications ORDER BY id DESC")
    if apps.empty:
      st.info("No registered applications found in the database yet.")
    else:
      status_filter = st.multiselect(
          "Filter by status",
          options=apps["status"].dropna().unique().tolist(),
          default=apps["status"].dropna().unique().tolist(),
      )
      filtered_apps = (
          apps[apps["status"].isin(status_filter)] if status_filter else apps
      )

      st.dataframe(
          filtered_apps.drop(columns=["resume_path"], errors="ignore"),
          use_container_width=True,
      )

      app_labels = {
          row["application_id"]: (
              f"{row['application_id']} | {row['full_name']}"
              f" ({row['preferred_domain']}) — [{row['status']}]"
          )
          for _, row in filtered_apps.iterrows()
      }

      if app_labels:
        selected_id = st.selectbox(
            "Choose registered applicant",
            options=list(app_labels.keys()),
            format_func=lambda x: app_labels[x],
        )
        record = apps[apps["application_id"] == selected_id].iloc[0]

        st.markdown("---")
        st.subheader(f"Applicant Details: {record['full_name']}")
        d1, d2, d3 = st.columns(3)
        d1.write(f"**Email:** {record['email']}")
        d2.write(f"**Phone:** {record['phone']}")
        d3.write(f"**Domain:** {record['preferred_domain']}")
        st.write(
            f"**College:** {record['college']} | **Education:** {record['education']}"
        )
        st.write(f"**Skills:** {record['skills']}")

        if (
            record["resume_path"]
            and Path(str(record["resume_path"])).exists()
        ):
          st.download_button(
              "📄 Download Resume",
              Path(str(record["resume_path"])).read_bytes(),
              file_name=Path(str(record["resume_path"])).name,
          )

        status_options = [
            "Under Review",
            "Shortlisted",
            "Interview Scheduled",
            "Selected",
            "Rejected",
            "Additional Information Required",
        ]
        default_idx = (
            status_options.index(record["status"])
            if record["status"] in status_options
            else 0
        )
        new_status = st.selectbox(
            "Update application status", status_options, index=default_idx
        )

        interview_link = ""
        if new_status == "Interview Scheduled":
          interview_link = st.text_input(
              "Interview / Assessment Link & Time",
              placeholder=(
                  "e.g. Google Meet link or ReinCrew AI Interview link +"
                  " Date/Time"
              ),
          )

        notes = st.text_area(
            "Admin notes / instructions", value=record["admin_notes"] or ""
        )

        if st.button("Save application decision", type="primary"):
          old_status = record["status"]
          full_notes = (
              f"{notes}\nInterview Details: {interview_link}".strip()
              if interview_link
              else notes
          )
          execute(
              "UPDATE applications SET status=?, admin_notes=? WHERE"
              " application_id=?",
              (new_status, full_notes, selected_id),
          )
          log_audit(
              actor_email=user_email,
              actor_role=role,
              action_type="STATUS_CHANGE",
              target_entity="application",
              target_id=selected_id,
              old_value={"status": old_status},
              new_value={"status": new_status},
          )

          if new_status == "Selected":
            existing_intern = df_query(
                "SELECT * FROM interns WHERE lower(email)=lower(?)",
                (record["email"],),
            )
            if existing_intern.empty:
              intern_id = "INT-" + uuid.uuid4().hex[:8].upper()
              start_dt = date.today().isoformat()
              domain = record["preferred_domain"]
              temp_password = generate_5_digit_password()

              intern_meta = df_query(
                  "SELECT duration FROM internships WHERE lower(domain)=lower(?)"
                  " LIMIT 1",
                  (domain,),
              )
              duration = (
                  intern_meta.iloc[0]["duration"]
                  if not intern_meta.empty
                  else "8 weeks"
              )

              # 1. Create Intern record
              execute(
                  """INSERT INTO interns(internship_id,application_id,full_name,email,domain,start_date,end_date,status)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (
                      intern_id,
                      selected_id,
                      record["full_name"],
                      record["email"],
                      domain,
                      start_dt,
                      "",
                      "Active",
                  ),
              )
              log_audit(
                  actor_email=user_email,
                  actor_role=role,
                  action_type="CREATE",
                  target_entity="intern",
                  target_id=intern_id,
                  old_value=None,
                  new_value={
                      "application_id": selected_id,
                      "email": record["email"],
                      "domain": domain,
                  },
              )

              # 2. Auto-register Student/Intern Login with random 5-digit password
              upsert_intern_user(record["email"], temp_password)

              # 3. Auto-generate Offer Letter PDF & save to documents
              offer_id = "RC-OFFER-" + datetime.now().strftime("%Y%m%d%H%M%S")
              offer_pdf_path = make_offer_letter_pdf(
                  record["full_name"],
                  domain,
                  intern_id,
                  start_dt,
                  duration,
                  offer_id,
                  "HR & Talent Acquisition, ReinCrew",
              )
              execute(
                  "INSERT INTO"
                  " documents(internship_id,document_id,doc_type,file_path,created_at)"
                  " VALUES(?,?,?,?,?)",
                  (
                      intern_id,
                      offer_id,
                      "Offer Letter",
                      str(offer_pdf_path),
                      datetime.now().isoformat(),
                  ),
              )
              log_audit(
                  actor_email=user_email,
                  actor_role=role,
                  action_type="DOC_GENERATED",
                  target_entity="document",
                  target_id=offer_id,
                  old_value=None,
                  new_value={
                      "doc_type": "Offer Letter",
                      "internship_id": intern_id,
                      "recipient": record["email"],
                  },
              )

              # 4. Auto-assign stream-based tasks
              with get_conn() as conn:
                assigned_count = auto_assign_stream_tasks(
                    conn, intern_id, domain
                )
                conn.commit()

              # 5. Send Email with Offer Letter PDF + 5-Digit Login Password
              subject = (
                  f"Congratulations! ReinCrew Internship Offer & Portal Login"
                  f" ({offer_id})"
              )
              body = (
                  f"Hello {record['full_name']},\n\n"
                  f"Congratulations! Your application {selected_id} for the {domain} Internship has been Selected.\n\n"
                  "--- YOUR STUDENT PORTAL CREDENTIALS ---\n"
                  f"Login Tab: Student / Intern Login\n"
                  f"Email: {record['email']}\n"
                  f"5-Digit Password: {temp_password}\n"
                  f"Internship ID: {intern_id}\n"
                  "---------------------------------------\n\n"
                  f"We have attached your official Offer Letter ({offer_id}) and automatically assigned {assigned_count} stream-specific tasks to your dashboard.\n"
                  f"{full_notes}\n\nReinCrew Team"
              )
              ok, detail = notify(
                  record["email"], subject, body, attachment_path=offer_pdf_path
              )
              if ok:
                st.success(
                    f"Selected! Intern {intern_id} registered, 5-digit password"
                    f" ({temp_password}) & Offer Letter emailed, and"
                    f" {assigned_count} tasks assigned."
                )
              else:
                st.warning(
                    f"Intern {intern_id} registered with 5-digit password"
                    f" **{temp_password}** and {assigned_count} tasks assigned,"
                    f" but email delivery reported: {detail}"
                )
            else:
              st.info("Intern profile already exists for this candidate.")
          else:
            subject = f"ReinCrew application update: {new_status}"
            body = (
                f"Hello {record['full_name']},\n\n"
                f"Your application {selected_id} is now: {new_status}.\n"
                f"{full_notes}\n\nReinCrew Team"
            )
            notify(record["email"], subject, body)
            st.success(
                f"Status updated to '{new_status}' and applicant notified."
            )
          st.rerun()

  elif page == "Interns & Access":
    st.header("Selected Interns & Portal Access")
    interns_df = df_query("SELECT * FROM interns ORDER BY id DESC")
    if interns_df.empty:
      st.info("No interns registered yet.")
    else:
      st.dataframe(interns_df, use_container_width=True)

      active_access_interns = interns_df[
          interns_df["status"] != "Access Revoked"
      ]
      if not active_access_interns.empty:
        st.divider()
        st.subheader("Revoke / Delete Intern Portal Access")
        st.caption(
            "Removes the intern's student login credentials immediately while"
            " preserving historical reports and audit records."
        )
        intern_options = {
            row["internship_id"]: (
                f"{row['internship_id']} | {row['full_name']} ({row['email']})"
                f" — [{row['status']}]"
            )
            for _, row in active_access_interns.iterrows()
        }
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
          target_intern_id = st.selectbox(
              "Select intern to revoke/delete access",
              options=list(intern_options.keys()),
              format_func=lambda x: intern_options[x],
          )
        with col_btn:
          st.write("")
          st.write("")
          if st.button(
              "Delete Intern Access", type="primary", use_container_width=True
          ):
            del_ok, del_msg = delete_intern_access(
                user_email, role, target_intern_id
            )
            if del_ok:
              st.success(del_msg)
              st.rerun()
            else:
              st.error(del_msg)

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
      execute(
          "INSERT INTO internships(title,domain,department,duration,description,active)"
          " VALUES(?,?,?,?,?,1)",
          (title, domain, department, duration, description),
      )
      log_audit(
          actor_email=user_email,
          actor_role=role,
          action_type="CREATE",
          target_entity="internship",
          target_id=title,
          old_value=None,
          new_value={
              "title": title,
              "domain": domain,
              "department": department,
              "duration": duration,
          },
      )
      st.success("Internship added.")
    st.dataframe(df_query("SELECT * FROM internships"), use_container_width=True)

  elif page == "Stream Templates":
    st.header("Stream-based automatic task templates")
    st.caption(
        "Tasks configured here are automatically assigned to interns when their"
        " application is marked 'Selected'."
    )
    with st.form("add_template"):
      domains = df_query("SELECT DISTINCT domain FROM internships")
      domain_list = (
          domains["domain"].tolist()
          if not domains.empty
          else ["Data Analytics", "AI/ML", "Web Development"]
      )
      t_domain = st.selectbox("Stream / Domain", domain_list)
      t_title = st.text_input("Task title")
      t_desc = st.text_area("Task description & deliverables")
      c1, c2 = st.columns(2)
      with c1:
        t_prio = st.selectbox(
            "Priority", ["Low", "Medium", "High", "Critical"]
        )
      with c2:
        t_days = st.number_input(
            "Due in (days from selection)", min_value=1, max_value=90, value=7
        )
      save_tpl = st.form_submit_button("Add stream task template")
    if save_tpl and t_title.strip() and t_desc.strip():
      execute(
          "INSERT INTO task_templates(domain,title,description,priority,due_days)"
          " VALUES(?,?,?,?,?)",
          (t_domain, t_title.strip(), t_desc.strip(), t_prio, int(t_days)),
      )
      log_audit(
          actor_email=user_email,
          actor_role=role,
          action_type="CREATE",
          target_entity="task_template",
          target_id=t_title.strip(),
          old_value=None,
          new_value={
              "domain": t_domain,
              "priority": t_prio,
              "due_days": int(t_days),
          },
      )
      st.success(f"Template added for {t_domain}.")
      st.rerun()
    st.dataframe(
        df_query("SELECT * FROM task_templates ORDER BY domain, due_days"),
        use_container_width=True,
    )

  elif page == "Tasks":
    st.header("Task allocation & review")
    interns = df_query(
        "SELECT internship_id,full_name,email,domain FROM interns WHERE"
        " status!='Access Revoked'"
    )
    with st.form("create_task"):
      task_title = st.text_input("Task title")
      task_description = st.text_area(
          "Task description / submission requirements"
      )
      priority = st.selectbox(
          "Priority", ["Low", "Medium", "High", "Critical"]
      )
      deadline = st.date_input("Deadline", value=date.today())
      intern_options = (
          interns["internship_id"].tolist() if not interns.empty else []
      )
      assignee = (
          st.selectbox("Assign to intern ID", intern_options)
          if intern_options
          else None
      )
      create = st.form_submit_button("Create and assign task")
    if create:
      if not task_title or not assignee:
        st.error("Enter a title and select an intern first.")
      else:
        execute(
            """INSERT INTO tasks(internship_id,title,description,priority,deadline,status,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                assignee,
                task_title,
                task_description,
                priority,
                deadline.isoformat(),
                "Assigned",
                datetime.now().isoformat(),
            ),
        )
        log_audit(
            actor_email=user_email,
            actor_role=role,
            action_type="CREATE",
            target_entity="task",
            target_id=assignee,
            old_value=None,
            new_value={
                "title": task_title,
                "priority": priority,
                "deadline": deadline.isoformat(),
            },
        )
        person = interns[interns.internship_id == assignee].iloc[0]
        notify(
            person["email"],
            "New ReinCrew task assigned",
            (
                f"Hello {person['full_name']},\n\nTask:"
                f" {task_title}\nDeadline: {deadline}\n\nPlease log in to"
                " submit your work."
            ),
        )
        st.success("Task assigned and notification sent.")

    st.subheader("All tasks")
    st.dataframe(
        df_query(
            "SELECT t.*,i.full_name,i.domain FROM tasks t LEFT JOIN interns i ON"
            " t.internship_id=i.internship_id ORDER BY t.id DESC"
        ),
        use_container_width=True,
    )

    task_rows = df_query(
        "SELECT id,internship_id,title,status,submission_link,submission_note"
        " FROM tasks WHERE status IN ('Submitted','Revision Required')"
    )
    if not task_rows.empty:
      st.subheader("Review submissions")
      task_id = st.selectbox("Submission ID", task_rows["id"].tolist())
      selected_task = task_rows[task_rows.id == task_id].iloc[0]
      st.write(
          f"**{selected_task['title']}** | Link:"
          f" {selected_task['submission_link']} | Notes:"
          f" {selected_task['submission_note']}"
      )
      decision = st.selectbox(
          "Decision", ["Approved", "Revision Required", "Rejected"]
      )
      feedback = st.text_area("Review feedback")
      if st.button("Save review"):
        execute(
            "UPDATE tasks SET status=?, review_feedback=? WHERE id=?",
            (decision, feedback, int(task_id)),
        )
        log_audit(
            actor_email=user_email,
            actor_role=role,
            action_type="STATUS_CHANGE",
            target_entity="task",
            target_id=str(task_id),
            old_value={"status": selected_task["status"]},
            new_value={"status": decision, "feedback": feedback},
        )
        if decision == "Approved":
          issued_cert = check_and_auto_issue_completion(
              selected_task["internship_id"],
              actor_email=user_email,
              actor_role=role,
          )
          if issued_cert:
            st.success(
                f"All tasks approved! Completion letter {issued_cert} was"
                " automatically generated and emailed."
            )
        st.success("Review saved.")
        st.rerun()

  elif page == "Reports":
    st.header("Daily reporting and attendance")
    reports = df_query(
        "SELECT d.*,i.full_name FROM daily_reports d LEFT JOIN interns i ON"
        " d.internship_id=i.internship_id ORDER BY d.id DESC"
    )
    st.dataframe(reports, use_container_width=True)
    if not reports.empty:
      st.download_button(
          "Download reports CSV",
          reports.to_csv(index=False).encode("utf-8"),
          "daily_reports.csv",
          "text/csv",
      )
    st.subheader("Weekly summary (basic)")
    st.dataframe(
        df_query(
            """SELECT internship_id, COUNT(*) report_days, SUM(CAST(hours_spent AS REAL)) total_hours
        FROM daily_reports WHERE report_date >= date('now','-7 day') GROUP BY internship_id"""
        ),
        use_container_width=True,
    )

  elif page == "Completion letters":
    st.header("Internship completion & offer documents")
    interns = df_query("SELECT * FROM interns ORDER BY id DESC")
    st.dataframe(interns, use_container_width=True)
    if not interns.empty:
      intern_id = st.selectbox("Select intern", interns["internship_id"].tolist())
      person = interns[interns.internship_id == intern_id].iloc[0]
      start = st.date_input(
          "Internship start date",
          value=(
              date.fromisoformat(person["start_date"])
              if person["start_date"]
              else date.today()
          ),
      )
      end = st.date_input("Completion date", value=date.today())
      signatory = st.text_input(
          "Authorised signatory", "Authorised Signatory, ReinCrew"
      )
      required = df_query(
          "SELECT COUNT(*) n FROM tasks WHERE internship_id=? AND"
          " status!='Approved'",
          (intern_id,),
      ).iloc[0]["n"]
      st.write(f"Tasks not approved: {int(required)}")
      if st.button("Approve completion and generate PDF"):
        if int(required) > 0:
          st.error("Completion blocked: approve all assigned tasks first.")
        else:
          cert_id = "RC-CERT-" + datetime.now().strftime("%Y%m%d%H%M%S")
          pdf_path = make_letter_pdf(
              person["full_name"],
              person["domain"],
              start.isoformat(),
              end.isoformat(),
              cert_id,
              signatory,
          )
          execute(
              "UPDATE interns SET start_date=?,end_date=?,status='Completed'"
              " WHERE internship_id=?",
              (start.isoformat(), end.isoformat(), intern_id),
          )
          execute(
              "INSERT INTO"
              " documents(internship_id,document_id,doc_type,file_path,created_at)"
              " VALUES(?,?,?,?,?)",
              (
                  intern_id,
                  cert_id,
                  "Completion Letter",
                  str(pdf_path),
                  datetime.now().isoformat(),
              ),
          )
          log_audit(
              actor_email=user_email,
              actor_role=role,
              action_type="DOC_GENERATED",
              target_entity="document",
              target_id=cert_id,
              old_value=None,
              new_value={
                  "doc_type": "Completion Letter",
                  "internship_id": intern_id,
                  "recipient": person["email"],
              },
          )
          notify(
              person["email"],
              f"Your ReinCrew internship completion document ({cert_id})",
              (
                  f"Congratulations {person['full_name']}! Your completion"
                  f" document {cert_id} has been generated and is attached."
              ),
              attachment_path=pdf_path,
          )
          st.success(f"Generated {cert_id}")
          st.download_button(
              "Download completion PDF",
              Path(pdf_path).read_bytes(),
              file_name=f"{cert_id}.pdf",
              mime="application/pdf",
          )

    st.subheader("All issued documents")
    st.dataframe(
        df_query("SELECT * FROM documents ORDER BY id DESC"),
        use_container_width=True,
    )

  elif page == "Email log":
    st.header("Email delivery log")
    st.dataframe(
        df_query("SELECT * FROM email_logs ORDER BY id DESC"),
        use_container_width=True,
    )

  elif page == "Audit logs" and role == "admin":
    st.header("Super Admin: System Audit Logs")
    logs = fetch_audit_logs(limit=200)
    if not logs:
      st.info("No audit logs recorded yet.")
    else:
      st.dataframe(pd.DataFrame(logs), use_container_width=True)
      st.download_button(
          "Download Audit Logs (JSON)",
          data=json.dumps(logs, indent=2),
          file_name="audit_logs_export.json",
          mime="application/json",
      )

  elif page == "Manage HR Admins" and role == "admin":
    st.header("Super Admin: Manage HR Admins")
    st.caption(
        "Create HR ('hr') coordinator accounts. A random alphanumeric password"
        " will be auto-generated and emailed directly to the HR."
    )
    with st.form("create_hr_form", clear_on_submit=True):
      hr_name = st.text_input("HR Full Name *", placeholder="e.g. Priya Sharma")
      hr_email = st.text_input("HR Email *", placeholder="e.g. hr@reincrew.in")
      create_hr_btn = st.form_submit_button(
          "Create HR Account & Email Credentials", type="primary"
      )

    if create_hr_btn:
      if not hr_name.strip():
        st.error("Please enter the HR's full name.")
      elif not hr_email.strip() or "@" not in hr_email:
        st.error("Please enter a valid HR email address.")
      else:
        auto_hr_password = generate_random_alphanumeric_password(8)
        ok, msg = create_hr_user(
            user_email,
            role,
            hr_name.strip(),
            hr_email.strip(),
            auto_hr_password,
        )
        if ok:
          subject = (
              "Welcome to ReinCrew Internship Portal — Your HR Admin Credentials"
          )
          body = (
              f"Dear {hr_name.strip()},\n\n"
              "Welcome to the ReinCrew team! You have been granted HR Coordinator access "
              "to the ReinCrew Internship Management Portal.\n\n"
              "--- YOUR HR PORTAL LOGIN CREDENTIALS ---\n"
              "Login Tab: Admin Login\n"
              f"Name: {hr_name.strip()}\n"
              f"Email: {hr_email.strip().lower()}\n"
              f"Password: {auto_hr_password}\n"
              "Role: HR Coordinator\n"
              "-----------------------------------------\n\n"
              "What you can manage on the portal:\n"
              "- Review and shortlist internship applications\n"
              "- Select candidates (auto-generates Offer Letters & assigns stream tasks)\n"
              "- Assign and review daily/weekly intern tasks\n"
              "- Monitor daily progress reports and issue completion certificates\n"
              "- Update your password anytime from the 'Change Password' tab\n\n"
              "For security, please keep your credentials confidential.\n\n"
              "Best regards,\n"
              "Admin Team\n"
              "ReinCrew Internship Program"
          )
          mail_ok, mail_detail = notify(hr_email.strip().lower(), subject, body)
          if mail_ok:
            st.success(f"{msg} Auto-generated credentials sent via email!")
          else:
            st.warning(
                f"{msg} However, email delivery reported: {mail_detail}"
            )
          st.rerun()
        else:
          st.warning(msg)

    st.divider()
    st.subheader("Active HR & Super Admin Accounts")
    accounts = df_query(
        "SELECT id, email, role, created_at FROM users WHERE role IN"
        " ('admin', 'hr') ORDER BY id ASC"
    )
    st.dataframe(accounts, use_container_width=True)

    hr_accounts = accounts[accounts["role"] == "hr"]
    if not hr_accounts.empty:
      st.subheader("Remove HR Coordinator Access")
      del_col1, del_col2 = st.columns([3, 1])
      with del_col1:
        hr_to_delete = st.selectbox(
            "Select HR account to delete",
            options=hr_accounts["email"].tolist(),
        )
      with del_col2:
        st.write("")
        st.write("")
        if st.button("Delete HR", type="primary", use_container_width=True):
          del_ok, del_msg = delete_hr_user(user_email, role, hr_to_delete)
          if del_ok:
            st.success(del_msg)
            st.rerun()
          else:
            st.error(del_msg)

  elif page == "Change Password" and role == "hr":
    render_change_password_section(user_email)

elif role == "intern":
  page = st.sidebar.radio(
      "Intern navigation",
      [
          "My dashboard",
          "My tasks",
          "Daily report",
          "My documents",
          "Change Password",
      ],
  )
  intern = df_query(
      "SELECT * FROM interns WHERE lower(email)=lower(?)", (user_email,)
  )
  if intern.empty or intern.iloc[0]["status"] == "Access Revoked":
    st.error(
        "Your portal access is inactive or has been revoked. Contact the"
        " administrator."
    )
    st.stop()
  person = intern.iloc[0]
  intern_id = person["internship_id"]

  if page == "My dashboard":
    st.header(f"Welcome, {person['full_name']}")
    a, b, c = st.columns(3)
    a.metric("Internship ID", intern_id)
    b.metric("Domain", person["domain"])
    c.metric("Status", person["status"])
    st.subheader("My task status")
    st.dataframe(
        df_query(
            "SELECT title,priority,deadline,status,review_feedback FROM tasks"
            " WHERE internship_id=?",
            (intern_id,),
        ),
        use_container_width=True,
    )

  elif page == "My tasks":
    st.header("My assigned tasks")
    tasks = df_query(
        "SELECT * FROM tasks WHERE internship_id=? ORDER BY id ASC",
        (intern_id,),
    )
    st.dataframe(tasks, use_container_width=True)
    available = (
        tasks[tasks.status.isin(["Assigned", "Revision Required"])]
        if not tasks.empty
        else tasks
    )
    if not available.empty:
      task_id = st.selectbox(
          "Select task to submit", available["id"].tolist()
      )
      task_link = st.text_input("Submission link (GitHub / Drive)")
      submission_note = st.text_area("Submission notes")
      if st.button("Submit task"):
        if not task_link and not submission_note:
          st.error("Add a submission link or notes.")
        else:
          execute(
              "UPDATE tasks SET"
              " status='Submitted',submission_link=?,submission_note=?,submitted_at=?"
              " WHERE id=?",
              (
                  task_link,
                  submission_note,
                  datetime.now().isoformat(),
                  int(task_id),
              ),
          )
          st.success("Submission received.")
          st.rerun()

  elif page == "Daily report":
    st.header("Submit daily progress")
    with st.form("daily_report"):
      report_date = st.date_input("Date", value=date.today())
      completed = st.text_area("Tasks completed")
      description = st.text_area("Work description")
      links = st.text_input("Submission links")
      hours = st.number_input(
          "Time spent (hours)", min_value=0.0, max_value=24.0, step=0.5
      )
      pending = st.text_area("Pending work")
      blockers = st.text_area("Blockers")
      send = st.form_submit_button("Submit daily report")
    if send:
      execute(
          """INSERT INTO daily_reports(internship_id,report_date,completed,work_description,submission_links,hours_spent,pending,blockers,created_at)
             VALUES(?,?,?,?,?,?,?,?,?)""",
          (
              intern_id,
              report_date.isoformat(),
              completed,
              description,
              links,
              str(hours),
              pending,
              blockers,
              datetime.now().isoformat(),
          ),
      )
      st.success("Daily report submitted.")

  elif page == "My documents":
    st.header("My Offer & Completion Documents")
    docs = df_query(
        "SELECT * FROM documents WHERE internship_id=? ORDER BY id DESC",
        (intern_id,),
    )
    if docs.empty:
      st.info("No documents have been issued yet.")
    for _, doc in docs.iterrows():
      p = Path(doc["file_path"])
      doc_label = doc.get("doc_type", "Document")
      if p.exists():
        st.download_button(
            f"Download {doc_label} ({doc['document_id']})",
            p.read_bytes(),
            file_name=p.name,
            mime="application/pdf",
        )

  elif page == "Change Password":
    render_change_password_section(user_email)

else:
  st.error("Unknown account role. Contact the administrator.")