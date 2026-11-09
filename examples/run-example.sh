#!/bin/sh
# Run the checker over each example HTML file and show the result.
# The bad example fails on purpose, so each run is allowed to fail.
cd "$(dirname "$0")/.."
for f in examples/good.html examples/bad.html examples/other.html; do
  echo "== $f =="
  python3 src/html_duplicate_id_checker.py "$f" || true
  echo
done
echo "== examples/ : the whole folder =="
python3 src/html_duplicate_id_checker.py examples/ || true
