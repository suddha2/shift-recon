# Workforce Allocation Analyzer

A Streamlit-based tool for analyzing workforce allocation data to detect duplicates, over-allocations, and invalid service type combinations.

## Features

- ✅ **Overlapping Allocation Detection**: Identifies when the same employee has overlapping shifts on the same day
- ✅ **Over-allocation Checks**: Validates shift type limits and weekly hour limits per employee
- ✅ **Combination Validation**: Uses whitelist approach to flag invalid Service Type + Requirement Type pairs
- ✅ **Visual Highlighting**: Color-coded issue display for easy identification
- ✅ **Database Storage**: Automatically saves all analysis results to SQLite
- ✅ **Historical Analysis**: View and compare past analyses
- ✅ **Excel Export**: Download results for further analysis

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup Steps

1. **Extract all files** to a directory on your computer

2. **Open terminal/command prompt** in that directory

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

1. **Start the application**:
   ```bash
   streamlit run app.py
   ```

2. **Access the web interface**: 
   - The browser should open automatically
   - If not, navigate to `http://localhost:8501`

## Configuration

Edit the rules in `config.py` to customize:

### 1. Shift Type Limits
```python
SHIFT_TYPE_LIMITS = {
    "Emergency Response": 2,  # Max 2 per week
    "Night Patrol": 3,        # Max 3 per week
    # Add your shift types here
}
```

### 2. Employee Hour Limits
```python
EMPLOYEE_HOUR_LIMITS = {
    "John Smith": 48,      # 48 hours max
    "Bob Wilson": None,    # No limit (opted out)
    # Add your employees here
}

DEFAULT_HOUR_LIMIT = 48  # Default for unlisted employees
```

### 3. Allowed Combinations (Whitelist)
```python
ALLOWED_COMBINATIONS = [
    ("Emergency Response", "Qualified Staff"),
    ("Night Patrol", "Security Certified"),
    # Add all valid combinations here
]
```

## CSV File Requirements

Your CSV must include these columns (exact names):
- Planned Employee Name
- Actual Employee Name
- Service Location Name
- Actual Service Type Description
- Actual Service Requirement Type Description
- Planned Start Date And Time
- Actual Start Date And Time
- Planned End Date And Time
- Actual End Date And Time
- Service Duty Created Date & Time
- Actual Pay Rate Type
- Reconciled
- Actual Start Date Weekday
- Actual Pay Rate Sheet Description

**Date/Time Format**: YYYY-MM-DD HH:MM:SS (e.g., 2024-10-15 09:00:00)

## Usage Guide

### Running New Analysis

1. Click **"New Analysis"** tab
2. Upload your CSV file
3. Review the data preview
4. Click **"Run Analysis"** button
5. View results automatically

### Viewing Results

Results are displayed in three categories:
- 🔴 **Overlapping Allocations** (red background)
- 🟠 **Over-allocations** (orange background)
- 🟡 **Unallowed Combinations** (yellow background)

Each issue shows:
- Employee name
- Date/Week of issue
- Shift type
- Detailed description
- CSV row numbers for reference

### Viewing History

1. Click **"History"** tab
2. Select an analysis from the dropdown
3. Filter by issue type or employee
4. Download results as Excel

## Database

Analysis results are stored in `workforce_analysis.db` (SQLite database).

**Location**: Same directory as the application files

**Backup**: Simply copy the `.db` file to back up all analysis history

## Troubleshooting

### Application won't start
- **Issue**: `ModuleNotFoundError`
- **Solution**: Run `pip install -r requirements.txt` again

### CSV upload fails
- **Issue**: "Error reading file"
- **Solution**: Ensure your CSV has all required columns with exact names (case-sensitive)

### No issues found when you expect some
- **Issue**: Rules not matching your data
- **Solution**: Check `config.py` - ensure shift type names match exactly with your CSV data

### Database errors
- **Issue**: "Database is locked"
- **Solution**: Close any other programs accessing `workforce_analysis.db`

## File Structure

```
workforce-analyzer/
├── app.py              # Main Streamlit application
├── config.py           # Configuration rules (EDIT THIS)
├── analyzer.py         # Analysis logic
├── database.py         # Database operations
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── workforce_analysis.db  # SQLite database (auto-created)
```

## Support

For issues or questions:
1. Check that all column names in your CSV match exactly
2. Verify date/time formats are correct
3. Review `config.py` to ensure rules match your data
4. Check the terminal/console for detailed error messages

## Technical Notes

- **Week Definition**: Monday (week start) to Sunday (week end)
- **Time Overlap Logic**: Checks if start1 < end2 AND start2 < end1
- **Database**: SQLite (no external DB server required)
- **Performance**: Optimized for ~25,000 rows, processes in 2-5 seconds

## License

Internal use tool - modify as needed for your organization.

---

**Version**: 1.0  
**Last Updated**: October 2025 "
