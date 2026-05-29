"""
Exhaustive search for any shift on a given date that might match an employee.
Checks BOTH 'Actual Employee Name' and 'Planned Employee Name' columns, and
matches the date against EITHER the actual or the planned start.

Also separately lists every Floating Shift on that date for any employee,
in case the shift was logged under someone else.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
from datetime import date

from analyzer import parse_datetime, calculate_hours

CSV = "Supported Living Recon V5 (2).csv"
EMP_QUERY = "Akabogu"        # partial, case-insensitive
TARGET_DATE = date(2026, 5, 1)


def read_csv(path):
    for enc in (None, "cp1252", "latin-1"):
        try:
            kw = {"low_memory": False}
            if enc is not None:
                kw["encoding"] = enc
            return pd.read_csv(path, **kw)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Could not decode {path}")


def fmt_dt(dt):
    if dt is None or pd.isna(dt):
        return "-"
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def date_of(dt):
    if dt is None or pd.isna(dt):
        return None
    try:
        return dt.date()
    except Exception:
        return None


def print_rows(label, rows):
    print(f"\n=== {label}  ({len(rows)} rows) ===")
    if not rows:
        print("  (none)")
        return
    print(f"  {'Row':<6} {'Actual Name':<28} {'Planned Name':<28} {'Service Type':<24} "
          f"{'Actual Start':<17} {'Actual End':<17} {'Mins':>5}  Location")
    for r in rows:
        print(f"  {r['row']:<6} {str(r['actual_name'])[:28]:<28} {str(r['planned_name'])[:28]:<28} "
              f"{str(r['service'])[:24]:<24} {fmt_dt(r['a_start']):<17} {fmt_dt(r['a_end']):<17} "
              f"{r['mins']:>5}  {str(r['location'])[:50]}")


def main():
    df = read_csv(CSV)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("Desciption", "Description", regex=False)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row_num"] = range(2, len(df) + 2)

    df["a_start"] = df["Actual Start Date And Time"].apply(parse_datetime)
    df["a_end"]   = df["Actual End Date And Time"].apply(parse_datetime)
    df["p_start"] = df["Planned Start Date And Time"].apply(parse_datetime)
    df["p_end"]   = df["Planned End Date And Time"].apply(parse_datetime)
    df["hours"]   = df.apply(lambda r: calculate_hours(r["a_start"], r["a_end"]), axis=1)
    df["mins"]    = (df["hours"].fillna(0) * 60).round().astype(int)

    df["a_date"] = df["a_start"].apply(date_of)
    df["p_date"] = df["p_start"].apply(date_of)

    actual_name = df["Actual Employee Name"].astype(str)
    planned_name = df["Planned Employee Name"].astype(str)

    name_match = (
        actual_name.str.contains(EMP_QUERY, case=False, na=False)
        | planned_name.str.contains(EMP_QUERY, case=False, na=False)
    )
    date_match = (df["a_date"] == TARGET_DATE) | (df["p_date"] == TARGET_DATE)

    def to_row(r):
        return {
            "row": int(r["_row_num"]),
            "actual_name": r["Actual Employee Name"],
            "planned_name": r["Planned Employee Name"],
            "service": r.get("Actual Service Type Description", ""),
            "a_start": r["a_start"],
            "a_end": r["a_end"],
            "mins": r["mins"],
            "location": r.get("Service Location Name", ""),
        }

    # 1. Every row attributed to her (actual or planned) on the target date
    rows_emp_on_date = [to_row(r) for _, r in df[name_match & date_match].iterrows()]
    print_rows(f"{EMP_QUERY} - any row on {TARGET_DATE} (actual OR planned)", rows_emp_on_date)

    # 2. Every Floating Shift on that date, regardless of who it's attributed to
    svc = df["Actual Service Type Description"].astype(str)
    fs_mask = svc.str.contains("floating shift", case=False, na=False)
    rows_fs_on_date = [to_row(r) for _, r in df[fs_mask & date_match].iterrows()]
    print_rows(f"ALL Floating Shifts on {TARGET_DATE} (any employee)", rows_fs_on_date)

    # 3. Every ~30-min row on that date, any service type, any employee
    short_mask = (df["mins"] >= 20) & (df["mins"] <= 45)
    rows_short_on_date = [to_row(r) for _, r in df[short_mask & date_match].iterrows()]
    print_rows(f"ALL rows on {TARGET_DATE} with duration 20-45 mins (any employee, any service)",
               rows_short_on_date)


if __name__ == "__main__":
    main()
