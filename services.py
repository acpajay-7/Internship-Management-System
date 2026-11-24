from datetime import date, datetime, timedelta
from email.message import EmailMessage
import os
from pathlib import Path
import random
import secrets
import smtplib
import string
import uuid
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def generate_5_digit_password() -> str:
  """Generates a cryptographically secure random 5-digit numeric password (10000 - 99999)."""
  return str(random.SystemRandom().randint(10000, 99999))


def generate_random_alphanumeric_password(length: int = 8) -> str:
  """Generates a secure random alphanumeric password containing both letters and digits."""
  alphabet = string.ascii_letters + string.digits
  while True:
    pwd = "".join(secrets.choice(alphabet) for _ in range(length))
    if any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd):
      return pwd


def save_upload(uploaded_file):
  folder = Path("uploads")
  folder.mkdir(exist_ok=True)
  safe_name = Path(uploaded_file.name).name.replace(" ", "_")
  target = folder / f"{uuid.uuid4().hex}_{safe_name}"
  target.write_bytes(uploaded_file.getbuffer())
  return str(target)


def send_email(to_email, subject, body, attachment_path=None):
  host = os.getenv("SMTP_HOST")
  username = os.getenv("SMTP_USERNAME")
  password = os.getenv("SMTP_PASSWORD")
  sender = os.getenv("SMTP_FROM", username or "")
  port = int(os.getenv("SMTP_PORT", "587"))
  if not all([host, username, password, sender]):
    return False, "SMTP is not configured. Email was logged but not sent."

  message = EmailMessage()
  message["From"] = sender
  message["To"] = to_email
  message["Subject"] = subject
  message.set_content(body)

  if attachment_path and Path(attachment_path).exists():
    pdf_bytes = Path(attachment_path).read_bytes()
    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=Path(attachment_path).name,
    )

  try:
    with smtplib.SMTP(host, port, timeout=20) as server:
      server.starttls()
      server.login(username, password)
      server.send_message(message)
    return True, "SMTP delivery accepted."
  except Exception as exc:
    return False, str(exc)


def make_offer_letter_pdf(
    name, domain, internship_id, start_date, duration, document_id, signatory
):
  output = Path("generated")
  output.mkdir(exist_ok=True)
  path = output / f"{document_id}.pdf"
  pdf = canvas.Canvas(str(path), pagesize=A4)
  width, height = A4

  pdf.setTitle("ReinCrew Internship Offer Letter")
  pdf.setFont("Helvetica-Bold", 22)
  pdf.drawCentredString(width / 2, height - 95, "REINCREW")
  pdf.setFont("Helvetica-Bold", 16)
  pdf.drawCentredString(width / 2, height - 135, "INTERNSHIP OFFER LETTER")

  pdf.setFont("Helvetica", 10)
  pdf.drawString(65, height - 175, f"Date: {date.today().isoformat()}")
  pdf.drawRightString(width - 65, height - 175, f"Offer ID: {document_id}")

  pdf.setFont("Helvetica-Bold", 12)
  pdf.drawString(65, height - 215, f"Dear {name},")

  pdf.setFont("Helvetica", 11)
  lines = [
      (
          "Congratulations! We are pleased to offer you an internship position"
          " at ReinCrew."
      ),
      "Your application and profile stood out for our upcoming cohort.",
      "",
      f"Role / Stream: {domain} Intern",
      f"Intern ID: {internship_id}",
      f"Start Date: {start_date}",
      f"Duration: {duration}",
      "Mode: Remote / Portal-Managed",
      "",
      (
          "Your student account has been activated and your stream-specific"
          " tasks"
      ),
      (
          "have been assigned on the ReinCrew Internship Portal. Please log in"
          " using"
      ),
      (
          "your registered email and the 5-digit password sent to your inbox to"
          " begin."
      ),
  ]
  y = height - 245
  for line in lines:
    pdf.drawString(65, y, line)
    y -= 22

  pdf.setFont("Helvetica-Bold", 11)
  pdf.drawString(65, 110, signatory)
  pdf.setFont("Helvetica", 10)
  pdf.drawString(65, 93, "ReinCrew Internship Program")
  pdf.save()
  return path


def make_letter_pdf(name, role, start_date, end_date, document_id, signatory):
  output = Path("generated")
  output.mkdir(exist_ok=True)
  path = output / f"{document_id}.pdf"
  pdf = canvas.Canvas(str(path), pagesize=A4)
  width, height = A4
  pdf.setTitle("ReinCrew Internship Completion Letter")
  pdf.setFont("Helvetica-Bold", 22)
  pdf.drawCentredString(width / 2, height - 110, "REINCREW")
  pdf.setFont("Helvetica-Bold", 18)
  pdf.drawCentredString(width / 2, height - 165, "INTERNSHIP COMPLETION LETTER")
  pdf.setFont("Helvetica", 12)
  lines = [
      f"This is to certify that {name}",
      f"has successfully completed the internship in {role}.",
      f"Internship period: {start_date} to {end_date}.",
      "",
      "We appreciate the contribution and wish them success.",
  ]
  y = height - 240
  for line in lines:
    pdf.drawCentredString(width / 2, y, line)
    y -= 28
  pdf.setFont("Helvetica-Bold", 10)
  pdf.drawString(65, 120, f"Document ID: {document_id}")
  pdf.setFont("Helvetica", 11)
  pdf.drawString(65, 75, signatory)
  pdf.drawString(65, 58, "ReinCrew")
  pdf.save()
  return path


def auto_assign_stream_tasks(conn, internship_id, domain):
  """Automatically assigns stream-specific tasks from task_templates when an intern is selected."""
  existing = conn.execute(
      "SELECT COUNT(*) FROM tasks WHERE internship_id=?", (internship_id,)
  ).fetchone()[0]
  if existing > 0:
    return 0

  templates = conn.execute(
      "SELECT title, description, priority, due_days FROM task_templates WHERE"
      " lower(domain)=lower(?) ORDER BY id ASC",
      (domain,),
  ).fetchall()

  if not templates:
    templates = [
        (
            f"{domain}: Week 1 Onboarding & Project Setup",
            (
                f"Set up your {domain} workspace, review project requirements,"
                " and submit initial architecture notes."
            ),
            "High",
            7,
        ),
        (
            f"{domain}: Week 2 Core Module Implementation",
            (
                f"Build and test the primary deliverable for your {domain}"
                " track and share your repository link."
            ),
            "Medium",
            14,
        ),
    ]

  now_iso = datetime.now().isoformat()
  for row in templates:
    title = row["title"] if hasattr(row, "keys") else row[0]
    desc = row["description"] if hasattr(row, "keys") else row[1]
    prio = row["priority"] if hasattr(row, "keys") else row[2]
    due_days = row["due_days"] if hasattr(row, "keys") else row[3]
    deadline_str = (date.today() + timedelta(days=int(due_days))).isoformat()

    conn.execute(
        """INSERT INTO tasks(internship_id,title,description,priority,deadline,status,created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (internship_id, title, desc, prio, deadline_str, "Assigned", now_iso),
    )
  return len(templates)