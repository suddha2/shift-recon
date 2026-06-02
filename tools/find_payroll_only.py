"""
Find Payroll Shift rows that have no matching row in the Recon V5 CSV.

Match key: (normalized staff name, visit date, normalized service type,
normalized location/service-user name). Multiset semantics: if Payroll
has 2 rows for the same key but Recon only has 1, one Payroll row is
counted as 'missing'.

This avoids the start-time-drift problem we hit with minute-precision
matching (Payroll = planned time, Recon = actual electronic-monitoring
time, often 1-15 minutes apart on the same shift).

Outputs:
  - Per-funding-authority summary of Payroll-only counts
  - Per-service-type summary
  - First N Payroll-only rows for inspection
  - Optional Excel export with the full list

Usage:
  python tools/find_payroll_only.py [<out.xlsx>]
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import re
from collections import Counter

import pandas as pd

from analyzer import parse_datetime

RECON_CSV = "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"
PAYROLL   = "/mnt/c/Users/SadharsunRamalingma/Downloads/Payroll Multiple Tabs Export (71) V2-Sudha.xlsx"
OUT_XLSX  = sys.argv[1] if len(sys.argv) >= 2 else None


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


def _norm(s):
    """Normalize a string for use in a match key (lowercase, single spaces)."""
    if pd.isna(s):
        return ""
    return re.sub(r"\s+", " ", str(s).strip().lower())


def norm_name(n):
    return _norm(n)


def main():
    print(f"Recon:   {RECON_CSV}")
    print(f"Payroll: {PAYROLL}\n")

    # ---------- Build Recon keys (multiset) ----------
    rdf = read_csv(RECON_CSV)
    rdf.columns = rdf.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    rdf.columns = rdf.columns.str.replace("and Time", "And Time", regex=False)
    rdf["start_dt"] = rdf["Actual Start Date And Time"].apply(parse_datetime)
    rdf["_name"] = rdf["Actual Employee Name"].apply(norm_name)
    rdf["_date"] = rdf["start_dt"].apply(lambda x: x.date() if pd.notna(x) else None)
    rdf["_svc"]  = rdf["Actual Service Type Description"].apply(_norm)
    rdf["_loc"]  = rdf["Service Location Name"].apply(_norm)
    rdf = rdf[(rdf["_name"] != "") & (rdf["_svc"] != "")]
    rdf = rdf.dropna(subset=["_date"])

    recon_counter = Counter(zip(rdf["_name"], rdf["_date"], rdf["_svc"], rdf["_loc"]))
    print(f"Recon rows with parseable name+date+svc+loc: {len(rdf):>6}")
    print(f"Distinct Recon keys: {len(recon_counter):>6}\n")

    # ---------- Scan Payroll ----------
    pdf = pd.read_excel(PAYROLL, sheet_name="Shift", dtype=str)
    pdf.columns = pdf.columns.str.strip()
    pdf["_name"] = pdf["Staff Name"].apply(norm_name)
    pdf["_date"] = pdf["Visit Date"].apply(parse_datetime).apply(
        lambda x: x.date() if pd.notna(x) else None
    )
    pdf["_svc"]  = pdf["Actual Service Type"].apply(_norm)
    pdf["_loc"]  = pdf["Services & Service Users Name"].apply(_norm)
    pdf = pdf[(pdf["_name"] != "") & (pdf["_svc"] != "")]
    pdf = pdf.dropna(subset=["_date"])

    # Multiset match: each Payroll row "consumes" one Recon slot for its
    # key. Rows that find no free slot in Recon are flagged as missing.
    available = dict(recon_counter)
    in_recon = []
    for _, r in pdf.iterrows():
        k = (r["_name"], r["_date"], r["_svc"], r["_loc"])
        if available.get(k, 0) > 0:
            available[k] -= 1
            in_recon.append(True)
        else:
            in_recon.append(False)
    pdf["_in_recon"] = in_recon
    payroll_only = pdf[~pdf["_in_recon"]].copy()

    print(f"Payroll rows scanned: {len(pdf):>6}")
    print(f"Payroll rows present in Recon: {len(pdf) - len(payroll_only):>6}")
    print(f"Payroll rows MISSING from Recon: {len(payroll_only):>6}\n")

    # ---------- Summaries ----------
    print("Payroll-only rows by Funding Authority:")
    by_funder = (payroll_only["Funding Authority Name"].fillna("(blank)")
                 .value_counts())
    for f, c in by_funder.items():
        print(f"  {c:>5}  {f!r}")

    print("\nPayroll-only rows by Pay Type:")
    by_pt = payroll_only["Pay Type"].fillna("(blank)").value_counts()
    for p, c in by_pt.items():
        print(f"  {c:>5}  {p!r}")

    print("\nPayroll-only rows by Actual Service Type (top 15):")
    by_svc = payroll_only["Actual Service Type"].fillna("(blank)").value_counts()
    for s, c in by_svc.head(15).items():
        print(f"  {c:>5}  {s!r}")

    print("\nTop 20 staff with most Payroll-only rows:")
    by_staff = payroll_only["Staff Name"].fillna("(blank)").value_counts()
    for n, c in by_staff.head(20).items():
        print(f"  {c:>5}  {n!r}")

    print("\nSample of 12 Payroll-only rows:")
    cols = ["Staff Name", "Visit Date", "Visit Start Time", "Visit End Time",
            "Hours", "Pay Type", "Actual Service Type",
            "Services & Service Users Name", "Funding Authority Name"]
    print(payroll_only[cols].head(12).to_string(index=False))

    if OUT_XLSX:
        payroll_only[cols].to_excel(OUT_XLSX, index=False)
        print(f"\nWrote full list to {OUT_XLSX}")


if __name__ == "__main__":
    main()
