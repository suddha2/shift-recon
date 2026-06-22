"""
Investigate Ndlovu, Rethabetsi's holidays - why they're not accounted
for in the visa-hour analysis.

Walks through the whole pipeline for this one employee:
  1. CSV: how much she worked per week (per the analyzer's eligible filter)
  2. PHR DB: her People HR ID
  3. PHR API: holiday + absence records for the period (live)
  4. Visa check: what the analyzer produces for her
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import io
import sqlite3
from datetime import date

import pandas as pd
import requests

from analyzer import (
    parse_datetime, get_week_number, calculate_hours,
    canonical_name, is_visa_hour_eligible,
)
from config import (
    APP_EMP_URL, APP_EMP_AUTH, APP_EMP_TIMEOUT,
    APP_EMP_NAME_COL, APP_EMP_TYPE_COL,
    DATABASE_NAME, PEOPLE_HR_TABLE,
)
from people_hr import fetch_holiday, fetch_absence

CSV = sys.argv[1] if len(sys.argv) >= 2 else \
    "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (7)/Supported Living Recon V5 (7).csv"
EMP_QUERY = "Ndlovu, Rethabetsi"


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


def main():
    print(f"CSV: {CSV}")
    print(f"Employee: {EMP_QUERY}\n")

    # === Step 1: CSV side - weekly hours
    df = read_csv(CSV)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row"] = range(2, len(df) + 2)
    df["start_dt"] = df["Actual Start Date And Time"].apply(parse_datetime)
    df["end_dt"]   = df["Actual End Date And Time"].apply(parse_datetime)
    df["hours"]    = df.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)
    df["week"]     = df["start_dt"].apply(lambda x: get_week_number(x)[0])
    df["year"]     = df["start_dt"].apply(lambda x: get_week_number(x)[1])

    mask = df["Actual Employee Name"].astype(str) == EMP_QUERY
    sub = df[mask].copy()
    print(f"=== CSV rows for {EMP_QUERY}: {len(sub)} ===")

    # Hours that the analyzer would COUNT
    sub["_counts"] = sub["Actual Service Type Description"].apply(is_visa_hour_eligible)
    counted = sub[sub["_counts"]]
    print(f"Eligible 'shift' rows the analyzer counts: {len(counted)}")
    weekly = (counted.dropna(subset=["year", "week"])
              .groupby(["year", "week"])["hours"].sum().sort_index())
    print(f"\nWeekly counted hours:")
    for (yr, wk), hrs in weekly.items():
        ws = date.fromisocalendar(int(yr), int(wk), 1)
        we = date.fromisocalendar(int(yr), int(wk), 7)
        flag = " *** BELOW 37.5 MIN ***" if hrs < 37.5 else ""
        print(f"  {int(yr)}-W{int(wk):02d}  ({ws} -> {we})   {hrs:6.2f}h{flag}")

    period_start = sub["start_dt"].min().date() if sub["start_dt"].notna().any() else None
    period_end   = sub["end_dt"].max().date()   if sub["end_dt"].notna().any()   else None
    print(f"\nCSV period for her: {period_start} -> {period_end}")

    # === Step 2: PHR DB - her ID
    print()
    print(f"=== People HR DB lookup ===")
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()
    cur.execute(f"SELECT employee_name, people_hr_id, updated_at FROM {PEOPLE_HR_TABLE} WHERE employee_name LIKE '%Retha%' OR employee_name LIKE '%Ndlovu%'")
    rows = cur.fetchall()
    print(f"  Rows matching Retha/Ndlovu: {len(rows)}")
    target_canon = canonical_name(EMP_QUERY)
    print(f"  CSV name canonical: {target_canon!r}")
    matched_id = None
    for name, pid, ts in rows:
        c = canonical_name(name)
        flag = " <- MATCH" if c == target_canon else ""
        print(f"    {name!r:<40}  id={pid:<8} canon={c!r}{flag}")
        if c == target_canon:
            matched_id = pid
    conn.close()

    if not matched_id:
        print("\n  *** No PHR ID match - her holidays cannot be fetched ***")
        return

    # === Step 3: PHR API - fetch live holiday + absence for the CSV period
    print()
    print(f"=== People HR API live fetch for {matched_id} ===")
    print(f"  Window: {period_start} -> {period_end}")

    try:
        hol = fetch_holiday(matched_id, period_start, period_end)
        print(f"  Holiday records (Approved only): {len(hol)}")
        for r in hol:
            print(f"    {r.get('StartDate')} -> {r.get('EndDate')}  "
                  f"days={r.get('DurationInDays')} "
                  f"min={r.get('DurationInMinutes')} "
                  f"thisPeriodDays={r.get('DurationInDaysThisPeriod')} "
                  f"thisPeriodMin={r.get('DurationInMinutesThisPeriod')} "
                  f"part={r.get('PartOfDay')!r}  status={r.get('Status')!r}")
    except Exception as e:
        print(f"  fetch_holiday failed: {e}")

    try:
        abs_ = fetch_absence(matched_id, period_start, period_end)
        print(f"  Absence records: {len(abs_)}")
        for r in abs_:
            print(f"    {r.get('StartDate')} -> {r.get('EndDate')}  "
                  f"days={r.get('DurationDays')} "
                  f"thisPeriod={r.get('DurationInDaysThisPeriod')} "
                  f"reason={r.get('Reason')!r}")
    except Exception as e:
        print(f"  fetch_absence failed: {e}")

    # === Step 4: What does the WHOLE analyzer say for her? Run summarize_leave_for_week per shortfall week
    from people_hr import summarize_leave_for_week
    if hol or abs_:
        print()
        print(f"=== summarize_leave_for_week per shortfall week (using cached records above) ===")
        for (yr, wk), hrs in weekly.items():
            if hrs >= 37.5:
                continue
            ws = date.fromisocalendar(int(yr), int(wk), 1)
            we = date.fromisocalendar(int(yr), int(wk), 7)
            status, total, details = summarize_leave_for_week(hol, abs_, ws, we)
            print(f"  {int(yr)}-W{int(wk):02d}  ({ws} -> {we})  worked={hrs:.2f}h  "
                  f"leave={status} {total}h")
            if details:
                print(f"        details: {details}")


if __name__ == "__main__":
    main()
