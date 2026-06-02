"""
For a list of employees flagged as 'Missing Visa Info', hit the live
visa feed and report - per employee - whether they're in the feed, what
their EE.Status is, what their raw EE.EmployeeType says, and whether a
visa-type suffix is present (split on ' - ').

Employees are expected in 'Last, First' format (as they appear in the
analysis export).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import io
import re

import pandas as pd
import requests

from config import (
    APP_EMP_URL, APP_EMP_AUTH, APP_EMP_TIMEOUT,
    APP_EMP_NAME_COL, APP_EMP_TYPE_COL,
)
from analyzer import canonical_name

# Hardcoded here (not in config) so this tool stays independent of the
# active-status filter being on/off in sync_visa_data.
APP_EMP_STATUS_COL = "EE.Status"

# canonical_name handles both 'Last, First' and 'First Last' orderings.
EMPLOYEES = [
    "Evans Bvkerwa",
    "Natasha Nhengo",
    "Abdulrasaq Hassan",
    "Joshua Adeyemo",
    "Israel Adedeji",
]


def main():
    resp = requests.get(
        APP_EMP_URL,
        headers={"Authorization": APP_EMP_AUTH},
        timeout=APP_EMP_TIMEOUT,
    )
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), dtype=str)
    df.columns = df.columns.str.strip()
    print(f"Feed rows: {len(df)}\n")

    # Build a canonical-name -> list of rows index, matching the analyzer
    # logic (hyphens in feed names -> spaces, then canonical_name).
    df["_norm_name"] = df[APP_EMP_NAME_COL].astype(str).str.replace("-", " ", regex=False)
    df["_canon"] = df["_norm_name"].apply(canonical_name)

    fmt = "{name:<24} {status:<26} {type:<35} {has_visa:<10} {visa}"
    print(fmt.format(
        name="CSV Name", status="Feed Status (count)",
        type="EE.EmployeeType", has_visa="Has visa?", visa="Visa parsed"))
    print("-" * 130)

    for emp in EMPLOYEES:
        canon = canonical_name(emp)
        matches = df[df["_canon"] == canon]

        if matches.empty:
            print(fmt.format(
                name=emp, status="NOT IN FEED", type="-",
                has_visa="-", visa="-"))
            continue

        # Multiple rows possible (e.g. Gerald-Dziva had two). Summarize each.
        # Prefer Active row first for the headline; list all afterwards.
        active = matches[matches[APP_EMP_STATUS_COL].astype(str).str.strip().str.lower() == "active"]
        order = pd.concat([active, matches.drop(active.index)]) if not active.empty else matches

        for i, (_, r) in enumerate(order.iterrows()):
            status = str(r.get(APP_EMP_STATUS_COL, "") or "").strip()
            emp_type = str(r.get(APP_EMP_TYPE_COL, "") or "").strip()
            visa = emp_type.split(" - ", 1)[1].strip() if " - " in emp_type else ""
            has = "YES" if visa else "NO"
            label = emp if i == 0 else f"  ({len(order)-i} more)"
            tag = f"{status} (#{r.get(_id_col(df), '')})"
            print(fmt.format(
                name=label[:24], status=tag[:26], type=emp_type[:35],
                has_visa=has, visa=visa[:30]))


def _id_col(df):
    """Pick an ID column to disambiguate dup rows, falling back gracefully."""
    for c in ("EE.EmployeeID", "EE.External_ID"):
        if c in df.columns:
            return c
    return df.columns[0]


if __name__ == "__main__":
    main()
