#!/usr/bin/env bash
# Pre-release audit and refactor script

set -e

echo "=== Django Micboard Pre-Release Audit ==="
echo ""

# Check Python version
echo "✓ Python version check:"
python --version

# List project structure
echo ""
echo "✓ Project structure:"
find . -type f -name "*.py" | head -20

# Generate current test coverage
echo ""
echo "✓ Current test coverage:"
if command -v pytest &> /dev/null; then
    pytest --cov=micboard --cov-report=term-missing -q 2>/dev/null || true
fi

# Check code quality tools
echo ""
echo "✓ Code quality tools:"
command -v pre-commit &> /dev/null && echo "  - pre-commit: installed" || echo "  - pre-commit: NOT installed"
command -v pytest &> /dev/null && echo "  - pytest: installed" || echo "  - pytest: NOT installed"
command -v black &> /dev/null && echo "  - black: installed" || echo "  - black: NOT installed"

# List management commands
echo ""
echo "✓ Management commands:"
find . -path "*management/commands*.py" -type f | sort

# Check for Django signals
echo ""
echo "✓ Django signals usage:"
grep -r "from django.db.models.signals import\|@receiver" --include="*.py" . 2>/dev/null | wc -l || true

# Report on dependencies
echo ""
echo "✓ Core dependencies:"
if [ -f "setup.py" ] || [ -f "setup.cfg" ] || [ -f "pyproject.toml" ]; then
    echo "  - Found: setup.py / setup.cfg / pyproject.toml"
else
    echo "  - WARNING: No standard packaging file found"
fi

echo ""
echo "=== Audit Complete ==="
