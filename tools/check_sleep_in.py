"""
Show how the analyzer's visa-hours filter treats Sleep In-style service
types. The filter is one line:
    df['Actual Service Type Description'].str.contains('shift', case=False, na=False)
so anything with 'shift' in the name counts toward worked hours, anything
without doesn't.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

from analyzer import parse_datetime, calculate_hours

CSV = "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"

# Variants we want to inspect (matched as substring, case-insensitive)
PATTERNS = [
    "Sleep In Shift",
    "Sleep In Support",
    "Paid Sleep In",
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


def main():
    df = read_csv(CSV)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["start_dt"] = df["Actual Start Date And Time"].apply(parse_datetime)
    df["end_dt"]   = df["Actual End Date And Time"].apply(parse_datetime)
    df["hours"]    = df.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)

    svc = df["Actual Service Type Description"].astype(str)
    df["_counts"] = svc.str.contains("shift", case=False, na=False)

    print(f"File: {CSV.split('/')[-1]}")
    print(f"Total rows in file: {len(df):>7}")
    print(f"Rows the analyzer counts ('shift' filter): {df['_counts'].sum():>7}\n")

    print(f"{'Service Type variant':<25} {'Rows':>7} {'Total Hrs':>12} {'Counts?':<10}  Distinct service-type strings matched")
    print("-" * 130)

    for pat in PATTERNS:
        mask = svc.str.contains(pat, case=False, na=False)
        sub = df[mask]
        counts = bool(sub["_counts"].iloc[0]) if not sub.empty else None
        # Distinct exact values that matched, so we see e.g. trailing
        # whitespace variants
        distinct = sorted(sub["Actual Service Type Description"]
                          .astype(str).str.strip().unique())
        distinct_disp = ", ".join(f"{v!r}" for v in distinct)
        flag = "YES" if (not sub.empty and sub["_counts"].iloc[0]) else "no"
        print(f"{pat:<25} {len(sub):>7} {sub['hours'].sum():>11.2f}h "
              f"{flag:<10}  {distinct_disp[:80]}")

    # Show the full breakdown of any service type with 'sleep' in the name
    print()
    print("=== All service types containing 'sleep' (any case) ===")
    sleep_mask = svc.str.contains("sleep", case=False, na=False)
    grouped = (df[sleep_mask]
               .assign(_svc=svc[sleep_mask].str.strip())
               .groupby("_svc")
               .agg(rows=("hours", "size"),
                    hours=("hours", "sum"),
                    counts=("_counts", "first"))
               .sort_values("hours", ascending=False))
    print(f"{'Service Type':<25} {'Rows':>7} {'Total Hrs':>12}  Counts toward visa hours?")
    print("-" * 80)
    for svc_name, row in grouped.iterrows():
        flag = "YES (contains 'shift')" if row["counts"] else "NO (no 'shift' in name)"
        print(f"{svc_name:<25} {int(row['rows']):>7} {row['hours']:>11.2f}h  {flag}")


if __name__ == "__main__":
    main()
