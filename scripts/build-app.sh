#!/usr/bin/env bash
# Build docman deployment ZIP for Loom Workshop app deployment.
#
# Output: dist/docman-{version}.zip
# Contents: manifest.yaml, configs/, src/docman/, scripts/
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    print(tomllib.load(f)['project']['version'])
")

OUTDIR="dist"
OUT="${OUTDIR}/docman-${VERSION}.zip"

mkdir -p "$OUTDIR"
rm -f "$OUT"

echo "Building docman app bundle v${VERSION}..."

zip -r "$OUT" \
    manifest.yaml \
    configs/ \
    src/docman/ \
    scripts/dev-start.sh \
    scripts/dev-start.ps1 \
    -x "*.pyc" "__pycache__/*"

echo "Built: $OUT ($(du -h "$OUT" | cut -f1))"
echo ""
echo "Deploy via Workshop UI: upload $OUT at http://localhost:8080/apps"
echo ""
echo "NOTE: This app includes a Python package (docman)."
echo "After deploying, install it: pip install -e ~/.loom/apps/docman/src/"
