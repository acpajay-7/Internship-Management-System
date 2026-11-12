# Database schema overview

- `users`: login identity, password hash, role (`admin` or `intern`)
- `internships`: public internship listings
- `applications`: candidate details, resume path, status and admin notes
- `interns`: selected candidate profile and internship ID
- `tasks`: assigned work, deadline, submission and review state
- `daily_reports`: daily progress, hours, pending work and blockers
- `documents`: generated completion document IDs and file paths
- `email_logs`: email attempt status and SMTP response

Relationships:
- An application can produce an intern profile.
- An intern can have many tasks and daily reports.
- An intern can have generated completion documents.
