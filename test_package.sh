#!/bin/bash
# Quick test script to verify package can be built

set -e

echo "=== Testing django-micboard package ==="
echo

echo "1. Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info/
echo "   ✓ Cleaned"

echo
echo "2. Installing build tools..."
pip install -q build twine
echo "   ✓ Installed"

echo
echo "3. Building package..."
python -m build
echo "   ✓ Built"

echo
echo "4. Checking package contents..."
echo "   Wheel contents:"
unzip -l dist/*.whl | grep -E "micboard/(models|views|admin|__init__|static|templates)" | head -10
echo "   ..."

echo
echo "5. Running twine check..."
twine check dist/*
echo "   ✓ Passed"

echo
echo "=== Package ready for publishing! ==="
echo
echo "Built files:"
ls -lh dist/
echo
echo "To publish to Test PyPI:"
echo "  twine upload --repository testpypi dist/*"
echo
echo "To publish to PyPI:"
echo "  twine upload dist/*"
