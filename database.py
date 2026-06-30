# database.py
# SQLite database operations for storing analysis results

import sqlite3
import io
import pandas as pd
import requests
from datetime import datetime
from config import (
    DATABASE_NAME, ANALYSIS_TABLE, VISA_TABLE, PEOPLE_HR_TABLE,
    APP_EMP_URL, APP_EMP_AUTH, APP_EMP_TIMEOUT,
    APP_EMP_NAME_COL, APP_EMP_TYPE_COL
)
from analyzer import canonical_name
from people_hr import fetch_all_employees

def init_database():
    """Initialize SQLite database and create tables if they don't exist"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Create analysis results table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {ANALYSIS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_timestamp TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            employee_name TEXT,
            issue_date TEXT,
            week TEXT,
            actual_hours TEXT,
            limit_hours TEXT,
            shift_type TEXT,
            details TEXT,
            row_numbers TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create employee visa status table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {VISA_TABLE} (
            employee_name TEXT PRIMARY KEY,
            visa_status TEXT,
            updated_at TEXT
        )
    ''')

    # People HR employee ID lookup (wiped + reloaded per analysis run)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {PEOPLE_HR_TABLE} (
            employee_name TEXT PRIMARY KEY,
            people_hr_id TEXT,
            updated_at TEXT
        )
    ''')

    # Idempotent column adds for the leave enrichment fields on
    # analysis_results. Older DBs created before this feature won't have
    # them; ALTER TABLE ADD COLUMN raises if it already exists, so we
    # swallow that specific case.
    for col, coltype in (
        ("leave", "TEXT"),
        ("leave_hours", "REAL"),
        ("leave_details", "TEXT"),
    ):
        try:
            cursor.execute(f"ALTER TABLE {ANALYSIS_TABLE} ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

def sync_visa_data():
    """
    Fetch the full employee dump (CSV) from APP_EMP_URL and replace the visa table.
    Visa status is the part of the EmployeeType column after the first ' - '.
    Returns: (success: bool, count: int, message: str)
    """
    try:
        resp = requests.get(
            APP_EMP_URL,
            headers={"Authorization": APP_EMP_AUTH},
            timeout=APP_EMP_TIMEOUT
        )
        resp.raise_for_status()
        feed = pd.read_csv(io.StringIO(resp.text), dtype=str)
    except Exception as e:
        return False, 0, f"Sync failed: {e}"

    feed.columns = feed.columns.str.strip()
    if APP_EMP_NAME_COL not in feed.columns or APP_EMP_TYPE_COL not in feed.columns:
        return False, 0, (f"Sync failed: feed missing expected columns "
                          f"'{APP_EMP_NAME_COL}' / '{APP_EMP_TYPE_COL}'")

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    records = []
    for _, row in feed.iterrows():
        # Feed names are hyphenated (e.g. "Beatrice-Kembabazi"); store with spaces
        name = str(row.get(APP_EMP_NAME_COL, '') or '').strip().replace('-', ' ')
        emp_type = str(row.get(APP_EMP_TYPE_COL, '') or '').strip()
        # Visa status is the segment after the first ' - ' (blank if none)
        visa_status = emp_type.split(' - ', 1)[1].strip() if ' - ' in emp_type else ''
        if name and name.lower() != 'nan':
            records.append((name, visa_status, timestamp))

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {VISA_TABLE}")
    cursor.executemany(
        f"INSERT OR REPLACE INTO {VISA_TABLE} (employee_name, visa_status, updated_at) VALUES (?, ?, ?)",
        records
    )
    conn.commit()
    conn.close()
    return True, len(records), f"Synced {len(records)} employees"

def get_visa_lookup():
    """
    Return a dict mapping canonical employee name -> visa_status.
    Keyed by canonical_name so 'Manneh, Aji' (CSV) and 'Aji Manneh'
    (feed) resolve to the same entry.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT employee_name, visa_status FROM {VISA_TABLE}")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return {canonical_name(name): status for name, status in rows}

