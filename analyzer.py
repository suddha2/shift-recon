# analyzer.py
# Analysis logic for workforce allocation validation

import pandas as pd
from datetime import datetime, timedelta
from config import SHIFT_TYPE_LIMITS, EMPLOYEE_HOUR_LIMITS, DEFAULT_HOUR_LIMIT, ALLOWED_COMBINATIONS,MULTIPLE_SHIFT_ALLOWED

def parse_datetime(dt_str):
    """Parse datetime string to datetime object with UK/European date format (DD/MM/YYYY)"""
    if pd.isna(dt_str) or dt_str == '':
        return None
    try:
        # Force dayfirst=True for DD/MM/YYYY format (UK/European dates)
        return pd.to_datetime(dt_str, dayfirst=True)
    except:
        return None

def get_week_number(dt):
    """Get week number (Monday=0) and year"""
    if dt is None:
        return None, None
    # Get ISO week (Monday as first day)
    return dt.isocalendar()[1], dt.year

def calculate_hours(start_dt, end_dt):
    """Calculate hours between two datetime objects"""
    if start_dt is None or end_dt is None:
        return 0
    delta = end_dt - start_dt
    return delta.total_seconds() / 3600

def check_duplicate_allocations(df):
    issues = []

    # Parse datetime columns
    df['start_dt'] = df['Actual Start Date And Time'].apply(parse_datetime)
    df['end_dt'] = df['Actual End Date And Time'].apply(parse_datetime)
    # ✅ Filter to include only 'Shift' types
    df = df[df['Actual Service Type Description'].str.contains('Shift', na=False)]

    df['date'] = df['start_dt'].dt.date

    # Group by employee and date
    grouped = df.groupby(['Actual Employee Name', 'date'])

    for (emp, date), group in grouped:
        shift_counts = group['Actual Service Type Description'].value_counts()
        shift_set = set(group['Actual Service Type Description'].dropna())

        # Check for disallowed multiple allocations
        for shift_type, count in shift_counts.items():
            if not MULTIPLE_SHIFT_ALLOWED.get(shift_type, False) and count > 1:
                rows = group[group['Actual Service Type Description'] == shift_type]
                issues.append({
                    'issue_type': 'Duplicate Shift Type',
                    'employee_name': emp,
                    'date': date,
                    'week': None,
                    'shift_type': shift_type,
                    'details': f"'{shift_type}' assigned {count} times (only 1 allowed)",
                    'row_numbers': ', '.join(map(str, rows['_row_num'].tolist()))
                })

        '''# Check if combination is allowed
        if not any(shift_set <= allowed for allowed in ALLOWED_DAILY_COMBINATIONS):
            issues.append({
                'issue_type': 'Invalid Shift Combination',
                'employee_name': emp,
                'date': date,
                'week': None,
                'shift_type': ', '.join(shift_set),
                'details': f"Combination {shift_set} not in allowed daily combinations",
                'row_numbers': ', '.join(map(str, group['_row_num'].tolist()))
            })
'''
        # Check for overlapping time windows
        rows = group.sort_values('start_dt').reset_index(drop=True)
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                start1, end1 = rows.loc[i, 'start_dt'], rows.loc[i, 'end_dt']
                start2, end2 = rows.loc[j, 'start_dt'], rows.loc[j, 'end_dt']

                if not (start1 and end1 and start2 and end2):
                    continue

                if start1 < end2 and start2 < end1:
                    loc1 = rows.loc[i, 'Service Location Name']
                    loc2 = rows.loc[j, 'Service Location Name']
                    shift1 = rows.loc[i, 'Actual Service Type Description']
                    shift2 = rows.loc[j, 'Actual Service Type Description']

                    has_diff_location = (loc1 and loc2 and loc1 != loc2)
                    has_diff_shift = (shift1 and shift2 and shift1 != shift2)

                    reasons = ["Time overlap"]
                    if has_diff_location:
                        reasons.append("different locations")
                    if has_diff_shift:
                        reasons.append("different shift types")

                    shift_details = []
                    for idx in [i, j]:
                        loc = rows.loc[idx, 'Service Location Name']
                        shift = rows.loc[idx, 'Actual Service Type Description']
                        start_time = rows.loc[idx, 'start_dt'].strftime('%H:%M')
                        end_time = rows.loc[idx, 'end_dt'].strftime('%H:%M')
                        shift_details.append(f"{shift} at {loc} ({start_time}-{end_time})")

                    issues.append({
                        'issue_type': 'Duplicate Allocation',
                        'employee_name': emp,
                        'date': date,
                        'week': None,
                        'shift_type': ' | '.join(shift_details),
                        'details': f"Overlapping shifts: {', '.join(reasons)}",
                        'row_numbers': ', '.join(map(str, [rows.loc[i, '_row_num'], rows.loc[j, '_row_num']]))
                    })

    return issues

