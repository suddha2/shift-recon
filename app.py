# app.py
# Main Streamlit application for Workforce Allocation Analyzer

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader


from analyzer import (
    analyze_workforce_data,
    check_unallowed_combinations,
    check_duplicate_allocations,
    check_over_allocations,
    check_rate_mismatches,
    check_visa_hour_violations,
    check_late_starts,
    summarize_rate_cards,
)

from database import (
    init_database,
    save_analysis_results,
    get_all_analyses,
    get_unique_analysis_timestamps,
    get_analysis_by_timestamp,
    delete_analysis,
    export_to_excel,
    sync_visa_data,
    get_visa_lookup,
    get_last_visa_sync,
    sync_people_hr_employees,
    get_people_hr_id_lookup,
    get_last_people_hr_sync,
)
from analyzer import parse_datetime
from config import SHIFT_TYPE_LIMITS, EMPLOYEE_HOUR_LIMITS, ALLOWED_COMBINATIONS, VISA_HOUR_RULES

# Page configuration
st.set_page_config(
    page_title="Workforce Allocation Analyzer",
    page_icon="📊",
    layout="wide"
)

# ============================================
# AUTHENTICATION
# ============================================
# Load config
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Create authenticator
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Call login ONCE
authenticator.login(location="main")

# Use session state to drive logic
auth_status = st.session_state.get("authentication_status")

# Check authentication status
if auth_status is False:
    st.error('❌ Username/Password is incorrect')
    st.stop()
elif auth_status is None:
    st.info('ℹ️ Please enter your username and password')
    st.stop()

# ============================================
# AUTHENTICATED AREA - Main App
# ============================================

# Initialize database
init_database()

# Initialize session state
if 'analyzed' not in st.session_state:
    st.session_state.analyzed = False
if 'results' not in st.session_state:
    st.session_state.results = None
if 'df' not in st.session_state:
    st.session_state.df = None
if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False

# Header with logout
col1, col2 = st.columns([6, 1])
with col1:
    st.title("📊 Workforce Allocation Analyzer")
with col2:
    st.write("")
    if st.button("Logout", key="logout_btn"):
        for key in list(st.session_state.keys()):
            if key.startswith("authentication") or key in ["name", "username"]:
                del st.session_state[key]
        st.session_state["authentication_status"] = None
        st.stop()


st.markdown(f"**Welcome, {st.session_state.get('name', 'User')}!**")
st.markdown("---")

# Sidebar - Configuration Display
with st.sidebar:
    st.header("⚙️ Current Rules")
    
    with st.expander("📋 Shift Type Limits", expanded=False):
        for combo, limit in SHIFT_TYPE_LIMITS.items():
            shift_type, rate_type = combo
            if isinstance(limit, dict):
                operator = limit.get("operator", "<=")
                value = limit.get("value", 0)
                st.write(f"**{shift_type} ({rate_type}):** {operator} {value} hours/day")
            else:
                st.write(f"**{shift_type} ({rate_type}):** ≤ {limit} hours/day")

    with st.expander("⏰ Hour Limits", expanded=False):
        st.write(f"**Default:** {EMPLOYEE_HOUR_LIMITS.get('DEFAULT', 48)} hours/week")
        st.write("**Custom Limits:**")
        for emp, limit in EMPLOYEE_HOUR_LIMITS.items():
            if emp != 'DEFAULT':
                st.write(f"• {emp}: {limit if limit else 'No limit'}")
    
    with st.expander("✅ Allowed Combinations", expanded=False):
        st.write(f"Total: {len(ALLOWED_COMBINATIONS)} combinations")
        for svc, req in ALLOWED_COMBINATIONS[:5]:
            st.write(f"• {svc} + {req}")
        if len(ALLOWED_COMBINATIONS) > 5:
            st.write(f"... and {len(ALLOWED_COMBINATIONS) - 5} more")

    with st.expander("🛂 Visa Hour Rules", expanded=False):
        last_sync = get_last_visa_sync()
        st.write(f"**Last visa sync:** {last_sync or 'Never'}")
        last_phr_sync = get_last_people_hr_sync()
        st.write(f"**Last People HR sync:** {last_phr_sync or 'Never'}")
        for status, rule in VISA_HOUR_RULES.items():
            st.write(f"**{status}:** {rule.get('operator', '<=')} {rule.get('value', 0)} hours/week")
    
    st.markdown("---")
    st.info("💡 Edit rules in `config.py`")

