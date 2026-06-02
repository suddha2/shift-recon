"""
Run the visa-hour check against the V5 (2)-redone CSV using the current
analyzer (allowlist-based eligibility + Excel-serial date fix). Pulls
visa statuses from the live AccessACloud feed. No DB writes; results
printed straight to stdout.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import io
from collections import defaultdict

import pandas as pd
import requests

from analyzer import check_visa_hour_violations, canonical_name
from config import (
    APP_EMP_URL, APP_EMP_AUTH, APP_EMP_TIMEOUT,
    APP_EMP_NAME_COL, APP_EMP_TYPE_COL,
    VISA_HOUR_RULES,
)

CSV = "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"


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


def fetch_visa_lookup():
    resp = requests.get(APP_EMP_URL, headers={"Authorization": APP_EMP_AUTH},
                        timeout=APP_EMP_TIMEOUT)
    resp.raise_for_status()
    feed = pd.read_csv(io.StringIO(resp.text), dtype=str)
    feed.columns = feed.columns.str.strip()
    lookup = {}
    for _, row in feed.iterrows():
        name = str(row.get(APP_EMP_NAME_COL, "") or "").strip().replace("-", " ")
        emp_type = str(row.get(APP_EMP_TYPE_COL, "") or "").strip()
        visa_status = emp_type.split(" - ", 1)[1].strip() if " - " in emp_type else ""
        if name and name.lower() != "nan":
            lookup[canonical_name(name)] = visa_status
    return lookup


def main():
    print(f"CSV:    {CSV}")
    df = read_csv(CSV)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("Desciption", "Description", regex=False)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row_num"] = range(2, len(df) + 2)
    print(f"Rows loaded: {len(df)}")

    print("Fetching visa lookup from live feed...")
    visa_lookup = fetch_visa_lookup()
    print(f"Visa lookup entries: {len(visa_lookup)}\n")

    violations = check_visa_hour_violations(df, visa_lookup)

    # Sort: Missing Visa Info first, then Over violations (most over), then Under
    def sort_key(v):
        if v["issue_type"] == "Missing Visa Info":
            return (0, v["employee_name"])
        details = str(v.get("details", "")).lower()
        is_over = "exceeds maximum" in details
        actual = float(v.get("actual_hours") or 0)
        limit  = float(v.get("limit_hours") or 0)
        delta = actual - limit if is_over else limit - actual
        return (1 if is_over else 2, -delta, v["employee_name"], v.get("week", ""))

    violations.sort(key=sort_key)

    missing = [v for v in violations if v["issue_type"] == "Missing Visa Info"]
    over    = [v for v in violations if v["issue_type"] != "Missing Visa Info"
               and "exceeds maximum" in str(v.get("details", "")).lower()]
    under   = [v for v in violations if v["issue_type"] != "Missing Visa Info"
               and "below minimum" in str(v.get("details", "")).lower()]
    other   = [v for v in violations if v not in missing and v not in over and v not in under]

    print(f"=== Summary ===")
    print(f"  Missing Visa Info:   {len(missing)}")
    print(f"  Over-max violations: {len(over)}")
    print(f"  Below-min violations:{len(under)}")
    print(f"  Other rule mismatch: {len(other)}")
    print()

    def show_table(title, rows):
        if not rows:
            return
        print(f"=== {title} ({len(rows)}) ===")
        print(f"  {'Employee':<32} {'Week':<8} {'Visa':<22} {'Hours':>7} {'Limit':>6} {'Gap':>7}")
        print("  " + "-" * 90)
        for v in rows:
            emp   = str(v.get("employee_name", ""))[:32]
            wk    = str(v.get("week", ""))
            visa  = str(v.get("shift_type", ""))[:22]
            try:
                hrs = float(v.get("actual_hours") or 0)
                lim = float(v.get("limit_hours") or 0)
            except (TypeError, ValueError):
                hrs, lim = 0.0, 0.0
            if "exceeds" in str(v.get("details", "")).lower():
                gap = hrs - lim
            else:
                gap = lim - hrs
            print(f"  {emp:<32} {wk:<8} {visa:<22} {hrs:>6.1f}h {lim:>5.1f}h {gap:>+6.1f}h")
        print()

    show_table("OVER-MAX (exceeds visa weekly cap)", over)
    show_table("BELOW-MINIMUM (under visa weekly floor)", under)
    show_table("Other rule mismatch", other)

    if missing:
        print(f"=== Missing Visa Info ({len(missing)}) ===")
        for v in missing:
            print(f"  {v['employee_name']}")
        print()


if __name__ == "__main__":
    main()
