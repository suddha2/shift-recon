"""
Hit the configured App employee feed (APP_EMP_URL) and inspect what
comes back. Used to verify:
  - feed schema (columns present)
  - whether the EE.Status column exists and what values it carries
  - a specific employee's row (e.g. Gerald Dziva, who shows as
    Missing Visa Info even though he's in the visa table)
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import io

import pandas as pd
import requests

from config import (
    APP_EMP_URL, APP_EMP_AUTH, APP_EMP_TIMEOUT,
    APP_EMP_NAME_COL, APP_EMP_TYPE_COL,
)

# Hardcoded here (not in config) so this tool stays independent of the
# active-status filter being on/off in sync_visa_data.
APP_EMP_STATUS_COL = "EE.Status"

EMP_QUERY = sys.argv[1] if len(sys.argv) >= 2 else "Gerald Dziva"


def main():
    print(f"URL:       {APP_EMP_URL}")
    print(f"Auth hdr:  {APP_EMP_AUTH[:8]}...{APP_EMP_AUTH[-4:]}")
    print(f"Timeout:   {APP_EMP_TIMEOUT}s")
    print(f"Looking for: {EMP_QUERY!r}\n")

    resp = requests.get(
        APP_EMP_URL,
        headers={"Authorization": APP_EMP_AUTH},
        timeout=APP_EMP_TIMEOUT,
    )
    print(f"HTTP status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type','?')}")
    print(f"Bytes:        {len(resp.content)}\n")
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text), dtype=str)
    df.columns = df.columns.str.strip()
    print(f"Feed rows: {len(df)}")
    print(f"Feed cols ({len(df.columns)}):")
    for c in df.columns:
        print(f"   - {c!r}")
    print()

    # Status column distribution
    if APP_EMP_STATUS_COL in df.columns:
        print(f"Distinct values in {APP_EMP_STATUS_COL!r}:")
        for v, c in df[APP_EMP_STATUS_COL].fillna("(blank)").value_counts().items():
            print(f"  {c:>5}  {v!r}")
    else:
        print(f"WARNING: configured status column {APP_EMP_STATUS_COL!r} NOT in feed")
    print()

    # Find the employee (LIKE on FullName)
    name_col = APP_EMP_NAME_COL
    if name_col not in df.columns:
        print(f"WARNING: name column {name_col!r} NOT in feed")
        return
    mask = df[name_col].astype(str).str.contains(EMP_QUERY, case=False, na=False)
    sub = df[mask]
    print(f"=== Rows matching {EMP_QUERY!r} on column {name_col!r}: {len(sub)} ===")
    for _, r in sub.iterrows():
        print()
        for c in df.columns:
            v = r.get(c)
            if pd.isna(v) or str(v).strip() == "":
                continue
            print(f"   {c:<35}  {str(v)[:120]}")


if __name__ == "__main__":
    main()
