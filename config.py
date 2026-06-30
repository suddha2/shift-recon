# config.py
# Configuration file for workforce allocation rules
# Edit these dictionaries to modify business rules

# ============================================
# SHIFT TYPE LIMITS
# ============================================
# Maximum occurrences of each shift type per employee per week (Monday-Sunday)
# Add or modify shift types as needed
SHIFT_TYPE_LIMITS = {
    ("Day Shift","Hourly"):{"operator": "<=", "value": 15}, 
    ("Floating Shift","Hourly"):{"operator": "<", "value": 6}, 
    ("L - Day Shift","Fixed"):{"operator": "<=", "value": 15},  
    ("Sleep In Shift","Fixed"):{"operator": "<=", "value": 12}, 
    ("Waking Night Shift","Hourly"):{"operator": "<=", "value": 12},
    ("Care Call Shift","Hourly"):{"operator": "<=", "value": 14},
    ("Day Support","Zero"):{"operator": "<=", "value": 15}, 
    ("Floating Support","Zero"):{"operator": "<=", "value": 4}, 
    ("Sleep In Support","Zero"):{"operator": "<=", "value": 12}, 
    ("Waking Night Support","Zero"):{"operator": "<=", "value": 12},
    ("Ad hoc Shift","Fixed"):{"operator": ">=", "value": 6}, 
    ("Ad hoc Shift","Hourly"):{"operator": "<", "value": 6}, 
    ("Driver Shift","Hourly"):{"operator": "<=", "value": 4}, 
    ("On Call Shift","Fixed"):{"operator": "<=", "value": 12}, 
    ("Shift Lead - Shift","Fixed"):{"operator": "<=", "value": 8}, 
    ("Training","Hourly"):{"operator": "<=", "value": 8},  
    ("Shadow","Hourly"):{"operator": "<=", "value": 6},  
    ("Paid Sleep In ","Fixed"):{"operator": "<=", "value": 10}, 
    # Add more shift types here as: "Shift Type Name": max_count
}

# ============================================
# EMPLOYEE HOUR LIMITS
# ============================================
# Maximum hours per employee per week (Monday-Sunday)
# Use None for employees who have opted out of hour limits
EMPLOYEE_HOUR_LIMITS = {
    
    # Add more employees here as: "Employee Name": max_hours or None
}

# Default hour limit for employees not specified above
DEFAULT_HOUR_LIMIT = -1

# ============================================
# ALLOWED COMBINATIONS (WHITELIST)
# ============================================
# Only these combinations of (Service Type, Requirement Type) are allowed
# Any combination NOT in this list will be flagged as invalid
ALLOWED_COMBINATIONS = [


("Day Shift","Long Day"), 
("Floating Shift","Cover"), 
("L - Day Shift","L - Shift"),  
("Sleep In Shift","Sleep In"), 
("Waking Night Shift","Waking Nights"),
("Care Call Shift","1. AM Call"),
("Care Call Shift","2. Lunch Call"),
("Care Call Shift","3. Tea Call"),
("Care Call Shift","4. PM Call"),
("Care Call Shift","Community Care Call"),
("Day Support","Day Support"), 
("Floating Support","Cover"), 
("Sleep In Support","Sleep In"), 
("Waking Night Support","Waking Nights"),
("Ad hoc Shift","Duties"), 
("Driver Shift","Duties"), 
("On Call Shift","On Call"), 
("On Call Shift","Day Support"),
("Shift Lead - Shift","Day Support"), 
("Training","Training"),
("Shadow","Shadow"),
("Paid Sleep In","Sleep In"),
("Services Coordinator Shift","Day Support"),
("Prelim Day Shift","Day Shift"),
("Prelim Floating Shift","Cover"),
("Prelim Waking Night Shift","Waking Night"),
("Prelim Waking Night Shift", "Waking Nights"),
("Prelim Day Shift","Long Day"),
("Complex Waking Night","Waking Night"),
("Complex Waking Night","Waking Nights"),
("Complex Day Shift","Long Day"),
("Complex Floating","Shift Cover"),
("Senior Carer Day Shift","Long Day"),

   # Add more allowed combinations here as: ("Service Type", "Requirement Type")
]


# Shift types that can be assigned more than once per day
MULTIPLE_SHIFT_ALLOWED = {
    "Floating Shift": True,
    "Care Call Shift": True,
    "L - Day Shift": False,
    "Day Shift": False,
    "Night Shift": False,
    "Waking Night Shift": False,
}

# Valid combinations of shift types per day
#ALLOWED_DAILY_COMBINATIONS = [
#    {"Type 1", "Type 2", "Type 3"),
#    {"Day Shift"),
#    {"Night Shift"),
#]
RATE_CARD_MAP={
("Zero Hour Pay Rates (SL)"):13.85,
("Level 1- Mnchetr/Ptrbrgh","Hourly"):12.82,
("Level 2- Mnchetr/Ptrbrgh","Hourly"):12.92,
("Level 3- Mnchetr/Ptrbrgh","Hourly"):13.02,
("Level 1 - Central Beds, Beds, Bucks, Gloce","Hourly"):12.93,
("Level 2 - Central Beds, Beds, Bucks, Gloce","Hourly"):13.02,
("Level 3 - Central Beds, Beds, Bucks, Gloce","Hourly"):13.12,
("Level 1 - Oxford,Herts,Kent and Cormwall","Hourly"):13.09,
("Level 2 - Oxford,Herts,Kent and Cormwall","Hourly"):13.19,
("Level 3 - Oxford, Herts, Kent, Cormwall","Hourly"):13.29,
("Level 1 - Barnet","Hourly"):13.39,
("Level 2 - Barnet","Hourly"):13.49,
("Level 3 - Barnet","Hourly"):13.59,
("Home Care","Hourly"):16.35,
("Live In Shift per day","Fixed"):137.00,
("Sleep In Shift","Hourly"):30.00,
("Ad hoc shift","Fixed"):161.00,
("Ad hoc shift","Hourly"):13.42,
("Live In Shift per week for all staff","Fixed"):1169.00,

}

