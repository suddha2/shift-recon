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
    check_over_allocations
)

from database import (
    init_database, 
    save_analysis_results, 
    get_all_analyses,
    get_unique_analysis_timestamps,
    get_analysis_by_timestamp,
    delete_analysis,
    export_to_excel
)
from config import SHIFT_TYPE_LIMITS, EMPLOYEE_HOUR_LIMITS, ALLOWED_COMBINATIONS

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
    
    st.markdown("---")
    st.info("💡 Edit rules in `config.py`")

# Main content tabs
tab1, tab2, tab3, tab4 = st.tabs(["🔍 New Analysis", "📊 View Results", "❌ Error Rows", "🗂️ History"])

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
            # Read CSV
            df = pd.read_csv(uploaded_file)
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
                        progress = st.progress(0, text="Starting analysis...")
                        df = st.session_state.df.copy()
                        df['_row_num'] = range(2, len(df) + 2)
                        total_rows = len(df)
                        chunk_size = 1000

                        # Preallocate issue lists
                        unallowed = []
                        duplicates = []
                        over_allocs = []

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

                            duplicates.extend(chunk_duplicates)
                            over_allocs.extend(chunk_over_allocs)

                            # Update progress bar
                            progress.progress(end / total_rows, text=f"Processed {end} of {total_rows} rows")

                        # Finalize progress bar
                        progress.progress(1.0, text="✅ Analysis complete")

                        # Save results
                        results = {
                            'duplicate_allocations': duplicates,
                            'over_allocations': over_allocs,
                            'unallowed_combinations': unallowed,
                            'total_issues': len(duplicates) + len(over_allocs) + len(unallowed)
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
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Issues", results['total_issues'])
        with col2:
            st.metric("Duplicates", len(results['duplicate_allocations']))
        with col3:
            st.metric("Over-allocations", len(results['over_allocations']))
        with col4:
            st.metric("Invalid Combos", len(results['unallowed_combinations']))

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

# Tab 4: History
with tab4:
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
                st.stop()

        
        if selected_timestamp:
            history_df = get_analysis_by_timestamp(selected_timestamp)
            
            st.subheader(f"Results from {selected_timestamp}")
            
            # Summary
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Issues", len(history_df))
            with col2:
                st.metric("Duplicates", len(history_df[history_df['issue_type'] == 'Duplicate Allocation']))
            with col3:
                st.metric("Over-allocations", len(history_df[history_df['issue_type'].str.contains('Over-allocation')]))
            with col4:
                st.metric("Invalid Combos", len(history_df[history_df['issue_type'] == 'Unallowed Combination']))
            
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