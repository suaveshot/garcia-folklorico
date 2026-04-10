"""
Garcia Folklorico Studio -- Google Sheets CRM Builder

Creates a production-ready, professionally formatted 9-tab Google Sheets CRM.
Run once to create the spreadsheet; run_sync.py handles ongoing data sync.

Usage:
    python -m sheets_sync.create_crm

    Or standalone:
    cd automation && python sheets_sync/create_crm.py

Prerequisites:
    - Google Cloud service account with Sheets API + Drive API enabled
    - Service account JSON key path in .env as GOOGLE_SHEETS_CREDS
    - pip install gspread gspread-formatting google-auth
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import GOOGLE_SHEETS_CREDS, AUTOMATION_DIR

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [create_crm] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brand palette (hex -> RGB 0-1 floats for gspread)
# ---------------------------------------------------------------------------
def hex_to_rgb(hex_color):
    """Convert hex color string to (r, g, b) floats 0.0-1.0."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))


# Brand colors
ORANGE = "#F97316"
ORANGE_DARK = "#C2410C"
ORANGE_LIGHT = "#FFF7ED"
LAVENDER = "#C4B5FD"
LAVENDER_DARK = "#7C3AED"
LAVENDER_LIGHT = "#F5F3FF"
INDIGO_DARK = "#1E1B4B"
SUCCESS = "#16A34A"
SUCCESS_LIGHT = "#DCFCE7"
ERROR = "#DC2626"
ERROR_LIGHT = "#FEE2E2"
WARNING = "#D97706"
WARNING_LIGHT = "#FEF3C7"
GRAY = "#6B7280"
GRAY_LIGHT = "#F3F4F6"
STRIPE = "#F9FAFB"
WHITE = "#FFFFFF"
BLUE = "#0284C7"
BLUE_DARK = "#0C4A6E"
BLUE_LIGHT = "#DBEAFE"
YELLOW_LIGHT = "#FEF9C3"
GREEN_DARK = "#14532D"
GREEN_MID = "#15803D"
AMBER = "#D97706"
AMBER_DARK = "#92400E"
PURPLE_LIGHT = "#FDF4FF"
ECFDF5 = "#ECFDF5"
EFF6FF = "#EFF6FF"
FFFBEB = "#FFFBEB"
FAFAFA = "#FAFAFA"

# Schedule data for seeding
SCHEDULE_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "backend" / "schedule_data.json"

# Pipeline stages
PIPELINE_STAGES = [
    "New Inquiry", "Contacted", "Trial Scheduled", "Trial Completed",
    "Registration Sent", "Enrolled", "Active Student", "Re-enrollment",
    "Alumni", "Lost", "Waitlisted"
]

STAGE_COLORS = {
    "New Inquiry": ORANGE_LIGHT,
    "Contacted": YELLOW_LIGHT,
    "Trial Scheduled": BLUE_LIGHT,
    "Trial Completed": LAVENDER_LIGHT,
    "Registration Sent": WARNING_LIGHT,
    "Enrolled": SUCCESS_LIGHT,
    "Active Student": SUCCESS_LIGHT,
    "Re-enrollment": ECFDF5,
    "Alumni": GRAY_LIGHT,
    "Lost": ERROR_LIGHT,
    "Waitlisted": LAVENDER_LIGHT,
}

CLASS_DROPDOWN = [
    "Mommy & Me", "Semillas", "Botones de Flor", "Elementary", "Raices", "Undecided"
]
CONTACT_METHODS = ["Email", "Phone", "Text", "Walk-in", "Web Form", "Referral"]
LANGUAGES = ["EN", "ES"]
TRIAL_RESULTS = ["Attended", "No-show", "Rescheduled", "Pending"]
LEAD_SOURCES = [
    "Website", "Referral", "Social Media", "Walk-in", "Event / Fair",
    "Google Search", "Instagram", "Facebook"
]
WAITLIST_STATUSES = ["Waiting", "Spot Offered", "Claimed", "Expired", "Withdrew"]
RENTAL_STATUSES = ["Confirmed", "Cancelled", "Completed", "Pending"]
PAYMENT_STATUSES = ["Unpaid", "Paid", "Partial", "Waived", "Refunded"]
PAYMENT_METHODS = ["Cash", "Zelle", "Venmo", "Check", "Card", "Other"]
REVENUE_TYPES = ["Tuition", "Rental", "Other"]
STUDENT_STATUSES = ["Active", "Cancelled", "Transferred"]
COMM_CHANNELS = [
    "Email", "Phone Call", "Text/SMS", "In-person", "WhatsApp",
    "Website Form", "Social Media DM"
]
COMM_DIRECTIONS = ["Outbound", "Inbound"]
COMM_RESPONSES = ["Yes", "No", "N/A"]
TOUCH_NUMBERS = ["1", "2", "3", "4", "Nurture", "One-off"]


def load_schedule_data():
    """Load class types and schedule from backend config."""
    try:
        return json.loads(SCHEDULE_DATA_PATH.read_text())
    except Exception as e:
        log.warning(f"Could not load schedule_data.json: {e}")
        return None


def rate_limit():
    """Pause briefly to stay under Sheets API quota (60 req/min)."""
    time.sleep(1.2)