# ============================================
# EMPLOYEE / VISA DATA SYNC
# ============================================
# External endpoint that returns the full employee dump as CSV.
# Synced (visa table wiped and reloaded) before every analysis run.
APP_EMP_URL = "https://b0e2b809ef774776889ef4cbd166c019.dataengine.accessacloud.com/ds/6WNIjfr8c8LBLdA"
APP_EMP_AUTH = "7eef61f9-519e-444e-8e4d-e215d05aa356"  # sent as the Authorization header
APP_EMP_TIMEOUT = 30  # seconds

# Columns in the employee feed CSV.
# Visa status is taken from the part of EMP_TYPE_COL after the first ' - '
# e.g. "Support Worker - Skilled Worker Visa" -> "Skilled Worker Visa".
APP_EMP_NAME_COL = "EE.FullName"
APP_EMP_TYPE_COL = "EE.EmployeeType"

# Visa status -> weekly working hour rules (Monday-Sunday).
# Same operator/value shape as SHIFT_TYPE_LIMITS.
# Keys must match the visa portion of EE.EmployeeType exactly.
# IMPORTANT: verify these hour caps against current UK right-to-work rules.
VISA_HOUR_RULES = {
    "Student Visa":                 {"operator": "<=", "value": 20},
    "Supplementary Worker":         {"operator": "<=", "value": 20},
    "Skilled Worker Visa":          {"operator": ">=", "value": 37.5},
    # "Graduate Visa":                {"operator": ">=", "value": 37.5},
    # "Dependent Visa":               {"operator": ">=", "value": 37.5},
    # "UK National":                  {"operator": ">=", "value": 37.5},
    # "EU Settlement status":         {"operator": ">=", "value": 37.5},
    # "Leave to Remain Indefinitely": {"operator": ">=", "value": 37.5},
    # "International Visa Migrant":   {"operator": ">=", "value": 37.5},
    # Add more visa statuses here as: "Visa Status": {"operator": "<=", "value": hours}
}

# Service types whose hours count toward the weekly visa-hour totals.
# Match is exact but case-insensitive and whitespace-tolerant, so
# "Paid Sleep In " or "ad hoc shift" still match. Any service type NOT
# listed here is excluded from the visa hours sum:
#   - Support / Shadow (no "Shift" suffix) - duplicate booking of the same actual work
#   - Sleep In Shift / Sleep In Support - unpaid overnight cover
#   - anything else not enumerated below
# Add or remove entries here when policy or shift-naming changes.
VISA_HOUR_ELIGIBLE_SHIFT_TYPES = (
    "Care Call Shift",
    "Floating Shift",
    "Waking Night Shift",
    "L - Day Shift",
    "Day Shift",
    "Shadow Shift",
    "Training",
    "Complex Day Shift",
    "Complex Floating Shift",
    "Paid Sleep In",
    "Prelim Waking Night Shift",
    "Complex Waking Night",
    "Ad Hoc Shift",
    "Community Care Call",
    "Driver Shift",
    "Prelim Day Shift",
    "Prelim Floating Shift",
    "On Call Shift",
)

# ============================================
# PEOPLE HR API
# ============================================
# Used to enrich below-minimum visa hour violations with holiday/absence
# context, so the operator can see whether a weekly shortfall is explained
# by approved leave.
PEOPLE_HR_BASE_URL = "https://api.peoplehr.net"
PEOPLE_HR_API_KEY  = "fb1a6844-d8d5-4ec7-a4d1-e0f6472318d3"          # fill in your key
PEOPLE_HR_TIMEOUT  = 30          # seconds

PEOPLE_HR_EMPLOYEE_RESOURCE = "/Employee"
PEOPLE_HR_HOLIDAY_RESOURCE  = "/Holiday"
PEOPLE_HR_ABSENCE_RESOURCE  = "/Absence"

PEOPLE_HR_ACTION_EMPLOYEES = "GetAllEmployeeDetail"
PEOPLE_HR_ACTION_HOLIDAY   = "GetHolidayDetail"
PEOPLE_HR_ACTION_ABSENCE   = "GetAbsenceDetail"

# People HR caps requests at ~50 calls per 60-second sliding window.
# Over the limit it returns an empty Result + Message='API calls will be
# limited to a 50 per minute', with IsError=None - a SILENT failure the
# analyzer used to mis-read as 'no leave found'.
#
# To stay under the cap we batch: up to BATCH_SIZE in a burst, then sleep
# BATCH_REST_SECONDS before the next burst. REST must be >= 60s so that
# PHR's 60s sliding window has rolled past the first call of the batch
# before we start the next - otherwise batch N+1 still counts against
# batch N inside that window.
PEOPLE_HR_BATCH_SIZE = 40
PEOPLE_HR_BATCH_REST_SECONDS = 60

# Used to convert People HR absence days into hours. Holiday already
# returns minutes so this only affects absence records.
STANDARD_WORK_DAY_HOURS = 7.5

# Table holding employee name -> People HR EmployeeId (wiped and reloaded
# on every analysis run, same pattern as the visa table).
PEOPLE_HR_TABLE = "people_hr_employees"

# ============================================
# DATABASE CONFIGURATION
# ============================================
DATABASE_NAME = "workforce_analysis.db"
ANALYSIS_TABLE = "analysis_results"
VISA_TABLE = "employee_visa_status"
