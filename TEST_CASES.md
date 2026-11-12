# Test Cases and Bug Tracker

| ID | Test | Expected result | Status |
|---|---|---|---|
| TC-01 | Submit valid application | Unique application ID displayed | To test |
| TC-02 | Submit same email twice | Duplicate active application blocked | To test |
| TC-03 | Submit without required field | Validation message shown | To test |
| TC-04 | Admin login with valid credentials | Admin dashboard opens | To test |
| TC-05 | Admin login with wrong password | Login denied | To test |
| TC-06 | Select applicant | Intern profile and unique intern ID created | To test |
| TC-07 | Create intern login | Intern can log in | To test |
| TC-08 | Assign task | Task appears in intern dashboard | To test |
| TC-09 | Submit task | Task status becomes Submitted | To test |
| TC-10 | Review task | Approved/Revision Required/Rejected saved | To test |
| TC-11 | Submit daily report | Report appears in admin reports | To test |
| TC-12 | Complete with unapproved task | Completion blocked | To test |
| TC-13 | Complete with all tasks approved | PDF and document ID generated | To test |
| TC-14 | SMTP not configured | Email not sent; failure/pending logged | To test |
| TC-15 | SMTP configured | Email accepted by SMTP and logged | To test |\



## Bug tracker

| Bug ID | Description | Severity | Owner | Status |

| BUG-001 | Fill after local test | — | Ajay | Open |