def build_crm():
    """Main entry: create the full CRM spreadsheet."""
    try:
        import gspread
        from gspread_formatting import (
            CellFormat, TextFormat, Color, Border, Borders,
            format_cell_range, set_column_width, set_frozen,
            NumberFormat,
        )
    except ImportError:
        log.error("Missing dependencies. Run: pip install gspread gspread-formatting")
        return

    if not GOOGLE_SHEETS_CREDS:
        log.error("GOOGLE_SHEETS_CREDS not set in .env")
        return

    creds_path = GOOGLE_SHEETS_CREDS
    if not Path(creds_path).exists():
        log.error(f"Credentials file not found: {creds_path}")
        return

    gc = gspread.service_account(filename=creds_path)

    log.info("Creating spreadsheet...")
    spreadsheet = gc.create("Garcia Folklorico Studio - CRM")

    share_email = os.getenv("SAM_EMAIL", "salarcon@americalpatrol.com")
    spreadsheet.share(share_email, perm_type="user", role="writer")
    log.info(f"Shared with {share_email}")

    itzel_email = os.getenv("ITZEL_EMAIL", "")
    if itzel_email:
        spreadsheet.share(itzel_email, perm_type="user", role="writer")
        log.info(f"Shared with {itzel_email}")

    schedule_data = load_schedule_data()

    # Helper to make Color from hex
    def c(hex_color):
        r, g, b = hex_to_rgb(hex_color)
        return Color(r, g, b)

    def header_fmt(bg_hex=INDIGO_DARK, size=11):
        return CellFormat(
            backgroundColor=c(bg_hex),
            textFormat=TextFormat(bold=True, fontSize=size,
                                 foregroundColor=c(WHITE)),
            horizontalAlignment="CENTER",
            verticalAlignment="MIDDLE",
        )

    def section_header_fmt(bg_hex):
        return CellFormat(
            backgroundColor=c(bg_hex),
            textFormat=TextFormat(bold=True, fontSize=11,
                                 foregroundColor=c(WHITE)),
            horizontalAlignment="LEFT",
            verticalAlignment="MIDDLE",
        )

    def label_fmt():
        return CellFormat(
            textFormat=TextFormat(bold=True, fontSize=10,
                                 foregroundColor=c(INDIGO_DARK)),
        )

    def value_fmt():
        return CellFormat(
            textFormat=TextFormat(bold=True, fontSize=10,
                                 foregroundColor=c(ORANGE)),
        )

    # -----------------------------------------------------------------------
    # Helper: add conditional formatting rules via raw API
    # -----------------------------------------------------------------------
    def add_cond_format_rules(sheet_id, rules):
        """Add conditional formatting rules to a sheet via batch update."""
        requests = []
        for idx, rule in enumerate(rules):
            requests.append({
                "addConditionalFormatRule": {
                    "rule": rule,
                    "index": idx,
                }
            })
        if requests:
            spreadsheet.batch_update({"requests": requests})
            rate_limit()

    def bool_condition(cond_type, values=None):
        cond = {"type": cond_type}
        if values:
            cond["values"] = [{"userEnteredValue": v} for v in values]
        return cond

    def cell_format_from_hex(bg_hex=None, fg_hex=None, bold=False):
        fmt = {}
        if bg_hex:
            r, g, b = hex_to_rgb(bg_hex)
            fmt["backgroundColor"] = {"red": r, "green": g, "blue": b}
        tf = {}
        if fg_hex:
            r, g, b = hex_to_rgb(fg_hex)
            tf["foregroundColor"] = {"red": r, "green": g, "blue": b}
        if bold:
            tf["bold"] = True
        if tf:
            fmt["textFormat"] = tf
        return fmt

    def make_range(sheet_id, sr, er, sc, ec):
        return {
            "sheetId": sheet_id,
            "startRowIndex": sr,
            "endRowIndex": er,
            "startColumnIndex": sc,
            "endColumnIndex": ec,
        }

    # -----------------------------------------------------------------------
    # Helper: add data validation via raw API
    # -----------------------------------------------------------------------
    def add_dropdown_validation(sheet_id, start_row, end_row, col_idx, values):
        """Add dropdown data validation to a column range."""
        request = {
            "setDataValidation": {
                "range": make_range(sheet_id, start_row, end_row, col_idx, col_idx + 1),
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in values],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        }
        return request

    # -----------------------------------------------------------------------
    # TAB 1: DASHBOARD
    # -----------------------------------------------------------------------
    log.info("Building Dashboard tab...")
    # Rename default Sheet1 to Dashboard
    dash = spreadsheet.sheet1
    dash.update_title("Dashboard")
    dash.resize(rows=40, cols=15)

    # Tab color
    dash_color = hex_to_rgb(ORANGE)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": dash.id, "tabColor": {"red": dash_color[0], "green": dash_color[1], "blue": dash_color[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    # Row 1: Banner
    dash.merge_cells("A1:O1")
    dash.update("A1", [["Garcia Folklorico Studio - CRM Dashboard"]], value_input_option="RAW")
    format_cell_range(dash, "A1:O1", CellFormat(
        backgroundColor=c(INDIGO_DARK),
        textFormat=TextFormat(bold=True, fontSize=18, foregroundColor=c(WHITE)),
        horizontalAlignment="CENTER",
        verticalAlignment="MIDDLE",
    ))
    spreadsheet.batch_update({"requests": [{"updateDimensionProperties": {
        "range": {"sheetId": dash.id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 52}, "fields": "pixelSize"
    }}]})
    rate_limit()

    # Row 3: KPI Labels | Row 4: KPI Values | Row 5: KPI sub-labels
    kpi_labels = ["Active Students", "", "", "Waitlisted", "", "", "Open Pipeline", "", "", "Monthly Revenue", "", "", "Rental $ MTD", "", ""]
    kpi_values = [
        '=COUNTIF(\'Active Students\'!L:L,"Active")', "", "",
        '=COUNTA(Waitlist!B2:B500)', "", "",
        '=COUNTIFS(\'Student Pipeline\'!F2:F500,"<>"&"Enrolled",\'Student Pipeline\'!F2:F500,"<>"&"Active Student",\'Student Pipeline\'!F2:F500,"<>"&"Lost",\'Student Pipeline\'!F2:F500,"<>"&"Alumni",\'Student Pipeline\'!F2:F500,"<>"&"")', "", "",
        '=SUMIFS(\'Revenue & Payments\'!G2:G500,\'Revenue & Payments\'!H2:H500,"Paid",\'Revenue & Payments\'!D2:D500,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1))', "", "",
        '=SUMIFS(\'Revenue & Payments\'!G2:G500,\'Revenue & Payments\'!C2:C500,"Rental",\'Revenue & Payments\'!H2:H500,"Paid",\'Revenue & Payments\'!D2:D500,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1))', "", ""
    ]

    dash.update("A3:O3", [kpi_labels], value_input_option="RAW")
    dash.update("A4:O4", [kpi_values], value_input_option="USER_ENTERED")
    rate_limit()

    # Merge KPI tile cells
    for start_col_idx in range(0, 15, 3):
        end_col = chr(ord("A") + start_col_idx + 2)
        start_col = chr(ord("A") + start_col_idx)
        dash.merge_cells(f"{start_col}3:{end_col}3")
        dash.merge_cells(f"{start_col}4:{end_col}4")

    # Format KPI labels (small gray)
    format_cell_range(dash, "A3:O3", CellFormat(
        textFormat=TextFormat(italic=True, fontSize=9, foregroundColor=c(GRAY)),
        horizontalAlignment="CENTER",
        verticalAlignment="BOTTOM",
        backgroundColor=c(WHITE),
    ))
    # Format KPI values (big orange numbers)
    format_cell_range(dash, "A4:O4", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=22, foregroundColor=c(ORANGE)),
        horizontalAlignment="CENTER",
        verticalAlignment="MIDDLE",
        backgroundColor=c(WHITE),
    ))
    # Format revenue KPIs as currency
    format_cell_range(dash, "J4:L4", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
    ))
    format_cell_range(dash, "M4:O4", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
    ))
    rate_limit()

    # Lavender accent borders on left side of each KPI tile
    for col_letter in ["A", "D", "G", "J", "M"]:
        format_cell_range(dash, f"{col_letter}3:{col_letter}4", CellFormat(
            borders=Borders(
                left=Border("SOLID_MEDIUM", c(LAVENDER)),
            ),
        ))
    rate_limit()

    # Row 6: spacer
    # Row 7: Class Capacity header (A-G)
    dash.merge_cells("A7:G7")
    dash.update("A7", [["CLASS CAPACITY - CURRENT BLOCK"]], value_input_option="RAW")
    format_cell_range(dash, "A7:G7", section_header_fmt(ORANGE))
    rate_limit()

    # Row 7 right: Pipeline Funnel header (I-N)
    dash.merge_cells("I7:N7")
    dash.update("I7", [["INQUIRY PIPELINE"]], value_input_option="RAW")
    format_cell_range(dash, "I7:N7", section_header_fmt(LAVENDER_DARK))
    rate_limit()

    # Class capacity headers (row 8)
    cap_headers = ["Class", "Enrolled", "Capacity", "Waitlisted", "Fill %", "Status", ""]
    dash.update("A8:G8", [cap_headers], value_input_option="RAW")
    format_cell_range(dash, "A8:G8", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=c(INDIGO_DARK)),
        backgroundColor=c(FAFAFA),
    ))
    rate_limit()

    # Class capacity data rows (9-13)
    classes = ["Mommy & Me", "Semillas", "Botones de Flor", "Elementary", "Raices"]
    capacities = [12, 14, 14, 20, 20]
    for i, (cls, cap) in enumerate(zip(classes, capacities)):
        row = 9 + i
        dash.update(f"A{row}", [[cls]], value_input_option="RAW")
        dash.update(f"B{row}", [[f'=COUNTIFS(\'Active Students\'!C2:C500,A{row},\'Active Students\'!L2:L500,"Active")']], value_input_option="USER_ENTERED")
        dash.update(f"C{row}", [[cap]], value_input_option="RAW")
        dash.update(f"D{row}", [[f'=COUNTIFS(Waitlist!D2:D500,A{row},Waitlist!J2:J500,"Waiting")']], value_input_option="USER_ENTERED")
        dash.update(f"E{row}", [[f"=IF(C{row}>0,B{row}/C{row},0)"]], value_input_option="USER_ENTERED")
        dash.update(f"F{row}", [[f'=IF(B{row}>=C{row},"FULL","OPEN")']], value_input_option="USER_ENTERED")
        dash.update(f"G{row}", [[f'=REPT("|",ROUND(E{row}*15,0))']], value_input_option="USER_ENTERED")
    rate_limit()

    # Format fill % column
    format_cell_range(dash, "E9:E13", CellFormat(
        numberFormat=NumberFormat(type="PERCENT", pattern="0%"),
    ))
    rate_limit()

    # Pipeline funnel data (rows 8-17, cols I-L)
    pipe_headers = ["Stage", "Count", ""]
    dash.update("I8:K8", [pipe_headers], value_input_option="RAW")
    format_cell_range(dash, "I8:K8", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=c(INDIGO_DARK)),
        backgroundColor=c(FAFAFA),
    ))

    funnel_stages = [
        "New Inquiry", "Contacted", "Trial Scheduled", "Trial Completed",
        "Registration Sent", "Enrolled", "Re-enrollment", "Lost"
    ]
    for i, stage in enumerate(funnel_stages):
        row = 9 + i
        dash.update(f"I{row}", [[stage]], value_input_option="RAW")
        dash.update(f"J{row}", [[f'=COUNTIF(\'Student Pipeline\'!F2:F500,I{row})']], value_input_option="USER_ENTERED")
    rate_limit()

    # Conversion rate
    dash.update(f"I17", [["TOTAL"]], value_input_option="RAW")
    dash.update(f"J17", [["=SUM(J9:J16)"]], value_input_option="USER_ENTERED")
    format_cell_range(dash, "I17:K17", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=c(INDIGO_DARK)),
        borders=Borders(top=Border("SOLID", c(GRAY))),
    ))

    dash.update("I18", [["Conversion"]], value_input_option="RAW")
    dash.update("J18", [['=IF(J17>0,J14/J17,0)']], value_input_option="USER_ENTERED")
    format_cell_range(dash, "J18", CellFormat(
        numberFormat=NumberFormat(type="PERCENT", pattern="0.0%"),
        textFormat=TextFormat(bold=True, foregroundColor=c(SUCCESS)),
    ))
    rate_limit()

    # Row 20: Action Items header
    dash.merge_cells("A20:G20")
    dash.update("A20", [["NEEDS ATTENTION"]], value_input_option="RAW")
    format_cell_range(dash, "A20:G20", section_header_fmt(INDIGO_DARK))
    rate_limit()

    # Action item rows
    action_labels = [
        ["Overdue follow-ups (>3 days)", '=COUNTIFS(\'Student Pipeline\'!F2:F500,"Contacted",\'Student Pipeline\'!H2:H500,"<"&TODAY()-3,\'Student Pipeline\'!H2:H500,"<>"&"")'],
        ["Trials scheduled today", '=COUNTIFS(\'Student Pipeline\'!F2:F500,"Trial Scheduled",\'Student Pipeline\'!O2:O500,TODAY())'],
        ["Unpaid tuition >7 days", '=COUNTIFS(\'Revenue & Payments\'!H2:H500,"Unpaid",\'Revenue & Payments\'!D2:D500,"<"&TODAY()-7,\'Revenue & Payments\'!D2:D500,"<>"&"")'],
        ["Waitlist spots expiring soon", '=COUNTIFS(Waitlist!J2:J500,"Spot Offered")'],
        ["Alumni for re-enrollment", '=COUNTIFS(\'Student Pipeline\'!F2:F500,"Alumni")'],
    ]
    for i, (label, formula) in enumerate(action_labels):
        row = 21 + i
        dash.update(f"A{row}", [[label]], value_input_option="RAW")
        dash.update(f"E{row}", [[formula]], value_input_option="USER_ENTERED")
    format_cell_range(dash, "A21:A25", label_fmt())
    format_cell_range(dash, "E21:E25", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=12, foregroundColor=c(ERROR)),
        horizontalAlignment="CENTER",
    ))
    rate_limit()

    # Revenue snapshot (right side)
    dash.merge_cells("I20:N20")
    dash.update("I20", [["REVENUE SNAPSHOT"]], value_input_option="RAW")
    format_cell_range(dash, "I20:N20", section_header_fmt(GREEN_DARK))

    rev_items = [
        ["Total Collected", '=SUMIF(\'Revenue & Payments\'!H2:H500,"Paid",\'Revenue & Payments\'!G2:G500)'],
        ["Outstanding", '=SUMIF(\'Revenue & Payments\'!H2:H500,"Unpaid",\'Revenue & Payments\'!G2:G500)'],
        ["Tuition Collected", '=SUMIFS(\'Revenue & Payments\'!G2:G500,\'Revenue & Payments\'!C2:C500,"Tuition",\'Revenue & Payments\'!H2:H500,"Paid")'],
        ["Rental Collected", '=SUMIFS(\'Revenue & Payments\'!G2:G500,\'Revenue & Payments\'!C2:C500,"Rental",\'Revenue & Payments\'!H2:H500,"Paid")'],
    ]
    for i, (label, formula) in enumerate(rev_items):
        row = 21 + i
        dash.update(f"I{row}", [[label]], value_input_option="RAW")
        dash.update(f"L{row}", [[formula]], value_input_option="USER_ENTERED")
    format_cell_range(dash, "I21:I24", label_fmt())
    format_cell_range(dash, "L21:L24", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=11, foregroundColor=c(SUCCESS)),
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
    ))
    rate_limit()

    # Column widths
    col_widths = {0: 140, 1: 80, 2: 80, 3: 80, 4: 70, 5: 70, 6: 120,
                  8: 130, 9: 60, 10: 60, 11: 100, 12: 100, 13: 80, 14: 80}
    width_requests = []
    for col, w in col_widths.items():
        width_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": dash.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": width_requests})
    rate_limit()

    # Freeze rows 1-2
    set_frozen(dash, rows=2)

    # Conditional formatting for capacity status
    cap_cond_rules = []
    for row_idx in range(8, 13):  # rows 9-13 (0-indexed: 8-12)
        # FULL = red
        cap_cond_rules.append({
            "ranges": [make_range(dash.id, row_idx, row_idx + 1, 5, 6)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["FULL"]),
                "format": cell_format_from_hex(ERROR, WHITE, True),
            }
        })
        # OPEN = green
        cap_cond_rules.append({
            "ranges": [make_range(dash.id, row_idx, row_idx + 1, 5, 6)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["OPEN"]),
                "format": cell_format_from_hex(SUCCESS, WHITE, True),
            }
        })
    if cap_cond_rules:
        add_cond_format_rules(dash.id, cap_cond_rules)

    log.info("Dashboard complete.")

    # -----------------------------------------------------------------------
    # TAB 2: STUDENT PIPELINE
    # -----------------------------------------------------------------------
    log.info("Building Student Pipeline tab...")
    pipe = spreadsheet.add_worksheet("Student Pipeline", rows=500, cols=22)
    rate_limit()

    # Tab color
    lav_rgb = hex_to_rgb(LAVENDER)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": pipe.id, "tabColor": {"red": lav_rgb[0], "green": lav_rgb[1], "blue": lav_rgb[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    pipe_headers = [
        "Lead ID", "Inquiry Date", "Parent Name", "Child Name", "Age",
        "Pipeline Stage", "Class Interest", "Last Contact Date", "Next Action Date",
        "Contact Method", "Phone", "Email", "Language", "Touch Count",
        "Trial Date", "Trial Result", "Reg. Sent Date", "Enrollment Date",
        "Block Enrolled", "Lead Source", "Notes", "Days in Stage"
    ]
    pipe.update("A1:V1", [pipe_headers], value_input_option="RAW")
    format_cell_range(pipe, "A1:V1", header_fmt())
    rate_limit()

    # Days in Stage formula for rows 2-500
    days_formulas = [[f'=IF(H{r}="","",TODAY()-H{r})'] for r in range(2, 101)]
    pipe.update("V2:V101", days_formulas, value_input_option="USER_ENTERED")
    rate_limit()

    # Column widths
    pipe_widths = {
        0: 70, 1: 100, 2: 150, 3: 130, 4: 55, 5: 130, 6: 130,
        7: 110, 8: 110, 9: 100, 10: 110, 11: 180, 12: 70, 13: 70,
        14: 100, 15: 100, 16: 110, 17: 100, 18: 110, 19: 110, 20: 250, 21: 80
    }
    pw_requests = []
    for col, w in pipe_widths.items():
        pw_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": pipe.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": pw_requests})
    rate_limit()

    set_frozen(pipe, rows=1, cols=1)

    # Data validation dropdowns
    validation_requests = [
        add_dropdown_validation(pipe.id, 1, 500, 5, PIPELINE_STAGES),   # F: Pipeline Stage
        add_dropdown_validation(pipe.id, 1, 500, 6, CLASS_DROPDOWN),     # G: Class Interest
        add_dropdown_validation(pipe.id, 1, 500, 9, CONTACT_METHODS),    # J: Contact Method
        add_dropdown_validation(pipe.id, 1, 500, 12, LANGUAGES),         # M: Language
        add_dropdown_validation(pipe.id, 1, 500, 15, TRIAL_RESULTS),     # P: Trial Result
        add_dropdown_validation(pipe.id, 1, 500, 19, LEAD_SOURCES),      # T: Lead Source
    ]
    spreadsheet.batch_update({"requests": validation_requests})
    rate_limit()

    # Conditional formatting: row color by pipeline stage
    pipe_cond_rules = []
    for stage, bg_hex in STAGE_COLORS.items():
        fg_hex = INDIGO_DARK
        if stage == "Lost":
            fg_hex = "#991B1B"
        elif stage in ("Enrolled", "Active Student", "Re-enrollment"):
            fg_hex = GREEN_MID

        pipe_cond_rules.append({
            "ranges": [make_range(pipe.id, 1, 500, 0, 22)],
            "booleanRule": {
                "condition": {
                    "type": "CUSTOM_FORMULA",
                    "values": [{"userEnteredValue": f'=$F2="{stage}"'}],
                },
                "format": cell_format_from_hex(bg_hex, fg_hex),
            }
        })

    # Days in Stage warnings: >14 red, >7 amber
    pipe_cond_rules.append({
        "ranges": [make_range(pipe.id, 1, 500, 21, 22)],
        "booleanRule": {
            "condition": {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "14"}]},
            "format": cell_format_from_hex(ERROR_LIGHT, ERROR, True),
        }
    })
    pipe_cond_rules.append({
        "ranges": [make_range(pipe.id, 1, 500, 21, 22)],
        "booleanRule": {
            "condition": {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "7"}]},
            "format": cell_format_from_hex(WARNING_LIGHT, WARNING),
        }
    })

    # Next Action Date overdue
    pipe_cond_rules.append({
        "ranges": [make_range(pipe.id, 1, 500, 8, 9)],
        "booleanRule": {
            "condition": {
                "type": "CUSTOM_FORMULA",
                "values": [{"userEnteredValue": '=AND(I2<>"",I2<TODAY())'}],
            },
            "format": cell_format_from_hex(ERROR, WHITE, True),
        }
    })

    add_cond_format_rules(pipe.id, pipe_cond_rules)
    log.info("Student Pipeline complete.")

    # -----------------------------------------------------------------------
    # TAB 3: ACTIVE STUDENTS
    # -----------------------------------------------------------------------
    log.info("Building Active Students tab...")
    students = spreadsheet.add_worksheet("Active Students", rows=500, cols=13)
    rate_limit()

    grn_rgb = hex_to_rgb(SUCCESS)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": students.id, "tabColor": {"red": grn_rgb[0], "green": grn_rgb[1], "blue": grn_rgb[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    stu_headers = [
        "Student ID", "Child Name", "Class", "Age", "Block / Session",
        "Parent Name", "Phone", "Email", "Emergency Contact", "Language",
        "Registered On", "Status", "Months Enrolled"
    ]
    students.update("A1:M1", [stu_headers], value_input_option="RAW")
    format_cell_range(students, "A1:M1", header_fmt())
    rate_limit()

    # Months formula
    months_formulas = [[f'=IF(K{r}="","",DATEDIF(DATEVALUE(TEXT(K{r},"YYYY-MM-DD")),TODAY(),"M"))'] for r in range(2, 101)]
    students.update("M2:M101", months_formulas, value_input_option="USER_ENTERED")
    rate_limit()

    stu_widths = {0: 80, 1: 140, 2: 130, 3: 50, 4: 120, 5: 140, 6: 110, 7: 180, 8: 180, 9: 70, 10: 110, 11: 90, 12: 90}
    sw_requests = []
    for col, w in stu_widths.items():
        sw_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": students.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": sw_requests})
    rate_limit()

    set_frozen(students, rows=1)

    # Data validation
    stu_val_requests = [
        add_dropdown_validation(students.id, 1, 500, 9, LANGUAGES),
        add_dropdown_validation(students.id, 1, 500, 11, STUDENT_STATUSES),
    ]
    spreadsheet.batch_update({"requests": stu_val_requests})
    rate_limit()

    # Conditional formatting: status colors
    stu_cond_rules = [
        {
            "ranges": [make_range(students.id, 1, 500, 11, 12)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["Active"]),
                "format": cell_format_from_hex(SUCCESS_LIGHT, GREEN_MID, True),
            }
        },
        {
            "ranges": [make_range(students.id, 1, 500, 11, 12)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["Cancelled"]),
                "format": cell_format_from_hex(ERROR_LIGHT, ERROR, True),
            }
        },
        {
            "ranges": [make_range(students.id, 1, 500, 11, 12)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["Transferred"]),
                "format": cell_format_from_hex(WARNING_LIGHT, AMBER_DARK),
            }
        },
    ]

    # Class name color coding
    class_colors = {
        "Mommy & Me": ORANGE_LIGHT,
        "Semillas": ECFDF5,
        "Botones de Flor": LAVENDER_LIGHT,
        "Elementary": EFF6FF,
        "Raices": PURPLE_LIGHT,
    }
    for cls_name, bg in class_colors.items():
        stu_cond_rules.append({
            "ranges": [make_range(students.id, 1, 500, 2, 3)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", [cls_name]),
                "format": cell_format_from_hex(bg),
            }
        })

    add_cond_format_rules(students.id, stu_cond_rules)

    # Orange accent on col A
    format_cell_range(students, "A1:A500", CellFormat(
        borders=Borders(left=Border("SOLID_MEDIUM", c(ORANGE))),
    ))
    rate_limit()

    log.info("Active Students complete.")

    # -----------------------------------------------------------------------
    # TAB 4: CLASS SCHEDULE
    # -----------------------------------------------------------------------
    log.info("Building Class Schedule tab...")
    sched = spreadsheet.add_worksheet("Class Schedule", rows=40, cols=12)
    rate_limit()

    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": sched.id, "tabColor": {"red": dash_color[0], "green": dash_color[1], "blue": dash_color[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    # Section 1: Class Type Reference
    sched.merge_cells("A1:H1")
    sched.update("A1", [["CLASS TYPES & CAPACITIES"]], value_input_option="RAW")
    format_cell_range(sched, "A1:H1", section_header_fmt(ORANGE))
    rate_limit()

    sched_headers = ["Class Key", "Class Name (EN)", "Class Name (ES)", "Age Range", "Max Capacity", "Enrolled", "Waitlisted", "Spots Available"]
    sched.update("A2:H2", [sched_headers], value_input_option="RAW")
    format_cell_range(sched, "A2:H2", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=c(INDIGO_DARK)),
        backgroundColor=c(FAFAFA),
    ))
    rate_limit()

    # Seed class type data
    class_data = [
        ["mommy_and_me", "Mommy & Me", "Mami y Yo", "Ages 1.5-3", 12],
        ["semillas", "Semillas", "Semillas", "Ages 3-5", 14],
        ["botones_de_flor", "Botones de Flor", "Botones de Flor", "Ages 6-8", 14],
        ["elementary", "Elementary", "Elemental", "Ages 9-11", 20],
        ["raices", "Raices", "Raices", "High School", 20],
    ]
    if schedule_data:
        class_data = []
        for key, ct in schedule_data.get("class_types", {}).items():
            class_data.append([
                key, ct["name_en"], ct["name_es"],
                ct["age_range_text_en"], ct["max_capacity"]
            ])

    for i, row_data in enumerate(class_data):
        row = 3 + i
        sched.update(f"A{row}:E{row}", [row_data], value_input_option="RAW")
        sched.update(f"F{row}", [[f'=COUNTIFS(\'Active Students\'!C2:C500,B{row},\'Active Students\'!L2:L500,"Active")']], value_input_option="USER_ENTERED")
        sched.update(f"G{row}", [[f'=COUNTIFS(Waitlist!D2:D500,B{row},Waitlist!J2:J500,"Waiting")']], value_input_option="USER_ENTERED")
        sched.update(f"H{row}", [[f"=E{row}-F{row}"]], value_input_option="USER_ENTERED")
    rate_limit()

    # Conditional formatting for Spots Available
    sched_cond_rules = [
        {
            "ranges": [make_range(sched.id, 2, 8, 7, 8)],
            "booleanRule": {
                "condition": {"type": "NUMBER_EQ", "values": [{"userEnteredValue": "0"}]},
                "format": cell_format_from_hex(ERROR, WHITE, True),
            }
        },
        {
            "ranges": [make_range(sched.id, 2, 8, 7, 8)],
            "booleanRule": {
                "condition": {"type": "NUMBER_LESS_THAN_EQ", "values": [{"userEnteredValue": "3"}]},
                "format": cell_format_from_hex(WARNING_LIGHT, AMBER_DARK, True),
            }
        },
        {
            "ranges": [make_range(sched.id, 2, 8, 7, 8)],
            "booleanRule": {
                "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "3"}]},
                "format": cell_format_from_hex(SUCCESS_LIGHT, GREEN_MID),
            }
        },
    ]
    add_cond_format_rules(sched.id, sched_cond_rules)

    # Section 2: Weekly Schedule
    sched.merge_cells("A9:G9")
    sched.update("A9", [["WEEKLY CLASS SCHEDULE"]], value_input_option="RAW")
    format_cell_range(sched, "A9:G9", section_header_fmt(LAVENDER_DARK))
    rate_limit()

    sched_col_headers = ["Day", "Start", "End", "Class (EN)", "Class (ES)", "Class Key", "Notes"]
    sched.update("A10:G10", [sched_col_headers], value_input_option="RAW")
    format_cell_range(sched, "A10:G10", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=c(INDIGO_DARK)),
        backgroundColor=c(FAFAFA),
    ))
    rate_limit()

    # Seed schedule slots
    if schedule_data:
        slot_rows = []
        class_types = schedule_data.get("class_types", {})
        for slot in schedule_data.get("slots", []):
            ct = class_types.get(slot["class"], {})
            slot_rows.append([
                slot["day"].capitalize(),
                slot["start"],
                slot["end"],
                ct.get("name_en", slot["class"]),
                ct.get("name_es", slot["class"]),
                slot["class"],
                "",
            ])
        if slot_rows:
            end_row = 11 + len(slot_rows) - 1
            sched.update(f"A11:G{end_row}", slot_rows, value_input_option="RAW")
    rate_limit()

    # Section 3: Block Info (right sidebar)
    sched.merge_cells("I1:L1")
    sched.update("I1", [["ACTIVE BLOCK INFO"]], value_input_option="RAW")
    format_cell_range(sched, "I1:L1", section_header_fmt(INDIGO_DARK))

    block_labels = [
        ["Block Name", ""],
        ["Start Date", ""],
        ["End Date", ""],
        ["Days Remaining", "=IF(L4=\"\",\"\",MAX(0,L4-TODAY()))"],
    ]
    if schedule_data and "block" in schedule_data:
        block_labels[0][1] = schedule_data["block"]["name"]
        block_labels[1][1] = schedule_data["block"]["start_date"]
        block_labels[2][1] = schedule_data["block"]["end_date"]
        block_labels[3][1] = f'=MAX(0,DATEVALUE("{schedule_data["block"]["end_date"]}")-TODAY())'

    for i, (label, val) in enumerate(block_labels):
        row = 2 + i
        sched.update(f"I{row}", [[label]], value_input_option="RAW")
        input_opt = "USER_ENTERED" if str(val).startswith("=") else "RAW"
        sched.update(f"L{row}", [[val]], value_input_option=input_opt)
    format_cell_range(sched, "I2:I5", label_fmt())
    format_cell_range(sched, "L2:L5", value_fmt())
    rate_limit()

    # Column widths
    sched_w = {0: 90, 1: 130, 2: 130, 3: 80, 4: 80, 5: 140, 6: 140, 7: 100, 8: 120, 9: 30, 10: 30, 11: 120}
    sw2_requests = []
    for col, w in sched_w.items():
        sw2_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sched.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": sw2_requests})
    rate_limit()

    set_frozen(sched, rows=2)
    log.info("Class Schedule complete.")

    # -----------------------------------------------------------------------
    # TAB 5: WAITLIST
    # -----------------------------------------------------------------------
    log.info("Building Waitlist tab...")
    wl = spreadsheet.add_worksheet("Waitlist", rows=200, cols=13)
    rate_limit()

    purp_rgb = hex_to_rgb(LAVENDER_DARK)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": wl.id, "tabColor": {"red": purp_rgb[0], "green": purp_rgb[1], "blue": purp_rgb[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    wl_headers = [
        "Waitlist ID", "Child Name", "Parent Name", "Class", "Age",
        "Phone", "Email", "Language", "Waitlisted Since", "Claim Status",
        "Spot Offered At", "Claim Deadline", "Hours Remaining"
    ]
    wl.update("A1:M1", [wl_headers], value_input_option="RAW")
    format_cell_range(wl, "A1:M1", header_fmt(LAVENDER_DARK))
    rate_limit()

    # Claim deadline + hours remaining formulas
    for r in range(2, 101):
        wl.update(f"L{r}", [[f'=IF(K{r}="","",K{r}+2)']], value_input_option="USER_ENTERED")
        wl.update(f"M{r}", [[f'=IF(OR(K{r}="",J{r}="Claimed",J{r}="Expired",J{r}="Withdrew"),"",MAX(0,(L{r}-NOW())*24))']], value_input_option="USER_ENTERED")
    rate_limit()

    format_cell_range(wl, "M2:M200", CellFormat(
        numberFormat=NumberFormat(type="NUMBER", pattern="0.0"),
    ))

    wl_widths = {0: 80, 1: 140, 2: 140, 3: 130, 4: 50, 5: 110, 6: 180, 7: 70, 8: 120, 9: 110, 10: 120, 11: 120, 12: 90}
    ww_requests = []
    for col, w in wl_widths.items():
        ww_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": wl.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": ww_requests})
    rate_limit()

    set_frozen(wl, rows=1)

    wl_val_requests = [
        add_dropdown_validation(wl.id, 1, 200, 3, CLASS_DROPDOWN[:5]),
        add_dropdown_validation(wl.id, 1, 200, 7, LANGUAGES),
        add_dropdown_validation(wl.id, 1, 200, 9, WAITLIST_STATUSES),
    ]
    spreadsheet.batch_update({"requests": wl_val_requests})
    rate_limit()

    # Conditional formatting
    wl_cond_rules = []
    wl_status_colors = {
        "Waiting": (LAVENDER_LIGHT, LAVENDER_DARK),
        "Spot Offered": (WARNING_LIGHT, AMBER_DARK),
        "Claimed": (SUCCESS_LIGHT, GREEN_MID),
        "Expired": (GRAY_LIGHT, GRAY),
        "Withdrew": (ERROR_LIGHT, ERROR),
    }
    for status, (bg, fg) in wl_status_colors.items():
        wl_cond_rules.append({
            "ranges": [make_range(wl.id, 1, 200, 9, 10)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", [status]),
                "format": cell_format_from_hex(bg, fg, True),
            }
        })

    # Hours remaining urgency
    wl_cond_rules.append({
        "ranges": [make_range(wl.id, 1, 200, 12, 13)],
        "booleanRule": {
            "condition": {
                "type": "CUSTOM_FORMULA",
                "values": [{"userEnteredValue": '=AND(M2<>"",M2<24,M2>0)'}],
            },
            "format": cell_format_from_hex(ERROR, WHITE, True),
        }
    })
    wl_cond_rules.append({
        "ranges": [make_range(wl.id, 1, 200, 12, 13)],
        "booleanRule": {
            "condition": {
                "type": "CUSTOM_FORMULA",
                "values": [{"userEnteredValue": '=AND(M2<>"",M2>=24,M2<=48)'}],
            },
            "format": cell_format_from_hex(WARNING_LIGHT, AMBER_DARK),
        }
    })

    # Spot Offered row highlight
    wl_cond_rules.append({
        "ranges": [make_range(wl.id, 1, 200, 0, 13)],
        "booleanRule": {
            "condition": {
                "type": "CUSTOM_FORMULA",
                "values": [{"userEnteredValue": '=$J2="Spot Offered"'}],
            },
            "format": cell_format_from_hex(FFFBEB),
        }
    })

    add_cond_format_rules(wl.id, wl_cond_rules)
    log.info("Waitlist complete.")

    # -----------------------------------------------------------------------
    # TAB 6: RENTAL BOOKINGS
    # -----------------------------------------------------------------------
    log.info("Building Rental Bookings tab...")
    rental = spreadsheet.add_worksheet("Rental Bookings", rows=300, cols=14)
    rate_limit()

    amber_rgb = hex_to_rgb(AMBER)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": rental.id, "tabColor": {"red": amber_rgb[0], "green": amber_rgb[1], "blue": amber_rgb[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    rental_headers = [
        "Booking ID", "Date", "Start Time", "End Time", "Hours",
        "Renter Name", "Phone", "Email", "Purpose", "Rate/Hr",
        "Total", "Status", "Language", "Booked On"
    ]
    rental.update("A1:N1", [rental_headers], value_input_option="RAW")
    format_cell_range(rental, "A1:N1", header_fmt(ORANGE_DARK))
    rate_limit()

    # Rate + Total formulas
    for r in range(2, 201):
        rental.update(f"J{r}", [[f'=IF(E{r}="","",IF(E{r}>=4,60,75))']], value_input_option="USER_ENTERED")
        rental.update(f"K{r}", [[f'=IF(E{r}="","",E{r}*J{r})']], value_input_option="USER_ENTERED")
    rate_limit()

    format_cell_range(rental, "J2:J200", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
    ))
    format_cell_range(rental, "K2:K200", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
        textFormat=TextFormat(bold=True),
    ))
    rate_limit()

    rental_widths = {0: 80, 1: 100, 2: 90, 3: 90, 4: 60, 5: 150, 6: 110, 7: 170, 8: 180, 9: 70, 10: 80, 11: 100, 12: 70, 13: 110}
    rw_requests = []
    for col, w in rental_widths.items():
        rw_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": rental.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": rw_requests})
    rate_limit()

    set_frozen(rental, rows=1)

    rental_val_requests = [
        add_dropdown_validation(rental.id, 1, 300, 11, RENTAL_STATUSES),
        add_dropdown_validation(rental.id, 1, 300, 12, LANGUAGES),
    ]
    spreadsheet.batch_update({"requests": rental_val_requests})
    rate_limit()

    # Conditional formatting
    rental_cond_rules = []
    rental_status_colors = {
        "Confirmed": (SUCCESS_LIGHT, GREEN_MID),
        "Cancelled": (ERROR_LIGHT, ERROR),
        "Completed": (GRAY_LIGHT, GRAY),
        "Pending": (WARNING_LIGHT, AMBER_DARK),
    }
    for status, (bg, fg) in rental_status_colors.items():
        rental_cond_rules.append({
            "ranges": [make_range(rental.id, 1, 300, 11, 12)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", [status]),
                "format": cell_format_from_hex(bg, fg, True),
            }
        })
    add_cond_format_rules(rental.id, rental_cond_rules)

    # Summary row
    summary_row = 202
    rental.update(f"I{summary_row}", [["SUMMARY"]], value_input_option="RAW")
    rental.update(f"J{summary_row}", [["Confirmed Revenue:"]], value_input_option="RAW")
    rental.update(f"K{summary_row}", [[f'=SUMIF(L2:L200,"Confirmed",K2:K200)']], value_input_option="USER_ENTERED")
    rental.update(f"J{summary_row+1}", [["Confirmed Bookings:"]], value_input_option="RAW")
    rental.update(f"K{summary_row+1}", [[f'=COUNTIF(L2:L200,"Confirmed")']], value_input_option="USER_ENTERED")
    rental.update(f"J{summary_row+2}", [["This Month:"]], value_input_option="RAW")
    rental.update(f"K{summary_row+2}", [[f'=SUMIFS(K2:K200,B2:B200,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1),L2:L200,"Confirmed")']], value_input_option="USER_ENTERED")
    format_cell_range(rental, f"I{summary_row}:K{summary_row+2}", CellFormat(
        textFormat=TextFormat(bold=True, foregroundColor=c(INDIGO_DARK)),
    ))
    format_cell_range(rental, f"K{summary_row}:K{summary_row+2}", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
        textFormat=TextFormat(bold=True, foregroundColor=c(SUCCESS)),
    ))
    rate_limit()

    log.info("Rental Bookings complete.")

    # -----------------------------------------------------------------------
    # TAB 7: COMMUNICATIONS LOG
    # -----------------------------------------------------------------------
    log.info("Building Communications Log tab...")
    comm = spreadsheet.add_worksheet("Communications Log", rows=500, cols=18)
    rate_limit()

    blue_rgb = hex_to_rgb(BLUE)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": comm.id, "tabColor": {"red": blue_rgb[0], "green": blue_rgb[1], "blue": blue_rgb[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    comm_headers = [
        "Log ID", "Date / Time", "Contact Name", "Child Name",
        "Pipeline Stage", "Touch #", "Channel", "Direction",
        "Summary", "Response?", "Next Action", "Next Action Date"
    ]
    comm.update("A1:L1", [comm_headers], value_input_option="RAW")
    format_cell_range(comm, "A1:L1", header_fmt(BLUE_DARK))
    rate_limit()

    # Auto-increment Log ID
    log_id_formulas = [[f'=IF(C{r}="","",ROW()-1)'] for r in range(2, 101)]
    comm.update("A2:A101", log_id_formulas, value_input_option="USER_ENTERED")
    rate_limit()

    comm_widths = {0: 60, 1: 120, 2: 150, 3: 130, 4: 130, 5: 70, 6: 100, 7: 90, 8: 250, 9: 80, 10: 150, 11: 110}
    cw_requests = []
    for col, w in comm_widths.items():
        cw_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": comm.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": cw_requests})
    rate_limit()

    set_frozen(comm, rows=1)

    comm_val_requests = [
        add_dropdown_validation(comm.id, 1, 500, 4, PIPELINE_STAGES),
        add_dropdown_validation(comm.id, 1, 500, 5, TOUCH_NUMBERS),
        add_dropdown_validation(comm.id, 1, 500, 6, COMM_CHANNELS),
        add_dropdown_validation(comm.id, 1, 500, 7, COMM_DIRECTIONS),
        add_dropdown_validation(comm.id, 1, 500, 9, COMM_RESPONSES),
    ]
    spreadsheet.batch_update({"requests": comm_val_requests})
    rate_limit()

    # 4-Touch Reference sidebar
    comm.merge_cells("N1:Q1")
    comm.update("N1", [["4-TOUCH FOLLOW-UP GUIDE"]], value_input_option="RAW")
    format_cell_range(comm, "N1:Q1", section_header_fmt(LAVENDER_DARK))

    touch_ref = [
        ["Touch", "Timing", "Channel", "Goal"],
        ["1", "Same day / 1 day", "Email or Phone", "Warm welcome + class info"],
        ["2", "Day 3-5", "Alt. channel", "Trial class invitation"],
        ["3", "Day 7-10", "Original channel", "Registration reminder"],
        ["4", "Day 14", "Final", "Last chance + waitlist offer"],
        ["Nurture", "Monthly", "Email", "Class news + upcoming block"],
    ]
    comm.update("N2:Q7", touch_ref, value_input_option="RAW")
    format_cell_range(comm, "N2:Q2", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=c(INDIGO_DARK)),
        backgroundColor=c(FAFAFA),
    ))
    format_cell_range(comm, "N3:Q7", CellFormat(
        textFormat=TextFormat(fontSize=9, foregroundColor=c(GRAY)),
    ))
    rate_limit()

    # Conditional formatting
    comm_cond_rules = [
        # Direction: Inbound = green
        {
            "ranges": [make_range(comm.id, 1, 500, 7, 8)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["Inbound"]),
                "format": cell_format_from_hex(SUCCESS_LIGHT, GREEN_MID),
            }
        },
        # Direction: Outbound = blue
        {
            "ranges": [make_range(comm.id, 1, 500, 7, 8)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["Outbound"]),
                "format": cell_format_from_hex(BLUE_LIGHT),
            }
        },
        # Response Yes = green
        {
            "ranges": [make_range(comm.id, 1, 500, 9, 10)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["Yes"]),
                "format": cell_format_from_hex(SUCCESS_LIGHT, GREEN_MID, True),
            }
        },
        # Response No = amber
        {
            "ranges": [make_range(comm.id, 1, 500, 9, 10)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["No"]),
                "format": cell_format_from_hex(WARNING_LIGHT, AMBER_DARK),
            }
        },
        # Next Action Date overdue
        {
            "ranges": [make_range(comm.id, 1, 500, 11, 12)],
            "booleanRule": {
                "condition": {
                    "type": "CUSTOM_FORMULA",
                    "values": [{"userEnteredValue": '=AND(L2<>"",L2<TODAY())'}],
                },
                "format": cell_format_from_hex(ERROR, WHITE, True),
            }
        },
        # Touch 4 = red tint
        {
            "ranges": [make_range(comm.id, 1, 500, 5, 6)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", ["4"]),
                "format": cell_format_from_hex(ERROR_LIGHT),
            }
        },
    ]
    add_cond_format_rules(comm.id, comm_cond_rules)
    log.info("Communications Log complete.")

    # -----------------------------------------------------------------------
    # TAB 8: REVENUE & PAYMENTS
    # -----------------------------------------------------------------------
    log.info("Building Revenue & Payments tab...")
    rev = spreadsheet.add_worksheet("Revenue & Payments", rows=500, cols=14)
    rate_limit()

    grn2_rgb = hex_to_rgb(GREEN_MID)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": rev.id, "tabColor": {"red": grn2_rgb[0], "green": grn2_rgb[1], "blue": grn2_rgb[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    rev_headers = [
        "Record ID", "Student / Renter", "Type", "Due Date",
        "Class / Service", "Block / Period", "Amount", "Payment Status",
        "Paid Date", "Payment Method", "Notes"
    ]
    rev.update("A1:K1", [rev_headers], value_input_option="RAW")
    format_cell_range(rev, "A1:K1", header_fmt(GREEN_DARK))
    rate_limit()

    format_cell_range(rev, "G2:G500", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
    ))
    rate_limit()

    rev_widths = {0: 80, 1: 160, 2: 80, 3: 100, 4: 150, 5: 120, 6: 90, 7: 110, 8: 100, 9: 110, 10: 200}
    rv_requests = []
    for col, w in rev_widths.items():
        rv_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": rev.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": rv_requests})
    rate_limit()

    set_frozen(rev, rows=1)

    rev_val_requests = [
        add_dropdown_validation(rev.id, 1, 500, 2, REVENUE_TYPES),
        add_dropdown_validation(rev.id, 1, 500, 7, PAYMENT_STATUSES),
        add_dropdown_validation(rev.id, 1, 500, 9, PAYMENT_METHODS),
    ]
    spreadsheet.batch_update({"requests": rev_val_requests})
    rate_limit()

    # Revenue summary sidebar
    rev.merge_cells("M1:N1")
    rev.update("M1", [["REVENUE SUMMARY"]], value_input_option="RAW")
    format_cell_range(rev, "M1:N1", section_header_fmt(ORANGE))

    rev_summary = [
        ["Total Collected", '=SUMIF(H2:H500,"Paid",G2:G500)'],
        ["Outstanding", '=SUMIF(H2:H500,"Unpaid",G2:G500)'],
        ["Tuition Collected", '=SUMIFS(G2:G500,C2:C500,"Tuition",H2:H500,"Paid")'],
        ["Rental Collected", '=SUMIFS(G2:G500,C2:C500,"Rental",H2:H500,"Paid")'],
        ["This Month", '=SUMIFS(G2:G500,H2:H500,"Paid",I2:I500,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1))'],
        ["Unpaid >7 days", '=COUNTIFS(H2:H500,"Unpaid",D2:D500,"<"&TODAY()-7,D2:D500,"<>"&"")'],
        ["Collection Rate", '=IFERROR(SUMIF(H2:H500,"Paid",G2:G500)/SUM(G2:G500),0)'],
    ]
    for i, (label, formula) in enumerate(rev_summary):
        row = 2 + i
        rev.update(f"M{row}", [[label]], value_input_option="RAW")
        rev.update(f"N{row}", [[formula]], value_input_option="USER_ENTERED")
    format_cell_range(rev, "M2:M8", label_fmt())
    format_cell_range(rev, "N2:N6", CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="$#,##0"),
        textFormat=TextFormat(bold=True, foregroundColor=c(SUCCESS)),
    ))
    format_cell_range(rev, "N8", CellFormat(
        numberFormat=NumberFormat(type="PERCENT", pattern="0.0%"),
        textFormat=TextFormat(bold=True, foregroundColor=c(SUCCESS)),
    ))
    rate_limit()

    # Conditional formatting
    rev_cond_rules = []
    rev_pay_colors = {
        "Paid": (SUCCESS_LIGHT, GREEN_MID),
        "Unpaid": (ERROR_LIGHT, ERROR),
        "Partial": (WARNING_LIGHT, AMBER_DARK),
        "Waived": (LAVENDER_LIGHT, GRAY),
        "Refunded": (ERROR_LIGHT, GRAY),
    }
    for status, (bg, fg) in rev_pay_colors.items():
        rev_cond_rules.append({
            "ranges": [make_range(rev.id, 1, 500, 7, 8)],
            "booleanRule": {
                "condition": bool_condition("TEXT_EQ", [status]),
                "format": cell_format_from_hex(bg, fg, True),
            }
        })

    # Overdue unpaid row highlight
    rev_cond_rules.append({
        "ranges": [make_range(rev.id, 1, 500, 0, 11)],
        "booleanRule": {
            "condition": {
                "type": "CUSTOM_FORMULA",
                "values": [{"userEnteredValue": '=AND($H2="Unpaid",$D2<>"",($D2<TODAY()-7))'}],
            },
            "format": cell_format_from_hex(ERROR_LIGHT),
        }
    })

    add_cond_format_rules(rev.id, rev_cond_rules)
    log.info("Revenue & Payments complete.")

    # -----------------------------------------------------------------------
    # TAB 9: SETTINGS
    # -----------------------------------------------------------------------
    log.info("Building Settings tab...")
    settings = spreadsheet.add_worksheet("Settings", rows=50, cols=6)
    rate_limit()

    gray_rgb = hex_to_rgb(GRAY)
    spreadsheet.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": settings.id, "tabColor": {"red": gray_rgb[0], "green": gray_rgb[1], "blue": gray_rgb[2]}},
            "fields": "tabColor",
        }
    }]})
    rate_limit()

    # Section 1: Class Types
    settings.merge_cells("A1:F1")
    settings.update("A1", [["GARCIA FOLKLORICO STUDIO - CRM SETTINGS"]], value_input_option="RAW")
    format_cell_range(settings, "A1:F1", header_fmt("#374151", 14))
    rate_limit()

    settings.merge_cells("A3:F3")
    settings.update("A3", [["CLASS TYPES"]], value_input_option="RAW")
    format_cell_range(settings, "A3:F3", section_header_fmt(ORANGE))

    ct_headers = ["Class Key", "Class Name (EN)", "Class Name (ES)", "Age Range", "Max Capacity", "Block Fee ($)"]
    settings.update("A4:F4", [ct_headers], value_input_option="RAW")
    format_cell_range(settings, "A4:F4", CellFormat(
        textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=c(INDIGO_DARK)),
        backgroundColor=c(FAFAFA),
    ))
    rate_limit()

    # Seed class data
    ct_rows = [
        ["mommy_and_me", "Mommy & Me", "Mami y Yo", "Ages 1.5-3", 12, 120],
        ["semillas", "Semillas", "Semillas", "Ages 3-5", 14, 120],
        ["botones_de_flor", "Botones de Flor", "Botones de Flor", "Ages 6-8", 14, 140],
        ["elementary", "Elementary", "Elemental", "Ages 9-11", 20, 150],
        ["raices", "Raices", "Raices", "High School", 20, 160],
    ]
    if schedule_data:
        ct_rows = []
        for key, ct in schedule_data.get("class_types", {}).items():
            ct_rows.append([
                key, ct["name_en"], ct["name_es"],
                ct["age_range_text_en"], ct["max_capacity"], ""
            ])

    settings.update("A5:F9", ct_rows, value_input_option="RAW")
    rate_limit()

    # Section 2: Rental Pricing
    settings.merge_cells("A11:C11")
    settings.update("A11", [["RENTAL PRICING"]], value_input_option="RAW")
    format_cell_range(settings, "A11:C11", section_header_fmt(LAVENDER_DARK))

    rental_config = [
        ["Standard Rate (1-3 hrs)", "$75/hr"],
        ["Discount Rate (4-6 hrs)", "$60/hr"],
        ["Discount Threshold", "4 hours"],
        ["Min Hours", "1"],
        ["Max Hours", "6"],
        ["Studio Open", "8:00 AM"],
        ["Studio Close", "10:00 PM"],
    ]
    for i, (label, val) in enumerate(rental_config):
        row = 12 + i
        settings.update(f"A{row}", [[label]], value_input_option="RAW")
        settings.update(f"C{row}", [[val]], value_input_option="RAW")
    format_cell_range(settings, "A12:A18", label_fmt())
    format_cell_range(settings, "C12:C18", value_fmt())
    rate_limit()

    # Section 3: Waitlist Config
    settings.merge_cells("A20:C20")
    settings.update("A20", [["WAITLIST SETTINGS"]], value_input_option="RAW")
    format_cell_range(settings, "A20:C20", section_header_fmt(LAVENDER_DARK))

    wl_config = [
        ["Claim Window", "48 hours"],
        ["Reminder At", "24 hours"],
        ["Auto-expire", "Yes"],
    ]
    for i, (label, val) in enumerate(wl_config):
        row = 21 + i
        settings.update(f"A{row}", [[label]], value_input_option="RAW")
        settings.update(f"C{row}", [[val]], value_input_option="RAW")
    format_cell_range(settings, "A21:A23", label_fmt())
    format_cell_range(settings, "C21:C23", value_fmt())
    rate_limit()

    # Section 4: Studio Info
    settings.merge_cells("A25:C25")
    settings.update("A25", [["STUDIO INFO"]], value_input_option="RAW")
    format_cell_range(settings, "A25:C25", section_header_fmt(INDIGO_DARK))

    studio_info = [
        ["Studio Name", "Garcia Folklorico Studio"],
        ["Tagline", "La Casa del Folklor"],
        ["City", "Oxnard, CA"],
        ["Contact Email", ""],
        ["Contact Phone", ""],
        ["Website", ""],
        ["Instagram", ""],
        ["Managed By", "WestCoast Automation Solutions"],
    ]
    for i, (label, val) in enumerate(studio_info):
        row = 26 + i
        settings.update(f"A{row}", [[label]], value_input_option="RAW")
        settings.update(f"C{row}", [[val]], value_input_option="RAW")
    format_cell_range(settings, "A26:A33", label_fmt())
    format_cell_range(settings, "C26:C33", CellFormat(
        textFormat=TextFormat(fontSize=10, foregroundColor=c(INDIGO_DARK)),
    ))
    rate_limit()

    # Section 5: Pipeline Stage Color Legend
    settings.merge_cells("A35:C35")
    settings.update("A35", [["PIPELINE STAGE COLOR KEY"]], value_input_option="RAW")
    format_cell_range(settings, "A35:C35", section_header_fmt(INDIGO_DARK))

    for i, (stage, color) in enumerate(STAGE_COLORS.items()):
        row = 36 + i
        settings.update(f"A{row}", [[stage]], value_input_option="RAW")
        settings.update(f"B{row}", [[color]], value_input_option="RAW")
        format_cell_range(settings, f"C{row}", CellFormat(backgroundColor=c(color)))
    rate_limit()

    # Column widths
    settings_w = {0: 180, 1: 160, 2: 160, 3: 120, 4: 100, 5: 100}
    stw_requests = []
    for col, w in settings_w.items():
        stw_requests.append({"updateDimensionProperties": {
            "range": {"sheetId": settings.id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"
        }})
    spreadsheet.batch_update({"requests": stw_requests})
    rate_limit()

    set_frozen(settings, rows=1)

    # Add note to settings header
    settings.update("A2", [["Settings are referenced by Dashboard formulas. Do not rename column headers."]], value_input_option="RAW")
    format_cell_range(settings, "A2", CellFormat(
        textFormat=TextFormat(italic=True, fontSize=9, foregroundColor=c(GRAY)),
    ))
    rate_limit()

    log.info("Settings complete.")

    # -----------------------------------------------------------------------
    # FINAL: Save sheet ID and print URL
    # -----------------------------------------------------------------------
    sheet_id = spreadsheet.id
    sheet_url = spreadsheet.url

    # Save sheet ID for run_sync.py to use
    env_path = Path(__file__).resolve().parent.parent.parent / "backend" / ".env"
    if env_path.exists():
        env_content = env_path.read_text()
        if "GOOGLE_SHEET_ID=" not in env_content or "GOOGLE_SHEET_ID=\n" in env_content or "GOOGLE_SHEET_ID=" in env_content and env_content.split("GOOGLE_SHEET_ID=")[1].split("\n")[0].strip() == "":
            log.info(f"Sheet ID to add to .env: GOOGLE_SHEET_ID={sheet_id}")
        else:
            log.info(f"GOOGLE_SHEET_ID already set in .env")

    print("\n" + "=" * 60)
    print("  Garcia Folklorico Studio - CRM Created Successfully!")
    print("=" * 60)
    print(f"\n  Spreadsheet URL: {sheet_url}")
    print(f"  Sheet ID: {sheet_id}")
    print(f"\n  Shared with: {share_email}")
    if itzel_email:
        print(f"  Shared with: {itzel_email}")
    print(f"\n  Add to .env: GOOGLE_SHEET_ID={sheet_id}")
    print("=" * 60 + "\n")

    return sheet_id


if __name__ == "__main__":
    build_crm()
