"""
Cross-check the actual_hours reported in the violation export against the
original CSV. Uses the same parsing + week-numbering as analyzer.py:
- only rows whose service type contains "shift" (case-insensitive) count
- DD/MM/YYYY HH:MM:SS parsing via parse_datetime
- ISO week (Monday-Sunday)
"""
from collections import defaultdict
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

from analyzer import parse_datetime, get_week_number, calculate_hours

CSV = "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"

# (employee_name_in_export, ISO year, ISO week, reported_actual_hours)
EXPECTED = [
    ("Akabogu, Genevieve",        2026, 18, 16.3),
    ("Akabogu, Genevieve",        2026, 20, 25.6),
    ("Akande, Dare",              2026, 21, 21.6),
    ("Akindejoye, Ayodeji",       2026, 21, 34.4),
    ("Akwaboah, Abraham",         2026, 18, 30.9),
    ("Akwaboah, Abraham",         2026, 19, 10.1),
    ("Akwaboah, Abraham",         2026, 20, 30.3),
    ("IWUJI, IFEANYICHUKWU",      2026, 21, 15.1),
    ("Iwuji, Ogochukwu",          2026, 21, 29.6),
    ("Maphosa, Carol Tametsi",    2026, 19, 35.7),
    ("Maphosa, Carol Tametsi",    2026, 21, 12.1),
    ("Mataure, Zoe",              2026, 21, 34.4),
    ("Mhlope, Bongiwe (Palesa)",  2026, 18, 28.4),
    ("Munkombwe, Loveness",       2026, 18, 34.6),
    ("Nwanagu, Ijeoma (Thelma)",  2026, 18, 34.9),
    ("Ojodu, Adebisi",            2026, 18, 14.5),
    ("Ojodu, Adebisi",            2026, 20, 24.1),
    ("Sarpong, Kofi",             2026, 18, 20.2),
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
    df.columns = df.columns.str.replace("Desciption", "Description", regex=False)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row_num"] = range(2, len(df) + 2)

    # Apply the analyzer's "shift" filter
    df = df[df["Actual Service Type Description"].str.contains("shift", case=False, na=False)]
    df["start_dt"] = df["Actual Start Date And Time"].apply(parse_datetime)
    df["end_dt"] = df["Actual End Date And Time"].apply(parse_datetime)
    df["hours"] = df.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)
    df["week"] = df["start_dt"].apply(lambda x: get_week_number(x)[0])
    df["year"] = df["start_dt"].apply(lambda x: get_week_number(x)[1])

    print(f"{'Employee':<28} {'YR-WK':<8} {'Reported':>8} {'Computed':>9} {'Diff':>7} {'Rows':>6}  Status")
    print("-" * 95)
    for emp, yr, wk, reported in EXPECTED:
        mask = (
            (df["Actual Employee Name"] == emp)
            & (df["year"] == yr)
            & (df["week"] == wk)
        )
        sub = df[mask]
        computed = round(sub["hours"].sum(), 1)
        diff = round(computed - reported, 1)
        status = "OK" if abs(diff) < 0.1 else "MISMATCH"
        print(f"{emp:<28} {yr}-W{wk:02d}  {reported:>7.1f}h {computed:>8.1f}h {diff:>+6.1f}h {len(sub):>6}  {status}")

        # Show per-row breakdown for any mismatch
        if abs(diff) >= 0.1:
            for _, r in sub.sort_values("start_dt").iterrows():
                s = r["start_dt"].strftime("%Y-%m-%d %H:%M") if r["start_dt"] is not None else "-"
                e = r["end_dt"].strftime("%Y-%m-%d %H:%M") if r["end_dt"] is not None else "-"
                print(f"    row {int(r['_row_num']):<6} {str(r['Actual Service Type Description'])[:30]:<30} "
                      f"{s} -> {e}  {r['hours']:6.2f}h")


if __name__ == "__main__":
    main()
