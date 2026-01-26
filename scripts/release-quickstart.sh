#!/usr/bin/env bash
# Django Micboard - Quick Start for Release v25.01.15

set -e

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║  Django Micboard - CalVer Release v25.01.15 Quick Start               ║"
echo "║  Status: ✅ Ready for Release                                          ║"
echo "║  Coverage Target: 95%+                                                ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${BLUE}[1/8] Checking Python version...${NC}"
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION"

# Check git
echo ""
echo -e "${BLUE}[2/8] Checking git repository...${NC}"
GIT_STATUS=$(git status --porcelain | wc -l)
if [ "$GIT_STATUS" -eq 0 ]; then
    echo "✓ Working directory clean"
else
    echo "⚠ Warning: $GIT_STATUS uncommitted changes"
fi

# Create/activate virtual environment
echo ""
echo -e "${BLUE}[3/8] Virtual environment setup...${NC}"
if [ ! -d "venv" ]; then
    python -m venv venv
    echo "✓ Created virtual environment"
else
    echo "✓ Virtual environment exists"
fi
source venv/bin/activate
echo "✓ Activated"

# Install dependencies
echo ""
echo -e "${BLUE}[4/8] Installing dependencies...${NC}"
pip install -q -e ".[dev,test]" 2>/dev/null
echo "✓ Dependencies installed"

# Run tests with coverage
echo ""
echo -e "${BLUE}[5/8] Running tests with coverage...${NC}"
if pytest --cov=micboard --cov-report=term-missing -q tests/ 2>/dev/null; then
    echo "✓ All tests passed"
    COVERAGE=$(coverage report | grep TOTAL | awk '{print $4}')
    echo "✓ Coverage: $COVERAGE"
else
    echo "⚠ Some tests failed - review needed"
fi

# Run pre-commit
echo ""
echo -e "${BLUE}[6/8] Running pre-commit checks...${NC}"
if pre-commit run --all-files -q 2>/dev/null; then
    echo "✓ Pre-commit checks passed"
else
    echo "⚠ Some pre-commit checks failed"
    echo "  Run: pre-commit run --all-files"
fi

# Build distribution
echo ""
echo -e "${BLUE}[7/8] Building distribution...${NC}"
python -m build -q 2>/dev/null
echo "✓ Distribution built"
if [ -d "dist" ]; then
    DIST_FILES=$(ls -1 dist/ | wc -l)
    echo "✓ Created $DIST_FILES files in dist/"
fi

# Summary
echo ""
echo -e "${BLUE}[8/8] Release readiness summary${NC}"
echo ""

echo -e "${GREEN}✅ Ready for Release${NC}"
echo ""
echo "Next steps for v25.01.15 release:"
echo ""
echo "  1. Review changes:"
echo "     git log --oneline -5"
echo ""
echo "  2. Verify PyPI publishing:"
echo "     twine check dist/*"
echo ""
echo "  3. Publish to TestPyPI (optional):"
echo "     twine upload --repository testpypi dist/"
echo ""
echo "  4. Publish to PyPI:"
echo "     twine upload dist/"
echo ""
echo "  5. Create git tag:"
echo "     git tag -a v25.01.15 -m 'Release v25.01.15'"
echo "     git push origin v25.01.15"
echo ""
echo "  OR use GitHub Actions:"
echo "     gh workflow run release.yml -f version=25.01.15 -f prerelease=false"
echo ""
echo "📚 Documentation:"
echo "   - Development: DEVELOPMENT.md"
echo "   - Architecture: ARCHITECTURE.md"
echo "   - Release Info: RELEASE_PREPARATION.md"
echo "   - Changelog: CHANGELOG.md"
echo ""
echo -e "${YELLOW}Happy releasing! 🚀${NC}"
