"""
Show a single row from a CSV/xlsx file, printed as one field per line.
Used to inspect one specific row the user referenced.
"""
import sys
import pandas as pd

PATH = sys.argv[1] if len(sys.argv) >= 2 else "Supported Living Recon V5 (2).csv"
TARGET_ROW = int(sys.argv[2]) if len(sys.argv) >= 3 else 7156


def read_any(path):
    if path.lower().endswith((".xlsx", ".xlsm")):
        # 'Data' is the populated sheet in the V5 (2) workbook (Sheet1 only
        # holds 1 row, likely a header copy). Fall back to first sheet if
        # 'Data' isn't present.
        try:
            return pd.read_excel(path, sheet_name="Data", dtype=str)
        except ValueError:
            return pd.read_excel(path, sheet_name=0, dtype=str)
    for enc in (None, "cp1252", "latin-1"):
        try:
            kw = {"low_memory": False}
            if enc is not None:
                kw["encoding"] = enc
            return pd.read_csv(path, **kw, dtype=str)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Could not decode {path}")


def main():
    df = read_any(PATH)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df.columns = df.columns.str.replace("Desciption", "Description", regex=False)
    df.columns = df.columns.str.replace("and Time", "And Time", regex=False)

    print(f"File: {PATH}")
    print(f"Total rows (excl. header): {len(df)}")

    # Try both interpretations:
    #   Excel row number = TARGET_ROW  (1-indexed, header = row 1, first data row = 2)
    #   Pandas index    = TARGET_ROW  (0-indexed)
    for label, idx in (
        (f"Excel row {TARGET_ROW} (i.e. pandas index {TARGET_ROW - 2})", TARGET_ROW - 2),
        (f"Pandas index {TARGET_ROW}", TARGET_ROW),
    ):
        if idx < 0 or idx >= len(df):
            continue
        r = df.iloc[idx]
        print("\n" + "=" * 90)
        print(f"=== {label} ===")
        print("=" * 90)
        for col in df.columns:
            v = r[col]
            if pd.isna(v) or str(v).strip() == "":
                continue
            # Truncate noisy columns
            print(f"  {col:<45}  {str(v)[:120]}")


if __name__ == "__main__":
    main()
