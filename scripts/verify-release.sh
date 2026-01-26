#!/usr/bin/env bash
# Django Micboard v25.01.15 - Release Verification Checklist
# Run this script to verify all release criteria are met

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# Helper functions
pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARN_COUNT++))
}

section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

section "Django Micboard v25.01.15 - Release Verification"

# ============================================================================
# 1. Project Structure
# ============================================================================

section "1. Project Structure"

[ -f "micboard/services.py" ] && pass "micboard/services.py exists" || fail "micboard/services.py missing"
[ -f "tests/conftest.py" ] && pass "tests/conftest.py exists" || fail "tests/conftest.py missing"
[ -f "tests/test_models.py" ] && pass "tests/test_models.py exists" || fail "tests/test_models.py missing"
[ -f "tests/test_services.py" ] && pass "tests/test_services.py exists" || fail "tests/test_services.py missing"
[ -f "tests/test_integrations.py" ] && pass "tests/test_integrations.py exists" || fail "tests/test_integrations.py missing"
[ -f "tests/test_e2e_workflows.py" ] && pass "tests/test_e2e_workflows.py exists" || fail "tests/test_e2e_workflows.py missing"

# ============================================================================
# 2. Configuration Files
# ============================================================================

section "2. Configuration Files"

[ -f ".pre-commit-config.yaml" ] && pass ".pre-commit-config.yaml exists" || fail ".pre-commit-config.yaml missing"
[ -f "pyproject.toml" ] && pass "pyproject.toml exists" || fail "pyproject.toml missing"
[ -f ".github/workflows/ci.yml" ] && pass ".github/workflows/ci.yml exists" || fail ".github/workflows/ci.yml missing"
[ -f ".github/workflows/release.yml" ] && pass ".github/workflows/release.yml exists" || fail ".github/workflows/release.yml missing"

# ============================================================================
# 3. Documentation
# ============================================================================

section "3. Documentation"

[ -f "DEVELOPMENT.md" ] && pass "DEVELOPMENT.md exists" || fail "DEVELOPMENT.md missing"
[ -f "ARCHITECTURE.md" ] && pass "ARCHITECTURE.md exists" || fail "ARCHITECTURE.md missing"
[ -f "RELEASE_PREPARATION.md" ] && pass "RELEASE_PREPARATION.md exists" || fail "RELEASE_PREPARATION.md missing"
[ -f "CHANGELOG.md" ] && pass "CHANGELOG.md exists" || fail "CHANGELOG.md missing"
[ -f "IMPLEMENTATION_SUMMARY.md" ] && pass "IMPLEMENTATION_SUMMARY.md exists" || fail "IMPLEMENTATION_SUMMARY.md missing"
[ -f "README_REFACTOR.md" ] && pass "README_REFACTOR.md exists" || fail "README_REFACTOR.md missing"

# Check documentation content
grep -q "CalVer" "CHANGELOG.md" && pass "CHANGELOG.md has CalVer format" || warn "CHANGELOG.md missing CalVer format"
grep -q "Services" "ARCHITECTURE.md" && pass "ARCHITECTURE.md documents services" || warn "ARCHITECTURE.md missing services docs"
grep -q "coverage" "DEVELOPMENT.md" && pass "DEVELOPMENT.md documents testing" || warn "DEVELOPMENT.md missing test docs"

# ============================================================================
# 4. Code Quality Configuration
# ============================================================================

section "4. Code Quality Configuration"

# Check pyproject.toml content
grep -q "pytest" "pyproject.toml" && pass "pyproject.toml has pytest config" || fail "pyproject.toml missing pytest config"
grep -q "coverage" "pyproject.toml" && pass "pyproject.toml has coverage config" || fail "pyproject.toml missing coverage config"
grep -q "black" "pyproject.toml" && pass "pyproject.toml has black config" || fail "pyproject.toml missing black config"
grep -q "version = \"25.01.15\"" "pyproject.toml" && pass "pyproject.toml has correct version" || fail "pyproject.toml wrong version"

# Check pre-commit config
grep -q "black" ".pre-commit-config.yaml" && pass "pre-commit has black" || fail "pre-commit missing black"
grep -q "isort" ".pre-commit-config.yaml" && pass "pre-commit has isort" || fail "pre-commit missing isort"
grep -q "flake8" ".pre-commit-config.yaml" && pass "pre-commit has flake8" || fail "pre-commit missing flake8"
grep -q "mypy" ".pre-commit-config.yaml" && pass "pre-commit has mypy" || fail "pre-commit missing mypy"
grep -q "bandit" ".pre-commit-config.yaml" && pass "pre-commit has bandit" || fail "pre-commit missing bandit"

# ============================================================================
# 5. GitHub Actions Workflows
# ============================================================================

section "5. GitHub Actions Workflows"

grep -q "pytest" ".github/workflows/ci.yml" && pass "ci.yml runs tests" || fail "ci.yml missing tests"
grep -q "coverage" ".github/workflows/ci.yml" && pass "ci.yml runs coverage" || fail "ci.yml missing coverage"
grep -q "black" ".github/workflows/ci.yml" && pass "ci.yml runs black" || fail "ci.yml missing black"
grep -q "matrix" ".github/workflows/ci.yml" && pass "ci.yml has matrix testing" || fail "ci.yml missing matrix testing"

