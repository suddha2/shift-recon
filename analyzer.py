# analyzer.py
# Analysis logic for workforce allocation validation

import pandas as pd
from datetime import datetime, timedelta
from config import SHIFT_TYPE_LIMITS, EMPLOYEE_HOUR_LIMITS, DEFAULT_HOUR_LIMIT, ALLOWED_COMBINATIONS,RATE_CARD_MAP 

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

    # Filter to include only rows where 'Actual Service Type Description' contains 'shift' (case-insensitive)
    df = df[df['Actual Service Type Description'].str.contains('shift', case=False, na=False)]
    
    # Parse datetime columns
    df['start_dt'] = df['Actual Start Date And Time'].apply(parse_datetime)
    df['end_dt'] = df['Actual End Date And Time'].apply(parse_datetime)
    df['date'] = df['start_dt'].apply(lambda x: x.date() if x else None)
    
    # Group by employee AND date (only check overlaps on same day)
    grouped = df.groupby(['Actual Employee Name', 'date'])
    
    for (emp, date), group in grouped:
        if len(group) < 2 or date is None:
            continue
        
        rows = group.sort_values('start_dt').reset_index(drop=True)
        
        # Check pairs for time overlaps
        flagged_pairs = []
        
        # 15-minute buffer for check-in/check-out
        BUFFER_MINUTES = 15
        
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                start1, end1 = rows.loc[i, 'start_dt'], rows.loc[i, 'end_dt']
                start2, end2 = rows.loc[j, 'start_dt'], rows.loc[j, 'end_dt']
                
                # Skip if any datetime is missing
                if not (start1 and end1 and start2 and end2):
                    continue
                
                # Check for actual time overlap first (without buffer)
                has_overlap = False
                if start1 < end2 and start2 < end1:
                    # There is an overlap - calculate overlap duration
                    overlap_start = max(start1, start2)
                    overlap_end = min(end1, end2)
                    overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60
                    
                    # Only flag if overlap exceeds the buffer
                    if overlap_minutes > BUFFER_MINUTES:
                        has_overlap = True
                    else:
                        continue  # Skip - overlap within buffer tolerance
                else:
                    # No overlap - check if gap is within buffer (allows early check-in)
                    # Calculate gap between shifts
                    if end1 <= start2:  # Shift 1 ends before Shift 2 starts
                        gap_minutes = (start2 - end1).total_seconds() / 60
                    elif end2 <= start1:  # Shift 2 ends before Shift 1 starts
                        gap_minutes = (start1 - end2).total_seconds() / 60
                    else:
                        gap_minutes = 0
                    
                    # If gap is within buffer or larger, skip
                    continue  # No overlap, skip this pair
                
                # If we reach here, there's a valid overlap to check
                if has_overlap:
                    # Get location and shift type info
                    loc1 = rows.loc[i, 'Service Location Name']
                    loc2 = rows.loc[j, 'Service Location Name']
                    shift1 = rows.loc[i, 'Actual Service Type Description']
                    shift2 = rows.loc[j, 'Actual Service Type Description']
                    
                    # Define allowed combinations at same location
                    ALLOWED_SAME_LOCATION_OVERLAPS = [
                        ("Day Shift", "Floating Shift"),
                        ("Floating Shift", "Day Shift"),
                        ("L - Day Shift", "Floating Shift"),
                        ("Floating Shift", "L - Day Shift"),
                        ("Waking Night Shift", "Floating Shift"),
                        ("Floating Shift", "Waking Night Shift"),
                        ("L - Day Shift", "Sleep In Shift"),
                        ("Floating Shift","Floating Shift"),
                        ("Day Shift", "Day Shift"),
                        ("Shift Lead - Shift","Floating Shift"),
                        ("On Call Shift","On Call Shift"),
                        ("L - Day Shift", "L - Day Shift"),
                    ]
                    
                    # Skip if same location AND allowed combination
                    same_location = (loc1 == loc2)
                    is_allowed_combo = (shift1, shift2) in ALLOWED_SAME_LOCATION_OVERLAPS
                    
                    if same_location and is_allowed_combo:
                        continue  # Skip this overlap - it's allowed
                    
                    # Otherwise, flag it
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
            
            # Calculate actual overlap in minutes
            start1, end1 = rows.loc[i, 'start_dt'], rows.loc[i, 'end_dt']
            start2, end2 = rows.loc[j, 'start_dt'], rows.loc[j, 'end_dt']
            
            overlap_start = max(start1, start2)
            overlap_end = min(end1, end2)
            overlap_minutes = int((overlap_end - overlap_start).total_seconds() / 60)
            
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
                'actual_hours': None,
                'limit_hours': None,
                'shift_type': ' | '.join(shift_details),
                'overlap_minutes': overlap_minutes,
                'details': f"Overlapping shifts: {', '.join(reasons)} ({overlap_minutes} min overlap)",
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
    df['date'] = df['start_dt'].apply(lambda x: x.date() if x else None)
    df['hours'] = df.apply(lambda row: calculate_hours(row['start_dt'], row['end_dt']), axis=1)

    # Group by employee and date
    grouped = df.groupby(['Actual Employee Name', 'date'])

    

    for (emp, date), group in grouped:
        if date is None:
            continue

        # Check shift type + rate type combination limits
        group['shift_rate_combo'] = list(zip(
            group['Actual Service Type Description'],
            group['Actual Pay Rate Type']
        ))


        combo_groups = group.groupby('shift_rate_combo')

        for combo, combo_group in combo_groups:
            shift_type, rate_type = combo
            total_combo_hours = combo_group['hours'].sum()

            if combo in SHIFT_TYPE_LIMITS:
                limit_config = SHIFT_TYPE_LIMITS[combo]

                if isinstance(limit_config, dict):
                    operator = limit_config.get("operator", "<=")
                    limit_value = limit_config.get("value", 0)
                else:
                    operator = "<="
                    limit_value = limit_config
                
                violation = False
                violation_msg=""
                if operator == "<=" and total_combo_hours > limit_value:
                    violation = True
                    violation_msg = f"exceeds maximum of {limit_value} hours"
                elif operator == ">=" and total_combo_hours < limit_value:
                    violation = True
                    violation_msg = f"below minimum of {limit_value} hours"
                elif operator == "<" and total_combo_hours >= limit_value:
                    violation = True
                    violation_msg = f"must be less than {limit_value} hours"
                elif operator == ">" and total_combo_hours <= limit_value:
                    violation = True
                    violation_msg = f"must be greater than {limit_value} hours"
                elif operator == "==" and total_combo_hours != limit_value:
                    violation = True
                    violation_msg = f"must be exactly {limit_value} hours"
                


                if violation:
                    row_numbers = combo_group['_row_num'].tolist()
                    issues.append({
                        'issue_type': 'Shift Type Hour Over-allocation',
                        'employee_name': emp,
                        'date': date,
                        'week': None,
                        'actual_hours': total_combo_hours,
                        'limit_hours': limit_value,
                        'shift_type': f"{shift_type} ({rate_type})",
                        'details': f"{total_combo_hours:.1f} hours of '{shift_type}' with '{rate_type}' rate - {violation_msg}",
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
                'actual_hours': None,
                'limit_hours': None,
                'shift_type': service_type,
                'details': f"Invalid: '{service_type}' + '{requirement_type}'",
                'row_numbers': str(row['_row_num'])
            })
    
    return issues

