"""
Cross-check the actual_hours reported in a violation export against the
source Recon CSV. Uses the same parsing + week-numbering as analyzer.py.

Usage:
  python tools/verify_hours.py <export.csv> <source.csv>

Defaults to the latest export + V5 (2) redone source in the user's
Downloads folder.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import re
import pandas as pd

from analyzer import parse_datetime, get_week_number, calculate_hours, is_visa_hour_eligible

EXPORT_DEFAULT = "/mnt/c/Users/SadharsunRamalingma/Downloads/2026-05-29T16-25_export.csv"
SOURCE_DEFAULT = "/mnt/c/Users/SadharsunRamalingma/Downloads/Supported Living Recon V5 (2)-redone.csv"

EXPORT = sys.argv[1] if len(sys.argv) >= 2 else EXPORT_DEFAULT
SOURCE = sys.argv[2] if len(sys.argv) >= 3 else SOURCE_DEFAULT


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


def parse_week_label(label):
    """'2026-W18' -> (2026, 18). Returns (None, None) on failure."""
    m = re.match(r"^(\d{4})-W(\d{1,2})$", str(label).strip())
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def main():
    print(f"Export: {EXPORT}")
    print(f"Source: {SOURCE}")

    exp = read_csv(EXPORT)
    exp.columns = exp.columns.str.strip()
    # Keep only Visa Hours Violation rows that have actual_hours + week
    vio = exp[exp["issue_type"] == "Visa Hours Violation"].copy()
    vio = vio.dropna(subset=["actual_hours", "week"])

    src = read_csv(SOURCE)
    src.columns = src.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    src.columns = src.columns.str.replace("Desciption", "Description", regex=False)
    src.columns = src.columns.str.replace("and Time", "And Time", regex=False)
    src["_row"] = range(2, len(src) + 2)

    # Apply analyzer's visa-hour eligibility filter (excludes Sleep In)
    src = src[src["Actual Service Type Description"].apply(is_visa_hour_eligible)]
    src["start_dt"] = src["Actual Start Date And Time"].apply(parse_datetime)
    src["end_dt"]   = src["Actual End Date And Time"].apply(parse_datetime)
    src["hours"]    = src.apply(lambda r: calculate_hours(r["start_dt"], r["end_dt"]), axis=1)
    src["week"]     = src["start_dt"].apply(lambda x: get_week_number(x)[0])
    src["year"]     = src["start_dt"].apply(lambda x: get_week_number(x)[1])

    print(f"\nExport rows to verify: {len(vio)}")
    print(f"Source rows (after Shift filter): {len(src)}\n")

    print(f"{'Employee':<30} {'YR-WK':<8} {'Type':<6} {'Reported':>9} {'Computed':>9} {'Diff':>7} {'Rows':>5}  Status")
    print("-" * 105)

    ok = 0
    mismatch = 0
    bad_week = 0

    for _, e in vio.iterrows():
        emp = str(e["employee_name"])
        yr, wk = parse_week_label(e["week"])
        try:
            reported = float(e["actual_hours"])
        except (TypeError, ValueError):
            continue
        if yr is None:
            bad_week += 1
            continue

        is_over = "exceeds maximum" in str(e.get("details", "")).lower()
        kind = "OVER" if is_over else "UNDER"

        mask = (
            (src["Actual Employee Name"] == emp)
            & (src["year"] == yr)
            & (src["week"] == wk)
        )
        sub = src[mask]
        computed = round(sub["hours"].sum(), 1)
        diff = round(computed - reported, 1)
        status = "OK" if abs(diff) < 0.2 else "MISMATCH"
        if status == "OK":
            ok += 1
        else:
            mismatch += 1

        print(f"{emp[:30]:<30} {yr}-W{wk:02d}  {kind:<6} {reported:>8.1f}h {computed:>8.1f}h {diff:>+6.1f}h {len(sub):>5}  {status}")

    print("-" * 105)
    print(f"OK: {ok}   MISMATCH: {mismatch}   Skipped (bad week): {bad_week}")


if __name__ == "__main__":
    main()
