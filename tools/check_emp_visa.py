"""
Diagnose why one employee is flagged as below-minimum visa hours.

Walks the whole pipeline for that employee:
  1. All CSV rows attributed to them
  2. Rows the analyzer's is_visa_hour_eligible filter would count
  3. Per-week counted totals with pass/fail vs limit
  4. Their visa status from the live feed
  5. PHR ID lookup + holiday/absence records for the period

Usage:
  python tools/check_emp_visa.py <csv> "Surname, Firstname"
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
    VISA_HOUR_RULES,
    DATABASE_NAME, PEOPLE_HR_TABLE,
)


CSV = sys.argv[1] if len(sys.argv) >= 2 else \
    "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (12).csv"
EMP_QUERY = sys.argv[2] if len(sys.argv) >= 3 else "Ncube, Keith"


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
    print(f"CSV:      {CSV}")
    print(f"Employee: {EMP_QUERY}\n")

    df = read_csv(CSV)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row"] = range(2, len(df) + 2)
    df["start_dt"] = df["Actual Start Date And Time"].apply(parse_datetime)
    df["end_dt"]   = df["Actual End Date And Time"].apply(parse_datetime)
    df["hours"]    = df.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)
    df["week"]     = df["start_dt"].apply(lambda x: get_week_number(x)[0])
    df["year"]     = df["start_dt"].apply(lambda x: get_week_number(x)[1])

    mask = (
        df["Actual Employee Name"].astype(str).str.contains(EMP_QUERY, case=False, na=False)
        | df["Planned Employee Name"].astype(str).str.contains(EMP_QUERY, case=False, na=False)
    )
    sub = df[mask].copy()
    print(f"CSV rows attributed (Actual or Planned) to {EMP_QUERY!r}: {len(sub)}")
    if sub.empty:
        return

    # Which are visa-hour eligible?
    sub["_counts"] = sub["Actual Service Type Description"].apply(is_visa_hour_eligible)
    counted = sub[sub["_counts"]]
    print(f"Rows counted by is_visa_hour_eligible: {len(counted)} / {len(sub)}\n")

    # Row dump
    print("=== ALL rows for this emp ===")
    print(f"  {'Row':<6} {'YR-WK':<9} {'Service Type':<26} {'Start':<17} {'End':<17} {'Hrs':>6}  {'Counts?':<8}  Location")
    print("  " + "-" * 130)
    for _, r in sub.sort_values("start_dt", na_position="last").iterrows():
        svc = str(r.get("Actual Service Type Description", "") or "")
        loc = str(r.get("Service Location Name", "") or "")
        s = r["start_dt"].strftime("%Y-%m-%d %H:%M") if r["start_dt"] is not None and not pd.isna(r["start_dt"]) else "-"
        e = r["end_dt"].strftime("%Y-%m-%d %H:%M") if r["end_dt"] is not None and not pd.isna(r["end_dt"]) else "-"
        yr = int(r["year"]) if pd.notna(r["year"]) else 0
        wk = int(r["week"]) if pd.notna(r["week"]) else 0
        label = f"{yr}-W{wk:02d}" if wk else "n/a"
        counts = "YES" if r["_counts"] else "no"
        print(f"  {int(r['_row']):<6} {label:<9} {svc[:26]:<26} {s:<17} {e:<17} {r['hours']:>5.2f}h  {counts:<8}  {loc[:55]}")

    # Weekly totals of counted hours
    print()
    print("=== Weekly totals (only rows counted by the visa check) ===")
    weekly = (counted.dropna(subset=["year", "week"])
              .groupby(["year", "week"])["hours"].sum().sort_index())
    for (yr, wk), hrs in weekly.items():
        ws = date.fromisocalendar(int(yr), int(wk), 1)
        we = date.fromisocalendar(int(yr), int(wk), 7)
        print(f"  {int(yr)}-W{int(wk):02d}  ({ws} -> {we})   {hrs:6.2f}h")

    # Visa status from live feed
    print()
    print("=== Visa status (live AccessACloud feed) ===")
    resp = requests.get(APP_EMP_URL, headers={"Authorization": APP_EMP_AUTH},
                        timeout=APP_EMP_TIMEOUT)
    feed = pd.read_csv(io.StringIO(resp.text), dtype=str)
    feed.columns = feed.columns.str.strip()
    emp_canon = canonical_name(EMP_QUERY)
    visa_status = None
    for _, row in feed.iterrows():
        name = str(row.get(APP_EMP_NAME_COL, "") or "").strip().replace("-", " ")
        if canonical_name(name) == emp_canon:
            emp_type = str(row.get(APP_EMP_TYPE_COL, "") or "").strip()
            visa_status = emp_type.split(" - ", 1)[1].strip() if " - " in emp_type else ""
            print(f"  Found in feed: name={name!r}  EmployeeType={emp_type!r}  visa_status={visa_status!r}")
            break
    else:
        print(f"  Not found in feed (canonical={emp_canon!r})")
        # Search loosely
        loose = feed[feed[APP_EMP_NAME_COL].astype(str).str.contains(EMP_QUERY.split(',')[0], case=False, na=False)]
        for _, r in loose.iterrows():
            print(f"    close match: {r.get(APP_EMP_NAME_COL)!r}  type={r.get(APP_EMP_TYPE_COL)!r}")

    # Rule that would apply
    if visa_status:
        rule = VISA_HOUR_RULES.get(visa_status)
        print(f"\n  VISA_HOUR_RULES[{visa_status!r}] = {rule!r}")
        if rule:
            print(f"  Weekly threshold: {rule.get('operator')} {rule.get('value')}h")
            print()
            print("  Verdict per week:")
            for (yr, wk), hrs in weekly.items():
                op, v = rule.get('operator', '<='), rule.get('value', 0)
                bad = (op == '>=' and hrs < v) or (op == '<=' and hrs > v)
                mark = " *** VIOLATION ***" if bad else " OK"
                print(f"    {int(yr)}-W{int(wk):02d}  {hrs:.2f}h {op} {v}h -> {mark}")
        else:
            print("  No rule defined for this visa status - would be silently skipped.")

    # People HR ID lookup
    print()
    print("=== People HR lookup ===")
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cur = conn.cursor()
        cur.execute(f"SELECT employee_name, people_hr_id, updated_at FROM {PEOPLE_HR_TABLE} "
                    f"WHERE employee_name LIKE ? OR employee_name LIKE ?",
                    (f"%{EMP_QUERY.split(',')[0]}%", f"%{EMP_QUERY.split(',')[-1].strip()}%"))
        rows = cur.fetchall()
        for n, pid, ts in rows:
            match = "MATCH" if canonical_name(n) == emp_canon else "no"
            print(f"  [{match:<5}]  {n!r:<40} id={pid}  updated={ts}")
        conn.close()
    except Exception as ex:
        print(f"  DB lookup failed: {ex}")


if __name__ == "__main__":
    main()
