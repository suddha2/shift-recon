"""
Dump Recon vs Payroll rows for one employee in one ISO week, side by side.
Used to pinpoint exactly which rows Payroll has that Recon's CSV export
is silently dropping.

Usage:
  python tools/diff_emp_week.py "Surname, First" YEAR WEEK
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from datetime import date

import pandas as pd

from analyzer import parse_datetime, get_week_number, calculate_hours

RECON_CSV = "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"
PAYROLL   = "/mnt/c/Users/SadharsunRamalingma/Downloads/Payroll Multiple Tabs Export (71) V2-Sudha.xlsx"

EMP = sys.argv[1] if len(sys.argv) >= 2 else "Sarpong, Kofi"
YR  = int(sys.argv[2]) if len(sys.argv) >= 3 else 2026
WK  = int(sys.argv[3]) if len(sys.argv) >= 4 else 18


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
    week_start = date.fromisocalendar(YR, WK, 1)
    week_end   = date.fromisocalendar(YR, WK, 7)
    print(f"Employee:  {EMP}")
    print(f"Week:      {YR}-W{WK:02d}   ({week_start} -> {week_end})")

    # ---- Recon source CSV ----
    rdf = read_csv(RECON_CSV)
    rdf.columns = rdf.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    rdf.columns = rdf.columns.str.replace("Desciption", "Description", regex=False)
    rdf.columns = rdf.columns.str.replace("and Time", "And Time", regex=False)
    rdf["_row"] = range(2, len(rdf) + 2)
    rdf["start_dt"] = rdf["Actual Start Date And Time"].apply(parse_datetime)
    rdf["end_dt"]   = rdf["Actual End Date And Time"].apply(parse_datetime)
    rdf["hours"]    = rdf.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)
    rdf["_iso"]     = rdf["start_dt"].apply(lambda x: x.isocalendar() if pd.notna(x) else None)
    rdf["_year"]    = rdf["_iso"].apply(lambda i: i[0] if i else None)
    rdf["_week"]    = rdf["_iso"].apply(lambda i: i[1] if i else None)

    # Both: rows where this employee appears in Actual OR Planned
    name_mask = (
        rdf["Actual Employee Name"].astype(str).str.contains(EMP, case=False, na=False)
        | rdf["Planned Employee Name"].astype(str).str.contains(EMP, case=False, na=False)
    )
    rsub_all = rdf[name_mask & (rdf["_year"] == YR) & (rdf["_week"] == WK)].sort_values("start_dt")

    # Subset the analyzer actually counts (service type contains 'shift')
    rsub_shift = rsub_all[rsub_all["Actual Service Type Description"]
                          .astype(str).str.contains("shift", case=False, na=False)]

    print()
    print(f"=== RECON CSV ({RECON_CSV.split('/')[-1]}) ===")
    print(f"  All rows for this emp+week:     {len(rsub_all):>3}   total hrs: "
          f"{rsub_all['hours'].sum():.2f}h")
    print(f"  After analyzer 'shift' filter:  {len(rsub_shift):>3}   total hrs: "
          f"{rsub_shift['hours'].sum():.2f}h")
    print()
    print(f"  {'Row':<6} {'Date / Time':<25} {'Hrs':>5}  {'Service Type':<25}  {'Counts?':<8}  Location")
    print("  " + "-" * 130)
    for _, r in rsub_all.iterrows():
        svc = str(r.get("Actual Service Type Description", "") or "")
        loc = str(r.get("Service Location Name", "") or "")
        s = r["start_dt"].strftime("%a %d/%m %H:%M") if pd.notna(r["start_dt"]) else "-"
        e = r["end_dt"].strftime("%H:%M") if pd.notna(r["end_dt"]) else "-"
        counts = "shift" in svc.lower()
        print(f"  {int(r['_row']):<6} {s + ' - ' + e:<25} {r['hours']:>5.2f}  "
              f"{svc[:25]:<25}  {'YES' if counts else 'no':<8}  {loc[:55]}")

    # ---- Payroll xlsx (Shift sheet) ----
    pdf = pd.read_excel(PAYROLL, sheet_name="Shift", dtype=str)
    pdf.columns = pdf.columns.str.strip()
    # Filter to Midco Internal funding rows only (other funders mirror the
    # same shift per service user, which would double-count).
    pdf = pdf[pdf["Funding Authority Name"].astype(str).str.strip() == "Midco Internal"]
    pdf["_date"]  = pdf["Visit Date"].apply(parse_datetime)
    pdf["_date"]  = pdf["_date"].apply(lambda x: x.date() if pd.notna(x) else None)
    pdf["_hours"] = pd.to_numeric(pdf["Hours"], errors="coerce")
    pdf["_banded"] = pd.to_numeric(pdf["Banded Hours"], errors="coerce")
    pdf["_iso"]   = pdf["_date"].apply(lambda d: d.isocalendar() if d else None)
    pdf["_year"]  = pdf["_iso"].apply(lambda i: i[0] if i else None)
    pdf["_week"]  = pdf["_iso"].apply(lambda i: i[1] if i else None)

    psub = pdf[
        (pdf["Staff Name"].astype(str).str.strip() == EMP)
        & (pdf["_year"] == YR)
        & (pdf["_week"] == WK)
    ].sort_values(["_date", "Visit Start Time"])

    print()
    print(f"=== PAYROLL Shift sheet ===")
    print(f"  Rows for this emp+week:         {len(psub):>3}   total hrs: "
          f"{psub['_hours'].sum():.2f}h    banded: {psub['_banded'].sum():.2f}h")
    print()
    print(f"  {'Date':<12} {'Start - End':<14} {'Hrs':>5} {'Banded':>7}  {'Pay Type':<10}  {'Service Type':<20}  Service User")
    print("  " + "-" * 130)
    for _, r in psub.iterrows():
        d = r["_date"].strftime("%a %d/%m") if r["_date"] else "-"
        s = str(r.get("Visit Start Time", "") or "")[:5]
        e = str(r.get("Visit End Time", "") or "")[:5]
        svc = str(r.get("Actual Service Type", "") or "")
        user = str(r.get("Services & Service Users Name", "") or "")
        pt = str(r.get("Pay Type", "") or "")
        h = r["_hours"] if pd.notna(r["_hours"]) else 0.0
        b = r["_banded"] if pd.notna(r["_banded"]) else 0.0
        print(f"  {d:<12} {s + ' - ' + e:<14} {h:>5.2f} {b:>7.2f}  {pt[:10]:<10}  {svc[:20]:<20}  {user[:55]}")

    print()
    print(f"Recon counted:  {rsub_shift['hours'].sum():.2f}h "
          f"(from {len(rsub_shift)} 'shift' rows out of {len(rsub_all)} total emp rows)")
    print(f"Payroll total:  {psub['_hours'].sum():.2f}h "
          f"({len(psub)} rows; banded {psub['_banded'].sum():.2f}h)")


if __name__ == "__main__":
    main()