def check_over_allocations(df):
    """
    Check for over-allocations based on shift type + rate type limits and hour limits
    Validates per day instead of per week
    """
    issues = []

    # Parse datetime columns
    df['start_dt'] = df['Actual Start Date And Time'].apply(parse_datetime)
    df['end_dt'] = df['Actual End Date And Time'].apply(parse_datetime)
    df['date'] = df['start_dt'].dt.date
    df['hours'] = df.apply(lambda row: calculate_hours(row['start_dt'], row['end_dt']), axis=1)

    # Group by employee and date
    grouped = df.groupby(['Actual Employee Name', 'date'])

    for (emp, date), group in grouped:
        # Create a combination column
        group['shift_rate_combo'] = list(zip(
            group['Actual Service Type Description'],
            group['Actual Pay Rate Type']
        ))

        combo_counts = group['shift_rate_combo'].value_counts()

        for combo, count in combo_counts.items():
            shift_type, rate_type = combo

            if combo in SHIFT_TYPE_LIMITS:
                limit_config = SHIFT_TYPE_LIMITS[combo]

                if isinstance(limit_config, dict):
                    operator = limit_config.get("operator", "<=")
                    limit_value = limit_config.get("value", 0)
                else:
                    operator = "<="
                    limit_value = limit_config

                violation = False
                if operator == "<=" and count > limit_value:
                    violation = True
                    violation_msg = f"exceeds maximum of {limit_value}"
                elif operator == ">=" and count < limit_value:
                    violation = True
                    violation_msg = f"below minimum of {limit_value}"
                elif operator == "<" and count >= limit_value:
                    violation = True
                    violation_msg = f"must be less than {limit_value}"
                elif operator == ">" and count <= limit_value:
                    violation = True
                    violation_msg = f"must be greater than {limit_value}"
                elif operator == "==" and count != limit_value:
                    violation = True
                    violation_msg = f"must be exactly {limit_value}"

                if violation:
                    row_numbers = group[group['shift_rate_combo'] == combo]['_row_num'].tolist()
                    issues.append({
                        'issue_type': 'Shift Type Over-allocation',
                        'employee_name': emp,
                        'date': date,
                        'week': None,
                        'shift_type': f"{shift_type} ({rate_type})",
                        'details': f"{count} shifts of '{shift_type}' with '{rate_type}' rate - {violation_msg}",
                        'row_numbers': ', '.join(map(str, row_numbers))
                    })

            # Check daily hour limits
            total_hours = group['hours'].sum()
            emp_limit = EMPLOYEE_HOUR_LIMITS.get(emp, DEFAULT_HOUR_LIMIT)

            # Only validate if a real limit is set (not -1)
            if emp_limit is not None and emp_limit >= 0 and total_hours > emp_limit:
                row_numbers = group['_row_num'].tolist()
                issues.append({
                    'issue_type': 'Daily Hours Over-allocation',
                    'employee_name': emp,
                    'date': date,
                    'week': None,
                    'shift_type': 'All shifts',
                    'details': f"{total_hours:.1f} hours (limit: {emp_limit})",
                    'row_numbers': ', '.join(map(str, row_numbers))
                })



    return issues


def check_unallowed_combinations(df):
    """
    Check for unallowed combinations of Service Type and Requirement Type
    Using whitelist approach - flag anything NOT in ALLOWED_COMBINATIONS
    Returns list of issue dictionaries
    """
    issues = []
    
    for idx, row in df.iterrows():
        service_type = row['Actual Service Type Description']
        requirement_type = row['Actual Service Requirement Type Description']
        
        # Skip if either value is empty
        if pd.isna(service_type) or pd.isna(requirement_type) or service_type == '' or requirement_type == '':
            continue
        
        # Check if combination is in whitelist
        if (service_type, requirement_type) not in ALLOWED_COMBINATIONS:
            issues.append({
                'issue_type': 'Unallowed Combination',
                'employee_name': row['Actual Employee Name'],
                'date': parse_datetime(row['Actual Start Date And Time']).date() if parse_datetime(row['Actual Start Date And Time']) else None,
                'week': None,
                'shift_type': service_type,
                'details': f"Invalid: '{service_type}' + '{requirement_type}'",
                'row_numbers': str(row['_row_num'])
            })
    
    return issues

def analyze_workforce_data(df):
    """
    Main analysis function
    Returns dictionary with all issues categorized
    """
    # Add row numbers for reference (Excel row number)
    df['_row_num'] = range(2, len(df) + 2)  # Starting from row 2 (after header)
    
    duplicates = check_duplicate_allocations(df.copy())
    over_allocs = check_over_allocations(df.copy())
    unallowed = check_unallowed_combinations(df.copy())
    
    return {
        'duplicate_allocations': duplicates,
        'over_allocations': over_allocs,
        'unallowed_combinations': unallowed,
        'total_issues': len(duplicates) + len(over_allocs) + len(unallowed)
    }