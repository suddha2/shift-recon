# app.py
# Main Streamlit application for Workforce Allocation Analyzer

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

from analyzer import analyze_workforce_data
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
        st.rerun()

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
                st.write(f"**{shift_type} ({rate_type}):** {operator} {value}/week")
            else:
                st.write(f"**{shift_type} ({rate_type}):** ≤ {limit}/week")
    
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
tab1, tab2, tab3 = st.tabs(["🔍 New Analysis", "📊 View Results", "🗂️ History"])

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
            st.session_state.df = df
            
            st.success(f"✅ File loaded successfully: {len(df)} rows")
            
            # Show preview
            with st.expander("📄 Data Preview", expanded=True):
                st.dataframe(df.head(10), use_container_width=True)
            
            # Analyze button
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(
                    "🔍 Run Analysis", 
                    type="primary", 
                    use_container_width=True,
                    disabled=st.session_state.is_processing
                ):
                    # Set processing state to True (disables button)
                    st.session_state.is_processing = True
                    
                    with st.spinner("Analyzing data..."):
                        # Run analysis
                        results = analyze_workforce_data(df)
                        st.session_state.results = results
                        st.session_state.analyzed = True
                        
                        # Save to database
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        saved_count = save_analysis_results(results, timestamp)
                        
                        # Reset processing state to False (re-enables button)
                        st.session_state.is_processing = False
                        
                        st.success(f"✅ Analysis complete! Found {results['total_issues']} issues. Saved {saved_count} records to database.")
                    
                    st.rerun()
        
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
        
        # Display issues by category
        if results['duplicate_allocations']:
            st.subheader("🔴 Duplicate Allocations")
            st.caption("Employees with overlapping shift times")
            dup_df = pd.DataFrame(results['duplicate_allocations'])
            st.dataframe(
                dup_df.style.apply(lambda x: ['background-color: #ffcccc']*len(x), axis=1),
                use_container_width=True
            )
        
        if results['over_allocations']:
            st.subheader("🟠 Over-allocations")
            over_df = pd.DataFrame(results['over_allocations'])
            st.dataframe(
                over_df.style.apply(lambda x: ['background-color: #ffe6cc']*len(x), axis=1),
                use_container_width=True
            )
        
        if results['unallowed_combinations']:
            st.subheader("🟡 Unallowed Combinations")
            combo_df = pd.DataFrame(results['unallowed_combinations'])
            st.dataframe(
                combo_df.style.apply(lambda x: ['background-color: #fff4cc']*len(x), axis=1),
                use_container_width=True
            )
        
        if results['total_issues'] == 0:
            st.success("✅ No issues found! All allocations are valid.")
    
    else:
        st.info("🔍 Upload a CSV file in the 'New Analysis' tab to get started.")

# Tab 3: History
with tab3:
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
                st.rerun()
        
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