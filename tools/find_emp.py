"""
List every row in the CSV for one employee, no filter on week or service type.
Use to track down rows that aren't appearing where you expect.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

from analyzer import parse_datetime, get_week_number, calculate_hours

CSV = "Supported Living Recon V5 (3).csv"
EMP = sys.argv[1] if len(sys.argv) >= 2 else "Akabogu, Genevieve"


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

    # Case-insensitive partial match so trailing whitespace etc. doesn't bite
    mask = df["Actual Employee Name"].astype(str).str.contains(EMP, case=False, na=False)
    sub = df[mask].copy()

    sub["start_dt"] = sub["Actual Start Date And Time"].apply(parse_datetime)
    sub["end_dt"]   = sub["Actual End Date And Time"].apply(parse_datetime)
    sub["hours"]    = sub.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)
    sub["week"]     = sub["start_dt"].apply(lambda x: get_week_number(x)[0])
    sub["year"]     = sub["start_dt"].apply(lambda x: get_week_number(x)[1])
    sub = sub.sort_values("start_dt")

    names = sorted(sub["Actual Employee Name"].dropna().unique())
    print(f"Search: '{EMP}'  -> matched {len(sub)} rows across name variants: {names}\n")

    print(f"{'Row':<6} {'YR-WK':<8} {'Service Type':<26} {'Start':<17} {'End':<17} {'Mins':>6}  {'Hrs':>6}  Location")
    print("-" * 140)
    for _, r in sub.iterrows():
        svc = str(r.get("Actual Service Type Description", "") or "")
        loc = str(r.get("Service Location Name", "") or "")
        s = r["start_dt"].strftime("%Y-%m-%d %H:%M") if r["start_dt"] is not None else "-"
        e = r["end_dt"].strftime("%Y-%m-%d %H:%M") if r["end_dt"] is not None else "-"
        yr = int(r["year"]) if pd.notna(r["year"]) else 0
        wk = int(r["week"]) if pd.notna(r["week"]) else 0
        wk_label = f"{yr}-W{wk:02d}" if wk else "n/a"
        mins = round(r["hours"] * 60)
        print(f"{int(r['_row_num']):<6} {wk_label:<8} {svc[:26]:<26} {s:<17} {e:<17} {mins:>6}  {r['hours']:>5.2f}h  {loc[:60]}")


if __name__ == "__main__":
    main()
