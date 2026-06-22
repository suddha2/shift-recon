"""
Diagnose why a CSV employee name isn't matching People HR.

Shows side by side:
  - the raw CSV name and its canonical form
  - what's in the people_hr_employees DB table for close name variants
  - the raw People HR API record (live fetch) for close name variants
  - any obvious extra tokens that would break the canonical match

Usage:
  python tools/diag_phr_match.py "Surname, First [other tokens]"
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import re
import sqlite3

from analyzer import canonical_name
from config import DATABASE_NAME, PEOPLE_HR_TABLE
from people_hr import fetch_all_employees

EMP = sys.argv[1] if len(sys.argv) >= 2 else "Mhlope, Bongiwe (Palesa)"


def tokens(s):
    return [t for t in re.split(r"[,\-\s]+", str(s or "")) if t]


def main():
    csv_canon = canonical_name(EMP)
    csv_tokens = tokens(EMP)
    print(f"CSV name:         {EMP!r}")
    print(f"CSV tokens:       {csv_tokens}")
    print(f"CSV canonical:    {csv_canon!r}\n")

    # 1. Look in local DB
    print("=== people_hr_employees table (local DB) ===")
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {PEOPLE_HR_TABLE}")
        total = cur.fetchone()[0]
        print(f"Total rows: {total}")

        # Search by any token from the query as a LIKE pattern
        clauses, params = [], []
        for t in csv_tokens:
            if len(t) >= 3:
                clauses.append("employee_name LIKE ?")
                params.append(f"%{t}%")
        if clauses:
            where = " OR ".join(clauses)
            cur.execute(
                f"SELECT employee_name, people_hr_id, updated_at "
                f"FROM {PEOPLE_HR_TABLE} WHERE {where} ORDER BY employee_name",
                params,
            )
            rows = cur.fetchall()
            print(f"Rows matching any token: {len(rows)}")
            for name, phr_id, ts in rows:
                c = canonical_name(name)
                match = "MATCH" if c == csv_canon else "no"
                print(f"  [{match:<5}]  {name:<40}  id={phr_id:<8}  canonical={c!r}")
        else:
            print("(no usable tokens for LIKE search)")
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"  DB not available: {e}")
    print()

    # 2. Hit People HR live and show close matches
    print("=== People HR API (live fetch) ===")
    try:
        recs = fetch_all_employees()
        print(f"Total records returned: {len(recs)}")
        candidates = []
        for r in recs:
            full = (r.get("full_name") or "").strip()
            phr_tokens = tokens(full)
            # Anything that shares at least one substantive token
            if any(t.lower() in (x.lower() for x in phr_tokens)
                   for t in csv_tokens if len(t) >= 3):
                candidates.append((full, r))
        print(f"Candidates sharing any token: {len(candidates)}")
        for full, r in candidates:
            c = canonical_name(full.replace("-", " "))
            match = "MATCH" if c == csv_canon else "no"
            print(f"  [{match:<5}]  {full:<40}  id={r.get('employee_id'):<8}  "
                  f"first={r.get('first_name')!r}  last={r.get('last_name')!r}")
    except Exception as e:
        print(f"  People HR fetch failed: {e}")
    print()

    # 3. Diagnose extra/missing tokens
    print("=== Token diff hint ===")
    print("If MATCH rows above are absent, the canonical forms differ.")
    print("Look at the canonical strings side by side to spot the extra")
    print("token (parenthetical alias, middle name, spelling drift).")
    print()
    print("Common fixes:")
    print("  - Parenthetical alias in CSV: strip '(...)' before canonical_name")
    print("  - Middle name on one side only: drop middle tokens, keep first+last")
    print("  - Spelling drift: source-data fix; nothing the analyser can do")


if __name__ == "__main__":
    main()