# Main content tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 New Analysis", "📊 View Results", "❌ Error Rows",
    "💷 Rate Cards", "🗂️ History",
])

# Tab 1: New Analysis
with tab1:
    st.header("Upload CSV for Analysis")
    
    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=['csv'],
        help="Upload your workforce allocation CSV file"
    )
    
    if uploaded_file is not None:
        try:
            # Read CSV with encoding fallback (Excel exports are often cp1252)
            try:
                df = pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                try:
                    df = pd.read_csv(uploaded_file, encoding='cp1252')
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='latin-1')
            df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
            df.columns = df.columns.str.replace('Desciption', 'Description', regex=False)
            df.columns = df.columns.str.replace('and Time', 'And Time', regex=False)
            st.session_state.df = df
            
            st.success(f"✅ File loaded successfully: {len(df)} rows")
            
            # DEBUG: Show column names
            with st.expander("🔍 Column Names (Debug)", expanded=False):
                st.write("**Columns in your CSV:**")
                for i, col in enumerate(df.columns):
                    st.write(f"{i+1}. `{col}` (length: {len(col)} chars)")
                
                # Check for required columns
                required_cols = [
                    'Actual Employee Name',
                    'Actual Start Date And Time',
                    'Actual End Date And Time',
                    'Service Location Name',
                    'Actual Service Type Description',
                    'Actual Pay Rate Type',
                    'Actual Service Requirement Type Description'
                ]
                st.write("\n**Required columns check:**")
                for col in required_cols:
                    if col in df.columns:
                        st.success(f"✅ {col}")
                    else:
                        st.error(f"❌ {col} - NOT FOUND")
            
            # Show preview
            with st.expander("📄 Data Preview", expanded=True):
                st.dataframe(df.head(10), use_container_width=True)
            
            # Analyze button
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔍 Run Analysis", type="primary", use_container_width=True, disabled=st.session_state.is_processing):
                    st.session_state.is_processing = True

                    try:
                        progress = st.progress(0, text="Syncing employee visa data...")

                        # Sync visa data before analysis begins
                        visa_ok, visa_count, visa_msg = sync_visa_data()
                        if visa_ok:
                            st.info(f"🔄 {visa_msg}")
                        else:
                            st.warning(f"⚠️ {visa_msg}. Using last synced visa data.")
                        visa_lookup = get_visa_lookup()

                        # Sync People HR roster (used to enrich below-minimum
                        # visa violations with holiday/absence context)
                        progress.progress(0, text="Syncing People HR employees...")
                        phr_ok, phr_count, phr_msg = sync_people_hr_employees()
                        if phr_ok:
                            st.info(f"🔄 {phr_msg}")
                        else:
                            st.warning(f"⚠️ {phr_msg}. Leave column will show 'Unknown' for visa shortfalls.")
                        people_hr_lookup = get_people_hr_id_lookup()

                        progress.progress(0, text="Starting analysis...")
                        df = st.session_state.df.copy()
                        df['_row_num'] = range(2, len(df) + 2)
                        total_rows = len(df)
                        chunk_size = 1000

                        # Preallocate issue lists
                        unallowed = []
                        duplicates = []
                        over_allocs = []
                        rate_mismatches = []

                        
                        for start in range(0, total_rows, chunk_size):
                            end = min(start + chunk_size, total_rows)
                            chunk = df.iloc[start:end]

                            # Step 1: Check unallowed combinations
                            chunk_unallowed = check_unallowed_combinations(chunk.copy())
                            unallowed.extend(chunk_unallowed)

                            # Step 2: Filter valid rows
                            invalid_row_nums = set(int(issue['row_numbers']) for issue in chunk_unallowed)
                            valid_chunk = chunk[~chunk['_row_num'].isin(invalid_row_nums)]

                            # Step 3: Run other checks on valid rows
                            chunk_duplicates = check_duplicate_allocations(valid_chunk.copy())
                            chunk_over_allocs = check_over_allocations(valid_chunk.copy())

                            # Step 4: Rate mismatch check
                            chunk_rate_mismatches = check_rate_mismatches(valid_chunk.copy())
                            rate_mismatches.extend(chunk_rate_mismatches)

                            duplicates.extend(chunk_duplicates)
                            over_allocs.extend(chunk_over_allocs)

                            # Update progress bar
                            progress.progress(end / total_rows, text=f"Processed {end} of {total_rows} rows")

                        # Visa weekly-hours check - runs on the FULL dataframe
                        # (weekly aggregation per employee cannot be chunked)
                        progress.progress(1.0, text="Checking visa working hours...")

                        # Period bounds drive the People HR holiday/absence fetches.
                        # One call per affected employee covers the full CSV span,
                        # then weekly violations are sliced from the cached records.
                        start_series = df['Actual Start Date And Time'].apply(parse_datetime).dropna()
                        end_series = df['Actual End Date And Time'].apply(parse_datetime).dropna()
                        period_start = start_series.min().date() if not start_series.empty else None
                        period_end = end_series.max().date() if not end_series.empty else None

                        visa_violations = check_visa_hour_violations(
                            df, visa_lookup,
                            people_hr_lookup=people_hr_lookup,
                            period_start=period_start,
                            period_end=period_end,
                        )

                        # Late-start check (Hourly shifts only, > 1 minute late)
                        progress.progress(1.0, text="Checking late starts...")
                        late_starts = check_late_starts(df)

                        # Rate-card summary (informational, not violations - shown
                        # in the Rate Cards tab)
                        progress.progress(1.0, text="Summarising rate cards...")
                        rate_cards = summarize_rate_cards(df)

                        # Finalize progress bar
                        progress.progress(1.0, text="✅ Analysis complete")

                        # Save results
                        results = {
                            'duplicate_allocations': duplicates,
                            'over_allocations': over_allocs,
                            'unallowed_combinations': unallowed,
                            'rate_mismatches': rate_mismatches,
                            'visa_violations': visa_violations,
                            'late_starts': late_starts,
                            'rate_cards': rate_cards,
                            'total_issues': (
                                len(duplicates) + len(over_allocs) + len(unallowed)
                                + len(rate_mismatches) + len(visa_violations)
                                + len(late_starts)
                            ),
                        }

                        st.session_state.results = results
                        st.session_state.analyzed = True

                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        saved_count = save_analysis_results(results, timestamp)

                        st.success(f"✅ Analysis complete! Found {results['total_issues']} issues. Saved {saved_count} records to database.")
                        st.session_state.is_processing = False

                    except Exception as e:
                        st.session_state.is_processing = False
                        st.error(f"❌ Analysis error: {str(e)}")
                        import traceback
                        with st.expander("🔍 Error Details"):
                            st.code(traceback.format_exc())
                        st.markdown("**DataFrame shape:**")
                        st.write(df.shape)
                        st.markdown("**Columns:**")
                        st.write(list(df.columns))
                        st.markdown("**Sample of 'Actual End Date And Time' column:**")
                        st.write(df.head(20))

        
        except Exception as e:
            st.error(f"❌ Error reading file: {str(e)}")

