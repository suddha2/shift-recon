# analyzer.py
# Analysis logic for workforce allocation validation

import pandas as pd
from datetime import datetime, timedelta
from config import SHIFT_TYPE_LIMITS, EMPLOYEE_HOUR_LIMITS, DEFAULT_HOUR_LIMIT, ALLOWED_COMBINATIONS

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
    """
    Find duplicate allocations for the same employee with overlapping times
    Only flags when shifts actually overlap in time (not just same day)
    Also checks: different locations or different shift types during overlap
    Returns list of issue dictionaries
    """
    issues = []



    # ✅ Filter to include only rows where 'Actual Service Type Description' contains 'shift' (case-insensitive)
    df = df[df['Actual Service Type Description'].str.contains('shift', case=False, na=False)]

    
    # Parse datetime columns
    df['start_dt'] = df['Actual Start Date And Time'].apply(parse_datetime)
    df['end_dt'] = df['Actual End Date And Time'].apply(parse_datetime)
    
    # Group by employee only (not by date, since we need to check time overlaps)
    grouped = df.groupby('Actual Employee Name')
    
    for emp, group in grouped:
        if len(group) < 2:
            continue
        
        rows = group.sort_values('start_dt').reset_index(drop=True)
        
        # Check pairs for time overlaps
        flagged_pairs = []
        
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                start1, end1 = rows.loc[i, 'start_dt'], rows.loc[i, 'end_dt']
                start2, end2 = rows.loc[j, 'start_dt'], rows.loc[j, 'end_dt']
                
                # Skip if any datetime is missing
                if not (start1 and end1 and start2 and end2):
                    continue
                
                # Check for time overlap (this is the CRITICAL condition)
                if start1 < end2 and start2 < end1:
                    # There IS a time overlap - now check additional conditions
                    loc1 = rows.loc[i, 'Service Location Name']
                    loc2 = rows.loc[j, 'Service Location Name']
                    shift1 = rows.loc[i, 'Actual Service Type Description']
                    shift2 = rows.loc[j, 'Actual Service Type Description']
                    
                    has_diff_location = (loc1 and loc2 and loc1 != loc2)
                    has_diff_shift = (shift1 and shift2 and shift1 != shift2)
                    
                    flagged_pairs.append({
                        'i': i,
                        'j': j,
                        'has_diff_location': has_diff_location,
                        'has_diff_shift': has_diff_shift
                    })
        
        # Create issue entries for each pair
        for pair in flagged_pairs:
            i, j = pair['i'], pair['j']
            
            row_nums = [rows.loc[i, '_row_num'], rows.loc[j, '_row_num']]
            
            # Get date for display (use start date of first shift)
            issue_date = rows.loc[i, 'start_dt'].date()
            
            # Build reason details
            reasons = ["Time overlap"]
            if pair['has_diff_location']:
                reasons.append("different locations")
            if pair['has_diff_shift']:
                reasons.append("different shift types")
            
            # Create shift details for both overlapping shifts
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
                'date': issue_date,
                'week': None,
                'shift_type': ' | '.join(shift_details),
                'details': f"Overlapping shifts: {', '.join(reasons)}",
                'row_numbers': ', '.join(map(str, row_nums))
            })
    
    return issues

