# audit_visa.py
# Verification tool for the Visa Hours Violation check.
#
# Prints the per-row breakdown that feeds an employee's weekly hour totals,
# so a flagged weekly total can be reconciled row by row, and warns about
# overlapping shifts whose time is counted more than once.
#
# Usage:
#   python audit_visa.py <workforce_csv> "<employee name or part of it>"
# Example:
#   python audit_visa.py shifts.csv "Akwaboah, Abraham"

import sys
from collections import defaultdict

import pandas as pd

from analyzer import parse_datetime, get_week_number, calculate_hours, is_visa_hour_eligible


def read_csv(path):
    """Read the CSV with the same encoding fallback the app uses."""
    for enc in (None, "cp1252", "latin-1"):
        try:
            kwargs = {"low_memory": False}
            if enc is not None:
                kwargs["encoding"] = enc
            return pd.read_csv(path, **kwargs)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Could not decode {path}")


def main():
    if len(sys.argv) < 3:
        print('Usage: python audit_visa.py <workforce_csv> "<employee name>"')
        sys.exit(1)

    csv_path, emp_query = sys.argv[1], sys.argv[2]

    df = read_csv(csv_path)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("Desciption", "Description", regex=False)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)
    df["_row_num"] = range(2, len(df) + 2)

    name_col = "Actual Employee Name"
    mask = df[name_col].astype(str).str.contains(emp_query, case=False, na=False)
    emp_df = df[mask].copy()
    if emp_df.empty:
        print(f"No rows match employee '{emp_query}'")
        sys.exit(1)

    names = sorted(emp_df[name_col].dropna().unique())
    print(f"Matched {len(emp_df)} row(s) across {len(names)} name(s): {names}\n")

    # Build per-row records using the exact same parsing as the analyzer
    rows = []
    for _, r in emp_df.iterrows():
        start = parse_datetime(r.get("Actual Start Date And Time"))
        end = parse_datetime(r.get("Actual End Date And Time"))
        wk, yr = get_week_number(start)
        service = str(r.get("Actual Service Type Description", ""))
        rows.append({
            "row": r["_row_num"],
            "name": r[name_col],
            "service": service,
            "start": start,
            "end": end,
            "hours": calculate_hours(start, end),
            "week": (yr, wk),
            # Visa-hour eligibility: 'Shift' types EXCEPT Sleep In variants.
            # See analyzer.is_visa_hour_eligible for the rule.
            "counts": is_visa_hour_eligible(service),
        })

    groups = defaultdict(list)
    for x in rows:
        groups[(x["name"], x["week"])].append(x)

    for (name, (yr, wk)), items in sorted(groups.items(), key=lambda k: str(k[0])):
        label = f"{yr}-W{int(wk):02d}" if wk is not None else "NO VALID DATE (excluded from check)"
        print(f"=== {name}  |  {label} ===")

        total = 0.0
        for x in sorted(items, key=lambda i: (i["start"] is None, i["start"])):
            s = x["start"].strftime("%Y-%m-%d %H:%M") if x["start"] is not None else "-"
            e = x["end"].strftime("%Y-%m-%d %H:%M") if x["end"] is not None else "-"
            if x["start"] is None or x["end"] is None:
                note = "  (excluded: no valid start/end date)"
            elif not x["counts"]:
                note = "  (excluded: not a Shift type)"
            elif x["hours"] <= 0:
                note = "  <-- negative/zero duration"
            else:
                note = ""
            print(f"  row {x['row']:<6} {x['service'][:24]:<24} {s} -> {e}  {x['hours']:7.2f}h{note}")
            if x["counts"]:
                total += x["hours"]
        print(f"  {'WEEK TOTAL (Shift types only)':<57} {total:7.2f}h")

        # Overlap detection - time counted in more than one counting row
        timed = sorted((x for x in items if x["counts"] and x["start"] and x["end"]),
                       key=lambda i: i["start"])
        for i in range(len(timed)):
            for j in range(i + 1, len(timed)):
                a, b = timed[i], timed[j]
                overlap_min = (min(a["end"], b["end"]) - max(a["start"], b["start"])).total_seconds() / 60
                if overlap_min > 15:
                    print(f"  ! rows {a['row']} & {b['row']} overlap by "
                          f"{int(overlap_min)} min - that time is counted in both")
        print()


if __name__ == "__main__":
    main()