def get_last_visa_sync():
    """Return the timestamp of the most recent visa sync, or None"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT MAX(updated_at) FROM {VISA_TABLE}")
        result = cursor.fetchone()
    except sqlite3.OperationalError:
        result = None
    conn.close()
    return result[0] if result and result[0] else None


def sync_people_hr_employees():
    """Fetch the full People HR employee roster and replace the lookup table.

    Names are stored as 'First Last' so that canonical_name() matches them
    against the 'Last, First' format used in the workforce CSV.

    Returns: (success: bool, count: int, message: str)
    """
    try:
        records = fetch_all_employees()
    except Exception as e:
        return False, 0, f"People HR sync failed: {e}"

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    for rec in records:
        name = (rec.get("full_name") or "").strip()
        emp_id = (rec.get("employee_id") or "").strip()
        if name and emp_id:
            rows.append((name, emp_id, timestamp))

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {PEOPLE_HR_TABLE}")
    cursor.executemany(
        f"INSERT OR REPLACE INTO {PEOPLE_HR_TABLE} (employee_name, people_hr_id, updated_at) VALUES (?, ?, ?)",
        rows
    )
    conn.commit()
    conn.close()
    return True, len(rows), f"Synced {len(rows)} People HR employees"


def get_people_hr_id_lookup():
    """Return {canonical_name: people_hr_id} for all synced employees."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT employee_name, people_hr_id FROM {PEOPLE_HR_TABLE}")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return {canonical_name(name): emp_id for name, emp_id in rows}


def get_last_people_hr_sync():
    """Return the timestamp of the most recent People HR sync, or None."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT MAX(updated_at) FROM {PEOPLE_HR_TABLE}")
        result = cursor.fetchone()
    except sqlite3.OperationalError:
        result = None
    conn.close()
    return result[0] if result and result[0] else None

def save_analysis_results(issues_dict, analysis_timestamp=None):
    """
    Save analysis results to database
    issues_dict: Dictionary with keys 'duplicate_allocations', 'over_allocations', 'unallowed_combinations'
    Returns: Number of records saved
    """
    if analysis_timestamp is None:
        analysis_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect(DATABASE_NAME)
    
    records = []
    
    # Combine all issues
    all_issues = (
        issues_dict.get('duplicate_allocations', []) +
        issues_dict.get('over_allocations', []) +
        issues_dict.get('unallowed_combinations', []) +
        issues_dict.get('visa_violations', []) +
        issues_dict.get('late_starts', [])
    )
    
    for issue in all_issues:
        records.append({
            'analysis_timestamp': analysis_timestamp,
            'issue_type': issue.get('issue_type'),
            'employee_name': issue.get('employee_name'),
            'issue_date': str(issue['date']) if issue.get('date') else None,
            'week': issue.get('week'),
            'actual_hours': issue.get('actual_hours'),
            'limit_hours': issue.get('limit_hours'),
            'shift_type': issue.get('shift_type'),
            'details': issue.get('details'),
            'row_numbers': issue.get('row_numbers'),
            'leave': issue.get('leave', 'N/A'),
            'leave_hours': issue.get('leave_hours'),
            'leave_details': issue.get('leave_details', ''),
        })
    
    if records:
        df = pd.DataFrame(records)
        df.to_sql(ANALYSIS_TABLE, conn, if_exists='append', index=False)
    
    conn.close()
    return len(records)

def get_all_analyses():
    """Get all analysis results from database"""
    conn = sqlite3.connect(DATABASE_NAME)
    query = f"SELECT * FROM {ANALYSIS_TABLE} ORDER BY analysis_timestamp DESC, id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_analysis_by_timestamp(timestamp):
    """Get specific analysis results by timestamp"""
    conn = sqlite3.connect(DATABASE_NAME)
    query = f"SELECT * FROM {ANALYSIS_TABLE} WHERE analysis_timestamp = ? ORDER BY id"
    df = pd.read_sql_query(query, conn, params=(timestamp,))
    conn.close()
    return df

def get_unique_analysis_timestamps():
    """Get list of unique analysis timestamps"""
    conn = sqlite3.connect(DATABASE_NAME)
    query = f"SELECT DISTINCT analysis_timestamp FROM {ANALYSIS_TABLE} ORDER BY analysis_timestamp DESC"
    cursor = conn.cursor()
    cursor.execute(query)
    timestamps = [row[0] for row in cursor.fetchall()]
    conn.close()
    return timestamps

def delete_analysis(timestamp):
    """Delete analysis results by timestamp"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {ANALYSIS_TABLE} WHERE analysis_timestamp = ?", (timestamp,))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count

def export_to_excel(timestamp=None, filename='analysis_export.xlsx'):
    """
    Export analysis results to Excel file
    If timestamp is provided, export only that analysis, otherwise export all
    """
    if timestamp:
        df = get_analysis_by_timestamp(timestamp)
    else:
        df = get_all_analyses()
    
    if not df.empty:
        df.to_excel(filename, index=False, engine='openpyxl')
        return True
    return False