def check_over_allocations(df):
    """
    Check for over-allocations based on shift type + rate type limits and hour limits
    Supports flexible operators: <=, >=, <, >, ==
    Returns list of issue dictionaries
    """
    issues = []
    
    # Parse datetime columns
    df['start_dt'] = df['Actual Start Date And Time'].apply(parse_datetime)
    df['end_dt'] = df['Actual End Date And Time'].apply(parse_datetime)
    df['week'], df['year'] = zip(*df['start_dt'].apply(lambda x: get_week_number(x)))
    df['hours'] = df.apply(lambda row: calculate_hours(row['start_dt'], row['end_dt']), axis=1)
    
    # Group by employee, year, and week
    grouped = df.groupby(['Actual Employee Name', 'year', 'week'])
    
    for (emp, year, week), group in grouped:
        if week is None:
            continue
        
        # Check shift type + rate type combination limits
        # Create a combination column
        group['shift_rate_combo'] = list(zip(
            group['Actual Service Type Description'],
            group['Actual Pay Rate Type']
        ))
        
        combo_counts = group['shift_rate_combo'].value_counts()
        
        for combo, count in combo_counts.items():
            shift_type, rate_type = combo
            
            # Check if this combination has a limit defined
            if combo in SHIFT_TYPE_LIMITS:
                limit_config = SHIFT_TYPE_LIMITS[combo]
                
                # Handle both old format (int) and new format (dict)
                if isinstance(limit_config, dict):
                    operator = limit_config.get("operator", "<=")
                    limit_value = limit_config.get("value", 0)
                else:
                    # Backward compatibility: treat int as <=
                    operator = "<="
                    limit_value = limit_config
                
                # Check if the count violates the rule
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
                        'date': None,
                        'week': f"{year}-W{week:02d}",
                        'shift_type': f"{shift_type} ({rate_type})",
                        'details': f"{count} shifts of '{shift_type}' with '{rate_type}' rate - {violation_msg}",
                        'row_numbers': ', '.join(map(str, row_numbers))
                    })
        
        # Check hour limits
        total_hours = group['hours'].sum()
        emp_limit = EMPLOYEE_HOUR_LIMITS.get(emp, DEFAULT_HOUR_LIMIT)
        
        if emp_limit is not None and emp_limit >= 0 and total_hours > emp_limit:
            row_numbers = group['_row_num'].tolist()
            issues.append({
                'issue_type': 'Weekly Hours Over-allocation',
                'employee_name': emp,
                'date': None,
                'week': f"{year}-W{week:02d}",
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
    Returns dictionary with all issues categorized and error rows
    """
    # Add row numbers for reference (Excel row number)
    df['_row_num'] = range(2, len(df) + 2)  # Starting from row 2 (after header)
    
    # Track error rows
    error_rows = []
    
    # Validate and clean data
    valid_df = df.copy()
    
    # Check for rows with missing critical columns
    critical_columns = [
        'Actual Employee Name',
        'Actual Start Date And Time',
        'Actual End Date And Time',
        'Actual Service Type Description'
    ]
    
    for idx, row in df.iterrows():
        errors = []
        
        # Check for missing critical fields
        for col in critical_columns:
            if pd.isna(row.get(col)) or row.get(col) == '':
                errors.append(f"Missing {col}")
        
        # Check date parsing
        if not pd.isna(row.get('Actual Start Date And Time')) and row.get('Actual Start Date And Time') != '':
            start_dt = parse_datetime(row['Actual Start Date And Time'])
            if start_dt is None:
                errors.append(f"Invalid start date format: {row['Actual Start Date And Time']}")
        
        if not pd.isna(row.get('Actual End Date And Time')) and row.get('Actual End Date And Time') != '':
            end_dt = parse_datetime(row['Actual End Date And Time'])
            if end_dt is None:
                errors.append(f"Invalid end date format: {row['Actual End Date And Time']}")
        
        # If errors found, add to error_rows and mark for removal
        if errors:
            error_rows.append({
                'row_number': row['_row_num'],
                'employee_name': row.get('Actual Employee Name', 'N/A'),
                'start_date': row.get('Actual Start Date And Time', 'N/A'),
                'end_date': row.get('Actual End Date And Time', 'N/A'),
                'shift_type': row.get('Actual Service Type Description', 'N/A'),
                'errors': ', '.join(errors)
            })
            valid_df = valid_df.drop(idx)
    
    # Run analysis on valid data only
    try:
        duplicates = check_duplicate_allocations(valid_df.copy())
    except Exception as e:
        duplicates = []
        error_rows.append({
            'row_number': 'N/A',
            'employee_name': 'ANALYSIS ERROR',
            'start_date': 'N/A',
            'end_date': 'N/A',
            'shift_type': 'Duplicate Check',
            'errors': f"Error in duplicate check: {str(e)}"
        })
    
    try:
        over_allocs = check_over_allocations(valid_df.copy())
    except Exception as e:
        over_allocs = []
        error_rows.append({
            'row_number': 'N/A',
            'employee_name': 'ANALYSIS ERROR',
            'start_date': 'N/A',
            'end_date': 'N/A',
            'shift_type': 'Over-allocation Check',
            'errors': f"Error in over-allocation check: {str(e)}"
        })
    
    try:
        unallowed = check_unallowed_combinations(valid_df.copy())
    except Exception as e:
        unallowed = []
        error_rows.append({
            'row_number': 'N/A',
            'employee_name': 'ANALYSIS ERROR',
            'start_date': 'N/A',
            'end_date': 'N/A',
            'shift_type': 'Unallowed Combinations Check',
            'errors': f"Error in unallowed combinations check: {str(e)}"
        })
    
    return {
        'duplicate_allocations': duplicates,
        'over_allocations': over_allocs,
        'unallowed_combinations': unallowed,
        'error_rows': error_rows,
        'total_issues': len(duplicates) + len(over_allocs) + len(unallowed),
        'total_errors': len(error_rows),
        'total_valid_rows': len(valid_df),
        'total_rows': len(df)
    }