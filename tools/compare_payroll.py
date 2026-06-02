"""
Side-by-side compare: Recon CSV violation export vs Payroll xlsx (Shift sheet).

For each (employee, week) flagged in the export, sum hours from the
Payroll Shift sheet over the same Mon-Sun calendar week, and compare
against the export's actual_hours.

Usage:
  python tools/compare_payroll.py <export.csv> <payroll.xlsx>

Defaults point to the latest export + Payroll xlsx in the user's
Downloads folder.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import re
from datetime import date

import pandas as pd

from analyzer import parse_datetime, get_week_number

EXPORT_DEFAULT  = "/mnt/c/Users/SadharsunRamalingma/Downloads/2026-05-29T16-25_export.csv"
PAYROLL_DEFAULT = "/mnt/c/Users/SadharsunRamalingma/Downloads/Payroll Multiple Tabs Export (71) V2-Sudha.xlsx"

EXPORT  = sys.argv[1] if len(sys.argv) >= 2 else EXPORT_DEFAULT
PAYROLL = sys.argv[2] if len(sys.argv) >= 3 else PAYROLL_DEFAULT


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


def parse_week_label(label):
    m = re.match(r"^(\d{4})-W(\d{1,2})$", str(label).strip())
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def main():
    print(f"Export:  {EXPORT}")
    print(f"Payroll: {PAYROLL}\n")

    exp = read_csv(EXPORT)
    exp.columns = exp.columns.str.strip()
    vio = exp[exp["issue_type"] == "Visa Hours Violation"].copy()
    vio = vio.dropna(subset=["actual_hours", "week"])

    # Read Payroll Shift sheet
    shift = pd.read_excel(PAYROLL, sheet_name="Shift", dtype=str)
    shift.columns = shift.columns.str.strip()
    # Filter to Midco Internal funding only - other funders mirror the same
    # shift under each service user, which the analyzer correctly dedupes
    # via its 'shift' filter on the Recon side.
    n_total = len(shift)
    shift = shift[shift["Funding Authority Name"].astype(str).str.strip() == "Midco Internal"]
    # Parse Visit Date + Hours
    shift["_date"]  = shift["Visit Date"].apply(parse_datetime)
    shift["_date"]  = shift["_date"].apply(lambda x: x.date() if pd.notna(x) else None)
    shift["_hours"] = pd.to_numeric(shift["Hours"], errors="coerce")
    # Add ISO week
    shift["_iso"] = shift["_date"].apply(lambda d: d.isocalendar() if d else None)
    shift["_year"] = shift["_iso"].apply(lambda i: i[0] if i else None)
    shift["_week"] = shift["_iso"].apply(lambda i: i[1] if i else None)

    n_parsed = shift["_date"].notna().sum()
    print(f"Payroll Shift sheet: {n_total} rows total, "
          f"{len(shift)} after 'Midco Internal' filter, "
          f"{n_parsed} with parseable Visit Date\n")

    print(f"{'Employee':<30} {'YR-WK':<8} {'Type':<6} {'Export':>9} {'Payroll':>9} {'Diff':>7} {'Rows':>5}  Status")
    print("-" * 105)

    ok = 0
    mismatch = 0
    missing = 0

    for _, e in vio.iterrows():
        emp = str(e["employee_name"]).strip()
        yr, wk = parse_week_label(e["week"])
        if yr is None:
            continue
        try:
            reported = float(e["actual_hours"])
        except (TypeError, ValueError):
            continue

        is_over = "exceeds maximum" in str(e.get("details", "")).lower()
        kind = "OVER" if is_over else "UNDER"

        mask = (
            (shift["Staff Name"].astype(str).str.strip() == emp)
            & (shift["_year"] == yr)
            & (shift["_week"] == wk)
        )
        sub = shift[mask]
        total = round(float(sub["_hours"].sum()), 1)
        diff  = round(total - reported, 1)

        if len(sub) == 0:
            status = "NO_PAYROLL_ROWS"
            missing += 1
        elif abs(diff) < 0.2:
            status = "OK"
            ok += 1
        else:
            status = "MISMATCH"
            mismatch += 1

        print(f"{emp[:30]:<30} {yr}-W{wk:02d}  {kind:<6} {reported:>8.1f}h {total:>8.1f}h {diff:>+6.1f}h {len(sub):>5}  {status}")

    print("-" * 105)
    print(f"OK: {ok}   MISMATCH: {mismatch}   No payroll rows: {missing}")


if __name__ == "__main__":
    main()
