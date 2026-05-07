"""
BluBridge Help & Templates module (iter67)
==========================================
- Provides downloadable multi-sheet XLSX templates per upload-flow.
- Currently exposes the WhatsApp Resend template (Template / Instructions /
  Match Priority Logic / FAQs).
- Designed as a standalone module so future templates (Naukri, Pipeline,
  Score Sheet, etc.) can be added without touching the core server.
"""
import io
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

_logger = logging.getLogger("bb_help")
help_router = APIRouter(prefix="/api/bb/help", tags=["Help"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# --- styles ---
_HDR_FILL = PatternFill(start_color="1D3A8A", end_color="1D3A8A", fill_type="solid")
_HDR_FONT = Font(bold=True, color="FFFFFF", size=11)
_SECTION_FILL = PatternFill(start_color="FAF9F1", end_color="FAF9F1", fill_type="solid")
_SECTION_FONT = Font(bold=True, color="1A2332", size=12)
_BORDER = Border(*[Side(style="thin", color="E5E3D8")] * 4)


def _autosize(ws, col_widths: dict[int, int]):
    for idx, w in col_widths.items():
        ws.column_dimensions[get_column_letter(idx)].width = w


def _write_header(ws, row: int, headers: list[str]):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.fill = _HDR_FILL
        c.font = _HDR_FONT
        c.alignment = Alignment(horizontal="left", vertical="center")
        c.border = _BORDER


def _write_section(ws, row: int, title: str, span: int = 2):
    c = ws.cell(row=row, column=1, value=title)
    c.fill = _SECTION_FILL
    c.font = _SECTION_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)


def _build_whatsapp_resend_workbook() -> bytes:
    wb = Workbook()

    # ---------- Sheet 1: Template ----------
    ws = wb.active
    ws.title = "Template"
    _write_header(ws, 1, ["Name", "Email", "Phone"])
    sample_rows = [
        ["Rishi Nayak", "rishi.nayak@blubridge.com", "9443109903"],
        ["Sharmila R",  "sharmilaramu772@gmail.com", "8015527422"],
        ["Aravind K",   "aravind.k@example.com",     "9876543210"],
    ]
    for r_idx, row in enumerate(sample_rows, 2):
        for c_idx, val in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.border = _BORDER

    # Helper note
    note_row = len(sample_rows) + 3
    ws.cell(row=note_row, column=1, value="Notes:").font = Font(bold=True, color="1A2332")
    notes = [
        "1. Replace the example rows with your candidates and re-upload.",
        "2. Column names are auto-mapped — these aliases are accepted:",
        "    Name : name | candidate_name | full_name | applicant",
        "    Email : email | email_id | mail | email_address",
        "    Phone : phone | mobile | phone_number | contact",
        "3. Phone must be a 10-digit Indian number starting with 6/7/8/9.",
        "4. At least one of Email or Phone is required per row.",
    ]
    for i, n in enumerate(notes):
        ws.cell(row=note_row + 1 + i, column=1, value=n).font = Font(color="3F4655")
    _autosize(ws, {1: 28, 2: 38, 3: 18})

    # ---------- Sheet 2: Instructions ----------
    ws2 = wb.create_sheet("Instructions")
    _write_section(ws2, 1, "How to use the WhatsApp Resend module", span=3)
    steps = [
        ("Step 1", "Open the module", "Go to BluBridge → sidebar → WhatsApp Resend."),
        ("Step 2", "Download this template", "Click 'Download Sample Template' on the upload zone."),
        ("Step 3", "Fill candidate list", "Enter Name, Email, Phone for each candidate (use 'Template' sheet)."),
        ("Step 4", "Upload", "Drag-drop or browse the .csv/.xlsx file. Max 5 MB."),
        ("Step 5", "Preview", "System auto-matches each row against pipeline_data + bb_registrations and fetches the latest active schedule + meeting link."),
        ("Step 6", "Filter / Search", "Use Match Status / WhatsApp Status filters to focus on rows."),
        ("Step 7", "Send Test", "(Optional) Click 'Send Test' to send the template to the allowlisted number."),
        ("Step 8", "Resend", "Use Bulk Resend, Resend Selected, or per-row send. Cooldown: 5 min per candidate."),
        ("Step 9", "History", "Click 'Resend History' to see every send with status & failure reason."),
    ]
    _write_header(ws2, 3, ["Step", "Action", "Details"])
    for i, (step, action, detail) in enumerate(steps, 4):
        ws2.cell(row=i, column=1, value=step).border = _BORDER
        ws2.cell(row=i, column=2, value=action).border = _BORDER
        ws2.cell(row=i, column=3, value=detail).border = _BORDER

    # Validations & limits section
    base = 4 + len(steps) + 2
    _write_section(ws2, base, "Validations & Limits", span=3)
    rules = [
        ("File size", "≤ 5 MB"),
        ("File types", ".csv, .xlsx, .xls"),
        ("Phone format", "10-digit Indian (6/7/8/9 prefix)"),
        ("Cooldown", "5 minutes per candidate"),
        ("Allowlist", "Strict — only allowlisted (email, phone) pairs receive WhatsApp; others log as 'blocked'"),
        ("Schedule link", "Resend is skipped if no active schedule exists for that candidate"),
        ("AiSensy template", "Reuses approved 'Candidate FollowUp' (5 params: name, role, date, time, link)"),
    ]
    _write_header(ws2, base + 1, ["Rule", "Value", ""])
    for i, (k, v) in enumerate(rules, base + 2):
        ws2.cell(row=i, column=1, value=k).border = _BORDER
        ws2.cell(row=i, column=2, value=v).border = _BORDER
    _autosize(ws2, {1: 16, 2: 32, 3: 60})

    # ---------- Sheet 3: Match Priority Logic ----------
    ws3 = wb.create_sheet("Match Priority Logic")
    _write_section(ws3, 1, "How candidates are matched", span=4)
    _write_header(ws3, 3, ["Priority", "Match Rule", "Confidence", "Status"])
    rows = [
        ("P1", "Exact Name + Email", "100%", "Exact Match"),
        ("P2", "Exact Name + Phone (last 10 digits)", "95%",  "Exact Match"),
        ("P3", "Email only — single candidate found",      "80%",  "Partial Match"),
        ("P3", "Email only — multiple candidates found",   "75%",  "Multiple Match"),
        ("P4", "Phone only — single candidate found",      "75%",  "Partial Match"),
        ("P4", "Phone only — multiple candidates found",   "70%",  "Multiple Match"),
        ("—",  "No match in pipeline_data or bb_registrations", "0%", "No Match"),
    ]
    for i, row in enumerate(rows, 4):
        for c, val in enumerate(row, 1):
            ws3.cell(row=i, column=c, value=val).border = _BORDER

    base3 = 4 + len(rows) + 2
    _write_section(ws3, base3, "Data Sources Searched", span=4)
    sources = [
        ("pipeline_data",      "Master HR table — name, email, phone, job_role, schedule_date, schedule_time, status"),
        ("bb_registrations",   "Public registrations + reschedule tokens — schedule_token used for the meeting link"),
    ]
    _write_header(ws3, base3 + 1, ["Collection", "Description", "", ""])
    for i, (k, v) in enumerate(sources, base3 + 2):
        ws3.cell(row=i, column=1, value=k).border = _BORDER
        ws3.cell(row=i, column=2, value=v).border = _BORDER
    _autosize(ws3, {1: 14, 2: 40, 3: 14, 4: 16})

    # ---------- Sheet 4: FAQs ----------
    ws4 = wb.create_sheet("FAQs")
    _write_section(ws4, 1, "Frequently Asked Questions", span=2)
    faqs = [
        ("Why is my WhatsApp message marked as 'blocked'?",
         "BluBridge enforces a strict allowlist for outbound messages. Only the configured (email, phone) pairs receive real WhatsApp. Update the allowlist in /app/backend/messaging.py to add more recipients."),
        ("Why do some matched rows show 'No active schedule available'?",
         "The candidate exists in pipeline_data but has no schedule_date/schedule_time set. Set their schedule first via the Hiring Forms / Update Scores flow."),
        ("Why does my upload show '0 matched'?",
         "The file's Name/Email/Phone columns may have non-standard headers. Rename them to one of the accepted aliases (see Template sheet) and re-upload."),
        ("How is the meeting link generated?",
         "If the candidate already has a bb_registrations.schedule_token, that token's URL is used. Otherwise a fresh token is created on send."),
        ("What is the cooldown?",
         "Each candidate can only receive a resend once per 5 minutes — additional attempts are skipped to prevent spam."),
        ("Can I resend only failed rows?",
         "Yes — click 'Retry Failed' in the toolbar."),
        ("Where can I see who sent what?",
         "Click 'Resend History' (top-right). Every send has timestamp, status, retry count, and failure reason."),
    ]
    for i, (q, a) in enumerate(faqs, 3):
        ws4.cell(row=i * 2,     column=1, value=f"Q: {q}").font = Font(bold=True, color="1A2332")
        ws4.cell(row=i * 2 + 1, column=1, value=f"A: {a}").alignment = Alignment(wrap_text=True, vertical="top")
        ws4.row_dimensions[i * 2 + 1].height = 45
    _autosize(ws4, {1: 110})

    # Serialize
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


@help_router.get("/template/whatsapp-resend")
async def download_whatsapp_resend_template():
    data = _build_whatsapp_resend_workbook()
    return StreamingResponse(
        io.BytesIO(data),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="BluBridge-WhatsApp-Resend-Template.xlsx"'},
    )


@help_router.get("/manifest")
async def help_manifest():
    """Return the structured help content used by the web Help page."""
    return {
        "modules": [
            {
                "id": "dashboard", "name": "Analytics Dashboard", "icon": "ChartBar", "color": "blue",
                "summary": "Upload Naukri / Pipeline / Score Sheet / College-Rank datasets and view live counts.",
                "steps": [
                    "Click any of the four upload tiles to push a CSV/XLSX into the system.",
                    "After upload finishes, the count badge updates automatically.",
                    "Use the Candidate Journey search box to look up any applicant by email or phone.",
                ],
                "tips": [
                    "Naukri must be uploaded before Pipeline (Pipeline matching depends on Naukri rows).",
                    "Score Sheet is normalised so duplicates (same email or phone) are merged.",
                ],
            },
            {
                "id": "hiring-forms", "name": "Hiring Forms", "icon": "FileText", "color": "violet",
                "summary": "Create custom application forms with conditional logic for each job role.",
                "steps": [
                    "Click '+ New Form' and pick the form type.",
                    "Add fields, options, and conditional rules.",
                    "Toggle 'Show Instruction Page' if you want a pre-form instruction screen.",
                    "Copy the public URL and share with candidates.",
                ],
                "tips": ["Slug-based URLs: /register/<your-slug>"],
            },
            {
                "id": "interview-reports", "name": "Interview Schedule Reports", "icon": "CalendarCheck", "color": "cyan",
                "summary": "Filterable report of every scheduled interview with attendance + college-tier breakdown.",
                "steps": [
                    "Filter by date range, job role, attendance, or college type.",
                    "Click 'Export' to pick fields to include in the CSV.",
                ],
                "tips": ["The KPI strip (Attended / Not Attended / Premium / Non-Premium) reflects current filters."],
            },
            {
                "id": "update-scores", "name": "Update Applicants Scores", "icon": "PencilLine", "color": "emerald",
                "summary": "Manage interview rounds and update each candidate's per-round score, command, status.",
                "steps": [
                    "Pick a candidate row and click 'Update Score'.",
                    "Add or edit round entries (Round name, Score, Command, Status).",
                    "Save — changes are append-only; previous values are preserved in history.",
                ],
                "tips": ["Use 'Manage Rounds' to add or rename round columns globally."],
            },
            {
                "id": "score-round", "name": "Score & Round", "icon": "Table", "color": "sky",
                "summary": "Excel-like grid of every candidate × round score + induction dates.",
                "steps": [
                    "Use the top filter bar to narrow by Job Role / Status / Date range.",
                    "Click any cell to inline-edit. Status filter shows only Shortlisted, Rejected, On-Hold (typos auto-grouped).",
                ],
                "tips": ["Three induction date columns — DOJ, Onboarding, Termination — are dedicated pickers."],
            },
            {
                "id": "candidate-journey", "name": "Candidate Journey", "icon": "MagnifyingGlass", "color": "indigo",
                "summary": "End-to-end timeline for a single candidate (rounds, scores, status, induction).",
                "steps": [
                    "Search by email or phone.",
                    "View the timeline + every recorded score change.",
                ],
                "tips": ["Useful for HR queries — 'why was this candidate rejected?'"],
            },
            {
                "id": "whatsapp-resend", "name": "WhatsApp Missed Schedule Link Resend", "icon": "WhatsappLogo", "color": "whatsapp",
                "summary": "Re-deliver interview schedules + meeting links via WhatsApp for candidates who missed/deleted their original message.",
                "steps": [
                    "Download the .xlsx template (Help page or upload zone).",
                    "Fill Name/Email/Phone, save, and upload.",
                    "Auto-match against pipeline_data + bb_registrations runs instantly.",
                    "Preview the table — sendable rows have an active schedule + valid phone.",
                    "Click 'Bulk Resend' or per-row send.",
                    "Track every send in 'Resend History'.",
                ],
                "tips": [
                    "5-min cooldown per candidate.",
                    "Strict allowlist applies — non-allowlisted recipients log as 'blocked'.",
                    "Reuses the AiSensy 'Candidate FollowUp' template (5 params).",
                ],
                "downloads": [
                    {"label": "WhatsApp Resend Template (.xlsx)", "url": "/api/bb/help/template/whatsapp-resend"},
                ],
            },
            {
                "id": "manage-job-roles", "name": "Create Job Roles", "icon": "Briefcase", "color": "navy",
                "summary": "Define and manage job titles used everywhere in the app.",
                "steps": ["Click 'Add Role', enter the title, click 'Save'."],
                "tips": ["Renaming a role updates references in pipeline_data automatically."],
            },
            {
                "id": "job-openings", "name": "Create Job Openings", "icon": "FolderOpen", "color": "rose",
                "summary": "Publish job openings with description, requirements, and status.",
                "steps": ["Add opening → fill description/requirements → toggle 'Active' to publish."],
                "tips": [],
            },
            {
                "id": "college-schedules", "name": "College Drives", "icon": "GraduationCap", "color": "pink",
                "summary": "Configure interview schedules per college and role.",
                "steps": ["Add a college, pick the job role chips, set the date/time, save."],
                "tips": ["Each college schedule generates a public registration link."],
            },
            {
                "id": "set-holidays", "name": "Set Holidays", "icon": "CalendarBlank", "color": "orange",
                "summary": "Block specific dates from being chosen as interview slots.",
                "steps": ["Pick a date → enter a name → save. Public schedule pages will hide that date."],
                "tips": [],
            },
            {
                "id": "verify-otp", "name": "Verify Applicant OTP", "icon": "ShieldCheck", "color": "teal",
                "summary": "Confirm applicant attendance via phone-number OTP at reception.",
                "steps": [
                    "Enter the candidate's phone (last 10 digits) and OTP.",
                    "On success, the candidate's status updates to 'Attended' across pipeline_data + bb_registrations.",
                ],
                "tips": ["OTP window: 3 hours before the scheduled time → 8 hours after it expires."],
            },
        ],
        "global_faqs": [
            {"q": "Why does WhatsApp say 'blocked'?",
             "a": "Strict allowlist enforces only configured (email, phone) pairs receive real outbound messages."},
            {"q": "Why does my upload show 0 matched?",
             "a": "Column headers may not match expected aliases. Use the .xlsx template — rename headers to Name / Email / Phone."},
            {"q": "How do I add a new accepted recipient?",
             "a": "Edit /app/backend/messaging.py → _ALLOWED_PAIRS tuple."},
            {"q": "Can I export a table?",
             "a": "Most module tables support 'Export' with field selection. Currently: Roles, Attended Roles, Interview Reports."},
            {"q": "What is the difference between Roles and Attended Roles?",
             "a": "Roles = all candidates. Attended Roles = candidates whose otp_verified=true (showed up at reception)."},
        ],
    }