# Tab 2: View Current Results
with tab2:
    if st.session_state.analyzed and st.session_state.results:
        results = st.session_state.results

        st.header("Analysis Results")

        # Summary metrics
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        with col1:
            st.metric("Total Issues", results['total_issues'])
        with col2:
            st.metric("Duplicates", len(results['duplicate_allocations']))
        with col3:
            st.metric("Over-allocations", len(results['over_allocations']))
        with col4:
            st.metric("Invalid Combos", len(results['unallowed_combinations']))
        with col5:
            st.metric("Rate Mismatches", len(results['rate_mismatches']))
        with col6:
            st.metric("Visa Violations", len(results['visa_violations']))
        with col7:
            st.metric("Late Starts", len(results.get('late_starts', [])))
        st.markdown("---")

        # Pagination helper
        def show_paginated_df(df, label, key_prefix, color=None):
            if df.empty:
                st.info(f"✅ No {label.lower()} found.")
                return

            st.subheader(label)
            if color:
                st.caption(f"Styled with background color: {color}")
            else:
                st.caption("Paginated view")

            page_size = 100
            total_pages = (len(df) - 1) // page_size + 1
            page = st.number_input(
                f"{label} Page",
                min_value=1,
                max_value=total_pages,
                value=1,
                key=f"{key_prefix}_page"
            )

            start = (page - 1) * page_size
            end = start + page_size
            page_df = df.iloc[start:end]

            st.dataframe(page_df, use_container_width=True)

        # Show each category with pagination
        dup_df = pd.DataFrame(results['duplicate_allocations'])
        show_paginated_df(dup_df, "🔴 Duplicate Allocations", "dup")

        over_df = pd.DataFrame(results['over_allocations'])
        show_paginated_df(over_df, "🟠 Over-allocations", "over")

        combo_df = pd.DataFrame(results['unallowed_combinations'])
        show_paginated_df(combo_df, "🟡 Unallowed Combinations", "combo")

        rate_df = pd.DataFrame(results['rate_mismatches'])
        show_paginated_df(rate_df, "🟣 Rate Mismatches", "rate")

        visa_df = pd.DataFrame(results['visa_violations'])
        show_paginated_df(visa_df, "🔵 Visa Hours Violations", "visa")

        late_df = pd.DataFrame(results.get('late_starts', []))
        show_paginated_df(late_df, "🟢 Late Starts (Hourly shifts >1 min late)", "late")

        if results['total_issues'] == 0:
            st.success("✅ No issues found! All allocations are valid.")

    else:
        st.info("🔍 Upload a CSV file in the 'New Analysis' tab to get started.")


