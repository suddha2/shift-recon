"""
Side-by-side dump of every Recon row and every Payroll row for one
employee on one date. Used to verify a row flagged as 'missing from
Recon' isn't actually present but mismatched on the join key.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from datetime import date

import pandas as pd

from analyzer import parse_datetime, calculate_hours

RECON = "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"
PAYROLL = "/mnt/c/Users/SadharsunRamalingma/Downloads/Payroll Multiple Tabs Export (71) V2-Sudha.xlsx"

EMP_QUERY = sys.argv[1] if len(sys.argv) >= 2 else "Adewole, Ayomide"
TARGET = (
    date(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
    if len(sys.argv) >= 5 else date(2026, 5, 16)
)


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
    print(f"Employee:  {EMP_QUERY}")
    print(f"Date:      {TARGET} ({TARGET.strftime('%A')})\n")

    # ---- Recon ----
    rdf = read_csv(RECON)
    rdf.columns = rdf.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    rdf.columns = rdf.columns.str.replace("and Time", "And Time", regex=False)
    rdf["_row"]   = range(2, len(rdf) + 2)
    rdf["a_start"] = rdf["Actual Start Date And Time"].apply(parse_datetime)
    rdf["a_end"]   = rdf["Actual End Date And Time"].apply(parse_datetime)
    rdf["p_start"] = rdf["Planned Start Date And Time"].apply(parse_datetime)
    rdf["hours"]   = rdf.apply(lambda r: calculate_hours(r["a_start"], r["a_end"]), axis=1)
    rdf["a_date"]  = rdf["a_start"].apply(lambda x: x.date() if pd.notna(x) else None)
    rdf["p_date"]  = rdf["p_start"].apply(lambda x: x.date() if pd.notna(x) else None)

    rmask = (
        (rdf["Actual Employee Name"].astype(str).str.contains(EMP_QUERY, case=False, na=False)
         | rdf["Planned Employee Name"].astype(str).str.contains(EMP_QUERY, case=False, na=False))
        & ((rdf["a_date"] == TARGET) | (rdf["p_date"] == TARGET))
    )
    rsub = rdf[rmask].sort_values("a_start")

    print(f"=== RECON CSV - rows for '{EMP_QUERY}' on {TARGET} ({len(rsub)} rows) ===")
    print(f"  {'Row':<6} {'Actual Start':<17} -> {'End':<5} {'Hrs':>5}  {'Service Type':<24}  {'Location':<35}  {'Customer':<22}  Funding")
    print("  " + "-" * 170)
    for _, r in rsub.iterrows():
        s = r["a_start"].strftime("%Y-%m-%d %H:%M") if pd.notna(r["a_start"]) else "(no actual)"
        e = r["a_end"].strftime("%H:%M") if pd.notna(r["a_end"]) else "-"
        svc = str(r.get("Actual Service Type Description", "") or "")
        loc = str(r.get("Service Location Name", "") or "")
        cust = str(r.get("Customer Name", "") or "")
        # No funder column in Recon CSV, but Customer + Branch usually maps to it
        branch = str(r.get("Customer Branch", "") or "")
        print(f"  {int(r['_row']):<6} {s:<17} -> {e:<5} {r['hours']:>5.2f}  {svc[:24]:<24}  {loc[:35]:<35}  {cust[:22]:<22}  {branch[:30]}")

    # ---- Payroll ----
    pdf = pd.read_excel(PAYROLL, sheet_name="Shift", dtype=str)
    pdf.columns = pdf.columns.str.strip()
    pdf["_date"] = pdf["Visit Date"].apply(parse_datetime).apply(
        lambda x: x.date() if pd.notna(x) else None
    )
    pmask = (
        pdf["Staff Name"].astype(str).str.contains(EMP_QUERY, case=False, na=False)
        & (pdf["_date"] == TARGET)
    )
    psub = pdf[pmask].sort_values("Visit Start Time")

    print()
    print(f"=== PAYROLL xlsx (Shift sheet) - rows for '{EMP_QUERY}' on {TARGET} ({len(psub)} rows) ===")
    print(f"  {'Start':<7} {'End':<7} {'Hrs':>4} {'Service Type':<22}  {'Service User':<28}  {'Branch':<28}  Funding")
    print("  " + "-" * 150)
    for _, r in psub.iterrows():
        s = str(r.get("Visit Start Time", "") or "")[:5]
        e = str(r.get("Visit End Time", "") or "")[:5]
        h = str(r.get("Hours", "") or "")
        svc = str(r.get("Actual Service Type", "") or "")
        user = str(r.get("Services & Service Users Name", "") or "")
        branch = str(r.get("Services & Service Users Branch", "") or "")
        funder = str(r.get("Funding Authority Name", "") or "")
        print(f"  {s:<7} {e:<7} {h:>4}  {svc[:22]:<22}  {user[:28]:<28}  {branch[:28]:<28}  {funder}")


if __name__ == "__main__":
    main()