def check_rate_mismatches(df):
    """
    Check for mismatches between actual pay rate and expected rate from RATE_CARD_MAP
    Returns list of issue dictionaries
    """
    issues = []

    for idx, row in df.iterrows():
        sheet_desc = str(row.get('Actual Pay Rate Sheet Description', '')).strip()
        rate_type = str(row.get('Actual Pay Rate Type', '')).strip()
        service_type = str(row.get('Actual Service Type Description', '')).strip()
        actual_rate = row.get('Actual Pay Rate', None)

        key1 = (sheet_desc,)
        key2 = (service_type, rate_type)

        expected_rate = None
        if key1 in RATE_CARD_MAP:
            expected_rate = RATE_CARD_MAP[key1]
        elif key2 in RATE_CARD_MAP:
            expected_rate = RATE_CARD_MAP[key2]

        if expected_rate is not None and actual_rate is not None:
            try:
                actual_rate_float = float(actual_rate)
                if abs(actual_rate_float - expected_rate) > 0.01:
                    issues.append({
                        'issue_type': 'Rate Mismatch',
                        'employee_name': row.get('Actual Employee Name', 'N/A'),
                        'date': parse_datetime(row.get('Actual Start Date And Time')).date() if row.get('Actual Start Date And Time') else None,
                        'week': None,
                        'actual_hours': None,
                        'limit_hours': expected_rate,
                        'shift_type': service_type,
                        'details': f"Expected rate: £{expected_rate:.2f}, Actual rate: £{actual_rate_float:.2f}",
                        'row_numbers': str(row['_row_num'])
                    })
            except:
                continue

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