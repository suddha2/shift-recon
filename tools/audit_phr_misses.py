"""
Run the visa-hour analysis against the supplied CSV and inspect every
"No People HR ID for ..." case. For each missing employee, report:

  - the CSV name + canonical
  - whether the local DB has a row whose canonical matches exactly
  - whether the local DB has any candidate row sharing tokens
  - the People HR ID it WOULD have matched (if any)

This proves whether each missing case is a code bug, a data gap, or
something else - without further guessing.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import io
import re
import sqlite3
from collections import Counter

import pandas as pd
import requests

from analyzer import check_visa_hour_violations, canonical_name
from config import (
    APP_EMP_URL, APP_EMP_AUTH, APP_EMP_TIMEOUT,
    APP_EMP_NAME_COL, APP_EMP_TYPE_COL,
    DATABASE_NAME, PEOPLE_HR_TABLE,
)
from database import get_people_hr_id_lookup

CSV = sys.argv[1] if len(sys.argv) >= 2 else \
    "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2).csv"


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


def tokens(s):
    if s is None or pd.isna(s):
        return set()
    return {t.lower() for t in re.split(r"[,\-\s]+", str(s)) if t}


def main():
    print(f"CSV:    {CSV}")
    print(f"DB:     {DATABASE_NAME}\n")

    df = read_csv(CSV)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("Desciption", "Description", regex=False)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row_num"] = range(2, len(df) + 2)

    print(f"CSV rows: {len(df)}")

    print("Fetching visa lookup from live AccessACloud feed...")
    visa_lookup = fetch_visa_lookup()
    print(f"  visa entries: {len(visa_lookup)}")

    print("Loading People HR lookup from local DB...")
    phr_lookup = get_people_hr_id_lookup()
    print(f"  PHR lookup entries: {len(phr_lookup)}\n")

    # Compute violations + leave check. Need a date window for the People HR
    # call - derive from the CSV (same logic as app.py).
    from analyzer import parse_datetime
    starts = df["Actual Start Date And Time"].apply(parse_datetime).dropna()
    ends   = df["Actual End Date And Time"].apply(parse_datetime).dropna()
    period_start = starts.min().date() if not starts.empty else None
    period_end   = ends.max().date()   if not ends.empty   else None
    print(f"Period: {period_start} -> {period_end}\n")

    print("Running visa-hour check (with People HR lookup)...")
    violations = check_visa_hour_violations(
        df, visa_lookup,
        people_hr_lookup=phr_lookup,
        period_start=period_start,
        period_end=period_end,
    )

    # Filter to PHR-related misses
    misses = []
    for v in violations:
        details = str(v.get("leave_details", "") or "")
        if details.startswith("No People HR ID"):
            misses.append(v)

    print(f"Total violations: {len(violations)}")
    print(f"Of which 'No People HR ID for ...': {len(misses)}\n")

    # For each missed employee, classify the cause
    # Load DB rows for token-overlap candidate search
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()
    cur.execute(f"SELECT employee_name, people_hr_id FROM {PEOPLE_HR_TABLE}")
    db_rows = cur.fetchall()
    conn.close()
    db_canon = {canonical_name(n): (n, pid) for n, pid in db_rows}
    print(f"Local DB has {len(db_rows)} rows; {len(db_canon)} distinct canonical keys")
    print()

    # Group by unique CSV emp (one violation can show multiple weeks)
    seen = set()
    classified = {"would_match_now": [], "token_subset": [],
                  "name_shared_but_no_match": [], "truly_missing": []}

    for v in misses:
        emp = str(v.get("employee_name", "")).strip()
        if emp in seen:
            continue
        seen.add(emp)
        emp_canon = canonical_name(emp)
        emp_tokens = tokens(emp)

        # 1. Direct canonical match (would resolve right now)
        if emp_canon in db_canon:
            classified["would_match_now"].append((emp, emp_canon, db_canon[emp_canon]))
            continue

        # 2. Token subset (Brandon Chagumachiyi vs Brandon Tinashe Chagumachiyi)
        candidates = []
        for k, (dbname, pid) in db_canon.items():
            db_tokens = set(k.split())
            if not db_tokens:
                continue
            if db_tokens.issubset(emp_tokens) or emp_tokens.issubset(db_tokens):
                if len(db_tokens & emp_tokens) >= 2:
                    candidates.append((dbname, pid, k))
        if candidates:
            classified["token_subset"].append((emp, emp_canon, candidates))
            continue

        # 3. Shares at least one token with some DB row but isn't a subset
        weak = []
        for k, (dbname, pid) in db_canon.items():
            db_tokens = set(k.split())
            if db_tokens & emp_tokens:
                weak.append((dbname, pid, k))
        if weak:
            classified["name_shared_but_no_match"].append((emp, emp_canon, weak[:5]))
            continue

        # 4. Truly not in PHR at all
        classified["truly_missing"].append((emp, emp_canon))

    # ============== Reports ==============
    print(f"=== Unique employees with 'No People HR ID': {len(seen)} ===\n")

    if classified["would_match_now"]:
        print(f"### A. Would resolve with current code (exact canonical match)  --  {len(classified['would_match_now'])}")
        print("    -> If you see these, the analyzer's people_hr_lookup wasn't")
        print("       loaded - check sync_people_hr_employees() ran successfully.")
        for emp, c, (dbname, pid) in classified["would_match_now"]:
            print(f"    CSV: {emp!r:<42} canon={c!r:<35}")
            print(f"       DB: {dbname!r}  id={pid}")
        print()

    if classified["token_subset"]:
        print(f"### B. Subset / superset of a DB row  --  {len(classified['token_subset'])}")
        print("    -> One side has extra tokens (middle name, alias). Tweak")
        print("       canonical_name to handle this, OR fix the source-data side.")
        for emp, c, cands in classified["token_subset"]:
            print(f"    CSV: {emp!r:<42} canon={c!r}")
            for dbname, pid, dbc in cands[:3]:
                print(f"       DB candidate: {dbname!r}  id={pid}  canon={dbc!r}")
        print()

    if classified["name_shared_but_no_match"]:
        print(f"### C. Shares some tokens but no subset relation  --  {len(classified['name_shared_but_no_match'])}")
        print("    -> Spelling drift / different person same surname / etc.")
        print("       Likely source-data fix needed.")
        for emp, c, weak in classified["name_shared_but_no_match"]:
            print(f"    CSV: {emp!r:<42} canon={c!r}")
            for dbname, pid, dbc in weak[:3]:
                print(f"       DB shares tokens: {dbname!r}  id={pid}")
        print()

    if classified["truly_missing"]:
        print(f"### D. Not in local PHR DB at all  --  {len(classified['truly_missing'])}")
        print("    -> Either People HR doesn't have them (data-onboarding gap),")
        print("       or sync hasn't run since they were added.")
        for emp, c in classified["truly_missing"]:
            print(f"    CSV: {emp!r:<42} canon={c!r}")
        print()


if __name__ == "__main__":
    main()