# Tab 3: Error Rows
with tab3:
    if st.session_state.analyzed and st.session_state.results:
        results = st.session_state.results
        error_rows = results.get('error_rows', [])
        
        if error_rows:
            st.header("❌ Error Rows")
            st.caption("These rows were excluded from analysis due to data issues")
            
            # Summary
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Error Rows", len(error_rows))
            with col2:
                st.metric("Total Rows Analyzed", results.get('total_valid_rows', 0))
            with col3:
                error_pct = (len(error_rows) / results.get('total_rows', 1)) * 100
                st.metric("Error Rate", f"{error_pct:.1f}%")
            
            st.markdown("---")
            
            # Display error rows
            error_df = pd.DataFrame(error_rows)
            
            # Color code by error type
            st.dataframe(
                error_df.style.apply(lambda x: ['background-color: #ffebee']*len(x), axis=1),
                use_container_width=True
            )
            
            # Export error rows
            col1, col2, col3 = st.columns([2, 1, 2])
            with col2:
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    error_df.to_excel(writer, index=False, sheet_name='Error Rows')
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📥 Download Error Rows",
                    data=excel_buffer,
                    file_name="error_rows.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        else:
            st.success("✅ No error rows! All data is valid.")
    else:
        st.info("🔍 Upload a CSV file in the 'New Analysis' tab to get started.")

