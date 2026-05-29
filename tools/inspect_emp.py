"""
Dump every row for one employee in one ISO week, with no service-type filter.
Shows start, end, hours, location, and service type so you can see what the
analyser keeps vs drops.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

from analyzer import parse_datetime, get_week_number, calculate_hours

CSV = "Supported Living Recon V5 (3).csv"

# Defaults — override via CLI: python inspect_emp.py "Name" YEAR WEEK
EMP = "Akabogu, Genevieve"
YEAR = 2026
WEEK = 18

if len(sys.argv) >= 4:
    EMP = sys.argv[1]
    YEAR = int(sys.argv[2])
    WEEK = int(sys.argv[3])


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
    df.columns = df.columns.str.replace("Desciption", "Description", regex=False)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row_num"] = range(2, len(df) + 2)

    df["start_dt"] = df["Actual Start Date And Time"].apply(parse_datetime)
    df["end_dt"] = df["Actual End Date And Time"].apply(parse_datetime)
    df["hours"] = df.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)
    df["week"] = df["start_dt"].apply(lambda x: get_week_number(x)[0])
    df["year"] = df["start_dt"].apply(lambda x: get_week_number(x)[1])

    mask = (
        (df["Actual Employee Name"] == EMP)
        & (df["year"] == YEAR)
        & (df["week"] == WEEK)
    )
    sub = df[mask].sort_values("start_dt")

    print(f"\n=== {EMP}  |  {YEAR}-W{WEEK:02d}  ({len(sub)} rows total) ===\n")
    print(f"{'Row':<6} {'Service Type':<26} {'Start':<17} {'End':<17} {'Hrs':>6}  {'Counts?':<8}  Location")
    print("-" * 130)

    total_all = 0.0
    total_shift = 0.0
    for _, r in sub.iterrows():
        svc = str(r.get("Actual Service Type Description", "") or "")
        loc = str(r.get("Service Location Name", "") or "")
        s = r["start_dt"].strftime("%Y-%m-%d %H:%M") if r["start_dt"] is not None else "-"
        e = r["end_dt"].strftime("%Y-%m-%d %H:%M") if r["end_dt"] is not None else "-"
        counts = "shift" in svc.lower()
        counts_str = "YES" if counts else "no"
        print(f"{int(r['_row_num']):<6} {svc[:26]:<26} {s:<17} {e:<17} {r['hours']:>5.2f}h  {counts_str:<8}  {loc[:60]}")
        total_all += r["hours"]
        if counts:
            total_shift += r["hours"]

    print("-" * 130)
    print(f"{'Total (all rows):':<70} {total_all:>5.2f}h")
    print(f"{'Total (Shift types only — what the visa check uses):':<70} {total_shift:>5.2f}h")


if __name__ == "__main__":
    main()
