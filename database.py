# database.py
# SQLite database operations for storing analysis results

import sqlite3
import pandas as pd
from datetime import datetime
from config import DATABASE_NAME, ANALYSIS_TABLE

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
            shift_type TEXT,
            details TEXT,
            row_numbers TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

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
        issues_dict.get('unallowed_combinations', [])
    )
    
    for issue in all_issues:
        records.append({
            'analysis_timestamp': analysis_timestamp,
            'issue_type': issue['issue_type'],
            'employee_name': issue['employee_name'],
            'issue_date': str(issue['date']) if issue['date'] else None,
            'week': issue['week'],
            'shift_type': issue['shift_type'],
            'details': issue['details'],
            'row_numbers': issue['row_numbers']
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