import os, smtplib, uuid
from pathlib import Path
from email.message import EmailMessage
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def save_upload(uploaded_file):
    folder = Path("uploads")
    folder.mkdir(exist_ok=True)
    safe_name = Path(uploaded_file.name).name.replace(" ", "_")
    target = folder / f"{uuid.uuid4().hex}_{safe_name}"
    target.write_bytes(uploaded_file.getbuffer())
    return str(target)

def send_email(to_email, subject, body):
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
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(message)
        return True, "SMTP delivery accepted."
    except Exception as exc:
        return False, str(exc)

def make_letter_pdf(name, role, start_date, end_date, document_id, signatory):
    output = Path("generated")
    output.mkdir(exist_ok=True)
    path = output / f"{document_id}.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    pdf.setTitle("ReinCrew Internship Completion Letter")
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(width/2, height-110, "REINCREW")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(width/2, height-165, "INTERNSHIP COMPLETION LETTER")
    pdf.setFont("Helvetica", 12)
    lines = [
        f"This is to certify that {name}",
        f"has successfully completed the internship in {role}.",
        f"Internship period: {start_date} to {end_date}.",
        "",
        "We appreciate the contribution and wish them success."
    ]
    y = height-240
    for line in lines:
        pdf.drawCentredString(width/2, y, line)
        y -= 28
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(65, 120, f"Document ID: {document_id}")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(65, 75, signatory)
    pdf.drawString(65, 58, "ReinCrew")
    pdf.save()
    return path
