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
("Floating Shift","Hourly"):{"operator": "<=", "value": 4}, 
("L - Day Shift","Fixed"):{"operator": "<=", "value": 14},  
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
("Shift Lead - Shift","Day Support"), 
("Training","Training"),
("Shadow","Shadow"),
("Paid Sleep In","Sleep In"),

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
#    {"Type 1", "Type 2", "Type 3"},
#    {"Day Shift"},
#    {"Night Shift"},
#]


# ============================================
# DATABASE CONFIGURATION
# ============================================
DATABASE_NAME = "workforce_analysis.db"
ANALYSIS_TABLE = "analysis_results"
