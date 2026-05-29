"""
Check the redone CSV for the Akabogu Genevieve / 1 May / Golders Rise
Floating Shift. Looks for the row by employee + date + location.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from datetime import date

import pandas as pd

from analyzer import parse_datetime, calculate_hours

CSV = sys.argv[1] if len(sys.argv) >= 2 else \
    "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"


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
    df["_Row"] = range(2, len(df) + 2)

    df["_start"] = df["Actual Start Date And Time"].apply(parse_datetime)
    df["_end"]   = df["Actual End Date And Time"].apply(parse_datetime)
    df["_hours"] = df.apply(lambda r: calculate_hours(r["_start"], r["_end"]), axis=1)
    df["_date"]  = df["_start"].apply(
        lambda x: x.date() if (x is not None and not pd.isna(x)) else None
    )

    target_date = date(2026, 5, 1)
    a = df["Actual Employee Name"].astype(str)
    p = df["Planned Employee Name"].astype(str)
    loc = df["Service Location Name"].astype(str)
    svc = df["Actual Service Type Description"].astype(str)

    # 1. Exact target: Genevieve + 1 May + Golders Rise + Floating Shift
    exact = df[
        (a.str.contains("Akabogu, Genevieve", case=False, na=False)
         | p.str.contains("Akabogu, Genevieve", case=False, na=False))
        & (df["_date"] == target_date)
        & (loc.str.contains("Golders Rise", case=False, na=False))
        & (svc.str.contains("Floating Shift", case=False, na=False))
    ]
    print(f"1. EXACT target row (Genevieve + 1 May + Golders Rise + Floating Shift): "
          f"{len(exact)} row(s)")
    show(exact)

    # 2. Loosen: drop the Floating Shift filter
    print(f"\n2. Genevieve + 1 May + Golders Rise (any service type): ")
    relax_loc = df[
        (a.str.contains("Akabogu, Genevieve", case=False, na=False)
         | p.str.contains("Akabogu, Genevieve", case=False, na=False))
        & (df["_date"] == target_date)
        & (loc.str.contains("Golders Rise", case=False, na=False))
    ]
    print(f"   {len(relax_loc)} row(s)")
    show(relax_loc)

    # 3. Loosen further: any Genevieve on 1 May at any location
    print(f"\n3. Genevieve on 1 May (ANY location, ANY service): ")
    relax_emp = df[
        (a.str.contains("Akabogu, Genevieve", case=False, na=False)
         | p.str.contains("Akabogu, Genevieve", case=False, na=False))
        & (df["_date"] == target_date)
    ]
    print(f"   {len(relax_emp)} row(s)")
    show(relax_emp)

    # 4. Anything at all at Golders Rise on 1 May, any employee
    print(f"\n4. ANY employee at Golders Rise on 1 May: ")
    golders_1may = df[
        (loc.str.contains("Golders Rise", case=False, na=False))
        & (df["_date"] == target_date)
    ]
    print(f"   {len(golders_1may)} row(s)")
    show(golders_1may)


def show(rows):
    if rows.empty:
        print("   (none)")
        return
    for _, r in rows.iterrows():
        print(f"   row {int(r['_Row']):<6}  "
              f"{str(r.get('Actual Employee Name','-'))[:24]:<24}  "
              f"{str(r.get('Actual Service Type Description','-'))[:20]:<20}  "
              f"{(r['_start'].strftime('%Y-%m-%d %H:%M') if r['_start'] else '-'):<17}  "
              f"-> {(r['_end'].strftime('%H:%M') if r['_end'] else '-')}  "
              f"{r['_hours']:>5.2f}h  "
              f"{str(r.get('Service Location Name',''))[:48]}")


if __name__ == "__main__":
    main()