grep -q "CalVer\|25.01.15" ".github/workflows/release.yml" && pass "release.yml mentions CalVer" || warn "release.yml missing CalVer reference"
grep -q "PyPI\|pypi" ".github/workflows/release.yml" && pass "release.yml publishes to PyPI" || fail "release.yml missing PyPI publishing"
grep -q "GitHub Release\|create-release" ".github/workflows/release.yml" && pass "release.yml creates GitHub release" || fail "release.yml missing GitHub release"

# ============================================================================
# 6. Test Files
# ============================================================================

section "6. Test Files"

# Count test functions
TEST_COUNT=$(grep -r "def test_" tests/ --include="*.py" | wc -l)
[ "$TEST_COUNT" -ge 100 ] && pass "Test count: $TEST_COUNT (target: 100+)" || warn "Test count: $TEST_COUNT (target: 100+)"

# Check test markers
grep -q "@pytest.mark.unit" tests/*.py && pass "Unit tests marked" || fail "Unit tests not marked"
grep -q "@pytest.mark.integration" tests/*.py && pass "Integration tests marked" || fail "Integration tests not marked"
grep -q "@pytest.mark.e2e" tests/*.py && pass "E2E tests marked" || fail "E2E tests not marked"

# Check for conftest
[ -f "tests/conftest.py" ] && {
    grep -q "def manufacturer" "tests/conftest.py" && pass "conftest has manufacturer fixture" || fail "conftest missing manufacturer fixture"
    grep -q "def receiver" "tests/conftest.py" && pass "conftest has receiver fixture" || fail "conftest missing receiver fixture"
    grep -q "Factory" "tests/conftest.py" && pass "conftest has factories" || fail "conftest missing factories"
}

# ============================================================================
# 7. Services Layer
# ============================================================================

section "7. Services Layer"

[ -f "micboard/services.py" ] && {
    grep -q "class DeviceService" "micboard/services.py" && pass "DeviceService exists" || fail "DeviceService missing"
    grep -q "class SynchronizationService" "micboard/services.py" && pass "SynchronizationService exists" || fail "SynchronizationService missing"
    grep -q "class LocationService" "micboard/services.py" && pass "LocationService exists" || fail "LocationService missing"
    grep -q "class MonitoringService" "micboard/services.py" && pass "MonitoringService exists" || fail "MonitoringService missing"
}

# ============================================================================
# 8. Version & Release Information
# ============================================================================

section "8. Version & Release Information"

grep -q "25.01.15" "pyproject.toml" && pass "pyproject.toml has version 25.01.15" || fail "pyproject.toml missing version"
grep -q "25.01.15\|v25.01.15" "CHANGELOG.md" && pass "CHANGELOG.md documents version" || fail "CHANGELOG.md missing version"
grep -q "CalVer\|YY.MM.DD" "CHANGELOG.md" && pass "CHANGELOG.md explains CalVer" || fail "CHANGELOG.md missing CalVer explanation"

# ============================================================================
# 9. Packaging & Distribution
# ============================================================================

section "9. Packaging & Distribution"

[ -f "setup.py" ] && pass "setup.py exists" || warn "setup.py missing (not required with pyproject.toml)"
[ -d "dist" ] && pass "dist/ directory exists" || warn "dist/ directory not yet created (create with: python -m build)"

# Check for build tools mention
grep -q "setuptools\|wheel" "pyproject.toml" && pass "pyproject.toml specifies build tools" || fail "pyproject.toml missing build tools"

# ============================================================================
# 10. Scripts
# ============================================================================

section "10. Scripts"

[ -f "scripts/release-quickstart.sh" ] && pass "scripts/release-quickstart.sh exists" || warn "scripts/release-quickstart.sh missing"
[ -f "scripts/pre-release-audit.sh" ] && pass "scripts/pre-release-audit.sh exists" || warn "scripts/pre-release-audit.sh missing"

# ============================================================================
# 11. Python Environment Check
# ============================================================================

section "11. Python Environment Check"

PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}' | cut -d'.' -f1,2)
[[ "$PYTHON_VERSION" =~ ^3\.(9|10|11|12)$ ]] && pass "Python version $PYTHON_VERSION supported" || warn "Python version $PYTHON_VERSION may not be supported"

# Check for test runner
which pytest > /dev/null 2>&1 && pass "pytest installed" || warn "pytest not installed (run: pip install pytest)"

# Check for build tools
python -m pip show build > /dev/null 2>&1 && pass "build module installed" || warn "build module not installed (run: pip install build)"

# ============================================================================
# Summary
# ============================================================================

section "Release Verification Summary"

TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))

echo ""
echo -e "${GREEN}Passed:${NC}  $PASS_COUNT/$TOTAL"
echo -e "${RED}Failed:${NC}  $FAIL_COUNT/$TOTAL"
echo -e "${YELLOW}Warnings:${NC} $WARN_COUNT/$TOTAL"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ All critical checks passed!${NC}"
    if [ $WARN_COUNT -gt 0 ]; then
        echo -e "${YELLOW}⚠ Fix warnings before release${NC}"
        exit 1
    else
        echo -e "${GREEN}✓ Ready for release v25.01.15!${NC}"
        exit 0
    fi
else
    echo -e "${RED}✗ Fix failures before release${NC}"
    exit 1
fi
