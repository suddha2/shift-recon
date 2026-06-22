"""
Run an absolute-string-match test: no canonicalising, no token sorting.
For every distinct employee in the workforce CSV, look the name up in
the People HR DB as a literal string. Report:

  - how many CSV employees match with a strict equality lookup
  - how many would match if we just reverse the 'Last, First' order
    to 'First Last' (no other transforms)
  - the 15 employees we already know are problem cases and what each
    approach does for them
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import sqlite3

import pandas as pd

from config import DATABASE_NAME, PEOPLE_HR_TABLE

CSV = sys.argv[1] if len(sys.argv) >= 2 else \
    "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2).csv"

# The 15 employees flagged in the previous audit as 'No People HR ID'
KNOWN_PROBLEM_NAMES = [
    "Chagumachiyi, Brandon Tinashe",
    "Chibhema, Kudzai",
    "Diis, Yassin Ali",
    "Hassan, Abdulrasaq",
    "Kadiri, Mutsawashe",
    "Khumalo, Nqabezulu",
    "Maphosa, Carol Tametsi",
    "Maringapasi, Elynna",
    "Masikati, Natalie",
    "Mlotshwa, Daryl",
    "Mvubu, Nothando",
    "Ndlovu, Nhlanhla",
    "Nkomo, Clive",
    "Ramushu, Sarah-Jane Tsepho",
    "Sinamasa, Olivia Nelia",
    "Tshuma, Watida",
]


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


def reverse_comma(name):
    """'Chagumachiyi, Brandon Tinashe' -> 'Brandon Tinashe Chagumachiyi'.
    No sorting, no token rearrangement - just put the part after the comma
    in front of the part before, with single-space join."""
    if name is None or pd.isna(name):
        return ""
    s = str(name).strip()
    if "," not in s:
        return s
    last, first = s.split(",", 1)
    return f"{first.strip()} {last.strip()}"


def main():
    print(f"CSV: {CSV}")
    print(f"DB:  {DATABASE_NAME}\n")

    # Pull DB names into a set for O(1) lookup
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()
    cur.execute(f"SELECT employee_name, people_hr_id FROM {PEOPLE_HR_TABLE}")
    db_rows = cur.fetchall()
    conn.close()
    db_by_name = {n: pid for n, pid in db_rows}
    db_names = set(db_by_name.keys())
    print(f"DB has {len(db_names)} People HR rows\n")

    # Pull distinct workforce-CSV names
    df = read_csv(CSV)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    csv_names = sorted(set(
        str(n).strip() for n in df["Actual Employee Name"].dropna()
        if str(n).strip().lower() != "nan"
    ))
    print(f"CSV has {len(csv_names)} distinct employee names\n")

    # ============================================================
    # Test 1: ABSOLUTE strict equality (no transform)
    # ============================================================
    matched_strict = [n for n in csv_names if n in db_names]
    print(f"=== Test 1: strict equality (CSV name == DB name verbatim) ===")
    print(f"  Matches: {len(matched_strict)} of {len(csv_names)}\n")

    # ============================================================
    # Test 2: simple Last,First -> First Last reverse, then strict equality
    # ============================================================
    matched_reversed = [(n, reverse_comma(n)) for n in csv_names
                        if reverse_comma(n) in db_names]
    print(f"=== Test 2: reverse 'Last, First' to 'First Last', then strict equality ===")
    print(f"  Matches: {len(matched_reversed)} of {len(csv_names)}\n")

    # Anyone matched in test 2 but not test 1?
    new_in_2 = [n for n, rev in matched_reversed if n not in matched_strict]
    print(f"  Of those, gained by the reverse: {len(new_in_2)}")
    print(f"  Of those, missed by both tests: {len(csv_names) - len(matched_reversed)}\n")

    # ============================================================
    # Drill-down on the 15 problem names
    # ============================================================
    print(f"=== Per-employee: how each known-problem name behaves ===")
    print(f"{'CSV name':<32} {'Strict match?':<13} {'Reversed form':<35} {'Reversed match?':<15}")
    print("-" * 100)
    for n in KNOWN_PROBLEM_NAMES:
        strict_hit = n in db_names
        rev = reverse_comma(n)
        rev_hit = rev in db_names
        print(f"{n[:32]:<32} {'YES' if strict_hit else 'no':<13} {rev[:35]:<35} {'YES' if rev_hit else 'no':<15}")

    print()
    print(f"=== Conclusion ===")
    print(f"Strict equality matches:   {len(matched_strict):>4} of {len(csv_names)}")
    print(f"Reversed equality matches: {len(matched_reversed):>4} of {len(csv_names)}")
    print(f"Still unmatched after reverse: {len(csv_names) - len(matched_reversed)} - these have a TRUE difference in name parts on at least one side")


if __name__ == "__main__":
    main()