# Tab 4: Rate Cards (informational - one row per employee)
with tab4:
    if st.session_state.analyzed and st.session_state.results:
        rate_cards = st.session_state.results.get('rate_cards', []) or []
        st.header("💷 Rate Cards by Employee")
        st.caption("One row per employee. Rows highlighted in amber are on "
                   "2+ distinct rate cards in this CSV - usually worth eyeballing.")

        if not rate_cards:
            st.info("No rate-card data available - the source CSV is missing "
                    "the 'Actual Pay Rate Sheet Description' column.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Employees", len(rate_cards))
            with col2:
                st.metric("On 2+ rate cards", sum(1 for r in rate_cards if r.get('is_multi_card')))
            with col3:
                st.metric("On 1 rate card",  sum(1 for r in rate_cards if r.get('distinct_rate_cards') == 1))
            st.markdown("---")

            # Flatten the rate_cards list-of-dicts (with nested breakdown) into
            # a plain DataFrame so st.dataframe can highlight rows.
            rows = []
            for rec in rate_cards:
                breakdown = "; ".join(f"{name} ({n})" for name, n in rec.get('rate_cards', []))
                rows.append({
                    'Employee': rec.get('employee_name'),
                    'Total Shifts': rec.get('total_shifts'),
                    'Distinct Rate Cards': rec.get('distinct_rate_cards'),
                    'Rate Card Breakdown': breakdown,
                    '_multi': bool(rec.get('is_multi_card')),
                })
            rc_df = pd.DataFrame(rows)

            def highlight_multi(row):
                if row.get('_multi'):
                    return ['background-color: #FFE699'] * len(row)
                return [''] * len(row)

            # Drop the marker column from the visible table but keep it for styling
            visible = rc_df.drop(columns=['_multi'])
            styled = visible.style.apply(
                lambda r: highlight_multi({'_multi': rc_df.loc[r.name, '_multi']}),
                axis=1,
            )
            st.dataframe(styled, use_container_width=True, height=600)

            # Quick filter for multi-card only
            with st.expander("🟡 Only show employees on 2+ rate cards", expanded=False):
                multi = rc_df[rc_df['_multi']].drop(columns=['_multi'])
                if multi.empty:
                    st.info("No employees are on more than one rate card.")
                else:
                    st.dataframe(multi, use_container_width=True)

            # Excel export
            col1, col2, col3 = st.columns([2, 1, 2])
            with col2:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                    visible.to_excel(writer, index=False, sheet_name='Rate Cards')
                buf.seek(0)
                st.download_button(
                    label="📥 Download as Excel",
                    data=buf,
                    file_name="rate_cards.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
    else:
        st.info("🔍 Upload a CSV file in the 'New Analysis' tab to get started.")


# Tab 5: History
with tab5:
    st.header("Analysis History")
    timestamps = get_unique_analysis_timestamps()
    
    if timestamps:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            selected_timestamp = st.selectbox(
                "Select an analysis to view:",
                timestamps,
                format_func=lambda x: f"Analysis from {x}"
            )
        
        with col2:
            st.write("")
            st.write("")
            if st.button("🗑️ Delete Selected", type="secondary"):
                deleted = delete_analysis(selected_timestamp)
                st.success(f"Deleted {deleted} records")
                st.session_state.analyzed = False
                st.session_state.results = None
                st.session_state.df = None
                st.rerun()
        
        if selected_timestamp:
            history_df = get_analysis_by_timestamp(selected_timestamp)
            
            # Process shift_type column to split into separate columns for duplicates
            def split_shift_columns(df):
                """Split shift_type column into separate columns for duplicate allocations"""
                df = df.copy()
                
                # Initialize new columns
                df['shift_1_type'] = ''
                df['shift_1_location'] = ''
                df['shift_1_times'] = ''
                df['shift_2_type'] = ''
                df['shift_2_location'] = ''
                df['shift_2_times'] = ''
                
                # Only process Duplicate Allocation rows
                duplicate_mask = df['issue_type'] == 'Duplicate Allocation'
                
                # Process shift_type column to split into separate columns for duplicates
            def split_shift_columns(df):
                """Split shift_type column into separate columns for duplicate allocations"""
                df = df.copy()
                
                # Initialize new columns
                df['shift_1_type'] = ''
                df['shift_1_location'] = ''
                df['shift_1_times'] = ''
                df['shift_2_type'] = ''
                df['shift_2_location'] = ''
                df['shift_2_times'] = ''
                df['overlap_minutes'] = None
                
                # Only process Duplicate Allocation rows
                duplicate_mask = df['issue_type'] == 'Duplicate Allocation'
                
                for idx in df[duplicate_mask].index:
                    shift_type_str = df.loc[idx, 'shift_type']
                    details_str = df.loc[idx, 'details']
                    
                    if ' | ' in str(shift_type_str):
                        # Split by pipe separator
                        shifts = shift_type_str.split(' | ')
                        
                        if len(shifts) >= 2:
                            # Process first shift
                            shift1 = shifts[0]
                            if ' at ' in shift1 and '(' in shift1:
                                type_loc = shift1.split(' at ')
                                df.loc[idx, 'shift_1_type'] = type_loc[0].strip()
                                
                                loc_times = type_loc[1].split('(')
                                df.loc[idx, 'shift_1_location'] = loc_times[0].strip()
                                df.loc[idx, 'shift_1_times'] = loc_times[1].replace(')', '').strip()
                            
                            # Process second shift
                            shift2 = shifts[1]
                            if ' at ' in shift2 and '(' in shift2:
                                type_loc = shift2.split(' at ')
                                df.loc[idx, 'shift_2_type'] = type_loc[0].strip()
                                
                                loc_times = type_loc[1].split('(')
                                df.loc[idx, 'shift_2_location'] = loc_times[0].strip()
                                df.loc[idx, 'shift_2_times'] = loc_times[1].replace(')', '').strip()
                    
                    # Extract overlap minutes from details
                    # Extract overlap minutes from details
                    if pd.notna(details_str) and 'min overlap' in str(details_str):
                        import re
                        match = re.search(r'\((-?\d+) min overlap\)', str(details_str))
                        if match:
                            df.loc[idx, 'overlap_minutes'] = int(match.group(1))
                
                return df
            
            # Apply the split
            history_df = split_shift_columns(history_df)
            
            st.subheader(f"Results from {selected_timestamp}")
            
            # Summary
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Total Issues", len(history_df))
            with col2:
                st.metric("Duplicates", len(history_df[history_df['issue_type'] == 'Duplicate Allocation']))
            with col3:
                st.metric("Over-allocations", len(history_df[history_df['issue_type'].str.contains('Over-allocation')]))
            with col4:
                st.metric("Invalid Combos", len(history_df[history_df['issue_type'] == 'Unallowed Combination']))
            with col5:
                st.metric("Rate Mismatches", len(history_df[history_df['issue_type'] == 'Rate Card Mismatch']))
            with col6:
                st.metric("Visa Violations", len(history_df[history_df['issue_type'] == 'Visa Hours Violation']))
            
            st.markdown("---")
            
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                issue_filter = st.multiselect(
                    "Filter by Issue Type:",
                    options=history_df['issue_type'].unique(),
                    default=history_df['issue_type'].unique()
                )
            with col2:
                emp_filter = st.multiselect(
                    "Filter by Employee:",
                    options=history_df['employee_name'].dropna().unique()
                )
            
            # Apply filters
            filtered_df = history_df[history_df['issue_type'].isin(issue_filter)]
            if emp_filter:
                filtered_df = filtered_df[filtered_df['employee_name'].isin(emp_filter)]
            
            # Display
            st.dataframe(filtered_df, use_container_width=True)
            
            # Export button
            col1, col2, col3 = st.columns([2, 1, 2])
            with col2:
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    filtered_df.to_excel(writer, index=False, sheet_name='Analysis')
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📥 Download as Excel",
                    data=excel_buffer,
                    file_name=f"analysis_{selected_timestamp.replace(':', '-')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
    
    else:
        st.info("🔭 No analysis history yet. Run your first analysis in the 'New Analysis' tab!")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "Workforce Allocation Analyzer | Built with Streamlit"
    "</div>",
    unsafe_allow_html=True
)