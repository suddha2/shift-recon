#!/usr/bin/env bash
# package.sh
# Builds a deployment zip containing only the files needed to run the
# Workforce Allocation Analyzer on a server.
#
# Usage:  ./package.sh
# Output: shift-recon-deploy.zip  (in the project root)
#
# The SQLite database (workforce_analysis.db) is intentionally excluded -
# it is created automatically on first run.

set -euo pipefail

cd "$(dirname "$0")"

OUTPUT_ZIP="shift-recon-deploy.zip"
REQUIRED_FILES=(
    app.py
    analyzer.py
    config.py
    database.py
    people_hr.py
    config.yaml
    requirements.txt
    README.md
)

# Verify all required files exist
missing=()
for f in "${REQUIRED_FILES[@]}"; do
    [[ -f "$f" ]] || missing+=("$f")
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "ERROR: required files not found:" >&2
    printf '  - %s\n' "${missing[@]}" >&2
    exit 1
fi

rm -f "$OUTPUT_ZIP"

# Use the zip utility if available, otherwise fall back to Python's zipfile
if command -v zip >/dev/null 2>&1; then
    zip -q "$OUTPUT_ZIP" "${REQUIRED_FILES[@]}"
else
    python3 -m zipfile -c "$OUTPUT_ZIP" "${REQUIRED_FILES[@]}"
fi

for f in "${REQUIRED_FILES[@]}"; do
    echo "  added  $f"
done

size_kb=$(( $(stat -c %s "$OUTPUT_ZIP") / 1024 ))
echo
echo "Created $OUTPUT_ZIP (${size_kb} KB) with ${#REQUIRED_FILES[@]} files."
echo "Copy to the server, unzip, then:"
echo "  pip install -r requirements.txt"
echo "  streamlit run app.py"
