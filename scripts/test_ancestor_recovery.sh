#!/bin/bash
# Test script for ancestor directory recovery feature
#
# This script creates test commits that modify .sql migration files
# in stacks/prod/migrations/. These files don't match the *.yaml pattern
# but should be recovered via ancestor directory lookup when
# files_ancestor_lookup_depth >= 2.
#
# Usage:
#   ./scripts/test_ancestor_recovery.sh
#
# Prerequisites:
#   - Git repo with stacks/prod/migrations/ directory
#   - stacks/prod/config.yaml and stacks/prod/networking.yaml must exist

set -euo pipefail

BRANCH_PREFIX="test/ancestor"
TIMESTAMP=$(date +%s)

echo "========================================================"
echo "  Ancestor Recovery Test Scenarios"
echo "========================================================"

# --- Scenario 1: Only .sql file changed (pure ancestor recovery) ---
echo ""
echo "  Scenario 1: Only .sql migration changed"
echo "  Expected: .sql file recovered via ancestor lookup"
echo ""

BRANCH="${BRANCH_PREFIX}-sql-only-${TIMESTAMP}"
git checkout -b "$BRANCH"

# Modify only a .sql file
echo "-- Test migration $(date)" >> stacks/prod/migrations/001_create_users.sql

git add stacks/prod/migrations/001_create_users.sql
git commit -m "test: modify prod migration (ancestor recovery test)"
git push origin "$BRANCH"

echo "  Pushed branch: $BRANCH"
echo "  Monitor: https://github.com/terekete/le-change-test/actions"
echo ""

# Clean up
git checkout main
git branch -D "$BRANCH"

sleep 3

# --- Scenario 2: .yaml + .sql files changed (mixed) ---
echo "  Scenario 2: .yaml + .sql files changed (mixed)"
echo "  Expected: .yaml matched directly, .sql recovered via ancestor"
echo ""

BRANCH="${BRANCH_PREFIX}-mixed-${TIMESTAMP}"
git checkout -b "$BRANCH"

# Modify both a .yaml and a .sql file
echo "# Test change $(date)" >> stacks/prod/config.yaml
echo "-- Test migration $(date)" >> stacks/prod/migrations/002_create_orders.sql

git add stacks/prod/config.yaml stacks/prod/migrations/002_create_orders.sql
git commit -m "test: modify prod config + migration (mixed ancestor test)"
git push origin "$BRANCH"

echo "  Pushed branch: $BRANCH"
echo ""

# Clean up
git checkout main
git branch -D "$BRANCH"

sleep 3

# --- Scenario 3: Multi-stack with migrations ---
echo "  Scenario 3: Changes across dev and prod (with migrations)"
echo "  Expected: dev .yaml matched directly, prod .sql recovered"
echo ""

BRANCH="${BRANCH_PREFIX}-multi-${TIMESTAMP}"
git checkout -b "$BRANCH"

mkdir -p stacks/dev/scripts
echo "#!/bin/bash" > stacks/dev/scripts/deploy.sh
echo "# Test change $(date)" >> stacks/prod/config.yaml
echo "-- Test migration $(date)" >> stacks/prod/migrations/001_create_users.sql

git add stacks/dev/scripts/deploy.sh stacks/prod/config.yaml stacks/prod/migrations/001_create_users.sql
git commit -m "test: multi-stack with migrations (ancestor recovery test)"
git push origin "$BRANCH"

echo "  Pushed branch: $BRANCH"
echo ""

# Clean up
git checkout main
git branch -D "$BRANCH"

echo "========================================================"
echo "  All scenarios pushed. Check GitHub Actions for results."
echo "========================================================"
